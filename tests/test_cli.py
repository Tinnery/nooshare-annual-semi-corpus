"""Basic CLI tests for nooshare-annual-semi-corpus."""

from typer.testing import CliRunner
from annual_semi_corpus.cli import app

runner = CliRunner()


def test_cli_help():
    """Test that CLI shows help message."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "inventory" in result.stdout
    assert "assess" in result.stdout
    assert "diff" in result.stdout


def test_inventory_command():
    """Test inventory command exists."""
    result = runner.invoke(app, ["inventory"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.stdout


def test_assess_command():
    """Test assess command exists."""
    result = runner.invoke(app, ["assess"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.stdout


def test_diff_command():
    """Test diff command exists."""
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.stdout
