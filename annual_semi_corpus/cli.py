"""CLI for nooshare-annual-semi-corpus.

Trigger layer only: parse parameters, validate input, call the check task,
format output, and map outcomes to exit status. Business orchestration lives
in tasks/check.py; pure computation in core.py; IO in adapters.py; configuration
in config.py.
"""

from __future__ import annotations

from typing import Optional

import typer

from annual_semi_corpus.adapters import write_report
from annual_semi_corpus.config import load_settings
from annual_semi_corpus.tasks.check import run_check

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
        None, "--output", "-o", help="检查问题明细输出路径（.json / .csv）；默认仅打印摘要"
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
        outcome = run_check(
            dsn=settings.dsn,
            endpoint=settings.endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            bucket=settings.bucket,
            prefix=settings.prefix,
            year_min=year_min,
            year_max=year_max,
            limit=limit,
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"错误：检查失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = outcome.result
    has_pub_date_filter = outcome.has_pub_date_filter

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

    content = outcome.content
    severities = content.severity_counts
    typer.echo("内容检查")
    typer.echo(f"  命中对象数 : {content.matched_count}（全量 Size 元数据核验）")
    typer.echo(
        f"  正文抽样数 : {content.sampled_count}（按报告年度×报告类型分组，每组最多 {content.sample_per_group} 份）"
    )
    typer.echo(f"  样本分组数 : {content.sample_group_count}")
    typer.echo(f"  已尝试读取 : {content.attempted_count}")
    typer.echo(f"  样本可读取 : {content.readable_count}")
    typer.echo(f"  样本无问题 : {content.clean_count}")
    typer.echo(f"  样本未识别年度 : {content.year_unverified_count}")
    typer.echo(
        "  内容问题   : "
        f"error={severities['error']}, "
        f"suspect={severities['suspect']}, "
        f"advisory={severities['advisory']}, "
        f"read_error={severities['execution']}"
    )
    for rule, count in content.rule_counts.items():
        if count:
            typer.echo(f"  {rule:<24}: {count}")

    if output:
        try:
            write_report(
                output, result, outcome.expected, "ju",
                settings.bucket, settings.prefix, content,
            )
        except (OSError, ValueError) as exc:
            typer.echo(f"错误：写出报告失败：{exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"报告已写出：{output}")

    # A read failure means the selected content sample did not complete.
    # Full coverage and object-size checks still run over the entire selected scope.
    raise typer.Exit(code=1 if severities["execution"] else 0)
