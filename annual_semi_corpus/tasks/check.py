"""Application use case for the unified corpus check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from annual_semi_corpus.adapters import (
    list_published_objects,
    query_expected_from_pub_date,
    read_published_objects,
)
from annual_semi_corpus.core import (
    CheckResult,
    ContentCheckResult,
    ContentFinding,
    ExpectedEntry,
    compare_keys,
    inspect_markdown,
    select_content_sample,
)


@dataclass(frozen=True)
class CheckOutcome:
    """Unified outcome: coverage and content results from one check."""

    result: CheckResult
    expected: dict[str, ExpectedEntry]
    has_pub_date_filter: bool
    content: ContentCheckResult


def run_check(
    *,
    dsn: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    prefix: str,
    year_min: Optional[int],
    year_max: Optional[int],
    limit: Optional[int],
) -> CheckOutcome:
    """Run full coverage/size checks plus stratified sample content checks."""
    expected = query_expected_from_pub_date(dsn, "ju", prefix, year_min, year_max, limit)
    object_sizes = list_published_objects(endpoint, access_key, secret_key, bucket, prefix)
    full_keys = set(object_sizes)

    has_pub_date_filter = year_min is not None or year_max is not None
    result = compare_keys(set(expected), full_keys, report_orphans=not has_pub_date_filter)

    rule_names = (
        "invalid_utf8",
        "empty",
        "too_short",
        "stub_content",
        "error_page",
        "truncated",
        "year_mismatch",
        "period_mismatch",
        "stock_code_mismatch",
        "annual_terminal_missing",
        "annual_tail_drift",
    )
    matched_keys = sorted(set(expected) & full_keys)
    empty_findings = [
        ContentFinding(key, "empty", "error", "RustFS 对象 Size 为 0 字节")
        for key in matched_keys
        if object_sizes.get(key) == 0
    ]
    sample_keys = select_content_sample(
        expected,
        [key for key in matched_keys if object_sizes.get(key) != 0],
        per_group=10,
    )
    sample_groups = {
        (expected[key].year, expected[key].period)
        for key in sample_keys
    }

    findings: list[ContentFinding] = list(empty_findings)
    severity_counts = {
        "error": len(empty_findings),
        "suspect": 0,
        "advisory": 0,
        "execution": 0,
    }
    rule_counts = {name: 0 for name in rule_names}
    rule_counts["empty"] = len(empty_findings)
    attempted = readable = clean = year_unverified = 0

    for key, data, read_error in read_published_objects(
        endpoint, access_key, secret_key, bucket, list(sample_keys)
    ):
        attempted += 1
        if read_error is not None:
            finding = ContentFinding(
                key, "read_error", "execution", f"对象 GET 失败（{read_error}）"
            )
            findings.append(finding)
            severity_counts["execution"] += 1
            continue

        assert data is not None
        inspection = inspect_markdown(key, expected[key], data)
        if inspection.readable:
            readable += 1
        if not inspection.year_verified:
            year_unverified += 1
        if not inspection.findings and inspection.year_verified:
            clean += 1
        for finding in inspection.findings:
            findings.append(finding)
            severity_counts[finding.severity] += 1
            if finding.rule in rule_counts:
                rule_counts[finding.rule] += 1

    findings.sort(key=lambda item: (item.key, item.rule))
    content = ContentCheckResult(
        matched_count=len(matched_keys),
        sampled_count=len(sample_keys),
        sample_per_group=10,
        sample_group_count=len(sample_groups),
        attempted_count=attempted,
        readable_count=readable,
        clean_count=clean,
        year_unverified_count=year_unverified,
        rule_counts=rule_counts,
        severity_counts=severity_counts,
        findings=tuple(findings),
    )
    return CheckOutcome(
        result=result,
        expected=expected,
        has_pub_date_filter=has_pub_date_filter,
        content=content,
    )
