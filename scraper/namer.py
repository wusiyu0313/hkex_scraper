from __future__ import annotations

import re
from dataclasses import dataclass


ILLEGAL_CHARS_RE = re.compile(r'[\/\\:\*\?"<>\|\x00-\x1f]')
MULTI_UNDERSCORE_RE = re.compile(r"_+")
TRAILING_DOT_SPACE_RE = re.compile(r"[\. ]+$")


@dataclass
class NamingResult:
    filename: str
    was_cleaned: bool
    cleaned_fields: dict[str, str]


def sanitize_component(value: str, default: str = "__待复核__") -> tuple[str, bool]:
    text = (value or "").strip()
    if not text:
        return default, True

    replaced = ILLEGAL_CHARS_RE.sub("_", text)
    replaced = MULTI_UNDERSCORE_RE.sub("_", replaced).strip("_")
    replaced = TRAILING_DOT_SPACE_RE.sub("", replaced)
    if not replaced:
        replaced = default
    return replaced, replaced != text


def build_filename(consultant: str, company_name: str, business: str, lang: str) -> NamingResult:
    c1, ch1 = sanitize_component(consultant)
    c2, ch2 = sanitize_component(company_name)
    c3, ch3 = sanitize_component(business)

    filename = f"{c1}_{c2}_{c3}_{lang}.pdf"
    cleaned = {"consultant": c1, "company_name": c2, "business": c3}
    return NamingResult(filename=filename, was_cleaned=(ch1 or ch2 or ch3), cleaned_fields=cleaned)
