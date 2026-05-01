from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import Event
from typing import Any, Callable

from loguru import logger

from scraper.backfill import backfill_manual_review_for_month
from scraper.browser import BrowserSession
from scraper.company import process_company
from scraper.listing import collect_candidates_from_json, collect_candidates_from_listing
from scraper.manifest import ManifestWriter
from scraper.progress import load_progress, save_progress
from scraper.retrying import retry_with_backoff
from scraper.types import CompanyProcessResult


@dataclass
class JobCallbacks:
    on_start: Callable[[int], None] | None = None
    on_company_done: Callable[[int, int, str, str], None] | None = None
    on_finished: Callable[["JobSummary"], None] | None = None
    on_log: Callable[[str], None] | None = None


@dataclass
class JobSummary:
    month: str
    period_label: str
    total: int
    processed: int
    done: int
    partial: int
    failed: int
    manual_review: int
    csv_path: Path
    xlsx_path: Path
    stopped: bool = False


def resolve_month_range(month: str) -> tuple[date, date]:
    dt = datetime.strptime(month, "%Y-%m")
    last_day = calendar.monthrange(dt.year, dt.month)[1]
    return date(dt.year, dt.month, 1), date(dt.year, dt.month, last_day)


def _build_failed_result(filing_date: str, company_name: str, error: str) -> CompanyProcessResult:
    return CompanyProcessResult(
        filing_date=filing_date,
        company_name=company_name,
        consultant="__待复核__",
        business="其他",
        cn_io_url="",
        en_io_url="",
        cn_filename="",
        en_filename="",
        status="failed",
        notes=error[:300],
    )


def _notify(callback: Callable[..., None] | None, *args) -> None:
    if callback is None:
        return
    try:
        callback(*args)
    except Exception:  # noqa: BLE001
        return


def _effective_limit(config: dict[str, Any]) -> int:
    limit_override = config.get("limit_override")
    if limit_override is not None:
        return max(1, int(limit_override))

    if bool(config.get("month_mode_full", True)):
        return int(config.get("month_mode_limit", 100000))

    return max(1, int(config.get("limit", 20)))


def run_month_job(
    month: str,
    config: dict[str, Any],
    callbacks: JobCallbacks | None = None,
    *,
    stop_event: Event | None = None,
) -> JobSummary:
    callbacks = callbacks or JobCallbacks()

    start_d, end_d = resolve_month_range(month)
    period_label = month

    project_root = Path(str(config.get("project_root", Path.cwd()))).resolve()
    output_dir = (project_root / str(config.get("output_dir", "./output"))).resolve()
    tmp_dir = (project_root / str(config.get("tmp_dir", "./tmp"))).resolve()
    progress_path = (project_root / str(config.get("progress_path", "./progress.json"))).resolve()
    consultants_map = dict(config.get("consultants_map", {}))

    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    month_dir = output_dir / period_label
    cn_output_dir = month_dir / "CN"
    en_output_dir = month_dir / "EN"
    manual_review_dir = month_dir / "待人工确认"
    cn_output_dir.mkdir(parents=True, exist_ok=True)
    en_output_dir.mkdir(parents=True, exist_ok=True)
    manual_review_dir.mkdir(parents=True, exist_ok=True)

    progress = load_progress(progress_path)
    manifest = ManifestWriter(output_dir, prefix=str(config.get("manifest_prefix", "hkex_io_manifest")))

    base_url = str(config.get("base_urls", {}).get("application_proof", "")).strip()
    if not base_url:
        raise ValueError("config.base_urls.application_proof is required")

    limit = _effective_limit(config)
    total = 0
    done_count = 0
    partial_count = 0
    failed_count = 0
    manual_review_count = 0
    processed = 0
    stopped = False

    with BrowserSession(config) as session:
        assert session.page is not None
        assert session.context is not None

        goto_retry = retry_with_backoff(
            max_retries=int(config["max_retries"]),
            min_delay=float(config["min_delay"]),
            max_delay=float(config["max_delay"]),
        )

        @goto_retry
        def _open_listing() -> None:
            session.goto_with_wait(base_url, timeout_ms=45000)

        _open_listing()
        session.click_accept_if_present()

        candidates = collect_candidates_from_json(start_date=start_d, end_date=end_d, limit=limit)
        if not candidates:
            logger.warning("JSON listing source returned 0 candidates, fallback to page expansion mode.")
            candidates = collect_candidates_from_listing(
                session.page,
                start_date=start_d,
                end_date=end_d,
                limit=limit,
            )

        total = len(candidates)
        _notify(callbacks.on_start, total)

        for candidate in candidates:
            if stop_event and stop_event.is_set():
                stopped = True
                break

            existing_status = progress.get(candidate.progress_key, "")
            if existing_status in {"done", "failed", "manual_review", "partial"}:
                if existing_status == "done":
                    done_count += 1
                elif existing_status == "partial":
                    partial_count += 1
                elif existing_status == "manual_review":
                    manual_review_count += 1
                else:
                    failed_count += 1
                processed += 1
                _notify(callbacks.on_company_done, processed, total, candidate.company_name_raw, existing_status)
                continue

            logger.info("Processing {} ({})", candidate.company_name_raw, candidate.filing_date)
            try:
                result = process_company(
                    session.page,
                    session.context,
                    candidate,
                    config,
                    consultants_map,
                    cn_output_dir,
                    en_output_dir,
                    manual_review_dir,
                    tmp_dir,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Company processing failed {}: {}", candidate.company_name_raw, exc)
                result = _build_failed_result(candidate.filing_date.isoformat(), candidate.company_name_raw, str(exc))

            manifest.add_row(result.as_manifest_row())
            progress[candidate.progress_key] = result.status
            save_progress(progress_path, progress)

            if result.status == "done":
                done_count += 1
            elif result.status == "partial":
                partial_count += 1
            elif result.status == "manual_review":
                manual_review_count += 1
            else:
                failed_count += 1

            processed += 1
            _notify(callbacks.on_company_done, processed, total, candidate.company_name_raw, result.status)

    csv_path, xlsx_path = manifest.save()

    if bool(config.get("enable_backfill", True)):
        moved = backfill_manual_review_for_month(output_dir, period_label)
        if moved > 0:
            logger.warning("Backfill moved {} records to manual review for {}", moved, period_label)

    summary = JobSummary(
        month=month,
        period_label=period_label,
        total=total,
        processed=processed,
        done=done_count,
        partial=partial_count,
        failed=failed_count,
        manual_review=manual_review_count,
        csv_path=csv_path,
        xlsx_path=xlsx_path,
        stopped=stopped,
    )
    _notify(callbacks.on_finished, summary)
    return summary
