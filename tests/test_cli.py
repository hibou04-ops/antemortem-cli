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


def test_run_stub_exits_non_zero(tmp_path):
    doc = tmp_path / "dummy.md"
    doc.write_text("# placeholder\n", encoding="utf-8")
    result = runner.invoke(app, ["run", str(doc), "--repo", str(tmp_path)])
    assert result.exit_code == 1


def test_lint_stub_exits_non_zero(tmp_path):
    doc = tmp_path / "dummy.md"
    doc.write_text("# placeholder\n", encoding="utf-8")
    result = runner.invoke(app, ["lint", str(doc), "--repo", str(tmp_path)])
    assert result.exit_code == 1
