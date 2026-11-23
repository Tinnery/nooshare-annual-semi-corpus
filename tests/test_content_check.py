"""Pure Markdown content checks used by the unified CLI check."""

from annual_semi_corpus.core import ExpectedEntry, inspect_markdown


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


def test_annual_missing_terminal_sections_is_suspect_not_hard_failure():
    text = ("# 2023年年度报告\n" + "正文。" * 100).encode()
    finding = _rules(text)["annual_terminal_missing"]
    assert finding.severity == "suspect"


def test_annual_tail_drift_is_advisory():
    text = (
        "# 2023年年度报告\n备查文件目录\n审计报告\n财务报表\n"
        + "正文。" * 100
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
