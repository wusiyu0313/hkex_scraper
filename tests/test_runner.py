from datetime import date
from pathlib import Path

from scraper import runner
from scraper.types import CandidateRecord, CompanyProcessResult


class DummySession:
    def __init__(self, _config):
        self.page = object()
        self.context = object()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def goto_with_wait(self, *_args, **_kwargs):
        return None

    def click_accept_if_present(self):
        return True


def test_runner_callbacks_and_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "BrowserSession", DummySession)

    candidates = [
        CandidateRecord(date(2026, 4, 1), "公司A", "https://example.com/a"),
        CandidateRecord(date(2026, 4, 2), "公司B", "https://example.com/b"),
    ]
    monkeypatch.setattr(runner, "collect_candidates_from_json", lambda **_kwargs: candidates)

    def fake_process_company(*args, **_kwargs):
        candidate = args[2]
        status = "done" if candidate.company_name_raw == "公司A" else "manual_review"
        return CompanyProcessResult(
            filing_date=candidate.filing_date.isoformat(),
            company_name=candidate.company_name_raw,
            consultant="沙利文",
            business="生物医药",
            cn_io_url="u1",
            en_io_url="u2",
            cn_filename="a_CN.pdf",
            en_filename="a_EN.pdf",
            status=status,
            notes="",
        )

    monkeypatch.setattr(runner, "process_company", fake_process_company)
    monkeypatch.setattr(runner, "backfill_manual_review_for_month", lambda *_args, **_kwargs: 0)

    starts: list[int] = []
    done_events: list[tuple[int, int, str, str]] = []
    finished = []

    callbacks = runner.JobCallbacks(
        on_start=lambda total: starts.append(total),
        on_company_done=lambda d, t, c, s: done_events.append((d, t, c, s)),
        on_finished=lambda summary: finished.append(summary),
    )

    cfg = {
        "project_root": str(tmp_path),
        "output_dir": "output",
        "tmp_dir": "tmp",
        "progress_path": "progress.json",
        "manifest_prefix": "hkex_io_manifest",
        "consultants_map": {},
        "base_urls": {"application_proof": "https://www1.hkexnews.hk/app/appindex.html"},
        "max_retries": 1,
        "min_delay": 0.0,
        "max_delay": 0.0,
        "headless": True,
    }

    summary = runner.run_month_job("2026-04", cfg, callbacks)

    assert starts == [2]
    assert len(done_events) == 2
    assert summary.total == 2
    assert summary.done == 1
    assert summary.manual_review == 1
    assert len(finished) == 1
