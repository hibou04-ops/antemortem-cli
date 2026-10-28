"""Deterministic source-open and bounded evidence-contract comparison.

Run this script with each installed distribution's Python from outside the
checkout. It performs no provider calls and makes no wall-clock speed claim.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from typer.testing import CliRunner

from antemortem import __version__
from antemortem.citations import compute_evidence_hash
from antemortem.citation_metrics import compute_citation_metrics
from antemortem.cli import app
from antemortem.schema import AntemortemOutput, Classification


def measure(root: Path, count: int, command: str) -> dict:
    source = root / "source.py"
    source.write_text("".join(f"line {i}\n" for i in range(1, 2001)), encoding="utf-8")
    doc = root / "check.md"
    rows = "\n".join(f"| {i} | risk {i} | trap |" for i in range(1, count + 1))
    doc.write_text(
        "---\nname: check\ndate: 2026-10-28\ntemplate: basic\n---\n"
        "# Antemortem\n\n## 1. The change\n\nCheck changes.\n\n"
        "## 2. Traps hypothesized\n\n| # | trap | label |\n|---|---|---|\n"
        + rows + "\n\n## 3. Recon protocol\n\n- **Files handed to the model:**\n  - `source.py`\n",
        encoding="utf-8",
    )
    output = AntemortemOutput(classifications=[
        Classification(id=f"t{i}", label="REAL", citation=f"source.py:{(i - 1) % 10 + 1}",
                       evidence_hash=compute_evidence_hash(f"line {(i - 1) % 10 + 1}"))
        for i in range(1, count + 1)
    ], decision="PROCEED_WITH_GUARDS")
    doc.with_suffix(".json").write_text(output.model_dump_json(), encoding="utf-8")
    original = Path.open
    reads = 0

    def observed(path, *args, **kwargs):
        nonlocal reads
        if path == source:
            reads += 1
        return original(path, *args, **kwargs)

    with patch.object(Path, "open", observed):
        if command == "metrics":
            metrics = compute_citation_metrics(output, root).to_json()
            code = 0
        else:
            result = CliRunner().invoke(app, [command, str(doc), "--repo", str(root), "--format", "json"])
            metrics = json.loads(result.stdout)["citation_metrics"]
            code = result.exit_code
    return dict(command=command, citations=count, source_lines=2000, source_opens=reads,
                verified=metrics["verified"], fabricated=metrics["fabricated"], exit_code=code)


def quality(root: Path) -> list[dict]:
    source = root / "quality.py"
    source.write_bytes(b"first\nsecond\n")
    cases = [
        ("plain_valid", "quality.py:2", {}, True),
        ("current_hash", "quality.py:2", {"evidence_hash": compute_evidence_hash("second")}, True),
        ("stale_hash", "quality.py:2", {"evidence_hash": compute_evidence_hash("old")}, False),
        ("stale_legacy_hash", "quality.py:2", {"evidence_sha256": "0" * 64}, False),
        ("wrong_snippet", "quality.py:2", {"evidence_snippet": "not in source"}, False),
        ("valid_snippet", "quality.py:2", {"evidence_snippet": "second"}, True),
        ("missing_file", "missing.py:2", {}, False),
        ("range_error", "quality.py:99", {}, False),
        ("traversal", "../outside.py:1", {}, False),
    ]
    observations = []
    for name, citation, binding, expected in cases:
        output = AntemortemOutput(classifications=[
            Classification(id="t1", label="REAL", citation=citation, **binding)
        ])
        metric = compute_citation_metrics(output, root)
        observations.append(dict(case=name, expected_verified=expected, observed_verified=metric.ok,
                                 correct=metric.ok == expected, reason=metric.findings[0].reason))
    source.write_bytes(b"first\vstill first\nsecond\n")
    output = AntemortemOutput(classifications=[Classification(
        id="t1", label="REAL", citation="quality.py:2", evidence_hash=compute_evidence_hash("second"),
    )])
    metric = compute_citation_metrics(output, root)
    observations.append(dict(case="vertical_tab_line_contract", expected_verified=True,
                             observed_verified=metric.ok, correct=metric.ok, reason=metric.findings[0].reason))
    return observations


def main() -> None:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        result = dict(package_version=__version__, python=sys.version, platform=platform.platform(),
                      method="deterministic Path.open count; one operation per workload; no elapsed-time claim",
                      workloads=[measure(root, n, command) for n in (1, 20, 200)
                                 for command in ("metrics", "lint", "gate")], quality_cases=quality(root))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
