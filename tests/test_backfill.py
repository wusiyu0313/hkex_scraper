from pathlib import Path

import pandas as pd

from scraper import backfill


def test_backfill_moves_reorg_files_to_manual_review(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    month = "2026-04"
    cn_dir = output_dir / month / "CN"
    en_dir = output_dir / month / "EN"
    manual_dir = output_dir / month / "待人工确认"
    cn_dir.mkdir(parents=True, exist_ok=True)
    en_dir.mkdir(parents=True, exist_ok=True)
    manual_dir.mkdir(parents=True, exist_ok=True)

    cn_file = cn_dir / "foo_CN.pdf"
    en_file = en_dir / "foo_EN.pdf"
    cn_file.write_bytes(b"%PDF")
    en_file.write_bytes(b"%PDF")

    df = pd.DataFrame(
        [
            {
                "filing_date": "2026-04-29",
                "company_name": "龙资源有限公司",
                "consultant": "MPA",
                "business": "其他",
                "cn_io_url": "https://x/cn.pdf",
                "en_io_url": "https://x/en.pdf",
                "cn_filename": "foo_CN.pdf",
                "en_filename": "foo_EN.pdf",
                "status": "done",
                "notes": "",
            }
        ]
    )
    csv_path = output_dir / "hkex_io_manifest.csv"
    xlsx_path = output_dir / "hkex_io_manifest.xlsx"
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False, engine="openpyxl")

    monkeypatch.setattr(backfill, "_is_non_industry_overview_pdf", lambda _p: True)

    moved = backfill.backfill_manual_review_for_month(output_dir, month)
    assert moved == 1
    assert (manual_dir / "foo_CN.pdf").exists()
    assert (manual_dir / "foo_EN.pdf").exists()

    out = pd.read_csv(csv_path)
    assert out.loc[0, "status"] == "manual_review"
    assert "no_industry_overview" in out.loc[0, "notes"]
    assert "moved_to_manual_review" in out.loc[0, "notes"]
