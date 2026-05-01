from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


class BrowserSession:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def _prepare_browser_env(self) -> None:
        local_pw = Path.cwd() / "ms-playwright"
        if local_pw.exists():
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(local_pw))

    def _install_chromium(self) -> None:
        logger.warning("Chromium not found. Installing Playwright Chromium runtime...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

    def __enter__(self) -> "BrowserSession":
        self._prepare_browser_env()
        self._playwright = sync_playwright().start()

        try:
            self.browser = self._playwright.chromium.launch(headless=bool(self.config.get("headless", True)))
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "executable doesn't exist" in message or "playwright install" in message:
                self._install_chromium()
                self.browser = self._playwright.chromium.launch(headless=bool(self.config.get("headless", True)))
            else:
                raise

        storage_state_path = Path(self.config.get("storage_state_path", "./storage_state.json"))
        context_kwargs: dict[str, Any] = {}
        if storage_state_path.exists():
            context_kwargs["storage_state"] = str(storage_state_path)

        self.context = self.browser.new_context(**context_kwargs)
        self.page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.context:
                storage_state_path = Path(self.config.get("storage_state_path", "./storage_state.json"))
                storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                self.context.storage_state(path=str(storage_state_path))
        except Exception as state_err:  # noqa: BLE001
            logger.warning("Failed to persist storage_state: {}", state_err)
        finally:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self._playwright:
                self._playwright.stop()

    def goto_with_wait(self, url: str, timeout_ms: int = 30000) -> None:
        if not self.page:
            raise RuntimeError("Page is not initialized")
        self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        self.page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))

    def click_accept_if_present(self) -> bool:
        if not self.page:
            raise RuntimeError("Page is not initialized")
        selectors = self.config.get("selectors", {}).get("accept_buttons", [])
        for sel in selectors:
            locator = self.page.locator(sel).first
            try:
                locator.wait_for(state="visible", timeout=3000)
                locator.click(timeout=3000)
                self.page.wait_for_timeout(1000)
                logger.info("Clicked ACCEPT popup.")
                return True
            except Exception:  # noqa: BLE001
                continue
        logger.warning("ACCEPT popup not found or not clickable in 10 seconds, continue.")
        return False
