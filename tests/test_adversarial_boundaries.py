"""Adversarial filesystem and parser boundary tests.

These tests lock down the offline safety boundary shared by doctor, lint,
and run preflight. They do not call provider SDKs or the network.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from antemortem.commands.doctor import build_doctor_report
from antemortem.commands.lint import run_lint
from antemortem.commands.run import load_files_for_recon
from antemortem.file_safety import FileSafetyConfig
from antemortem.parser import parse_document


DOC_TEMPLATE = """---
name: adversarial
date: 2026-05-22
template: basic
---

# Antemortem - adversarial

## 1. The change

{spec}

## 2. Traps hypothesized

{traps}

## 3. Recon protocol

- **Files handed to the model:**
{files}
"""

VALID_TRAPS = """| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | auth bypass | trap | 60% | check guard |"""


def _write_doc(
    tmp_path: Path,
    *,
    files: list[str] | None = None,
    spec: str = "Add authentication guard.",
    traps: str = VALID_TRAPS,
) -> Path:
    file_lines = "\n".join(
        f"  - `{path}`" for path in (files if files is not None else ["src/auth.py"])
    )
    doc = tmp_path / "recon.md"
    doc.write_text(
        DOC_TEMPLATE.format(spec=spec, traps=traps, files=file_lines),
        encoding="utf-8",
    )
    return doc


def _write_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text(
        "def check_auth(user):\n    return bool(user)\n",
        encoding="utf-8",
    )
    return repo


def _write_artifact(doc: Path, citation: str) -> None:
    doc.with_suffix(".json").write_text(
        json.dumps(
            {
                "classifications": [
                    {
                        "id": "t1",
                        "label": "REAL",
                        "citation": citation,
                        "note": "n",
                    }
                ],
                "new_traps": [],
                "spec_mutations": [],
            }
        ),
        encoding="utf-8",
    )


def _make_escape_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:  # pragma: no cover - environment-specific fallback.
                raise AssertionError(
                    "could not create a Windows junction or directory symlink: "
                    f"{result.stdout}{result.stderr}{exc}"
                ) from exc
    else:
        link.symlink_to(target, target_is_directory=True)


def test_doctor_lint_and_run_agree_on_recon_path_traversal(tmp_path: Path):
    repo = _write_repo(tmp_path)
    (tmp_path / "outside.py").write_text("SECRET = True\n", encoding="utf-8")
    doc = _write_doc(tmp_path, files=["../outside.py"])

    report = build_doctor_report(doc, repo)
    lint = run_lint(doc, repo)
    parsed = parse_document(doc)
    files, warnings = load_files_for_recon(parsed, repo)

    assert report["readiness"] == "NOT_READY"
    assert report["files_excluded"] == [
        {"path": "../outside.py", "reason": "path escapes repo root"}
    ]
    assert "path traversal attempt: ../outside.py" in report["warnings"]
    assert not lint.ok
    assert "files_to_read ../outside.py: path escapes repo root" in lint.violations
    assert files == []
    assert "skipped '../outside.py': path escapes repo root" in warnings


def test_lint_rejects_path_traversal_citation(tmp_path: Path):
    repo = _write_repo(tmp_path)
    (tmp_path / "outside.py").write_text("SECRET = True\n", encoding="utf-8")
    doc = _write_doc(tmp_path)
    _write_artifact(doc, "../outside.py:1")

    result = run_lint(doc, repo)

    assert not result.ok
    assert any("cited path escapes repo root" in violation for violation in result.violations)


def test_symlink_escape_rejected_by_doctor_lint_and_run_preflight(tmp_path: Path):
    repo = _write_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escape.py").write_text("token = 'outside'\n", encoding="utf-8")
    _make_escape_link(repo / "linked", outside)
    doc = _write_doc(tmp_path, files=["linked/escape.py"])

    report = build_doctor_report(doc, repo)
    lint = run_lint(doc, repo)
    parsed = parse_document(doc)
    files, warnings = load_files_for_recon(parsed, repo)

    assert report["readiness"] == "NOT_READY"
    assert report["files_excluded"] == [
        {"path": "linked/escape.py", "reason": "path escapes repo root"}
    ]
    assert not lint.ok
    assert "files_to_read linked/escape.py: path escapes repo root" in lint.violations
    assert files == []
    assert "skipped 'linked/escape.py': path escapes repo root" in warnings


def test_preflight_reports_hidden_binary_huge_and_invalid_encoding(tmp_path: Path):
    repo = _write_repo(tmp_path)
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (repo / "bin.dat").write_bytes(b"abc\x00def")
    (repo / "huge.py").write_text("x" * 200_001, encoding="utf-8")
    (repo / "bad_utf8.py").write_bytes(b"ok = 1\nbad = \xff\n")
    doc = _write_doc(tmp_path, files=[".env", "bin.dat", "huge.py", "bad_utf8.py"])

    report = build_doctor_report(doc, repo)
    parsed = parse_document(doc)
    files, warnings = load_files_for_recon(
        parsed,
        repo,
        FileSafetyConfig(max_file_bytes=20),
    )

    assert report["readiness"] == "READY_WITH_WARNINGS"
    assert {item["path"] for item in report["files_excluded"]} == {
        ".env",
        "bin.dat",
        "huge.py",
    }
    assert any("matches deny-glob '.env'" in item["reason"] for item in report["files_excluded"])
    assert {"path": "bin.dat", "reason": "binary file skipped"} in report["files_excluded"]
    assert any("exceeds --max-file-bytes" in item["reason"] for item in report["files_excluded"])
    assert "invalid UTF-8 bytes replaced: bad_utf8.py" in report["warnings"]
    assert files == [("bad_utf8.py", "ok = 1\nbad = \ufffd\n")]
    assert any("skipped '.env': matches deny-glob '.env'" in warning for warning in warnings)
    assert "skipped 'bin.dat': binary file skipped" in warnings
    assert any("skipped 'huge.py': file size" in warning for warning in warnings)
    assert "bad_utf8.py: invalid UTF-8 bytes replaced" in warnings


def test_lint_reports_malformed_markdown_table(tmp_path: Path):
    repo = _write_repo(tmp_path)
    malformed = """| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | only two cells |"""
    doc = _write_doc(tmp_path, traps=malformed)

    result = run_lint(doc, repo)

    assert not result.ok
    assert "traps: malformed table row in pre-recon Traps section" in result.violations


def test_lint_reports_duplicate_trap_ids(tmp_path: Path):
    repo = _write_repo(tmp_path)
    duplicate = """| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | auth bypass | trap | 60% | check guard |
| 1 | stale cache | worry | 30% | same id |"""
    doc = _write_doc(tmp_path, traps=duplicate)

    result = run_lint(doc, repo)

    assert not result.ok
    assert "traps: duplicate trap ids: t1" in result.violations


def test_lint_reports_empty_spec_no_traps_and_no_files(tmp_path: Path):
    repo = _write_repo(tmp_path)
    doc = _write_doc(tmp_path, spec="", traps="No table here.", files=[])

    result = run_lint(doc, repo)

    assert not result.ok
    assert "spec: '## 1. The change' section is empty or missing" in result.violations
    assert "traps: no rows parsed from the pre-recon Traps table" in result.violations
    assert "files_to_read: no files listed under 'Recon protocol'" in result.violations
