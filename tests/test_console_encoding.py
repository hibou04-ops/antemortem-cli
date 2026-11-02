"""Public help stays usable when UTF-8 mode is off and pipes use ASCII/cp949."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("encoding", ["ascii", "cp949"])
def test_all_command_help_is_ascii_outside_checkout(tmp_path: Path, encoding: str):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = encoding + ":strict"
    env["NO_COLOR"] = "1"
    for command in (None, "init", "doctor", "run", "lint", "evidence", "gate", "eval", "report", "metrics"):
        args = [] if command is None else [command]
        result = subprocess.run(
            [sys.executable, "-m", "antemortem.cli", *args, "--help"],
            cwd=tmp_path, env=env, capture_output=True, check=False,
        )
        assert result.returncode == 0, (command, result.stderr.decode(encoding, errors="replace"))
        assert result.stdout.isascii(), (command, result.stdout)
        assert b"Usage:" in result.stdout


@pytest.mark.parametrize("encoding", ["ascii", "cp949"])
def test_real_warning_error_and_json_paths_are_ascii_without_changing_values(tmp_path: Path, encoding: str):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = encoding + ":strict"
    env.pop("PYTHONPATH", None)
    missing = "missing-\U0001f4a5.py"
    finding_id = "trap-\U0001f4a5"
    document = tmp_path / "case-\U0001f4a5.md"
    document.write_text(
        "---\nname: case\ndate: 2026-11-02\ntemplate: basic\n---\n"
        "## 1. The change\nInspect evidence.\n"
        "## 2. Traps hypothesized\n"
        "| # | trap | label | P(issue) | notes |\n|---|------|-------|----------|-------|\n"
        "| 1 | risk | trap | 50% | test |\n"
        "## 3. Recon protocol\n- **Files handed to the model:**\n"
        f"  - `{missing}`\n", encoding="utf-8",
    )
    artifact = document.with_suffix(".json")
    artifact.write_text(json.dumps({
        "classifications": [{"id": finding_id, "label": "REAL", "citation": missing + ":1"}],
        "decision": "SAFE_TO_PROCEED",
    }, ensure_ascii=False), encoding="utf-8")

    def invoke(*args: str):
        result = subprocess.run([sys.executable, "-m", "antemortem.cli", *args],
                                cwd=tmp_path, env=env, capture_output=True, check=False)
        assert result.stdout.isascii(), result.stdout
        assert result.stderr.isascii(), result.stderr
        assert b"UnicodeEncodeError" not in result.stderr
        return result

    # Missing evidence exits before provider construction: no key, daemon or API call.
    warning = invoke("run", str(document), "--repo", str(tmp_path), "--provider", "ollama")
    assert warning.returncode == 1 and b"warning:" in warning.stderr
    assert b"\\U0001f4a5" in warning.stderr
    text = invoke("metrics", str(artifact), "--repo", str(tmp_path))
    assert text.returncode == 4 and b"FABRICATED" in text.stdout
    machine = invoke("metrics", str(artifact), "--repo", str(tmp_path), "--format", "json")
    payload = json.loads(machine.stdout)
    assert machine.returncode == 4
    assert payload["findings"][0]["id"] == finding_id
    assert payload["findings"][0]["citation"] == missing + ":1"
    for fmt in ("text", "json"):
        gated = invoke("gate", str(document), "--repo", str(tmp_path), "--format", fmt)
        assert gated.returncode != 0
        if fmt == "json":
            assert json.loads(gated.stdout)["document"] == str(document)
            assert json.loads(gated.stdout)["deployment_authorized"] is False
