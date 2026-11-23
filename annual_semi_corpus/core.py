"""Pure computation and document inspection for corpus check."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_PERIOD_RE = re.compile(r"^(\d{4})\s*([qh])\s*([1-4])$", re.IGNORECASE)

_STUB_PATTERNS = (
    re.compile(r"公告内容详见.*附件"),
    re.compile(r"详见.*PDF", re.IGNORECASE),
    re.compile(r"全文见附件"),
    re.compile(r"请见附件"),
    re.compile(r"具体内容见附件"),
)
_STRONG_TRUNCATION_PATTERNS = (
    re.compile(r"document\.write", re.IGNORECASE),
    re.compile(r"查看完整公告"),
)
_WEAK_TRUNCATION_PATTERNS = (
    re.compile(r"（未完）"),
    re.compile(r"未完待续"),
    re.compile(r"\(未完\)"),
)
_ERROR_PAGE_PATTERN = re.compile(
    r"^(?:404(?: Not Found)?|403 Forbidden|AccessDenied|NoSuchKey|"
    r"Internal Server Error|Service Unavailable)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_REPORT_IDENTITY_PATTERNS = (
    re.compile(
        r"(?P<year>19\d{2}|20\d{2})\s*年\s*"
        r"(?P<kind>半年度报告|半年报|年度报告|年报)"
    ),
    re.compile(
        r"(?P<year>[零〇○一二三四五六七八九]{4})\s*年\s*"
        r"(?P<kind>半年度报告|半年报|年度报告|年报)"
    ),
)
_CHINESE_DIGITS = {
    "零": "0", "〇": "0", "○": "0",
    "一": "1", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
}
_STOCK_CODE_PATTERN = re.compile(r"(?:股票代码|证券代码)\s*[：:]?\s*(\d{6})")
_TERMINAL_PATTERNS = ("备查文件目录", "审计报告", "财务报表")
_TERMINAL_MERGED = "审计报告及财务报表"


@dataclass(frozen=True)
class ExpectedEntry:
    """Expected report slot derived from ju.pub_date."""

    code: str
    key: str
    year: Optional[int] = None
    period: Optional[int] = None


@dataclass(frozen=True)
class CheckResult:
    """Read-only comparison result."""

    expected_count: int
    actual_count: int
    missing: tuple[str, ...]
    orphans: tuple[str, ...]


@dataclass(frozen=True)
class ContentFinding:
    """One actionable finding for a published Markdown object."""

    key: str
    rule: str
    severity: str
    detail: str


@dataclass(frozen=True)
class MarkdownInspection:
    """Result of checking one object's bytes."""

    readable: bool
    year_verified: bool
    findings: tuple[ContentFinding, ...]


@dataclass(frozen=True)
class ContentCheckResult:
    """Aggregated content checks from one check invocation."""

    attempted_count: int
    readable_count: int
    clean_count: int
    year_unverified_count: int
    rule_counts: dict[str, int]
    severity_counts: dict[str, int]
    findings: tuple[ContentFinding, ...]


def period_to_slot(period: str) -> Optional[tuple[int, int]]:
    """Convert pub_date period vocabulary to (report year, published period)."""
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
    if number == 1:
        return year, 2
    if number == 2:
        return year, 4
    return None


def build_md_key(code: str, year: int, period: int, prefix: str = "published/") -> str:
    """Build the published Markdown object key."""
    base = prefix if prefix.endswith("/") else prefix + "/"
    return f"{base}{code}/{code}_{year}_{period}.md"


def compare_keys(
    expected: set[str], actual: set[str], *, report_orphans: bool = True
) -> CheckResult:
    """Compare expected and actual object keys.

    With a pub_date filter, actual_count means expected keys found in the full
    object listing. Orphan classification is omitted because keys do not carry
    pub_date.
    """
    missing = tuple(sorted(expected - actual))
    matched = expected & actual
    orphans = tuple(sorted(actual - expected)) if report_orphans else ()
    return CheckResult(
        expected_count=len(expected),
        actual_count=len(actual) if report_orphans else len(matched),
        missing=missing,
        orphans=orphans,
    )


def _report_identity(text: str) -> tuple[int, int] | None:
    """Find a report year/type in the first 5,000 characters."""
    head = text[:5000]
    candidates: list[tuple[int, int, int]] = []
    for position, line in enumerate(head.splitlines()):
        for pattern in _REPORT_IDENTITY_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            raw_year = match.group("year")
            if raw_year[0].isdigit():
                year = int(raw_year)
            else:
                digits = "".join(_CHINESE_DIGITS.get(char, "") for char in raw_year)
                if len(digits) != 4:
                    continue
                year = int(digits)
            if not 1990 <= year <= 2100:
                continue
            kind = 2 if match.group("kind").startswith(("半年度", "半年")) else 4
            is_heading = line.lstrip().startswith("#")
            candidates.append((0 if is_heading else 1, position, year * 10 + kind))
    if not candidates:
        return None
    _, _, encoded = min(candidates)
    return encoded // 10, encoded % 10


def _terminal_presence(text: str) -> set[str]:
    present = {marker for marker in _TERMINAL_PATTERNS if marker in text}
    if _TERMINAL_MERGED in text:
        present.update(("审计报告", "财务报表"))
    return present


def inspect_markdown(key: str, entry: ExpectedEntry, data: bytes) -> MarkdownInspection:
    """Inspect one published Markdown byte sequence using conservative rules.

    Hard findings are limited to objectively malformed or contradictory
    content. Annual-report terminal-section checks are heuristic signals.
    """
    findings: list[ContentFinding] = []

    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return MarkdownInspection(
            readable=False,
            year_verified=False,
            findings=(ContentFinding(key, "invalid_utf8", "error", "对象内容不是有效 UTF-8"),),
        )

    def add(rule: str, severity: str, detail: str) -> None:
        findings.append(ContentFinding(key, rule, severity, detail))

    if not text:
        add("empty", "error", "Markdown 内容为空")
        return MarkdownInspection(True, False, tuple(findings))

    if len(text) < 100:
        add("too_short", "error", f"正文只有 {len(text)} 个字符，少于上游基础质检阈值 100")

    head = text[:2000]
    if any(pattern.search(head) for pattern in _STUB_PATTERNS):
        add("stub_content", "error", "正文开头包含附件占位内容，未包含实际报告")

    if _ERROR_PAGE_PATTERN.search(head):
        add("error_page", "error", "正文开头匹配到明确的 HTTP/对象存储错误页面标记")

    if any(pattern.search(text) for pattern in _STRONG_TRUNCATION_PATTERNS):
        add("truncated", "error", "正文包含明确的网页预览或动态加载残留标记")
    else:
        tail = text[-5000:]
        if any(pattern.search(tail) for pattern in _WEAK_TRUNCATION_PATTERNS):
            add("truncated", "error", "文档尾部包含未完或未完待续标记")

    identity = _report_identity(text)
    year_verified = identity is not None
    if identity is not None:
        content_year, content_period = identity
        if entry.year is not None and content_year != entry.year:
            add(
                "year_mismatch",
                "error",
                f"正文报告年度 {content_year} 与对象报告年度 {entry.year} 不一致",
            )
        if entry.period is not None and content_period != entry.period:
            expected_name = "半年报" if entry.period == 2 else "年报"
            content_name = "半年报" if content_period == 2 else "年报"
            add(
                "period_mismatch",
                "error",
                f"正文识别为{content_name}，对象 Key 对应{expected_name}",
            )

    code_matches = set(_STOCK_CODE_PATTERN.findall(text[:5000]))
    if len(code_matches) == 1:
        content_code = next(iter(code_matches))
        if content_code != entry.code:
            add(
                "stock_code_mismatch",
                "error",
                f"正文证券代码 {content_code} 与对象代码 {entry.code} 不一致",
            )

    if entry.period == 4:
        full_present = _terminal_presence(text)
        tail_present = _terminal_presence(text[-5000:])
        missing_full = [item for item in _TERMINAL_PATTERNS if item not in full_present]
        missing_tail = [item for item in _TERMINAL_PATTERNS if item not in tail_present]
        if missing_full:
            add(
                "annual_terminal_missing",
                "suspect",
                "年报全文未识别到尾部结构锚点：" + "、".join(missing_full),
            )
        elif missing_tail:
            add(
                "annual_tail_drift",
                "advisory",
                "年报尾部 5,000 字符未覆盖全部结构锚点，可能存在章节位置漂移",
            )

    return MarkdownInspection(True, year_verified, tuple(findings))
