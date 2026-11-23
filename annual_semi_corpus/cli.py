"""CLI for nooshare-annual-semi-corpus.

Trigger + orchestration only: resolve configuration, call outbound adapters,
combine pure results, map outcomes to output and exit status. Business logic
lives in core.py; IO lives in adapters.py; configuration lives in config.py.
"""

from __future__ import annotations

from typing import Optional

import typer

from annual_semi_corpus.adapters import (
    list_published_keys,
    query_expected_from_pub_date,
    write_report,
)
from annual_semi_corpus.config import load_settings
from annual_semi_corpus.core import compare_keys

app = typer.Typer(
    help="Independent registry and quality management for the A-share annual and semi-annual Markdown corpus.",
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Corpus registry and quality CLI."""


@app.command()
def check(
    dsn: Optional[str] = typer.Option(None, "--dsn", help="PG 连接串；默认读 DATABASE_URL 或 .env"),
    bucket: Optional[str] = typer.Option(
        None, "--bucket", help="RustFS bucket；默认 CORPUS_RUSTFS_BUCKET 或 nooshare-dev"
    ),
    endpoint: Optional[str] = typer.Option(
        None, "--endpoint", help="S3 endpoint；默认 RUSTFS_ENDPOINT_URL 或 .env"
    ),
    prefix: Optional[str] = typer.Option(None, "--prefix", help="md 对象前缀；默认 CORPUS_PREFIX 或 published/"),
    env_file: Optional[str] = typer.Option(
        None, "--env-file", help=".env 路径；默认从当前目录读取 .env"
    ),
    year_min: Optional[int] = typer.Option(None, "--year-min", help="按 pub_date 年份过滤：下界（含）"),
    year_max: Optional[int] = typer.Option(None, "--year-max", help="按 pub_date 年份过滤：上界（含）"),
    limit: Optional[int] = typer.Option(None, "--limit", help="只检查前 N 个 code（调试用）"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="缺失清单输出路径（.json / .csv）；默认仅打印摘要"
    ),
) -> None:
    """只读检查 ju.pub_date 期望清单与 RustFS published/ md 库的完整性。

    只读：仅 SELECT / list_objects_v2，不写 PG、不 put/delete 对象。
    key 映射：(code, year, period) -> published/{code}/{code}_{year}_{period}.md。
    """
    settings = load_settings(
        dotenv_path=env_file or ".env",
        dsn=dsn,
        endpoint=endpoint,
        bucket=bucket,
        prefix=prefix,
    )

    absent = settings.missing()
    if absent:
        typer.echo(
            "错误：缺少必需配置：" + "、".join(absent) + "。请设置环境变量或写入 .env（本命令不打印密钥）。",
            err=True,
        )
        raise typer.Exit(code=1)

    if year_min is not None and year_max is not None and year_min > year_max:
        typer.echo("错误：--year-min 不能大于 --year-max。", err=True)
        raise typer.Exit(code=1)
    if limit is not None and limit <= 0:
        typer.echo("错误：--limit 必须为正整数。", err=True)
        raise typer.Exit(code=1)

    try:
        expected = query_expected_from_pub_date(
            settings.dsn, "ju", settings.prefix, year_min, year_max, limit
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"错误：读取 PG 期望清单失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        full_keys = list_published_keys(
            settings.endpoint, settings.access_key, settings.secret_key, settings.bucket, settings.prefix
        )
    except RuntimeError as exc:
        typer.echo(f"错误：读取 RustFS 清单失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    has_pub_date_filter = year_min is not None or year_max is not None
    result = compare_keys(
        set(expected), full_keys, report_orphans=not has_pub_date_filter
    )

    typer.echo("check 摘要")
    typer.echo("  schema     : ju")
    typer.echo(f"  bucket     : {settings.bucket}")
    typer.echo(f"  prefix     : {settings.prefix}")
    typer.echo(f"  期望对象数 : {result.expected_count}")
    if has_pub_date_filter:
        typer.echo(f"  实有对象数（期望命中）: {result.actual_count}")
    else:
        typer.echo(f"  实有对象数 : {result.actual_count}")
    typer.echo(f"  缺失数     : {len(result.missing)}")
    if has_pub_date_filter:
        typer.echo("  孤儿数     : 不适用（对象 Key 不包含 pub_date，无法按发布日期范围归属）")
    else:
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
            write_report(output, result, expected, "ju", settings.bucket, settings.prefix)
        except (OSError, ValueError) as exc:
            typer.echo(f"错误：写出报告失败：{exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"报告已写出：{output}")

    raise typer.Exit(code=0)
