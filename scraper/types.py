from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class CandidateRecord:
    filing_date: date
    company_name_raw: str
    multi_files_url: str
    multi_files_url_en: str = ""

    @property
    def progress_key(self) -> str:
        return f"{self.filing_date.strftime('%Y%m%d')}_{self.company_name_raw}"


@dataclass
class CompanyProcessResult:
    filing_date: str
    company_name: str
    consultant: str
    business: str
    cn_io_url: str
    en_io_url: str
    cn_filename: str
    en_filename: str
    status: str
    notes: str = ""
    cn_file_path: Path | None = None
    en_file_path: Path | None = None
    extra_notes: list[str] = field(default_factory=list)

    def as_manifest_row(self) -> dict[str, str]:
        notes = self.notes
        if self.extra_notes:
            notes = "; ".join(filter(None, [notes, *self.extra_notes]))
        return {
            "filing_date": self.filing_date,
            "company_name": self.company_name,
            "consultant": self.consultant,
            "business": self.business,
            "cn_io_url": self.cn_io_url,
            "en_io_url": self.en_io_url,
            "cn_filename": self.cn_filename,
            "en_filename": self.en_filename,
            "status": self.status,
            "notes": notes,
        }
