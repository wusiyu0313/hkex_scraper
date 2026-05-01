from __future__ import annotations

import re
from pathlib import Path
from threading import Event
from typing import Any

import flet as ft

from main import load_yaml, merge_config, setup_logger, validate_config
from scraper.runner import JobCallbacks, JobSummary, run_month_job

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def _load_runtime_config(project_root: Path) -> dict[str, Any]:
    config = load_yaml(project_root / "config.yaml")
    args_like = type("Args", (), {
        "month": None,
        "start_date": None,
        "end_date": None,
        "limit": None,
        "output_dir": None,
        "headless": None,
        "min_delay": None,
        "max_delay": None,
        "max_retries": None,
        "no_backfill": False,
    })()
    config = merge_config(config, args_like)
    validate_config(config)
    return config


def _summary_text(s: JobSummary) -> str:
    return (
        f"完成: total={s.total}, processed={s.processed}, "
        f"done={s.done}, partial={s.partial}, failed={s.failed}, manual_review={s.manual_review}"
    )


def main(page: ft.Page) -> None:
    page.title = "HKEX IO 抓取器"
    page.window_width = 980
    page.window_height = 760
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT

    project_root = Path(__file__).resolve().parent
    config = _load_runtime_config(project_root)
    output_dir = (project_root / str(config.get("output_dir", "./output"))).resolve()
    setup_logger(output_dir)

    consultants_map = load_yaml(project_root / "consultants.yaml")

    month_input = ft.TextField(
        label="月份 (YYYY-MM)",
        value="2026-04",
        width=220,
        hint_text="例如 2026-04",
    )

    status_text = ft.Text("等待开始", size=14)
    total_text = ft.Text("本月公司总数: -", size=14)
    progress_text = ft.Text("下载进度: 0/0", size=16, weight=ft.FontWeight.W_600)
    progress_bar = ft.ProgressBar(width=600, value=0)

    done_count_text = ft.Text("done: 0")
    partial_count_text = ft.Text("partial: 0")
    failed_count_text = ft.Text("failed: 0")
    manual_count_text = ft.Text("manual_review: 0")

    logs = ft.ListView(expand=True, spacing=6, auto_scroll=True)

    start_btn = ft.ElevatedButton("开始下载", icon=ft.Icons.DOWNLOAD)
    stop_btn = ft.OutlinedButton("停止", icon=ft.Icons.STOP_CIRCLE_OUTLINED, disabled=True)

    running = {"value": False}
    stop_event = {"value": Event()}
    counters = {"done": 0, "partial": 0, "failed": 0, "manual_review": 0}

    def append_log(message: str) -> None:
        logs.controls.append(ft.Text(message, size=12))
        page.update()

    def reset_progress_ui() -> None:
        counters["done"] = 0
        counters["partial"] = 0
        counters["failed"] = 0
        counters["manual_review"] = 0
        done_count_text.value = "done: 0"
        partial_count_text.value = "partial: 0"
        failed_count_text.value = "failed: 0"
        manual_count_text.value = "manual_review: 0"
        progress_text.value = "下载进度: 0/0"
        progress_bar.value = 0
        logs.controls.clear()
        page.update()

    def on_start(total: int) -> None:
        total_text.value = f"本月公司总数: {total}"
        progress_text.value = f"下载进度: 0/{total}"
        progress_bar.value = 0
        status_text.value = "进行中"
        page.update()

    def on_company_done(done: int, total: int, company: str, status: str) -> None:
        if status in counters:
            counters[status] += 1
        done_count_text.value = f"done: {counters['done']}"
        partial_count_text.value = f"partial: {counters['partial']}"
        failed_count_text.value = f"failed: {counters['failed']}"
        manual_count_text.value = f"manual_review: {counters['manual_review']}"
        progress_text.value = f"下载进度: {done}/{total}"
        progress_bar.value = 0 if total == 0 else done / total
        logs.controls.append(ft.Text(f"[{status}] {company}", size=12))
        page.update()

    def on_finished(summary: JobSummary) -> None:
        status_text.value = "已停止" if summary.stopped else "已完成"
        append_log(_summary_text(summary))
        append_log(f"Manifest CSV: {summary.csv_path}")
        append_log(f"Manifest XLSX: {summary.xlsx_path}")
        running["value"] = False
        start_btn.disabled = False
        stop_btn.disabled = True
        page.update()

    def run_job() -> None:
        month = (month_input.value or "").strip()
        if not MONTH_PATTERN.match(month):
            status_text.value = "月份格式错误，请使用 YYYY-MM"
            page.update()
            return

        run_cfg = dict(config)
        run_cfg["project_root"] = str(project_root)
        run_cfg["consultants_map"] = consultants_map
        run_cfg["headless"] = True
        run_cfg["month_mode_full"] = True

        callbacks = JobCallbacks(
            on_start=on_start,
            on_company_done=on_company_done,
            on_finished=on_finished,
            on_log=append_log,
        )

        try:
            run_month_job(month, run_cfg, callbacks, stop_event=stop_event["value"])
        except Exception as exc:  # noqa: BLE001
            status_text.value = f"运行失败: {exc}"
            append_log(f"ERROR: {exc}")
            running["value"] = False
            start_btn.disabled = False
            stop_btn.disabled = True
            page.update()

    def start_click(_e: ft.ControlEvent) -> None:
        if running["value"]:
            return
        running["value"] = True
        stop_event["value"] = Event()
        reset_progress_ui()
        start_btn.disabled = True
        stop_btn.disabled = False
        status_text.value = "准备中"
        page.update()
        page.run_thread(run_job)

    def stop_click(_e: ft.ControlEvent) -> None:
        stop_event["value"].set()
        status_text.value = "停止中（将在当前公司完成后停止）"
        stop_btn.disabled = True
        page.update()

    start_btn.on_click = start_click
    stop_btn.on_click = stop_click

    header = ft.Container(
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.BLUE_50,
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Text("HKEX 行业概览批量下载", size=24, weight=ft.FontWeight.BOLD),
                ft.Text(f"输出目录: {output_dir}", size=12),
            ],
        ),
    )

    controls_row = ft.Row(
        controls=[month_input, start_btn, stop_btn],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    stats_row = ft.Row(
        controls=[done_count_text, partial_count_text, failed_count_text, manual_count_text],
        spacing=24,
    )

    page.add(
        ft.Column(
            expand=True,
            spacing=14,
            controls=[
                header,
                controls_row,
                status_text,
                total_text,
                progress_text,
                progress_bar,
                stats_row,
                ft.Divider(),
                ft.Text("运行日志", size=14, weight=ft.FontWeight.W_600),
                ft.Container(expand=True, border=ft.border.all(1, ft.Colors.GREY_300), padding=10, content=logs),
            ],
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
