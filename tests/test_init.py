"""Tests for `antemortem init`."""

from pathlib import Path

from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.templates import BASIC_TEMPLATE, ENHANCED_TEMPLATE

runner = CliRunner()


def test_init_creates_basic_doc(tmp_path: Path):
    output_dir = tmp_path / "antemortem"
    result = runner.invoke(
        app,
        ["init", "my-feature", "--output-dir", str(output_dir)],
    )
    assert result.exit_code == 0, result.stdout
    target = output_dir / "my-feature.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "name: my-feature" in content
    assert "template: basic" in content
    assert BASIC_TEMPLATE.splitlines()[0] in content


def test_init_creates_enhanced_doc(tmp_path: Path):
    output_dir = tmp_path / "antemortem"
    result = runner.invoke(
        app,
        ["init", "high-stakes-migration", "--enhanced", "--output-dir", str(output_dir)],
    )
    assert result.exit_code == 0, result.stdout
    target = output_dir / "high-stakes-migration.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "template: enhanced" in content
    assert ENHANCED_TEMPLATE.splitlines()[0] in content


def test_init_refuses_overwrite_without_force(tmp_path: Path):
    output_dir = tmp_path / "antemortem"
    runner.invoke(app, ["init", "dup", "--output-dir", str(output_dir)])
    result = runner.invoke(
        app,
        ["init", "dup", "--output-dir", str(output_dir)],
    )
    assert result.exit_code == 1


def test_init_force_overwrites(tmp_path: Path):
    output_dir = tmp_path / "antemortem"
    first = runner.invoke(app, ["init", "dup", "--output-dir", str(output_dir)])
    assert first.exit_code == 0
    target = output_dir / "dup.md"
    target.write_text("tampered\n", encoding="utf-8")
    second = runner.invoke(
        app,
        ["init", "dup", "--force", "--output-dir", str(output_dir)],
    )
    assert second.exit_code == 0
    assert "tampered" not in target.read_text(encoding="utf-8")


def test_init_rejects_path_traversal(tmp_path: Path):
    result = runner.invoke(
        app,
        ["init", "../../etc/passwd", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 2


def test_init_frontmatter_contains_iso_date(tmp_path: Path):
    from datetime import date

    result = runner.invoke(
        app,
        ["init", "dated", "--output-dir", str(tmp_path / "antemortem")],
    )
    assert result.exit_code == 0
    target = tmp_path / "antemortem" / "dated.md"
    assert f"date: {date.today().isoformat()}" in target.read_text(encoding="utf-8")
