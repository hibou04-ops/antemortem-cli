"""Determinism / replay hardening for the new offline renderers.

CI golden checks depend on byte-stable output. The report and metrics
renderers must produce identical bytes for identical (artifact, repo)
inputs across repeated runs and across processes — no clocks, no dict
ordering leaks, no locale dependence. These tests render the committed
gallery artifacts (real, offline fixtures) twice and across a subprocess
and assert byte-equality.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from antemortem.citation_metrics import metrics_from_artifact
from antemortem.commands.report import build_report

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "examples" / "gallery"


def _gallery_cases() -> list[tuple[Path, Path]]:
    cases = []
    for scenario in sorted(GALLERY.iterdir()):
        artifact = scenario / "recon.json"
        repo = scenario / "repo"
        if artifact.is_file() and repo.is_dir():
            cases.append((artifact, repo))
    return cases


GALLERY_CASES = _gallery_cases()


def test_gallery_cases_discovered():
    assert GALLERY_CASES, "no gallery artifact+repo fixtures found"


@pytest.mark.parametrize("output_format", ["markdown", "html"])
@pytest.mark.parametrize("artifact,repo", GALLERY_CASES, ids=lambda p: p.parent.name if hasattr(p, "parent") else str(p))
def test_report_render_is_byte_stable(artifact: Path, repo: Path, output_format: str):
    first = build_report(artifact, repo, output_format=output_format)
    second = build_report(artifact, repo, output_format=output_format)
    assert first == second


@pytest.mark.parametrize("artifact,repo", GALLERY_CASES, ids=lambda p: p.parent.name if hasattr(p, "parent") else str(p))
def test_metrics_json_is_byte_stable(artifact: Path, repo: Path):
    first = metrics_from_artifact(artifact, repo).to_json_str()
    second = metrics_from_artifact(artifact, repo).to_json_str()
    assert first == second
    # JSON keys are sorted → stable serialization for golden comparison.
    parsed = json.loads(first)
    assert parsed["schema"] == "antemortem-citation-metrics-v1"


def _render_in_subprocess(artifact: Path, repo: Path) -> str:
    """Render a markdown report in a fresh process to catch in-process state leaks."""
    code = (
        "from pathlib import Path;"
        "from antemortem.commands.report import build_report;"
        f"print(build_report(Path(r'{artifact}'), Path(r'{repo}'), output_format='markdown'), end='')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


def test_report_cross_process_byte_stable():
    artifact, repo = GALLERY_CASES[0]
    in_process = build_report(artifact, repo, output_format="markdown")
    out_of_process = _render_in_subprocess(artifact, repo)
    assert in_process == out_of_process
