from scraper.namer import build_filename


def test_namer_sanitize_invalid_chars() -> None:
    result = build_filename("沙利文", '公司A/测试:*?"<>|', "AI\\业务", "CN")
    assert result.filename == "沙利文_公司A_测试_AI_业务_CN.pdf"
    assert result.was_cleaned is True


def test_namer_placeholder_when_empty() -> None:
    result = build_filename("", "公司B", "", "EN")
    assert "__待复核__" in result.filename
    assert result.filename.endswith("_EN.pdf")
