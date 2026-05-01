from __future__ import annotations

import argparse
import calendar
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from scraper.runner import JobCallbacks, JobSummary, run_month_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HKEX IO batch scraper")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--month", help="Target month in YYYY-MM, e.g. 2026-04")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-dir")
    parser.add_argument("--headless", choices=["true", "false"])
    parser.add_argument("--min-delay", type=float)
    parser.add_argument("--max-delay", type=float)
    parser.add_argument("--max-retries", type=int)
    parser.add_argument("--no-backfill", action="store_true")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data


def merge_config(base: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    merged = dict(base)
    cli_map = {
        "month": args.month,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "limit": args.limit,
        "output_dir": args.output_dir,
        "min_delay": args.min_delay,
        "max_delay": args.max_delay,
        "max_retries": args.max_retries,
    }
    for key, val in cli_map.items():
        if val is not None:
            merged[key] = val

    if args.headless is not None:
        merged["headless"] = args.headless.lower() == "true"

    merged["enable_backfill"] = not args.no_backfill
    return merged


def resolve_date_range(config: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(config)
    month_value = str(resolved.get("month", "")).strip()
    if not month_value:
        return resolved

    try:
        dt = datetime.strptime(month_value, "%Y-%m")
    except ValueError as exc:
        raise ValueError("month must be in YYYY-MM format, e.g. 2026-04") from exc

    last_day = calendar.monthrange(dt.year, dt.month)[1]
    resolved["start_date"] = f"{dt.year:04d}-{dt.month:02d}-01"
    resolved["end_date"] = f"{dt.year:04d}-{dt.month:02d}-{last_day:02d}"
    return resolved


def _derive_month(config: dict[str, Any]) -> str:
    month = str(config.get("month", "")).strip()
    if month:
        datetime.strptime(month, "%Y-%m")
        return month

    start_date = str(config.get("start_date", "")).strip()
    end_date = str(config.get("end_date", "")).strip()
    if start_date and end_date:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")
        if s.year == e.year and s.month == e.month:
            return f"{s.year:04d}-{s.month:02d}"

    raise ValueError("Please provide --month YYYY-MM (or config.month).")


def validate_config(config: dict[str, Any]) -> None:
    required = ["output_dir", "headless", "min_delay", "max_delay", "max_retries"]
    missing = [k for k in required if k not in config]
    if missing:
        raise ValueError(f"Missing config keys: {missing}")

    if float(config["min_delay"]) < 0 or float(config["max_delay"]) < 0:
        raise ValueError("delay must be >= 0")
    if float(config["min_delay"]) > float(config["max_delay"]):
        raise ValueError("min_delay must be <= max_delay")
    if int(config["max_retries"]) <= 0:
        raise ValueError("max_retries must be > 0")


def setup_logger(output_dir: Path) -> None:
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level="INFO")
    logger.add(
        str(output_dir / "hkex_scraper.log"),
        rotation="00:00",
        retention="30 days",
        level="INFO",
        encoding="utf-8",
    )


def _print_finished(summary: JobSummary) -> None:
    logger.info(
        "Finished month {} | total={} processed={} done={} partial={} failed={} manual_review={} stopped={}",
        summary.month,
        summary.total,
        summary.processed,
        summary.done,
        summary.partial,
        summary.failed,
        summary.manual_review,
        summary.stopped,
    )
    logger.info("Manifest CSV: {}", summary.csv_path)
    logger.info("Manifest XLSX: {}", summary.xlsx_path)


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent

    config_path = (project_root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    config = merge_config(load_yaml(config_path), args)
    config = resolve_date_range(config)
    validate_config(config)

    month = _derive_month(config)

    output_dir = (project_root / str(config["output_dir"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_logger(output_dir)

    consultants_map = load_yaml(project_root / "consultants.yaml")

    # 月份模式默认全量抓取；CLI 显式指定 --limit 时才生效。
    config["month_mode_full"] = True
    if args.limit is not None:
        config["limit_override"] = args.limit

    config["project_root"] = str(project_root)
    config["consultants_map"] = consultants_map

    callbacks = JobCallbacks(on_finished=_print_finished)
    run_month_job(month, config, callbacks)


if __name__ == "__main__":
    main()
