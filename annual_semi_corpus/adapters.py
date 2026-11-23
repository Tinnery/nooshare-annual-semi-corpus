"""Outbound adapters for the corpus check command.

Each adapter owns exactly one external resource: PostgreSQL (read-only),
RustFS S3 (read-only listing and object reads), and the local report file. Heavy third-party
imports are lazy so ``--help`` and pure-function tests stay offline.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Optional

from annual_semi_corpus.core import CheckResult, ContentCheckResult, ExpectedEntry, build_md_key, period_to_slot

_SAFE_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# --- PostgreSQL adapter (read-only) -----------------------------------------


def _build_year_clause(
    column: str, year_min: Optional[int], year_max: Optional[int]
) -> tuple[str, list[Any]]:
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


def fetch_rows(dsn: str, sql: str, params: list[Any], source: str) -> list[tuple[Any, ...]]:
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
        # Fail closed: 第三方异常原文可能夹带 DSN / 连接参数，一律不回显。
        # 只保留固定错误分类 + 异常类型名；详细诊断留在受控本地环境。
        raise RuntimeError(f"PG 查询失败（{source}）：{type(exc).__name__}") from exc


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
    rows = fetch_rows(dsn, sql, inner_params + limit_params + outer_params, f"{schema}.pub_date")

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


# --- RustFS S3 adapter (read-only) ------------------------------------------


def list_published_objects(
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    prefix: str,
) -> dict[str, Optional[int]]:
    """只读列举 RustFS prefix 下的对象 Key 与 Size（list_objects_v2 自动翻页）。"""

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
    objects: dict[str, Optional[int]] = {}
    token: Optional[str] = None
    try:
        while True:
            kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                if item.get("Key"):
                    objects[item["Key"]] = item.get("Size")
            if not response.get("IsTruncated"):
                break
            next_token = response.get("NextContinuationToken")
            if not next_token:
                break
            token = next_token
    except Exception as exc:
        # Fail closed: botocore 异常原文可能夹带 endpoint / 请求细节，
        # 一律不回显。只保留固定分类 + 异常类型名（bucket/prefix 非凭据）。
        raise RuntimeError(
            f"RustFS 列举失败（bucket={bucket}, prefix={prefix}）：{type(exc).__name__}"
        ) from exc
    return objects


# --- Local report adapter ---------------------------------------------------


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
    content: Optional[ContentCheckResult] = None,
) -> None:
    """按扩展名写出 .json / .csv 清单；只写本地文件，不碰 PG / RustFS。"""
    target = Path(path)
    missing_rows = [_report_row(expected.get(key), key, "missing") for key in result.missing]
    orphan_rows = [_report_row(None, key, "orphan") for key in result.orphans]
    content_findings = []
    if content is not None:
        for finding in content.findings:
            entry = expected.get(finding.key)
            content_findings.append({
                "kind": finding.rule,
                "code": entry.code if entry else "",
                "year": entry.year if entry and entry.year is not None else "",
                "period": entry.period if entry and entry.period is not None else "",
                "key": finding.key,
                "severity": finding.severity,
                "reason": finding.detail,
            })
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
            "content": {
                "matched": content.matched_count if content else 0,
                "sampled": content.sampled_count if content else 0,
                "sample_per_group": content.sample_per_group if content else 0,
                "sample_group_count": content.sample_group_count if content else 0,
                "attempted": content.attempted_count if content else 0,
                "readable": content.readable_count if content else 0,
                "clean": content.clean_count if content else 0,
                "year_unverified": content.year_unverified_count if content else 0,
                "rule_counts": content.rule_counts if content else {},
                "severity_counts": content.severity_counts if content else {},
                "findings": content_findings,
            },
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif target.suffix.lower() == ".csv":
        with target.open("w", newline="", encoding="utf-8") as handle:
            fields = ["kind", "code", "year", "period", "key", "severity", "reason"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(missing_rows)
            writer.writerows(orphan_rows)
            writer.writerows(content_findings)
    else:
        raise ValueError(f"--output 仅支持 .json / .csv，收到：{target.suffix or '(无扩展名)'}")


# --- RustFS object reader ----------------------------------------------------


def read_published_objects(
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    keys: list[str],
    *,
    workers: int = 4,
):
    """Yield (key, bytes, error_type) with bounded concurrent GET requests.

    The S3 client is shared across a small worker pool. At most twice the
    worker count is in flight, avoiding one Future per object for large corpora.
    Error messages are reduced to exception type names before leaving the adapter.
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    try:
        import boto3
        import botocore.config
    except ImportError as exc:
        raise RuntimeError("缺少 boto3 依赖，请先安装：boto3>=1.34") from exc

    worker_count = max(1, workers)
    try:
        client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=botocore.config.Config(
            proxies={"http": None, "https": None},
            max_pool_connections=worker_count,
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
        )
    except Exception as exc:
        raise RuntimeError(f"RustFS 对象读取初始化失败（{type(exc).__name__}）") from exc

    def read_one(key: str):
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            body = response["Body"]
            try:
                data = body.read()
            finally:
                body.close()
            return key, data, None
        except Exception as exc:
            return key, None, type(exc).__name__

    iterator = iter(keys)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        pending = set()

        def fill_pending() -> None:
            while len(pending) < worker_count * 2:
                try:
                    key = next(iterator)
                except StopIteration:
                    return
                pending.add(executor.submit(read_one, key))

        fill_pending()
        while pending:
            completed, pending_remaining = wait(
                pending, return_when=FIRST_COMPLETED
            )
            pending = set(pending_remaining)
            for future in completed:
                yield future.result()
            fill_pending()
