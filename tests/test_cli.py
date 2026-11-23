"""CLI structure tests: only the check command is exposed."""

from typer.testing import CliRunner

from annual_semi_corpus.cli import app

runner = CliRunner()


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
    assert "--env-file" in result.stdout
