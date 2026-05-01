from scraper.company import _infer_business_from_text


def test_business_infer_biomed() -> None:
    sample = (
        "业务\n概览\n"
        "我们是一家处于临床阶段的生物技术公司，拥有多条候选药物管线。\n"
        "后文包含付款条款。"
    )
    assert _infer_business_from_text(sample) == "生物医药"


def test_business_infer_other_when_only_generic_overview() -> None:
    sample = "Business Overview\nOverview\nBusiness\n"
    assert _infer_business_from_text(sample) == "其他"
