"""Self-check the deterministic README demo replay."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
README_DEMO_COMMAND = "PYTHONIOENCODING=utf-8 python examples/demo_replay.py"
REQUIRED_DEMO_TOKENS = (
    "GHOST",
    "REAL",
    "NEW",
    "UNRESOLVED",
    "verdict:   PROCEED_WITH_GUARDS",
    "$ antemortem lint examples/demo_antemortem.md --repo .",
    "PASS -- demo_antemortem.md validates clean (schema + classifications)",
    "citations: 4/4 paths exist, all line ranges in bounds",
)


def _offline_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["ANTEMORTEM_DEMO_REPLAY_NO_SLEEP"] = "1"
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        env.pop(key, None)
    return env


def _run_script(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_offline_env(),
        check=False,
    )


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


@pytest.fixture(scope="module")
def demo_replay_output() -> str:
    result = _run_script("examples/demo_replay.py")
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_readme_demo_command_runs_without_api_keys(demo_replay_output: str):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert README_DEMO_COMMAND in readme
    for token in REQUIRED_DEMO_TOKENS:
        assert token in demo_replay_output


def test_demo_capture_matches_machine_speed_demo_output():
    result = _run_script("examples/demo_recon.py")
    expected = (ROOT / "examples" / "_demo_output.txt").read_text(encoding="utf-8")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _normalize(result.stdout) == _normalize(expected)


def test_demo_docs_claims_are_backed_by_replay_output(demo_replay_output: str):
    docs = [
        ROOT / "README.md",
        ROOT / "README_KR.md",
        ROOT / "EASY_README.md",
        ROOT / "EASY_README_KR.md",
        ROOT / "docs" / "demo" / "antemortem-cli-demo.en.srt",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "demo_replay.py" in text or path.suffix == ".srt"
        for label in ("REAL", "GHOST", "NEW", "UNRESOLVED"):
            assert label in text, f"{label} missing from {path}"
        assert "PROCEED_WITH_GUARDS" in text, f"decision missing from {path}"
        assert re.search(r"lint", text, re.I), f"lint verification missing from {path}"

    for token in REQUIRED_DEMO_TOKENS:
        assert token in demo_replay_output
