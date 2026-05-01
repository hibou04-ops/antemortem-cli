# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Tests for the file_safety module + run integration.

Covers: deny-glob, .gitignore respect, --max-file-bytes, --redact-secrets.
The discipline forbids silently shipping secrets to an external LLM
provider, so each guardrail must be testable in isolation and end-to-end
through the `run` command.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from antemortem.cli import app
from antemortem.file_safety import (
    DEFAULT_DENY_GLOBS,
    FileSafetyConfig,
    evaluate_file,
    load_gitignore_patterns,
    redact_secrets,
)
from antemortem.schema import AntemortemOutput, Classification

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit: evaluate_file rules
# ---------------------------------------------------------------------------


def test_deny_glob_blocks_dotenv_at_root(tmp_path: Path):
    f = tmp_path / ".env"
    f.write_text("SECRET=1\n", encoding="utf-8")
    cfg = FileSafetyConfig()
    decision = evaluate_file(".env", f, cfg, gitignore_patterns=())
    assert decision.allowed is False
    assert "deny-glob" in decision.reason


def test_deny_glob_blocks_pem_anywhere(tmp_path: Path):
    nested = tmp_path / "infra" / "tls"
    nested.mkdir(parents=True)
    f = nested / "server.pem"
    f.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    cfg = FileSafetyConfig()
    decision = evaluate_file("infra/tls/server.pem", f, cfg, ())
    assert decision.allowed is False


def test_deny_glob_blocks_secrets_subtree(tmp_path: Path):
    nested = tmp_path / "config" / "secrets"
    nested.mkdir(parents=True)
    f = nested / "db.json"
    f.write_text("{}", encoding="utf-8")
    cfg = FileSafetyConfig()
    decision = evaluate_file("config/secrets/db.json", f, cfg, ())
    assert decision.allowed is False


def test_normal_source_file_is_allowed(tmp_path: Path):
    f = tmp_path / "auth.py"
    f.write_text("def login(): pass\n", encoding="utf-8")
    cfg = FileSafetyConfig()
    decision = evaluate_file("src/auth.py", f, cfg, ())
    assert decision.allowed is True


def test_max_file_bytes_blocks_oversize(tmp_path: Path):
    f = tmp_path / "big.py"
    f.write_text("x = 1\n" * 50_000, encoding="utf-8")
    cfg = FileSafetyConfig(max_file_bytes=1024)
    decision = evaluate_file("big.py", f, cfg, ())
    assert decision.allowed is False
    assert "exceeds --max-file-bytes" in decision.reason


def test_user_can_disable_default_deny_globs(tmp_path: Path):
    """Empty deny_globs lets the user override defaults — useful when
    intentionally auditing a credentials file."""
    f = tmp_path / ".env"
    f.write_text("OK=1\n", encoding="utf-8")
    cfg = FileSafetyConfig(deny_globs=())
    decision = evaluate_file(".env", f, cfg, ())
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# Unit: gitignore reading
# ---------------------------------------------------------------------------


def test_gitignore_patterns_read_from_repo_root(tmp_path: Path):
    (tmp_path / ".gitignore").write_text(
        "# comment\n.env\nnode_modules/\n!included\n", encoding="utf-8"
    )
    patterns = load_gitignore_patterns(tmp_path)
    # `.env` shows as both bare + `**/` variants
    assert ".env" in patterns
    assert "**/.env" in patterns
    # directory pattern → ** glob
    assert any("node_modules" in p for p in patterns)
    # negation `!included` is dropped (we only deny)
    assert "!included" not in patterns


def test_gitignore_blocks_when_respected(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    f_dir = tmp_path / "build"
    f_dir.mkdir()
    f = f_dir / "out.bin"
    f.write_text("x", encoding="utf-8")
    patterns = load_gitignore_patterns(tmp_path)
    cfg = FileSafetyConfig(respect_gitignore=True)
    decision = evaluate_file("build/out.bin", f, cfg, patterns)
    assert decision.allowed is False
    assert "gitignore" in decision.reason


def test_gitignore_can_be_opted_out(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    f_dir = tmp_path / "build"
    f_dir.mkdir()
    f = f_dir / "out.bin"
    f.write_text("x", encoding="utf-8")
    cfg = FileSafetyConfig(respect_gitignore=False)
    # Patterns aren't loaded when respect is off — pass () to mirror that.
    decision = evaluate_file("build/out.bin", f, cfg, ())
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# Unit: secret redaction
# ---------------------------------------------------------------------------


def test_redact_aws_access_key():
    text = "key = AKIAIOSFODNN7EXAMPLE\n"
    out, n = redact_secrets(text)
    assert "AKIA" not in out
    assert "[REDACTED:AWS_ACCESS_KEY]" in out
    assert n == 1


def test_redact_github_pat():
    text = "token = ghp_abcdefghijklmnopqrstuvwxyz0123456789AB\n"
    out, n = redact_secrets(text)
    assert "ghp_" not in out
    assert "[REDACTED:GITHUB_TOKEN]" in out
    assert n == 1


def test_redact_pem_block():
    text = (
        "before\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA\n"
        "-----END RSA PRIVATE KEY-----\n"
        "after\n"
    )
    out, n = redact_secrets(text)
    assert "BEGIN RSA PRIVATE KEY" not in out
    assert "[REDACTED:PEM_BLOCK]" in out
    assert n == 1


def test_redact_anthropic_key():
    text = "ANTHROPIC_API_KEY=sk-ant-api01-abcdefghijklmnopqrstuvwxyz1234567890\n"
    out, n = redact_secrets(text)
    assert "sk-ant-api01" not in out
    assert n >= 1


def test_redact_returns_zero_on_clean_code():
    text = "def add(a, b): return a + b\n"
    out, n = redact_secrets(text)
    assert n == 0
    assert out == text


# ---------------------------------------------------------------------------
# Integration: run command with deny-glob defaults
# ---------------------------------------------------------------------------


_DOC = """---
name: feat
date: 2026-04-21
template: basic
---

# Antemortem — feat

## 1. The change

Refactor.

## 2. Traps hypothesized

| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
| 1 | x | trap | 50% | n |

## 3. Recon protocol

- **Files handed to the model:**
  - `.env`
  - `src/auth.py`
"""


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / ".env").write_text("DATABASE_URL=postgres://prod\n", encoding="utf-8")
    (repo / "src" / "auth.py").write_text(
        "\n".join(f"auth line {i}" for i in range(1, 21)) + "\n",
        encoding="utf-8",
    )
    return repo


def _fake_provider(output, usage):
    p = MagicMock()
    p.name = "anthropic"
    p.model = "mock-model"
    p.structured_complete.return_value = (output, usage)
    return p


def test_run_skips_dotenv_by_default(tmp_path: Path, monkeypatch):
    """The whole point: a doc that names .env must NOT ship .env to the LLM."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})

    captured: dict = {}

    def capture(*args, **kwargs):
        captured["files"] = kwargs.get("files")
        return (output, {"input_tokens": 1, "output_tokens": 1})

    fake.structured_complete.side_effect = None
    with patch("antemortem.commands.run.make_provider", return_value=fake), patch(
        "antemortem.commands.run.run_classification", side_effect=capture
    ):
        result = runner.invoke(app, ["run", str(doc_path), "--repo", str(repo)])

    assert result.exit_code == 0, result.stdout
    file_paths = [p for p, _ in (captured.get("files") or [])]
    assert ".env" not in file_paths
    assert "src/auth.py" in file_paths
    # Warning about the skip surfaces to the user.
    assert ".env" in result.stderr
    assert "deny-glob" in result.stderr


def test_run_respects_max_file_bytes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
        ],
    )
    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})

    with patch("antemortem.commands.run.make_provider", return_value=fake):
        result = runner.invoke(
            app,
            [
                "run",
                str(doc_path),
                "--repo",
                str(repo),
                "--max-file-bytes",
                "10",  # any real file exceeds this
            ],
        )

    # Both files exceed 10 bytes, so neither makes it; run aborts with
    # "no readable files".
    assert result.exit_code == 1
    assert "exceeds --max-file-bytes" in result.stderr


def test_run_redact_secrets_substitutes_before_send(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)
    # Plant an obvious AWS key in the source file.
    (repo / "src" / "auth.py").write_text(
        "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n" * 5, encoding="utf-8"
    )

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:1", note="n"),
        ],
    )
    captured: dict = {}

    def capture(*args, **kwargs):
        captured["files"] = kwargs.get("files")
        return (output, {"input_tokens": 1, "output_tokens": 1})

    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})
    fake.structured_complete.side_effect = None
    with patch("antemortem.commands.run.make_provider", return_value=fake), patch(
        "antemortem.commands.run.run_classification", side_effect=capture
    ):
        result = runner.invoke(
            app,
            [
                "run",
                str(doc_path),
                "--repo",
                str(repo),
                "--redact-secrets",
                "--deny-glob",
                "",  # disable defaults so .env doesn't get blocked first
            ],
        )

    assert result.exit_code == 0, result.stdout
    sent_files = dict(captured.get("files") or [])
    auth_payload = sent_files.get("src/auth.py", "")
    assert "AKIA" not in auth_payload
    assert "[REDACTED:AWS_ACCESS_KEY]" in auth_payload
    assert "redact-secrets applied" in result.stderr


def test_run_user_can_disable_deny_globs_to_audit_credentials(
    tmp_path: Path, monkeypatch
):
    """Edge case: user explicitly wants to audit a credentials file —
    --deny-glob '' lets them, with a clear pattern of intent."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-stub")
    doc_path = tmp_path / "feat.md"
    doc_path.write_text(_DOC, encoding="utf-8")
    repo = _make_repo(tmp_path)

    output = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="src/auth.py:5", note="n"),
        ],
    )
    captured: dict = {}

    def capture(*args, **kwargs):
        captured["files"] = kwargs.get("files")
        return (output, {"input_tokens": 1, "output_tokens": 1})

    fake = _fake_provider(output, {"input_tokens": 1, "output_tokens": 1})
    with patch("antemortem.commands.run.make_provider", return_value=fake), patch(
        "antemortem.commands.run.run_classification", side_effect=capture
    ):
        result = runner.invoke(
            app,
            [
                "run",
                str(doc_path),
                "--repo",
                str(repo),
                "--deny-glob",
                "",
                "--no-respect-gitignore",
            ],
        )

    assert result.exit_code == 0, result.stdout
    sent = [p for p, _ in (captured.get("files") or [])]
    assert ".env" in sent
