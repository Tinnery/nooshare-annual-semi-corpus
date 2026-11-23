"""CLI structure tests: only the check command is exposed."""

import re

from typer.testing import CliRunner

from annual_semi_corpus.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI color codes so help assertions work with and without color."""
    return _ANSI_RE.sub("", text)


def test_cli_help_shows_check():
    """CLI help lists check."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.stdout


def test_only_check_command_registered():
    """No legacy commands remain registered."""
    names = sorted(cmd.callback.__name__ for cmd in app.registered_commands)
    assert names == ["check"]


def test_check_help_exposes_env_file_option():
    """check accepts --env-file so config can come from a local .env."""
    result = runner.invoke(app, ["check", "--help"])
    assert result.exit_code == 0
    assert "--env-file" in _plain(result.stdout)
