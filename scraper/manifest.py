from __future__ import annotations

from pathlib import Path

import pandas as pd

MANIFEST_COLUMNS = [
    "filing_date",
    "company_name",
    "consultant",
    "business",
    "cn_io_url",
    "en_io_url",
    "cn_filename",
    "en_filename",
    "status",
    "notes",
]


class ManifestWriter:
    def __init__(self, output_dir: Path, prefix: str = "hkex_io_manifest") -> None:
        self.output_dir = output_dir
        self.prefix = prefix
        self.rows: list[dict[str, str]] = []
        self._load_existing_rows()

    @property
    def csv_path(self) -> Path:
        return self.output_dir / f"{self.prefix}.csv"

    @property
    def xlsx_path(self) -> Path:
        return self.output_dir / f"{self.prefix}.xlsx"

    def _load_existing_rows(self) -> None:
        if not self.csv_path.exists():
            return
        try:
            df = pd.read_csv(self.csv_path)
            for _, row in df.iterrows():
                normalized = {col: str(row.get(col, "") if pd.notna(row.get(col, "")) else "") for col in MANIFEST_COLUMNS}
                self.rows.append(normalized)
        except Exception:
            return

    def add_row(self, row: dict[str, str]) -> None:
        normalized = {col: str(row.get(col, "")) for col in MANIFEST_COLUMNS}
        self.rows.append(normalized)

    def save(self) -> tuple[Path, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(self.rows, columns=MANIFEST_COLUMNS)
        df.to_csv(self.csv_path, index=False, encoding="utf-8-sig")
        df.to_excel(self.xlsx_path, index=False, engine="openpyxl")
        return self.csv_path, self.xlsx_path
