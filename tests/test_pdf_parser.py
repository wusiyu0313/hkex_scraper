from pathlib import Path

from scraper import pdf_parser


def test_pdf_parser_fallback_to_pdfminer(monkeypatch) -> None:
    monkeypatch.setattr(pdf_parser, "extract_text_with_pdfplumber", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(pdf_parser, "extract_text_with_pdfminer", lambda *_args, **_kwargs: "from_pdfminer")
    text, method = pdf_parser.extract_text_first_pages(Path("dummy.pdf"))
    assert text == "from_pdfminer"
    assert method == "pdfminer"


def test_pdf_parser_fallback_to_ocr(monkeypatch) -> None:
    monkeypatch.setattr(pdf_parser, "extract_text_with_pdfplumber", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(pdf_parser, "extract_text_with_pdfminer", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom2")))
    monkeypatch.setattr(pdf_parser, "extract_text_with_ocr", lambda *_args, **_kwargs: "from_ocr")
    text, method = pdf_parser.extract_text_first_pages(Path("dummy.pdf"))
    assert text == "from_ocr"
    assert method == "ocr"


def test_pdf_parser_all_failed(monkeypatch) -> None:
    monkeypatch.setattr(pdf_parser, "extract_text_with_pdfplumber", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("a")))
    monkeypatch.setattr(pdf_parser, "extract_text_with_pdfminer", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("b")))
    monkeypatch.setattr(pdf_parser, "extract_text_with_ocr", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("c")))
    text, method = pdf_parser.extract_text_first_pages(Path("dummy.pdf"))
    assert text == ""
    assert method == "failed"

