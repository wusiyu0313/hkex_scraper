from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber
import pytesseract
from loguru import logger
from pdf2image import convert_from_path
from pdfminer.high_level import extract_text as pdfminer_extract_text


def extract_text_with_pdfplumber(pdf_path: Path, max_pages: int = 5) -> str:
    chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
    return "\n".join(chunks).strip()


def extract_text_with_pdfminer(pdf_path: Path, max_pages: int = 5) -> str:
    page_numbers = list(range(max_pages))
    text = pdfminer_extract_text(str(pdf_path), page_numbers=page_numbers)
    return (text or "").strip()


def extract_text_with_ocr(pdf_path: Path, max_pages: int = 5) -> str:
    pytesseract.get_tesseract_version()
    images = convert_from_path(str(pdf_path), first_page=1, last_page=max_pages)
    chunks: list[str] = []
    for image in images:
        text = pytesseract.image_to_string(image, lang="eng+chi_sim+chi_tra")
        if text.strip():
            chunks.append(text)
    return "\n".join(chunks).strip()


def extract_text_first_pages(pdf_path: Path, max_pages: int = 5) -> tuple[str, str]:
    try:
        text = extract_text_with_pdfplumber(pdf_path, max_pages=max_pages)
        if text:
            return text, "pdfplumber"
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdfplumber failed for {}: {}", pdf_path, exc)

    try:
        text = extract_text_with_pdfminer(pdf_path, max_pages=max_pages)
        if text:
            return text, "pdfminer"
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdfminer failed for {}: {}", pdf_path, exc)

    try:
        text = extract_text_with_ocr(pdf_path, max_pages=max_pages)
        if text:
            return text, "ocr"
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr failed for {}: {}", pdf_path, exc)

    return "", "failed"


def normalize_text_for_match(text: str) -> str:
    return (text or "").lower().replace(" ", "")


def detect_consultant(text: str, consultants_map: dict[str, dict[str, Any]]) -> tuple[str, bool]:
    normalized = normalize_text_for_match(text)
    raw_lower = (text or "").lower()

    for canonical_name, payload in consultants_map.items():
        aliases = payload.get("aliases", []) if isinstance(payload, dict) else []
        for alias in aliases:
            alias_str = str(alias)
            alias_norm = normalize_text_for_match(alias_str)

            if re.fullmatch(r"[A-Za-z]{2,4}", alias_str):
                if re.search(rf"\b{re.escape(alias_str.lower())}\b", raw_lower):
                    return canonical_name, True
                continue

            if alias_norm and alias_norm in normalized:
                return canonical_name, True

        if normalize_text_for_match(str(canonical_name)) in normalized:
            return canonical_name, True

    return "__待复核__", False
