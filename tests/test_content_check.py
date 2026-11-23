"""Pure Markdown content checks used by the unified CLI check."""

from annual_semi_corpus.core import ExpectedEntry, inspect_markdown, select_content_sample


def _entry(year=2023, period=4, code="000001"):
    return ExpectedEntry(
        code=code,
        key=f"published/{code}/{code}_{year}_{period}.md",
        year=year,
        period=period,
    )


def _annual_body(title="# 2023年年度报告"):
    return (
        title + "\n"
        + "公司经营情况与财务信息。" * 20 + "\n"
        + "备查文件目录\n审计报告\n财务报表\n"
    ).encode("utf-8")


def _rules(data, entry=None):
    result = inspect_markdown(
        entry.key if entry else _entry().key,
        entry or _entry(),
        data,
    )
    return {finding.rule: finding for finding in result.findings}


def test_valid_annual_report_passes_basic_content_rules():
    result = inspect_markdown(_entry().key, _entry(), _annual_body())
    assert result.readable
    assert result.year_verified
    assert result.findings == ()


def test_empty_document_is_reported():
    assert "empty" in _rules(b"")


def test_short_document_uses_upstream_100_character_threshold():
    assert "too_short" in _rules("# 2023年年度报告\n正文很短".encode())


def test_attachment_stub_is_reported():
    text = ("# 2023年年度报告\n公告内容详见本公告附件，请下载 PDF。" + "正文。" * 50).encode()
    assert "stub_content" in _rules(text)


def test_error_page_is_reported():
    text = ("404 Not Found\n" + "x" * 200).encode()
    assert "error_page" in _rules(text)


def test_explicit_truncation_marker_is_reported():
    text = ("# 2023年年度报告\n" + "正文。" * 50 + "\n未完待续").encode()
    assert "truncated" in _rules(text)


def test_report_year_mismatch_is_reported():
    entry = _entry(year=2022)
    result = _rules(_annual_body("# 2023年年度报告"), entry)
    assert "year_mismatch" in result


def test_chinese_report_year_is_recognized():
    text = _annual_body("# 二〇二三年年度报告")
    result = inspect_markdown(_entry().key, _entry(), text)
    assert result.year_verified
    assert result.findings == ()


def test_report_period_mismatch_is_reported():
    entry = _entry(period=4)
    text = _annual_body("# 2023年半年度报告")
    assert "period_mismatch" in _rules(text, entry)


def test_explicit_stock_code_mismatch_is_reported():
    text = ("# 2023年年度报告\n股票代码：600000\n" + "正文。" * 50
            + "\n备查文件目录\n审计报告\n财务报表\n").encode()
    assert "stock_code_mismatch" in _rules(text)


def test_single_nian_year_title_is_recognized():
    """真实语料常见单年字写法（如 "# 2025年度报告"）应识别为年报身份。"""
    text = _annual_body("# 2025年度报告")
    result = inspect_markdown(_entry(year=2025).key, _entry(year=2025), text)
    assert result.year_verified
    assert "year_mismatch" not in {f.rule for f in result.findings}


def test_single_nian_year_mismatch_is_reported():
    entry = _entry(year=2023)
    text = _annual_body("# 2025年度报告")
    assert "year_mismatch" in _rules(text, entry)


def test_reference_line_is_not_treated_as_identity():
    """正文只有引用句式（参见…年报）时不应把引用年度当报告身份。"""
    entry = _entry(year=2020, period=2)
    text = ("第一节 重要提示\n公司注册地址报告期无变化，具体可参见2019年年报。\n"
            + "正文。" * 50).encode()
    result = inspect_markdown(entry.key, entry, text)
    assert not result.year_verified
    assert not any(f.rule in ("year_mismatch", "period_mismatch") for f in result.findings)


def test_genuine_year_mismatch_survives_reference_filter():
    """行首身份行（公司名+年份，无引用词）识别的错位仍然报告。"""
    entry = _entry(year=2020, period=4)
    text = _annual_body("大连橡胶塑料机械股份有限公司2010年半年度报告")
    assert "year_mismatch" in _rules(text, entry)
    assert "period_mismatch" in _rules(text, entry)


def test_company_code_variant_and_referenced_codes_are_not_reported():
    """封面"公司代码：600400"识别为本公司代码；释义表"曾用名…002243.SZ"不参与比对。"""
    entry = _entry(year=2021, period=2, code="600400")
    text = ("# 公司代码：600400 公司简称：红豆股份\n"
            "# 2021年半年度报告\n"
            "| 力合科创 | 指 | 深圳市力合科创股份有限公司（曾用名\"深圳市通产丽星股份有限公司\"，"
            "股票代码：002243.SZ） |\n"
            + "正文。" * 50).encode()
    result = inspect_markdown(entry.key, entry, text)
    assert not any(f.rule == "stock_code_mismatch" for f in result.findings)


def test_controlling_shareholder_code_reference_is_not_reported():
    """标题无代码、正文唯一代码来自控股股东释义时不应误报。"""
    entry = _entry(year=2024, period=2, code="002167")
    text = ("# 广东某科技股份有限公司\n"
            "# 2024年半年度报告\n"
            "| 龙佰集团 | 指 | 龙佰集团股份有限公司（股票代码：002601），"
            "为广东某科技股份有限公司控股股东 |\n"
            + "正文。" * 50).encode()
    result = inspect_markdown(entry.key, entry, text)
    assert not any(f.rule == "stock_code_mismatch" for f in result.findings)


def test_foreign_exchange_suffix_code_is_not_reported():
    """客户公司的境外交易所代码（.KS 后缀）不参与证券代码比对。"""
    entry = _entry(year=2024, period=2, code="301567")
    text = ("# 某精密科技股份有限公司\n"
            "# 2024年半年度报告\n"
            "三星电机株式会社（Samsung Electro-Mechanics，股票代码：009150.KS），系公司客户\n"
            + "正文。" * 50).encode()
    result = inspect_markdown(entry.key, entry, text)
    assert not any(f.rule == "stock_code_mismatch" for f in result.findings)


def test_genuine_wrong_cover_code_is_still_reported():
    """封面"公司代码"变体识别出的真实错码仍然报告。"""
    entry = _entry(year=2023, period=4, code="002167")
    text = ("# 公司代码：002999 公司简称：错误主体\n"
            "# 2023年年度报告\n"
            + "正文。" * 50 + "\n备查文件目录\n审计报告\n财务报表\n").encode()
    assert "stock_code_mismatch" in _rules(text, entry)


def test_annual_missing_terminal_sections_is_suspect_not_hard_failure():
    text = ("# 2023年年度报告\n" + "正文。" * 100).encode()
    finding = _rules(text)["annual_terminal_missing"]
    assert finding.severity == "suspect"


def test_annual_tail_drift_is_advisory():
    text = (
        "# 2023年年度报告\n备查文件目录\n审计报告\n财务报表\n"
        + "正文。" * 2000
    ).encode()
    finding = _rules(text)["annual_tail_drift"]
    assert finding.severity == "advisory"


def test_semi_annual_does_not_apply_annual_terminal_rule():
    entry = _entry(period=2)
    text = ("# 2023年半年度报告\n" + "正文。" * 100).encode()
    result = inspect_markdown(entry.key, entry, text)
    assert not any(item.rule.startswith("annual_") for item in result.findings)


def test_invalid_utf8_is_reported_without_text_scanning():
    result = inspect_markdown(_entry().key, _entry(), b"\xff\xfe\xfa")
    assert not result.readable
    assert [finding.rule for finding in result.findings] == ["invalid_utf8"]

def test_content_sample_is_deterministic_and_stratified_by_report_year_and_period():
    expected = {}
    keys = []
    for year, period in ((2022, 4), (2023, 2), (2023, 4)):
        for index in range(5):
            code = f"{index + 1:06d}"
            key = f"published/{code}/{code}_{year}_{period}.md"
            expected[key] = ExpectedEntry(code, key, year, period)
            keys.append(key)

    first = select_content_sample(expected, keys, per_group=2)
    second = select_content_sample(expected, keys, per_group=2)

    assert first == second
    assert len(first) == 6
    assert len(set((expected[key].year, expected[key].period) for key in first)) == 3
    for group in ((2022, 4), (2023, 2), (2023, 4)):
        assert sum((expected[key].year, expected[key].period) == group for key in first) == 2


