"""Smoke tests for the top-level CLI wiring."""

from typer.testing import CliRunner

from antemortem import __version__
from antemortem.cli import app

runner = CliRunner()


def test_help_lists_three_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    stdout = result.stdout
    assert "init" in stdout
    assert "run" in stdout
    assert "lint" in stdout


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_prints_help():
    result = runner.invoke(app, [])
    assert result.exit_code != 0  # typer uses 2 for usage error / help-on-no-args
    combined = result.stdout + result.output
    assert "Usage" in combined or "init" in combined


# Proper run/lint tests live in tests/test_run.py and tests/test_lint.py.
# They're covered there with real docs and mocked API clients — the earlier
# "stub returns exit 1" smoke tests here became stale once the commands were
# fully implemented.
