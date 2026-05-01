from __future__ import annotations

from pathlib import Path

import pandas as pd

from scraper.pdf_parser import extract_text_first_pages

INDUSTRY_MARKERS = ["industry overview", "行业概览", "行業概覽"]
NON_INDUSTRY_OVERVIEW_MARKERS = [
    "overview of the reorganisation proposal",
    "overview of the reorganization proposal",
    "regulatory overview",
    "重组方案概览",
    "重組方案概覽",
]


def _is_non_industry_overview_pdf(pdf_path: Path) -> bool:
    if not pdf_path.exists():
        return False
    text, _ = extract_text_first_pages(pdf_path, max_pages=2)
    lower = (text or "").lower()
    if any(marker.lower() in lower for marker in INDUSTRY_MARKERS):
        return False
    return any(marker.lower() in lower for marker in NON_INDUSTRY_OVERVIEW_MARKERS)


def _append_note(base: str, add: str) -> str:
    if base is None or (isinstance(base, float) and pd.isna(base)):
        base = ""
    parts = [x.strip() for x in str(base or "").split(";") if x.strip() and x.strip().lower() != "nan"]
    if add not in parts:
        parts.append(add)
    return "; ".join(parts)


def backfill_manual_review_for_month(output_dir: Path, month_label: str) -> int:
    manifest_csv = output_dir / "hkex_io_manifest.csv"
    manifest_xlsx = output_dir / "hkex_io_manifest.xlsx"
    month_dir = output_dir / month_label
    cn_dir = month_dir / "CN"
    en_dir = month_dir / "EN"
    manual_dir = month_dir / "待人工确认"
    manual_dir.mkdir(parents=True, exist_ok=True)

    if not manifest_csv.exists():
        return 0

    df = pd.read_csv(manifest_csv)
    if "notes" in df.columns:
        df["notes"] = df["notes"].fillna("").astype(str)

    moved = 0
    for idx, row in df.iterrows():
        status = str(row.get("status", "")).strip().lower()
        if status == "manual_review":
            continue

        cn_name = str(row.get("cn_filename", "") or "").strip()
        en_name = str(row.get("en_filename", "") or "").strip()
        cn_path = cn_dir / cn_name if cn_name else None
        en_path = en_dir / en_name if en_name else None

        cn_bad = bool(cn_path and cn_path.exists() and _is_non_industry_overview_pdf(cn_path))
        en_bad = bool(en_path and en_path.exists() and _is_non_industry_overview_pdf(en_path))
        if not cn_bad and not en_bad:
            continue

        if cn_path and cn_path.exists():
            target = manual_dir / cn_path.name
            if target.exists():
                target.unlink()
            cn_path.replace(target)

        if en_path and en_path.exists():
            target = manual_dir / en_path.name
            if target.exists():
                target.unlink()
            en_path.replace(target)

        df.at[idx, "status"] = "manual_review"
        df.at[idx, "notes"] = _append_note(row.get("notes", ""), "no_industry_overview")
        df.at[idx, "notes"] = _append_note(df.at[idx, "notes"], "moved_to_manual_review")
        moved += 1

    if moved > 0:
        df.to_csv(manifest_csv, index=False, encoding="utf-8-sig")
        df.to_excel(manifest_xlsx, index=False, engine="openpyxl")
    return moved
