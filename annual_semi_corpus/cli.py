"""CLI for nooshare-annual-semi-corpus."""

import typer
from typing import Optional

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
