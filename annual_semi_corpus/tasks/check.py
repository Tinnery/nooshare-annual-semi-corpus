"""Check task: orchestrates PG query, RustFS listing, and pure comparison.

This task coordinates the application-level workflow for the `check` command.
It calls outbound adapters (PG, RustFS) and pure computation units (core.compare_keys),
returning the business result. The CLI layer handles parameter parsing, validation,
output formatting, and exit status mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from annual_semi_corpus.adapters import list_published_keys, query_expected_from_pub_date
from annual_semi_corpus.core import CheckResult, ExpectedEntry, compare_keys


@dataclass(frozen=True)
class CheckOutcome:
    """Task 产出：比对结果 + 期望字典 + 是否启用日期过滤。

    CLI 层消费此对象做输出格式化和报告生成。
    """

    result: CheckResult
    expected: dict[str, ExpectedEntry]
    has_pub_date_filter: bool


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
    """执行 corpus check 用例。

    编排步骤：
    1. 从 PG ju.pub_date 查询期望 key
    2. 从 RustFS published/ 列举实际 key
    3. 用 core.compare_keys 做纯集合比对

    日期过滤时孤儿计数不适用（对象 Key 不含 pub_date），由 has_pub_date_filter 标记。
    """
    expected = query_expected_from_pub_date(dsn, "ju", prefix, year_min, year_max, limit)
    full_keys = list_published_keys(endpoint, access_key, secret_key, bucket, prefix)

    has_pub_date_filter = year_min is not None or year_max is not None
    result = compare_keys(set(expected), full_keys, report_orphans=not has_pub_date_filter)

    return CheckOutcome(result=result, expected=expected, has_pub_date_filter=has_pub_date_filter)
