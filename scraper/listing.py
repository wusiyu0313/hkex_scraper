from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from loguru import logger
from playwright.sync_api import Page

from scraper.types import CandidateRecord

MULTI_FILES_KEYWORDS = ["multi-files", "多档案", "多檔案"]
EXPAND_BUTTON_KEYWORDS = ["Load more", "More", "Next", "更多", "下一页", "下一頁"]

DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(20\d{2})/(\d{1,2})/(\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b"),
]

HKEX_JSON_ENDPOINTS_EN = [
    "https://www1.hkexnews.hk/ncms/json/eds/appactive_app_sehk_e.json",
    "https://www1.hkexnews.hk/ncms/json/eds/appactive_app_gem_e.json",
]
HKEX_JSON_ENDPOINTS_ZH = [
    "https://www1.hkexnews.hk/ncms/json/eds/appactive_app_sehk_c.json",
    "https://www1.hkexnews.hk/ncms/json/eds/appactive_app_gem_c.json",
]


def parse_date(text: str) -> date | None:
    value = text or ""
    for idx, pattern in enumerate(DATE_PATTERNS):
        m = pattern.search(value)
        if not m:
            continue
        try:
            if idx in (0, 1):
                yyyy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(yyyy, mm, dd)
        except ValueError:
            continue
    return None


def _parse_ddmmyyyy(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except Exception:  # noqa: BLE001
        return None


def _fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        payload = resp.read().decode("utf-8", "ignore")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError(f"unexpected json root from {url}")
    return data


def _has_multi_files(text: str) -> bool:
    lower = (text or "").lower()
    return any(keyword in lower for keyword in MULTI_FILES_KEYWORDS)


def _collect_chinese_maps() -> tuple[dict[int, str], dict[int, str]]:
    name_map: dict[int, str] = {}
    u2_map: dict[int, str] = {}
    for url in HKEX_JSON_ENDPOINTS_ZH:
        try:
            data = _fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load zh listing json {}: {}", url, exc)
            continue

        app_rows = data.get("app", [])
        if not isinstance(app_rows, list):
            continue

        for row in app_rows:
            if not isinstance(row, dict):
                continue
            rid = row.get("id")
            cname = str(row.get("a", "")).strip()
            if isinstance(rid, int) and cname:
                name_map[rid] = cname

            links = row.get("ls", [])
            if not isinstance(links, list) or not isinstance(rid, int):
                continue

            for item in links:
                if not isinstance(item, dict):
                    continue
                n2 = str(item.get("nS2", "")).strip()
                if not _has_multi_files(n2):
                    continue
                u2 = str(item.get("u2", "")).strip()
                if u2:
                    u2_map[rid] = u2
                    break

    return name_map, u2_map


def collect_candidates_from_json(*, start_date: date, end_date: date, limit: int) -> list[CandidateRecord]:
    name_map_zh, u2_map_zh = _collect_chinese_maps()
    candidates: list[CandidateRecord] = []

    for url in HKEX_JSON_ENDPOINTS_EN:
        try:
            data = _fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load listing json {}: {}", url, exc)
            continue

        app_rows = data.get("app", [])
        if not isinstance(app_rows, list):
            continue

        for row in app_rows:
            if not isinstance(row, dict):
                continue

            filing_date = _parse_ddmmyyyy(str(row.get("d", "")))
            if not filing_date or filing_date < start_date or filing_date > end_date:
                continue

            links = row.get("ls", [])
            if not isinstance(links, list):
                continue

            mf_u2_en = ""
            for item in links:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("nS2", "")).strip()
                if not _has_multi_files(title):
                    continue
                u2 = str(item.get("u2", "")).strip()
                if u2:
                    mf_u2_en = u2
                    break
            if not mf_u2_en:
                continue

            rid = row.get("id")
            company_name = ""
            if isinstance(rid, int):
                company_name = name_map_zh.get(rid, "")
            if not company_name:
                company_name = str(row.get("a", "")).strip() or "__待复核__"

            selected_u2_cn = mf_u2_en
            if isinstance(rid, int) and rid in u2_map_zh:
                selected_u2_cn = u2_map_zh[rid]

            cn_url = f"https://www1.hkexnews.hk/app/{selected_u2_cn.lstrip('/')}"
            en_url = f"https://www1.hkexnews.hk/app/{mf_u2_en.lstrip('/')}"

            candidates.append(
                CandidateRecord(
                    filing_date=filing_date,
                    company_name_raw=company_name,
                    multi_files_url=cn_url,
                    multi_files_url_en=en_url,
                )
            )

    candidates.sort(key=lambda c: c.filing_date)
    deduped: dict[tuple[str, str], CandidateRecord] = {}
    for c in candidates:
        key = (c.filing_date.isoformat(), c.company_name_raw)
        if key not in deduped:
            deduped[key] = c
    return list(deduped.values())[:limit]


def extract_company_name_from_row(row_text: str) -> str:
    lines = [line.strip() for line in (row_text or "").splitlines() if line.strip()]
    for line in lines:
        if parse_date(line):
            continue
        if _has_multi_files(line):
            continue
        if len(line) < 2:
            continue
        return line
    return lines[0] if lines else "__待复核__"


def extract_candidates_from_blocks(
    blocks: list[dict[str, str]],
    *,
    start_date: date,
    end_date: date,
    limit: int,
) -> list[CandidateRecord]:
    candidates: list[CandidateRecord] = []
    for block in blocks:
        row_text = block.get("row_text", "")
        link_text = block.get("link_text", "")
        href = block.get("href", "")

        joined_text = f"{row_text}\n{link_text}"
        if not _has_multi_files(joined_text):
            continue

        filing_date = parse_date(joined_text)
        if not filing_date:
            continue
        if filing_date < start_date or filing_date > end_date:
            continue

        company_name = extract_company_name_from_row(row_text)
        candidates.append(
            CandidateRecord(
                filing_date=filing_date,
                company_name_raw=company_name,
                multi_files_url=href,
            )
        )

    candidates.sort(key=lambda c: c.filing_date)
    deduped: dict[tuple[str, str], CandidateRecord] = {}
    for c in candidates:
        key = (c.filing_date.isoformat(), c.company_name_raw)
        if key not in deduped:
            deduped[key] = c
    return list(deduped.values())[:limit]


def _collect_blocks_from_page(page: Page) -> list[dict[str, str]]:
    anchors = page.query_selector_all("a")
    rows: list[dict[str, str]] = []
    for anchor in anchors:
        try:
            link_text = (anchor.inner_text() or "").strip()
            if not _has_multi_files(link_text):
                continue

            href = (anchor.get_attribute("href") or "").strip()
            row_text = anchor.evaluate(
                "el => (el.closest('tr, li, .table-row, .row, .item, div') || el).innerText || ''"
            )
            if href and href.startswith("/"):
                href = urljoin(page.url, href)
            rows.append({"row_text": row_text, "link_text": link_text, "href": href})
        except Exception:  # noqa: BLE001
            continue
    return rows


def _try_click_expand(page: Page) -> bool:
    for keyword in EXPAND_BUTTON_KEYWORDS:
        locator = page.locator(f"button:has-text('{keyword}'), a:has-text('{keyword}')").first
        if locator.count() == 0:
            continue
        try:
            if locator.is_visible():
                locator.click(timeout=2000)
                page.wait_for_timeout(1200)
                logger.debug("Clicked expand control: {}", keyword)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _scroll_page_and_iframes(page: Page) -> None:
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:  # noqa: BLE001
            continue
    page.wait_for_timeout(1200)


def collect_candidates_from_listing(
    page: Page,
    *,
    start_date: date,
    end_date: date,
    limit: int,
) -> list[CandidateRecord]:
    no_growth_scroll_rounds = 0
    prev_count = 0
    early_date_seen = False

    for _ in range(80):
        blocks = _collect_blocks_from_page(page)
        all_dates = [parse_date((b.get("row_text", "") + "\n" + b.get("link_text", "")).strip()) for b in blocks]
        all_dates = [d for d in all_dates if d is not None]
        if all_dates and min(all_dates) < start_date:
            early_date_seen = True

        parsed = extract_candidates_from_blocks(blocks, start_date=start_date, end_date=end_date, limit=max(limit, 500))

        cur_count = len(blocks)
        if cur_count <= prev_count:
            no_growth_scroll_rounds += 1
        else:
            no_growth_scroll_rounds = 0
        prev_count = cur_count

        if len(parsed) >= limit:
            return parsed[:limit]
        if early_date_seen:
            return parsed[:limit]
        if no_growth_scroll_rounds >= 2:
            return parsed[:limit]

        if not _try_click_expand(page):
            _scroll_page_and_iframes(page)

    logger.warning("Reached max expand loops when collecting listing candidates")
    blocks = _collect_blocks_from_page(page)
    return extract_candidates_from_blocks(blocks, start_date=start_date, end_date=end_date, limit=limit)


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
