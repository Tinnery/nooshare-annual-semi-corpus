"""CLI for nooshare-annual-semi-corpus."""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import typer

app = typer.Typer(
    help="Independent registry and quality management for the A-share annual and semi-annual Markdown corpus.",
    add_completion=False,
)


@app.command()
def inventory(
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source directory or pattern to scan"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output path for inventory manifest"),
):
    """Scan actual Markdown files and build corpus inventory."""
    if source:
        typer.echo(f"Scanning source: {source}")
    if output:
        typer.echo(f"Output path: {output}")
    typer.echo("inventory: not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def assess(
    inventory_path: Optional[str] = typer.Option(None, "--inventory", "-i", help="Path to inventory manifest"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output path for assessment results"),
):
    """Perform quality assessment on specified inventory."""
    if inventory_path:
        typer.echo(f"Assessing inventory: {inventory_path}")
    if output:
        typer.echo(f"Output path: {output}")
    typer.echo("assess: not yet implemented")
    raise typer.Exit(code=0)


@app.command()
def diff(
    before: str = typer.Argument(..., help="First inventory or assessment to compare"),
    after: str = typer.Argument(..., help="Second inventory or assessment to compare"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output path for diff results"),
):
    """Compare changes between two corpus inventories or quality assessments."""
    typer.echo(f"Comparing: {before} vs {after}")
    if output:
        typer.echo(f"Output path: {output}")
    typer.echo("diff: not yet implemented")
    raise typer.Exit(code=0)


# ---------------------------------------------------------------------------
# check：只读完整性巡检
#
# 只读语义：仅执行 SELECT / list_objects_v2；不写 PG、不 put/delete 对象。
# key 映射（RustFS published 契约）：
#   期望槽位 (code, year, period) -> published/{code}/{code}_{year}_{period}.md
#   其中 period 为半年报=2 / 年报=4，来自 ju.pub_date.period 词法解析。
# ---------------------------------------------------------------------------

_SAFE_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PERIOD_RE = re.compile(r"^(\d{4})\s*([qh])\s*([1-4])$", re.IGNORECASE)


@dataclass(frozen=True)
class ExpectedEntry:
    """一个期望条目。

    ju 模式：year/period 来自 period 词法，key 为完整 md 对象键；
    public 模式：只有 code（无 pub dates），key 为 published/{code}/ 前缀。
    """

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


def project_actual_keys(keys: set[str], prefix: str, by_code: bool) -> set[str]:
    """public 模式把完整 key 折叠为 published/{code}/ 前缀，以便同维比较。"""
    if not by_code:
        return set(keys)
    base = prefix if prefix.endswith("/") else prefix + "/"
    projected: set[str] = set()
    for key in keys:
        if not key.startswith(base):
            continue
        code = key[len(base):].split("/", 1)[0]
        if code:
            projected.add(f"{base}{code}/")
    return projected


def _build_year_clause(column: str, year_min: Optional[int], year_max: Optional[int]) -> tuple[str, list[Any]]:
    """按 pub_date 年份构造 WHERE 片段与参数（参数化，防注入）。"""
    clauses: list[str] = []
    params: list[Any] = []
    if year_min is not None:
        clauses.append(f"EXTRACT(YEAR FROM {column}) >= %s")
        params.append(year_min)
    if year_max is not None:
        clauses.append(f"EXTRACT(YEAR FROM {column}) <= %s")
        params.append(year_max)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _fetch_rows(dsn: str, sql: str, params: list[Any], source: str) -> list[tuple[Any, ...]]:
    """统一只读取数入口：会话级 read_only=True，杜绝误写生产库。"""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("缺少 psycopg 依赖，请先安装：psycopg[binary]>=3.1") from exc
    try:
        with psycopg.connect(dsn) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
    except Exception as exc:
        # 不回显 dsn（可能含凭据），只报异常类型与消息。
        raise RuntimeError(f"PG 查询失败（{source}）：{type(exc).__name__}: {exc}") from exc


def query_expected_from_pub_date(
    dsn: str,
    schema: str,
    prefix: str,
    year_min: Optional[int],
    year_max: Optional[int],
    limit: Optional[int],
) -> dict[str, ExpectedEntry]:
    """只读查询 {schema}.pub_date，返回期望 key -> ExpectedEntry。"""
    if not _SAFE_SCHEMA_RE.match(schema):
        raise ValueError(f"非法 schema 标识：{schema!r}")

    inner_where, inner_params = _build_year_clause("pub_date", year_min, year_max)
    outer_where, outer_params = _build_year_clause("p.pub_date", year_min, year_max)
    # --limit 限制的是去重后的 code 数（调试用），故先收窄 code 再回表。
    limit_sql = " LIMIT %s" if limit is not None else ""
    limit_params: list[Any] = [limit] if limit is not None else []
    sql = (
        f'WITH codes AS (SELECT DISTINCT stock_code FROM "{schema}".pub_date'
        f"{inner_where} ORDER BY stock_code{limit_sql}) "
        f'SELECT p.stock_code, p.period FROM "{schema}".pub_date p '
        f"JOIN codes c ON c.stock_code = p.stock_code{outer_where}"
    )
    rows = _fetch_rows(dsn, sql, inner_params + limit_params + outer_params, f"{schema}.pub_date")

    expected: dict[str, ExpectedEntry] = {}
    for stock_code, period_value in rows:
        code = str(stock_code).strip()
        if not code:
            continue
        slot = period_to_slot(str(period_value))
        if slot is None:
            # q1/q3 或无法解析的 period 没有 published 对象，跳过以免假缺失。
            continue
        year, period_num = slot
        key = build_md_key(code, year, period_num, prefix)
        expected[key] = ExpectedEntry(code=code, key=key, year=year, period=period_num)
    return expected


def query_expected_from_canonical_symbol(
    dsn: str,
    prefix: str,
    limit: Optional[int],
) -> dict[str, ExpectedEntry]:
    """只读查询 public.canonical_symbol 的 code 列表，期望键为 published/{code}/。"""
    sql = (
        "SELECT DISTINCT code FROM public.canonical_symbol "
        "WHERE code IS NOT NULL ORDER BY code"
    )
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    rows = _fetch_rows(dsn, sql, params, "public.canonical_symbol")

    base = prefix if prefix.endswith("/") else prefix + "/"
    expected: dict[str, ExpectedEntry] = {}
    for (code_value,) in rows:
        code = str(code_value).strip()
        if not code:
            continue
        key = f"{base}{code}/"
        expected[key] = ExpectedEntry(code=code, key=key)
    return expected


def list_published_keys(
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    prefix: str,
) -> set[str]:
    """只读列举 RustFS prefix 下所有 key（list_objects_v2 自动翻页）。"""
    try:
        import boto3
        import botocore.config
    except ImportError as exc:
        raise RuntimeError("缺少 boto3 依赖，请先安装：boto3>=1.34") from exc

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=botocore.config.Config(
            proxies={"http": None, "https": None},  # 本地/内网 RustFS 不走代理
        ),
    )
    keys: set[str] = set()
    token: Optional[str] = None
    try:
        while True:
            kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                if item.get("Key"):
                    keys.add(item["Key"])
            if not response.get("IsTruncated"):
                break
            next_token = response.get("NextContinuationToken")
            if not next_token:
                break
            token = next_token
    except Exception as exc:
        raise RuntimeError(
            f"RustFS 列举失败（bucket={bucket}, prefix={prefix}）：{type(exc).__name__}: {exc}"
        ) from exc
    return keys


def _report_row(entry: Optional[ExpectedEntry], key: str, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "code": entry.code if entry else "",
        "year": entry.year if entry and entry.year is not None else "",
        "period": entry.period if entry and entry.period is not None else "",
        "key": key,
    }


def write_report(
    path: str,
    result: CheckResult,
    expected: dict[str, ExpectedEntry],
    schema: str,
    bucket: str,
    prefix: str,
) -> None:
    """按扩展名写出 .json / .csv 清单；只写本地文件，不碰 PG / RustFS。"""
    target = Path(path)
    missing_rows = [_report_row(expected.get(key), key, "missing") for key in result.missing]
    orphan_rows = [_report_row(None, key, "orphan") for key in result.orphans]
    if target.suffix.lower() == ".json":
        payload = {
            "schema": schema,
            "bucket": bucket,
            "prefix": prefix,
            "summary": {
                "expected": result.expected_count,
                "actual": result.actual_count,
                "missing": len(result.missing),
                "orphans": len(result.orphans),
            },
            "missing": missing_rows,
            "orphans": orphan_rows,
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif target.suffix.lower() == ".csv":
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["kind", "code", "year", "period", "key"]
            )
            writer.writeheader()
            writer.writerows(missing_rows)
            writer.writerows(orphan_rows)
    else:
        raise ValueError(f"--output 仅支持 .json / .csv，收到：{target.suffix or '(无扩展名)'}")


@app.command()
def check(
    dsn: Optional[str] = typer.Option(None, "--dsn", help="PG 连接串；默认读环境变量 DATABASE_URL"),
    schema: str = typer.Option("ju", "--schema", help="期望清单所在 schema：ju 或 public"),
    bucket: Optional[str] = typer.Option(
        None, "--bucket", help="RustFS bucket；默认 CORPUS_RUSTFS_BUCKET 或 nooshare-dev"
    ),
    endpoint: Optional[str] = typer.Option(
        None, "--endpoint", help="S3 endpoint；默认读环境变量 RUSTFS_ENDPOINT_URL"
    ),
    prefix: str = typer.Option("published/", "--prefix", help="md 对象前缀"),
    year_min: Optional[int] = typer.Option(None, "--year-min", help="按 pub_date 年份过滤：下界（含）"),
    year_max: Optional[int] = typer.Option(None, "--year-max", help="按 pub_date 年份过滤：上界（含）"),
    limit: Optional[int] = typer.Option(None, "--limit", help="只检查前 N 个 code（调试用）"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="缺失清单输出路径（.json / .csv）；默认仅打印摘要"
    ),
) -> None:
    """只读检查 PG 期望清单与 RustFS published/ md 库的完整性。

    只读：仅 SELECT / list_objects_v2，不写 PG、不 put/delete 对象。
    key 映射：(code, year, period) -> published/{code}/{code}_{year}_{period}.md。
    """
    resolved_dsn = dsn or os.environ.get("DATABASE_URL", "")
    if not resolved_dsn:
        typer.echo("错误：缺少 PG 连接串，请设置 DATABASE_URL 或使用 --dsn。", err=True)
        raise typer.Exit(code=1)

    resolved_endpoint = endpoint or os.environ.get("RUSTFS_ENDPOINT_URL", "")
    if not resolved_endpoint:
        typer.echo("错误：缺少 S3 endpoint，请设置 RUSTFS_ENDPOINT_URL 或使用 --endpoint。", err=True)
        raise typer.Exit(code=1)

    access_key = os.environ.get("RUSTFS_ACCESS_KEY", "")
    secret_key = os.environ.get("RUSTFS_SECRET_KEY", "")
    if not access_key or not secret_key:
        typer.echo(
            "错误：缺少 RustFS 凭据，请设置 RUSTFS_ACCESS_KEY / RUSTFS_SECRET_KEY（本命令不打印密钥）。",
            err=True,
        )
        raise typer.Exit(code=1)

    resolved_bucket = bucket or os.environ.get("CORPUS_RUSTFS_BUCKET", "") or "nooshare-dev"
    if year_min is not None and year_max is not None and year_min > year_max:
        typer.echo("错误：--year-min 不能大于 --year-max。", err=True)
        raise typer.Exit(code=1)
    if limit is not None and limit <= 0:
        typer.echo("错误：--limit 必须为正整数。", err=True)
        raise typer.Exit(code=1)

    by_code = schema == "public"
    try:
        if by_code:
            expected = query_expected_from_canonical_symbol(resolved_dsn, prefix, limit)
        else:
            expected = query_expected_from_pub_date(
                resolved_dsn, schema, prefix, year_min, year_max, limit
            )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"错误：读取 PG 期望清单失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        full_keys = list_published_keys(
            resolved_endpoint, access_key, secret_key, resolved_bucket, prefix
        )
    except RuntimeError as exc:
        typer.echo(f"错误：读取 RustFS 清单失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    actual = project_actual_keys(full_keys, prefix, by_code)
    result = compare_keys(set(expected), actual)

    typer.echo("check 摘要")
    typer.echo(f"  schema     : {schema}")
    typer.echo(f"  bucket     : {resolved_bucket}")
    typer.echo(f"  prefix     : {prefix}")
    typer.echo(f"  期望对象数 : {result.expected_count}")
    typer.echo(f"  实有对象数 : {result.actual_count}")
    typer.echo(f"  缺失数     : {len(result.missing)}")
    typer.echo(f"  孤儿数     : {len(result.orphans)}")

    if result.missing:
        typer.echo("缺失样本（前 20）：")
        for key in result.missing[:20]:
            typer.echo(f"  - {key}")
        if len(result.missing) > 20:
            suffix = "（详见 --output）" if output else ""
            typer.echo(f"  ... 其余 {len(result.missing) - 20} 条{suffix}")
    else:
        typer.echo("缺失样本：无")

    if output:
        try:
            write_report(output, result, expected, schema, resolved_bucket, prefix)
        except (OSError, ValueError) as exc:
            typer.echo(f"错误：写出报告失败：{exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"报告已写出：{output}")

    raise typer.Exit(code=0)
