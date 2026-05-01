from datetime import date
from pathlib import Path

from scraper.company import process_company
from scraper.types import CandidateRecord


class DummyPage:
    def __init__(self) -> None:
        self.url = "https://example.com/20240101_c.htm"

    def goto(self, url: str, *_args, **_kwargs) -> None:
        self.url = url

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        return None

    def query_selector_all(self, *_args, **_kwargs):
        return []


class DummyContext:
    pass


def base_config() -> dict:
    return {"max_retries": 2, "min_delay": 0.0, "max_delay": 0.0}


def test_company_done_when_both_industry_overview_available(monkeypatch, tmp_path: Path) -> None:
    from scraper import company as m

    page = DummyPage()
    context = DummyContext()
    candidate = CandidateRecord(date(2024, 1, 2), "测试公司B", "https://example.com/multi2", "https://example.com/multi2_en")
    consultants = {"沙利文": {"aliases": ["Frost & Sullivan"]}}

    def fake_open(_page, url: str, _config):
        _page.url = url
        return True

    monkeypatch.setattr(m, "_open_page_retry", fake_open)

    def fake_collect(_page):
        if "lang=en" in _page.url or "multi2_en" in _page.url:
            return [
                ("Industry Overview", "https://example.com/en_io.pdf"),
                ("Business", "https://example.com/en_business.pdf"),
            ]
        return [
            ("行业概览", "https://example.com/cn_io.pdf"),
            ("业务", "https://example.com/cn_business.pdf"),
        ]

    monkeypatch.setattr(m, "_collect_pdf_links", fake_collect)
    monkeypatch.setattr(m, "_derive_business_from_business_pdf", lambda *_args, **_kwargs: ("半导体", []))

    cn_pdf = tmp_path / "cn.pdf"
    en_pdf = tmp_path / "en.pdf"
    cn_pdf.write_bytes(b"%PDF")
    en_pdf.write_bytes(b"%PDF")

    def fake_download(_ctx, *, io_url: str, **_kwargs):
        if io_url.endswith("cn_io.pdf"):
            return cn_pdf, [], "pdfplumber", "Frost & Sullivan"
        return en_pdf, [], "pdfplumber", "Frost & Sullivan"

    monkeypatch.setattr(m, "_download_io_pdf", fake_download)

    result = process_company(
        page=page,  # type: ignore[arg-type]
        context=context,  # type: ignore[arg-type]
        candidate=candidate,
        config=base_config(),
        consultants_map=consultants,
        cn_output_dir=tmp_path / "out" / "CN",
        en_output_dir=tmp_path / "out" / "EN",
        manual_review_dir=tmp_path / "out" / "待人工确认",
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "done"
    assert result.business == "半导体"
    assert result.cn_filename.endswith("_CN.pdf")
    assert result.en_filename.endswith("_EN.pdf")


def test_company_manual_review_when_only_reorg_overview(monkeypatch, tmp_path: Path) -> None:
    from scraper import company as m

    page = DummyPage()
    context = DummyContext()
    candidate = CandidateRecord(date(2024, 1, 3), "重组公司", "https://example.com/reorg_c.htm", "https://example.com/reorg_en.htm")
    consultants = {"沙利文": {"aliases": ["Frost & Sullivan"]}}

    def fake_open(_page, url: str, _config):
        _page.url = url
        return True

    monkeypatch.setattr(m, "_open_page_retry", fake_open)

    def fake_collect(_page):
        if "lang=en" in _page.url or "reorg_en" in _page.url:
            return [("OVERVIEW OF THE REORGANISATION PROPOSAL", "https://example.com/en_reorg.pdf")]
        return [("重组方案概览", "https://example.com/cn_reorg.pdf")]

    monkeypatch.setattr(m, "_collect_pdf_links", fake_collect)
    monkeypatch.setattr(m, "_derive_business_from_business_pdf", lambda *_args, **_kwargs: ("其他", []))

    def fake_download_review(_ctx, *, url: str, target_dir: Path, target_name: str, config: dict):
        p = target_dir / target_name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF")
        return p, "downloaded"

    monkeypatch.setattr(m, "_download_pdf_for_review", fake_download_review)

    result = process_company(
        page=page,  # type: ignore[arg-type]
        context=context,  # type: ignore[arg-type]
        candidate=candidate,
        config=base_config(),
        consultants_map=consultants,
        cn_output_dir=tmp_path / "out" / "CN",
        en_output_dir=tmp_path / "out" / "EN",
        manual_review_dir=tmp_path / "out" / "待人工确认",
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "manual_review"
    assert result.cn_io_url == ""
    assert result.en_io_url == ""
    assert "no_industry_overview" in result.notes
    assert (tmp_path / "out" / "待人工确认" / result.cn_filename).exists()
    assert (tmp_path / "out" / "待人工确认" / result.en_filename).exists()


def test_company_manual_review_when_no_overview_links(monkeypatch, tmp_path: Path) -> None:
    from scraper import company as m

    page = DummyPage()
    context = DummyContext()
    candidate = CandidateRecord(date(2024, 1, 4), "无IO公司", "https://example.com/noio_c.htm")
    consultants = {"沙利文": {"aliases": ["Frost & Sullivan"]}}

    def fake_open(_page, url: str, _config):
        _page.url = url
        return True

    monkeypatch.setattr(m, "_open_page_retry", fake_open)
    monkeypatch.setattr(m, "_collect_pdf_links", lambda _page: [("Corporate Information", "https://example.com/a.pdf")])
    monkeypatch.setattr(m, "_derive_business_from_business_pdf", lambda *_args, **_kwargs: ("其他", []))

    result = process_company(
        page=page,  # type: ignore[arg-type]
        context=context,  # type: ignore[arg-type]
        candidate=candidate,
        config=base_config(),
        consultants_map=consultants,
        cn_output_dir=tmp_path / "out" / "CN",
        en_output_dir=tmp_path / "out" / "EN",
        manual_review_dir=tmp_path / "out" / "待人工确认",
        tmp_dir=tmp_path / "tmp",
    )

    assert result.status == "manual_review"
    assert "no_industry_overview" in result.notes
