"""CLI entry point for nooshare-annual-semi-corpus."""

import typer

app = typer.Typer(
    name="nooshare-annual-semi-corpus",
    help="Independent registry and quality management for the A-share annual and semi-annual Markdown corpus.",
    add_completion=False,
)


@app.command()
def inventory():
    """Scan actual Markdown files and build corpus inventory."""
    typer.echo("inventory: not yet implemented")


@app.command()
def assess():
    """Perform quality assessment on specified inventory."""
    typer.echo("assess: not yet implemented")


@app.command()
def diff():
    """Compare changes between two corpus inventories or quality assessments."""
    typer.echo("diff: not yet implemented")


if __name__ == "__main__":
    app()
