"""Integration of coverage and Markdown inspection within one check use case."""

from annual_semi_corpus.core import ExpectedEntry


def test_run_check_reads_only_expected_objects_that_exist(monkeypatch):
    from annual_semi_corpus.tasks import check

    expected_key = "published/000001/000001_2023_4.md"
    missing_key = "published/000002/000002_2023_4.md"
    expected = {
        expected_key: ExpectedEntry("000001", expected_key, 2023, 4),
        missing_key: ExpectedEntry("000002", missing_key, 2023, 4),
    }
    monkeypatch.setattr(check, "query_expected_from_pub_date", lambda *a, **k: expected)
    monkeypatch.setattr(check, "list_published_keys", lambda *a, **k: {expected_key: 2048})

    data = (
        "# 2023年年度报告\n" + "正文。" * 50
        + "\n备查文件目录\n审计报告\n财务报表\n"
    ).encode()
    requested = []

    def read_objects(*args, **kwargs):
        requested.extend(args[-1])
        yield expected_key, data, None

    monkeypatch.setattr(check, "read_published_objects", read_objects)
    outcome = check.run_check(
        dsn="unused",
        endpoint="unused",
        access_key="unused",
        secret_key="unused",
        bucket="unused",
        prefix="published/",
        year_min=None,
        year_max=None,
        limit=None,
    )

    assert requested == [expected_key]
    assert outcome.result.missing == (missing_key,)
    assert outcome.content.attempted_count == 1
    assert outcome.content.readable_count == 1
    assert outcome.content.clean_count == 1
    assert outcome.content.findings == ()


def test_run_check_reports_object_read_errors(monkeypatch):
    from annual_semi_corpus.tasks import check

    key = "published/000001/000001_2023_4.md"
    expected = {key: ExpectedEntry("000001", key, 2023, 4)}
    monkeypatch.setattr(check, "query_expected_from_pub_date", lambda *a, **k: expected)
    monkeypatch.setattr(check, "list_published_keys", lambda *a, **k: {key: 2048})
    monkeypatch.setattr(
        check, "read_published_objects",
        lambda *a, **k: iter([(key, None, "EndpointConnectionError")]),
    )
    outcome = check.run_check(
        dsn="unused",
        endpoint="unused",
        access_key="unused",
        secret_key="unused",
        bucket="unused",
        prefix="published/",
        year_min=None,
        year_max=None,
        limit=None,
    )
    assert outcome.content.severity_counts["execution"] == 1
    assert outcome.content.findings[0].rule == "read_error"

def test_run_check_checks_all_zero_sizes_and_reads_only_stratified_sample(monkeypatch):
    from annual_semi_corpus.tasks import check

    expected = {}
    sizes = {}
    for index in range(12):
        code = f"{index + 1:06d}"
        key = f"published/{code}/{code}_2023_4.md"
        expected[key] = ExpectedEntry(code, key, 2023, 4)
        sizes[key] = 0 if index == 0 else 2048

    monkeypatch.setattr(check, "query_expected_from_pub_date", lambda *a, **k: expected)
    monkeypatch.setattr(check, "list_published_objects", lambda *a, **k: sizes)

    requested = []

    def read_objects(*args, **kwargs):
        requested.extend(args[-1])
        for key in args[-1]:
            body = (
                "# 2023年年度报告\n" + "正文。" * 50
                + "\n备查文件目录\n审计报告\n财务报表\n"
            ).encode()
            yield key, body, None

    monkeypatch.setattr(check, "read_published_objects", read_objects)
    outcome = check.run_check(
        dsn="unused",
        endpoint="unused",
        access_key="unused",
        secret_key="unused",
        bucket="unused",
        prefix="published/",
        year_min=None,
        year_max=None,
        limit=None,
    )

    assert outcome.content.matched_count == 12
    assert outcome.content.sampled_count == 10
    assert outcome.content.sample_per_group == 10
    assert len(requested) == 10
    assert all(sizes[key] > 0 for key in requested)
    assert outcome.content.rule_counts["empty"] == 1
    assert outcome.content.severity_counts["error"] == 1


