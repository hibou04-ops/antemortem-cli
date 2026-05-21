"""Tests for post-release verification orchestration."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "post_release_check.py"
SPEC = importlib.util.spec_from_file_location("post_release_check", SCRIPT_PATH)
assert SPEC is not None
post_release_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = post_release_check
SPEC.loader.exec_module(post_release_check)


def _write_release_root(root: Path, version: str = "0.9.4") -> None:
    (root / "pyproject.toml").write_text(
        f"""
[project]
name = "antemortem"
version = "{version}"
urls = {{ Source = "https://github.com/hibou04-ops/antemortem-cli" }}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        f"""
# antemortem-cli

> **Current release: v{version}**

[![PyPI](https://img.shields.io/badge/pypi-{version}-blue.svg)](https://pypi.org/project/antemortem/)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "post_release_verification.md").write_text(
        """
python scripts/post_release_check.py --version 0.9.4 --dry-run --json
python scripts/post_release_check.py --version 0.9.4 --skip-network --json
python scripts/check_repo_consistency.py
python scripts/generate_readme_claims.py --check
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "download_analytics_note.md").write_text("# note\n", encoding="utf-8")
    (root / "docs" / "download_analytics_note_kr.md").write_text("# note\n", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples" / "demo_recon.md").write_text("# demo\n", encoding="utf-8")
    (root / "examples" / "demo_antemortem.md").write_text("# demo artifact\n", encoding="utf-8")
    (root / "benchmarks" / "golden_cases").mkdir(parents=True)


def _runner(commands: list[list[str]], envs: list[dict[str, str]]):
    def runner(command, cwd, env, text, encoding, errors, capture_output, check):
        commands.append(list(command))
        envs.append(dict(env))
        display = " ".join(str(part) for part in command)
        stdout = ""
        if "ls-remote" in display:
            stdout = "abc123\trefs/tags/v0.9.4\n"
        elif "--version" in display:
            stdout = "antemortem 0.9.4\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    return runner


def test_post_release_check_success_path_with_mocked_subprocesses(tmp_path: Path, monkeypatch):
    _write_release_root(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    commands: list[list[str]] = []
    envs: list[dict[str, str]] = []
    venv_calls: list[dict[str, object]] = []

    def venv_creator(path, **kwargs):
        venv_calls.append({"path": path, **kwargs})

    exit_code, summary = post_release_check.run_post_release_check(
        tmp_path,
        expected_version="0.9.4",
        runner=_runner(commands, envs),
        venv_creator=venv_creator,
        fetch_json=lambda url: {"info": {"version": "0.9.4"}},
    )

    assert exit_code == 0
    assert summary["ok"] is True
    assert summary["release_verified"] is True
    assert summary["failed_count"] == 0
    assert any(command[:3] == ["git", "ls-remote", "--tags"] for command in commands)
    assert any("antemortem==0.9.4" in command for command in commands)
    assert commands[-3][1:] == ["doctor", "examples/demo_recon.md", "--repo", ".", "--json"]
    assert commands[-2][1:] == ["lint", "examples/demo_antemortem.md", "--repo", "."]
    assert commands[-1][1:] == ["eval", "benchmarks/golden_cases", "--json"]
    assert all("OPENAI_API_KEY" not in env for env in envs)
    assert venv_calls[0]["with_pip"] is True
    assert venv_calls[0]["system_site_packages"] is False
    assert venv_calls[0]["clear"] is True


def test_post_release_check_skip_network_does_not_call_pypi_or_github(tmp_path: Path):
    _write_release_root(tmp_path)
    commands: list[list[str]] = []
    envs: list[dict[str, str]] = []

    exit_code, summary = post_release_check.run_post_release_check(
        tmp_path,
        expected_version="0.9.4",
        skip_network=True,
        runner=_runner(commands, envs),
        fetch_json=lambda url: (_ for _ in ()).throw(AssertionError("network called")),
    )

    statuses = [step["status"] for step in summary["steps"]]
    assert exit_code == 0
    assert summary["release_verified"] is False
    assert "SKIPPED" in statuses
    assert not any(command[:3] == ["git", "ls-remote", "--tags"] for command in commands)
    assert not any("pip" in " ".join(command) for command in commands)
    assert commands[0][:3] == [sys.executable, "-m", "antemortem.cli"]


def test_post_release_check_dry_run_json_is_stable_and_not_verified(tmp_path: Path):
    _write_release_root(tmp_path)
    commands: list[list[str]] = []
    envs: list[dict[str, str]] = []

    exit_code, summary = post_release_check.run_post_release_check(
        tmp_path,
        expected_version="0.9.4",
        dry_run=True,
        json_output=True,
        runner=_runner(commands, envs),
    )
    payload = json.loads(json.dumps(summary, sort_keys=True))

    assert exit_code == 0
    assert payload["mode"] == "dry-run"
    assert payload["release_verified"] is False
    assert payload["pending_count"] == 3
    assert payload["not_run_count"] == 1
    assert payload["steps"][0] == {
        "command": "--version",
        "exit_code": 0,
        "label": "Check expected version argument",
        "message": "0.9.4 is a valid release version",
        "status": "PASS",
    }


def test_post_release_check_fails_on_pypi_version_mismatch(tmp_path: Path):
    _write_release_root(tmp_path)

    exit_code, summary = post_release_check.run_post_release_check(
        tmp_path,
        expected_version="0.9.4",
        runner=_runner([], []),
        fetch_json=lambda url: {"info": {"version": "0.9.3"}},
    )

    assert exit_code == 1
    assert summary["ok"] is False
    assert summary["release_verified"] is False
    assert summary["steps"][-1]["label"] == "Check PyPI package version"
    assert "expected 0.9.4" in summary["steps"][-1]["message"]


def test_post_release_check_fails_on_github_tag_mismatch(tmp_path: Path):
    _write_release_root(tmp_path)

    def runner(command, **kwargs):
        display = " ".join(str(part) for part in command)
        stdout = "" if "ls-remote" in display else "antemortem 0.9.4\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    exit_code, summary = post_release_check.run_post_release_check(
        tmp_path,
        expected_version="0.9.4",
        runner=runner,
        fetch_json=lambda url: {"info": {"version": "0.9.4"}},
    )

    assert exit_code == 1
    assert summary["steps"][-1]["label"] == "Check GitHub release tag"
    assert summary["steps"][-1]["status"] == "FAIL"
    assert "remote tag v0.9.4 was not found" in summary["steps"][-1]["message"]


def test_post_release_check_fails_on_remote_install_failure(tmp_path: Path):
    _write_release_root(tmp_path)
    venv_calls: list[str] = []

    def venv_creator(path, **kwargs):
        venv_calls.append(path)

    def runner(command, **kwargs):
        display = " ".join(str(part) for part in command)
        if "ls-remote" in display:
            return subprocess.CompletedProcess(command, 0, stdout="abc\trefs/tags/v0.9.4\n", stderr="")
        if "pip install" in display or ("pip" in display and "antemortem==0.9.4" in display):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="install failed")
        return subprocess.CompletedProcess(command, 0, stdout="antemortem 0.9.4\n", stderr="")

    exit_code, summary = post_release_check.run_post_release_check(
        tmp_path,
        expected_version="0.9.4",
        runner=runner,
        venv_creator=venv_creator,
        fetch_json=lambda url: {"info": {"version": "0.9.4"}},
    )

    assert exit_code == 1
    assert venv_calls
    assert summary["steps"][-1]["label"] == "Install package from PyPI"
    assert summary["steps"][-1]["status"] == "FAIL"


def test_post_release_check_fails_on_missing_local_docs(tmp_path: Path):
    _write_release_root(tmp_path)
    (tmp_path / "docs" / "download_analytics_note.md").unlink()

    exit_code, summary = post_release_check.run_post_release_check(
        tmp_path,
        expected_version="0.9.4",
        skip_network=True,
        runner=_runner([], []),
    )

    assert exit_code == 1
    assert summary["steps"][-1]["label"] == "Check post-release docs"
    assert "download_analytics_note.md" in summary["steps"][-1]["message"]


def test_download_analytics_wording_avoids_unsupported_claims():
    root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        [
            (root / "docs" / "download_analytics_note.md").read_text(encoding="utf-8"),
            (root / "docs" / "download_analytics_note_kr.md").read_text(encoding="utf-8"),
        ]
    ).lower()

    forbidden = (
        "production-proven",
        "active users",
        "active-user",
        "customers",
        "enterprise usage",
        "production usage",
    )
    assert all(term not in combined for term in forbidden)
    assert "download activity" in combined
    assert "estimated real-user share" in combined
    assert "mirror/ci-adjusted estimate" in combined
    assert "directional signal" in combined
