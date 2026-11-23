"""Pure computation Units for the corpus check command.

No network, filesystem or environment dependencies. Every function here is
deterministic and independently verifiable; external IO lives in adapters.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_PERIOD_RE = re.compile(r"^(\d{4})\s*([qh])\s*([1-4])$", re.IGNORECASE)


@dataclass(frozen=True)
class ExpectedEntry:
    """一个期望条目：year/period 来自 ju.pub_date.period 词法，key 为完整 md 对象键。"""

    code: str
    key: str
    year: Optional[int] = None
    period: Optional[int] = None


@dataclass(frozen=True)
class CheckResult:
    """只读比对结果（纯数据，便于测试）。"""

    expected_count: int
    actual_count: int
    missing: tuple[str, ...]
    orphans: tuple[str, ...]


def period_to_slot(period: str) -> Optional[tuple[int, int]]:
    """把 ju.pub_date.period 词法解析为 (报告年度, published period)。

    转换规则（写在明处，避免命名歧义）：
      - period 形如 ``2008q1`` / ``2018h1``（大小写不敏感，容许空格）；
      - published 文件名用 ``{code}_{year}_{period_num}.md``，period_num 仅 2/4：
          q2 / h1 -> 2（半年报），q4 / h2 -> 4（年报）；
      - q1 / q3 不产生 published 对象，返回 None 由调用方跳过，
        否则会把合法数据误报为大量「缺失」。
    """
    match = _PERIOD_RE.match(period.strip()) if isinstance(period, str) else None
    if not match:
        return None
    year = int(match.group(1))
    marker = match.group(2).lower()
    number = int(match.group(3))
    if marker == "q":
        if number == 2:
            return year, 2
        if number == 4:
            return year, 4
        return None
    # h 标记：h1 = 半年报(2)，h2 = 年报(4)；h3/h4 非法。
    if number == 1:
        return year, 2
    if number == 2:
        return year, 4
    return None


def build_md_key(code: str, year: int, period: int, prefix: str = "published/") -> str:
    """构造期望对象 key：``published/{code}/{code}_{year}_{period}.md``。"""
    base = prefix if prefix.endswith("/") else prefix + "/"
    return f"{base}{code}/{code}_{year}_{period}.md"


def compare_keys(expected: set[str], actual: set[str]) -> CheckResult:
    """集合比对：期望−实有=缺失，实有−期望=孤儿。纯函数，不访问外部系统。"""
    missing = tuple(sorted(expected - actual))
    orphans = tuple(sorted(actual - expected))
    return CheckResult(
        expected_count=len(expected),
        actual_count=len(actual),
        missing=missing,
        orphans=orphans,
    )
