from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from loguru import logger
from playwright.sync_api import BrowserContext, Page

from scraper.downloader import download_pdf
from scraper.namer import build_filename
from scraper.pdf_parser import detect_consultant, extract_text_first_pages
from scraper.retrying import retry_with_backoff
from scraper.types import CandidateRecord, CompanyProcessResult

CN_IO_TITLES = {
    "行业概览",
    "行業概覽",
    "业务及行业概览",
    "業務及行業概覽",
    "业务概览及行业概览",
    "業務概覽及行業概覽",
}
EN_IO_TITLES = {
    "industry overview",
    "business and industry overview",
}

CN_BUSINESS_TITLES = {"业务", "業務", "业务概览", "業務概覽"}
EN_BUSINESS_TITLES = {"business", "business overview"}

CN_OVERVIEW_HINTS = ("概览", "概覽")
EN_OVERVIEW_HINTS = ("overview",)
CN_REORG_HINTS = ("重组", "重組", "重整", "监管", "監管")
EN_REORG_HINTS = ("reorganisation", "reorganization", "regulatory")

GENERIC_BUSINESS_TERMS = {"business", "business overview", "业务", "業務", "概览", "概覽"}

BUSINESS_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("生物医药", ("biotech", "biotechnology", "生物技术", "生物科技", "药物", "藥物", "制药", "製藥", "临床", "臨床")),
    ("半导体", ("semiconductor", "chip", "wafer", "晶圆", "晶圓", "半导体", "半導體")),
    ("新能源", ("新能源", "储能", "儲能", "锂", "鋰", "光伏", "风电", "風電", "氢能", "氫能", "battery")),
    ("物流", ("logistics", "supply chain", "freight", "物流", "仓储", "倉儲", "配送")),
    ("餐饮", ("restaurant", "food service", "foodservice", "餐饮", "餐飲", "连锁餐", "連鎖餐")),
    ("消费零售", ("retail", "consumer", "零售", "消费", "消費", "品牌运营", "品牌運營")),
    ("互联网平台", ("internet", "platform", "online marketplace", "e-commerce", "互联网", "互聯網", "电商", "電商")),
    ("软件服务", ("software", "saas", "paas", "cloud", "enterprise software", "软件", "軟件", "信息系统", "資訊系統")),
    ("人工智能", ("artificial intelligence", "ai", "machine learning", "algorithm", "人工智能", "机器学习", "機器學習")),
    ("金融服务", ("fintech", "payment", "insurance", "securities", "banking", "金融", "支付", "保险", "證券")),
    ("汽车出行", ("automotive", "mobility", "ride-hailing", "vehicle", "汽车", "汽車", "出行", "驾驶", "駕駛")),
    ("先进制造", ("industrial", "manufacturing", "automation", "equipment", "制造", "製造", "自动化", "自動化", "工业")),
    ("化工材料", ("chemical", "polymer", "composite", "materials", "化工", "材料", "高分子")),
    ("医疗服务", ("healthcare service", "hospital", "clinic", "medical service", "医疗服务", "醫療服務", "医院", "診所")),
    ("文娱传媒", ("media", "content", "game", "gaming", "entertainment", "文娱", "文娛", "传媒", "傳媒", "影视", "影視")),
    ("教育服务", ("education", "edtech", "learning", "training", "教育", "培训", "培訓")),
]
OTHER_INDUSTRY = "其他"
FIXED_INDUSTRIES = {label for label, _ in BUSINESS_CATEGORIES} | {OTHER_INDUSTRY}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _is_generic_business(label: str) -> bool:
    return _normalize(label) in {_normalize(x) for x in GENERIC_BUSINESS_TERMS}


def _classify_fixed_industry(text: str) -> str:
    lower = (text or "").lower()
    best_label = OTHER_INDUSTRY
    best_score = 0
    for label, keywords in BUSINESS_CATEGORIES:
        score = sum(1 for kw in keywords if kw.lower() in lower)
        if score > best_score:
            best_label = label
            best_score = score
    return best_label if best_score > 0 else OTHER_INDUSTRY


def _extract_overview_window(text: str) -> str:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines:
        return ""

    markers = ["业务概览", "業務概覽", "业务", "業務", "Business Overview", "Business", "Overview"]
    start = 0
    for i, line in enumerate(lines):
        if any(m.lower() in line.lower() for m in markers):
            start = i
            break
    return "\n".join(lines[start : start + 160])[:8000]


def _infer_business_from_text(text: str) -> str:
    overview = _extract_overview_window(text)
    if not overview:
        return OTHER_INDUSTRY

    compact = re.sub(r"\s+", "", overview)
    zh_def = re.search(r"(我们|本公司)[^。；\n]{0,60}(是一家|主要从事|專注於|专注于)[^。；\n]{4,120}", compact)
    if zh_def:
        candidate = _classify_fixed_industry(f"{zh_def.group(0)}\n{compact}")
        if candidate in FIXED_INDUSTRIES and not _is_generic_business(candidate):
            return candidate

    en_def = re.search(r"(we|ourcompany)[a-z\s,\-]{0,80}(are|is)[a-z\s,\-]{5,180}", compact.lower())
    if en_def:
        candidate = _classify_fixed_industry(f"{en_def.group(0)}\n{compact}")
        if candidate in FIXED_INDUSTRIES and not _is_generic_business(candidate):
            return candidate

    return _classify_fixed_industry(overview)


def _ensure_chinese_business(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return OTHER_INDUSTRY

    mapping = {
        "ai": "人工智能",
        "artificial intelligence": "人工智能",
        "saas": "软件服务",
        "cloud": "软件服务",
        "semiconductor": "半导体",
        "payment": "金融服务",
        "logistics": "物流",
        "biotech": "生物医药",
    }
    lower = raw.lower()
    if lower in mapping:
        return mapping[lower]
    if raw in FIXED_INDUSTRIES:
        return raw
    return _classify_fixed_industry(raw)


def _with_lang(url: str, lang: str) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["lang"] = lang
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(params), parsed.fragment))


def _swap_htm_suffix(url: str, target: str) -> str:
    lower = url.lower()
    if target == "en" and lower.endswith("_c.htm"):
        return url[:-6] + "_e.htm"
    if target == "zh" and lower.endswith("_e.htm"):
        return url[:-6] + "_c.htm"
    return url


def _build_page_variants(base_url: str, target: str) -> list[str]:
    if target == "zh":
        candidates = [_with_lang(base_url, "zh"), _swap_htm_suffix(base_url, "zh"), base_url]
    else:
        candidates = [_with_lang(base_url, "en"), _swap_htm_suffix(base_url, "en"), base_url]

    out: list[str] = []
    for c in candidates:
        if c and c not in out:
            out.append(c)
    return out


def _open_page_retry(page: Page, url: str, config: dict[str, Any]) -> bool:
    retry_decorator = retry_with_backoff(
        max_retries=int(config["max_retries"]),
        min_delay=float(config["min_delay"]),
        max_delay=float(config["max_delay"]),
    )

    @retry_decorator
    def _open() -> None:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)

    try:
        _open()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Open page failed {}: {}", url, exc)
        return False


def _collect_pdf_links(page: Page) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for anchor in page.query_selector_all("a"):
        try:
            text = (anchor.inner_text() or "").strip()
            href = (anchor.get_attribute("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(page.url, href)
            if abs_url.lower().endswith(".pdf"):
                links.append((text, abs_url))
        except Exception:  # noqa: BLE001
            continue
    return links


def _try_collect_lang_links(page: Page, config: dict[str, Any], variants: list[str]) -> tuple[str, list[tuple[str, str]]]:
    for url in variants:
        if _open_page_retry(page, url, config):
            links = _collect_pdf_links(page)
            if links:
                return url, links
    return "", []


def _is_exact_io_title(text: str, lang: str) -> bool:
    t = (text or "").strip()
    if lang == "CN":
        return t in CN_IO_TITLES
    return _normalize(t) in EN_IO_TITLES


def _find_exact_io_url(links: list[tuple[str, str]], lang: str) -> str:
    for text, url in links:
        if _is_exact_io_title(text, lang):
            return url
    return ""


def _find_business_url(links: list[tuple[str, str]], lang: str) -> str:
    titles = CN_BUSINESS_TITLES if lang == "CN" else EN_BUSINESS_TITLES

    for text, url in links:
        if _normalize(text) in {_normalize(x) for x in titles}:
            return url

    for text, url in links:
        lower = _normalize(text)
        if lang == "CN" and ("业务" in text or "業務" in text):
            return url
        if lang == "EN" and "business" in lower:
            return url
    return ""


def _find_manual_review_overview_url(links: list[tuple[str, str]], lang: str) -> str:
    for text, url in links:
        t = (text or "").strip()
        lower = t.lower()

        if lang == "CN":
            if not any(h in t for h in CN_OVERVIEW_HINTS):
                continue
            if _is_exact_io_title(t, "CN"):
                continue
            if any(k in t for k in CN_REORG_HINTS):
                return url
        else:
            if not any(h in lower for h in EN_OVERVIEW_HINTS):
                continue
            if _is_exact_io_title(t, "EN"):
                continue
            if any(k in lower for k in EN_REORG_HINTS):
                return url

    # 没有明确重组类标题时，仍然给人工复核保留一个 overview 链接。
    for text, url in links:
        t = (text or "").strip()
        lower = t.lower()
        if lang == "CN":
            if any(h in t for h in CN_OVERVIEW_HINTS) and not _is_exact_io_title(t, "CN"):
                return url
        else:
            if any(h in lower for h in EN_OVERVIEW_HINTS) and not _is_exact_io_title(t, "EN"):
                return url
    return ""


def _download_pdf_for_review(
    context: BrowserContext,
    *,
    url: str,
    target_dir: Path,
    target_name: str,
    config: dict[str, Any],
) -> tuple[Path | None, str]:
    path, status = download_pdf(
        context,
        url,
        target_dir,
        max_retries=int(config["max_retries"]),
        min_delay=float(config["min_delay"]),
        max_delay=float(config["max_delay"]),
    )
    if not path:
        return None, status

    final_path = target_dir / target_name
    if final_path.exists():
        final_path.unlink()
    path.replace(final_path)
    return final_path, status


def _download_io_pdf(
    context: BrowserContext,
    *,
    io_url: str,
    config: dict[str, Any],
    tmp_dir: Path,
) -> tuple[Path | None, list[str], str, str]:
    notes: list[str] = []

    file_path, status = download_pdf(
        context,
        io_url,
        tmp_dir,
        max_retries=int(config["max_retries"]),
        min_delay=float(config["min_delay"]),
        max_delay=float(config["max_delay"]),
    )
    if status == "too_large":
        notes.append("IO PDF >200MB 已跳过下载")
        return None, notes, "", ""
    if not file_path:
        notes.append("IO PDF 下载失败")
        return None, notes, "", ""

    text, extract_status = extract_text_first_pages(file_path, max_pages=5)
    return file_path, notes, extract_status, text


def _derive_business_from_business_pdf(
    context: BrowserContext,
    *,
    business_pdf_url: str,
    config: dict[str, Any],
    tmp_dir: Path,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    file_path, status = download_pdf(
        context,
        business_pdf_url,
        tmp_dir,
        max_retries=int(config["max_retries"]),
        min_delay=float(config["min_delay"]),
        max_delay=float(config["max_delay"]),
    )
    if status == "too_large":
        notes.append("业务 PDF >200MB 已跳过下载")
        return OTHER_INDUSTRY, notes
    if not file_path:
        notes.append("业务 PDF 下载失败")
        return OTHER_INDUSTRY, notes

    text, method = extract_text_first_pages(file_path, max_pages=10)
    if method == "failed":
        notes.append("业务 PDF text_extract=failed")

    business = _infer_business_from_text(text)
    if business == OTHER_INDUSTRY:
        notes.append("业务字段来源=业务章节未识别")
        return OTHER_INDUSTRY, notes

    notes.append("业务字段来源=业务章节概览")
    return business, notes


def process_company(
    page: Page,
    context: BrowserContext,
    candidate: CandidateRecord,
    config: dict[str, Any],
    consultants_map: dict[str, Any],
    cn_output_dir: Path,
    en_output_dir: Path,
    manual_review_dir: Path,
    tmp_dir: Path,
) -> CompanyProcessResult:
    notes: list[str] = []
    company_name = candidate.company_name_raw or "__待复核__"

    cn_base = candidate.multi_files_url or candidate.multi_files_url_en
    en_base = candidate.multi_files_url_en or candidate.multi_files_url
    cn_variants = _build_page_variants(cn_base, "zh")
    en_variants = _build_page_variants(en_base, "en")

    opened_cn_url, cn_links = _try_collect_lang_links(page, config, cn_variants)
    if not opened_cn_url:
        return CompanyProcessResult(
            filing_date=candidate.filing_date.isoformat(),
            company_name=company_name,
            consultant="__待复核__",
            business=OTHER_INDUSTRY,
            cn_io_url="",
            en_io_url="",
            cn_filename="",
            en_filename="",
            status="failed",
            notes="公司页面打开失败",
        )

    opened_en_url, en_links = _try_collect_lang_links(page, config, en_variants)
    if opened_en_url:
        _open_page_retry(page, opened_cn_url, config)

    cn_io_url = _find_exact_io_url(cn_links, "CN")
    en_io_url = _find_exact_io_url(en_links, "EN") if en_links else ""

    cn_business_url = _find_business_url(cn_links, "CN")
    en_business_url = _find_business_url(en_links, "EN") if en_links else ""

    business = OTHER_INDUSTRY
    business_notes: list[str] = []
    if cn_business_url:
        business, business_notes = _derive_business_from_business_pdf(
            context, business_pdf_url=cn_business_url, config=config, tmp_dir=tmp_dir
        )
    elif en_business_url:
        business, business_notes = _derive_business_from_business_pdf(
            context, business_pdf_url=en_business_url, config=config, tmp_dir=tmp_dir
        )
    else:
        notes.append("business_pdf_not_found")

    notes.extend(business_notes)
    business = _ensure_chinese_business(business)
    if business == OTHER_INDUSTRY:
        notes.append("业务字段=其他")

    consultant = "__待复核__"
    cn_local_file: Path | None = None
    en_local_file: Path | None = None
    cn_extract_status = ""
    en_extract_status = ""

    if not cn_io_url and not en_io_url:
        notes.append("no_industry_overview")
        manual_review_dir.mkdir(parents=True, exist_ok=True)

        cn_review_url = _find_manual_review_overview_url(cn_links, "CN")
        en_review_url = _find_manual_review_overview_url(en_links, "EN") if en_links else ""

        cn_filename = ""
        en_filename = ""

        if cn_review_url:
            cn_name = build_filename(consultant, company_name, business, "CN").filename.replace("_CN.pdf", "_CN_REVIEW.pdf")
            cn_filename = cn_name
            _download_pdf_for_review(context, url=cn_review_url, target_dir=manual_review_dir, target_name=cn_name, config=config)
            notes.append(f"manual_cn_url={cn_review_url}")

        if en_review_url:
            en_name = build_filename(consultant, company_name, business, "EN").filename.replace("_EN.pdf", "_EN_REVIEW.pdf")
            en_filename = en_name
            _download_pdf_for_review(context, url=en_review_url, target_dir=manual_review_dir, target_name=en_name, config=config)
            notes.append(f"manual_en_url={en_review_url}")

        return CompanyProcessResult(
            filing_date=candidate.filing_date.isoformat(),
            company_name=company_name,
            consultant=consultant,
            business=business,
            cn_io_url="",
            en_io_url="",
            cn_filename=cn_filename,
            en_filename=en_filename,
            status="manual_review",
            notes="; ".join(dict.fromkeys(notes)),
        )

    if not cn_io_url:
        notes.append("io_not_found_cn")
    if not en_io_url:
        notes.append("io_not_found_en")

    if cn_io_url:
        cn_local_file, cn_io_notes, cn_extract_status, cn_text = _download_io_pdf(
            context, io_url=cn_io_url, config=config, tmp_dir=tmp_dir
        )
        notes.extend(cn_io_notes)
        if cn_local_file:
            c_name, matched = detect_consultant(cn_text, consultants_map)
            if matched:
                consultant = c_name
            else:
                notes.append("委托公司=未识别")

    if en_io_url:
        en_local_file, en_io_notes, en_extract_status, en_text = _download_io_pdf(
            context, io_url=en_io_url, config=config, tmp_dir=tmp_dir
        )
        notes.extend(en_io_notes)
        if en_local_file and consultant == "__待复核__":
            c_name, matched = detect_consultant(en_text, consultants_map)
            if matched:
                consultant = c_name
            else:
                notes.append("委托公司=未识别")

    cn_filename = ""
    en_filename = ""
    if cn_io_url:
        n = build_filename(consultant, company_name, business, "CN")
        cn_filename = n.filename
        if n.was_cleaned:
            notes.append("CN 文件名字段清洗")

    if en_io_url:
        n = build_filename(consultant, company_name, business, "EN")
        en_filename = n.filename
        if n.was_cleaned:
            notes.append("EN 文件名字段清洗")

    cn_output_dir.mkdir(parents=True, exist_ok=True)
    en_output_dir.mkdir(parents=True, exist_ok=True)

    cn_final_path: Path | None = None
    en_final_path: Path | None = None

    if cn_local_file and cn_filename:
        cn_final_path = cn_output_dir / cn_filename
        if cn_final_path.exists():
            cn_final_path.unlink()
        cn_local_file.replace(cn_final_path)

    if en_local_file and en_filename:
        en_final_path = en_output_dir / en_filename
        if en_final_path.exists():
            en_final_path.unlink()
        en_local_file.replace(en_final_path)

    cn_ok = bool(cn_io_url and (cn_local_file or "IO PDF >200MB 已跳过下载" in notes))
    en_ok = bool(en_io_url and (en_local_file or "IO PDF >200MB 已跳过下载" in notes))

    if cn_ok and en_ok:
        status = "done"
    elif cn_ok or en_ok:
        status = "partial"
    else:
        status = "failed"

    if cn_extract_status == "failed":
        notes.append("CN text_extract=failed")
    if en_extract_status == "failed":
        notes.append("EN text_extract=failed")

    return CompanyProcessResult(
        filing_date=candidate.filing_date.isoformat(),
        company_name=company_name,
        consultant=consultant,
        business=business,
        cn_io_url=cn_io_url,
        en_io_url=en_io_url,
        cn_filename=cn_filename,
        en_filename=en_filename,
        status=status,
        notes="; ".join(dict.fromkeys(notes)),
        cn_file_path=cn_final_path,
        en_file_path=en_final_path,
    )
