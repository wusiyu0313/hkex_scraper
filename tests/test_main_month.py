from main import resolve_date_range


def test_resolve_date_range_month_january() -> None:
    config = {"month": "2024-01"}
    resolved = resolve_date_range(config)
    assert resolved["start_date"] == "2024-01-01"
    assert resolved["end_date"] == "2024-01-31"


def test_resolve_date_range_month_leap_feb() -> None:
    config = {"month": "2024-02"}
    resolved = resolve_date_range(config)
    assert resolved["start_date"] == "2024-02-01"
    assert resolved["end_date"] == "2024-02-29"


def test_resolve_date_range_invalid_month() -> None:
    try:
        resolve_date_range({"month": "2024/01"})
    except ValueError as exc:
        assert "YYYY-MM" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid month format")

