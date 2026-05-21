"""Static checks for the GitHub Actions trust workflow."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _supported_python_versions() -> list[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    versions = []
    for classifier in pyproject["project"]["classifiers"]:
        match = re.fullmatch(r"Programming Language :: Python :: (\d+\.\d+)", classifier)
        if match:
            versions.append(match.group(1))
    return sorted(versions)


def test_ci_workflow_name_matches_readme_badge():
    workflow = _workflow_text()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_kr = (ROOT / "README_KR.md").read_text(encoding="utf-8")

    assert re.search(r"^name:\s+CI$", workflow, flags=re.M)
    assert "[![CI]" in readme
    assert "actions/workflows/ci.yml/badge.svg" in readme
    assert "[![CI]" in readme_kr
    assert "actions/workflows/ci.yml/badge.svg" in readme_kr


def test_ci_matrix_covers_supported_python_versions():
    workflow = _workflow_text()

    for version in _supported_python_versions():
        assert f'"{version}"' in workflow
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow


def test_ci_runs_required_offline_trust_commands():
    workflow = _workflow_text()

    required = [
        'python -m pip install -e ".[dev]"',
        "pytest -q",
        "python scripts/check_repo_consistency.py",
        "python scripts/generate_readme_claims.py --check",
        "python scripts/check_claim_ledger.py",
        "antemortem eval benchmarks/golden_cases --json",
        "python -m build",
        "python -m twine check dist/*",
    ]
    for command in required:
        assert command in workflow
    assert "uses: actions/upload-artifact@v4" in workflow
    assert "benchmark-results.json" in workflow


def test_ci_wheel_smoke_is_separate_and_does_not_require_provider_keys():
    workflow = _workflow_text()

    assert re.search(r"^  wheel-smoke:$", workflow, flags=re.M)
    assert "python scripts/smoke_wheel_install.py" in workflow
    assert "ANTHROPIC_API_KEY" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "GEMINI_API_KEY" not in workflow
