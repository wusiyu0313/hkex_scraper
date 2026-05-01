from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from playwright.sync_api import BrowserContext
from tenacity import retry, stop_after_attempt, wait_exponential


def _sleep_jitter(min_delay: float, max_delay: float) -> None:
    time.sleep(random.uniform(min_delay, max_delay))


def _build_download_retry(max_retries: int, min_delay: float, max_delay: float):
    def _before_sleep(_retry_state) -> None:
        _sleep_jitter(min_delay, max_delay)

    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=_before_sleep,
        reraise=True,
    )


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or "document.pdf"


def get_remote_file_size(context: BrowserContext, url: str, timeout_ms: int = 20000) -> int | None:
    try:
        resp = context.request.fetch(url, method="HEAD", timeout=timeout_ms)
        if not resp.ok:
            return None
        size = resp.headers.get("content-length")
        return int(size) if size and size.isdigit() else None
    except Exception:  # noqa: BLE001
        return None


def download_pdf(
    context: BrowserContext,
    url: str,
    output_dir: Path,
    *,
    max_retries: int,
    min_delay: float,
    max_delay: float,
    max_size_mb: int = 200,
) -> tuple[Path | None, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = max_size_mb * 1024 * 1024
    size = get_remote_file_size(context, url)
    if size and size > max_bytes:
        logger.warning("Skip large PDF >{}MB: {}", max_size_mb, url)
        return None, "too_large"

    retry_decorator = _build_download_retry(max_retries, min_delay, max_delay)

    @retry_decorator
    def _download() -> Path:
        _sleep_jitter(min_delay, max_delay)
        resp = context.request.get(url, timeout=60000)
        if not resp.ok:
            raise RuntimeError(f"download failed status={resp.status}")
        filename = _filename_from_url(url)
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        target = output_dir / filename
        target.write_bytes(resp.body())
        return target

    try:
        file_path = _download()
        return file_path, "downloaded"
    except Exception as exc:  # noqa: BLE001
        logger.error("PDF download failed {}: {}", url, exc)
        return None, "failed"

