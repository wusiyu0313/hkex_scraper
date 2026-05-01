from datetime import date

from scraper import listing


def test_collect_candidates_from_json_filters_and_builds_multi_files(monkeypatch) -> None:
    en_payload = {
        "app": [
            {
                "id": 1,
                "d": "29/04/2026",
                "a": "Eccogene Inc. - B",
                "ls": [
                    {"nS2": "Multi-Files", "u2": "sehk/2026/108485/2026042906029_c.htm"},
                ],
            },
            {
                "id": 2,
                "d": "30/03/2026",
                "a": "OutOfRange Co",
                "ls": [{"nS2": "Multi-Files", "u2": "sehk/2026/999/202603300001_c.htm"}],
            },
        ]
    }
    zh_payload = {
        "app": [
            {"id": 1, "a": "依科基因有限公司"},
            {"id": 2, "a": "超范围公司"},
        ]
    }

    def fake_fetch(url: str):
        if "_c.json" in url:
            return zh_payload
        return en_payload

    monkeypatch.setattr(listing, "_fetch_json", fake_fetch)

    items = listing.collect_candidates_from_json(
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        limit=10,
    )
    assert len(items) == 1
    assert items[0].company_name_raw == "依科基因有限公司"
    assert items[0].multi_files_url == "https://www1.hkexnews.hk/app/sehk/2026/108485/2026042906029_c.htm"
    assert items[0].multi_files_url_en == "https://www1.hkexnews.hk/app/sehk/2026/108485/2026042906029_c.htm"
