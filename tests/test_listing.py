from datetime import date

from scraper.listing import extract_candidates_from_blocks


def test_listing_filter_sort_and_limit() -> None:
    blocks = [
        {
            "row_text": "2024-01-20\n上海万怡医学科技股份有限公司\nMulti-Files",
            "link_text": "Multi-Files",
            "href": "https://example.com/a",
        },
        {
            "row_text": "2024-01-05\n乙公司\n多档案",
            "link_text": "多档案",
            "href": "https://example.com/b",
        },
        {
            "row_text": "2023-12-30\n过早公司\nMulti-Files",
            "link_text": "Multi-Files",
            "href": "https://example.com/c",
        },
        {
            "row_text": "2024-02-01\n非目标公司\nSingle File",
            "link_text": "Prospectus",
            "href": "https://example.com/d",
        },
    ]
    results = extract_candidates_from_blocks(
        blocks,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        limit=1,
    )
    assert len(results) == 1
    assert results[0].company_name_raw == "乙公司"
    assert results[0].filing_date.isoformat() == "2024-01-05"
