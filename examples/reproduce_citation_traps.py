"""Keyless, offline reproduction of coverage and forged-decision traps.

Run from this checkout after installing its dependencies:
    python examples/reproduce_citation_traps.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typer.testing import CliRunner  # noqa: E402

from antemortem.citation_metrics import compute_citation_metrics  # noqa: E402
from antemortem.cli import app  # noqa: E402
from antemortem.schema import AntemortemOutput, Classification  # noqa: E402


def reproduce() -> list[dict]:
    results = []
    cases = [
        ("unresolved_denominator", 1, 9, "SAFE_TO_PROCEED", False),
        ("forged_safe_decision", 10, 0, "SAFE_TO_PROCEED", False),
        ("empty_evidence", 0, 0, "SAFE_TO_PROCEED", False),
        ("complete_verified_evidence", 10, 0, "SAFE_TO_PROCEED", True),
    ]
    with tempfile.TemporaryDirectory(prefix="antemortem-citation-traps-") as scratch:
        root = Path(scratch)
        (root / "source.py").write_text("value = 1\n", encoding="utf-8")
        for name, verified, unresolved, stored, should_pass in cases:
            output = AntemortemOutput(classifications=[
                *[Classification(id=f"t{i}", label="GHOST", citation="source.py:1")
                  for i in range(1, verified + 1)],
                *[Classification(id=f"t{i}", label="UNRESOLVED")
                  for i in range(verified + 1, verified + unresolved + 1)],
            ], decision=stored)
            if name == "forged_safe_decision":
                output.classifications = [
                    Classification(id=f"t{i}", label="REAL", citation="source.py:1")
                    for i in range(1, 11)
                ]
            # Keep the document's ten expected claims fixed, including empty
            # output: absent classifications cannot disappear from gate checks.
            rows = "\n".join(f"| {i} | risk {i} | trap | 50% | demo |" for i in range(1, 11))
            doc = root / f"{name}.md"
            doc.write_text("""---
name: citation-trap
date: 2026-11-02
template: basic
---
## 1. The change
Check a reviewed local source.
## 2. Traps hypothesized
| # | trap | label | P(issue) | notes |
|---|------|-------|----------|-------|
""" + rows + """
## 3. Recon protocol
- **Files handed to the model:**
  - `source.py`
""", encoding="utf-8")
            doc.with_suffix(".json").write_text(output.model_dump_json(), encoding="utf-8")
            metrics = compute_citation_metrics(output, root)
            run = CliRunner().invoke(app, ["gate", str(doc), "--repo", str(root), "--format", "json"])
            gate = json.loads(run.stdout)
            assert (run.exit_code == 0) is should_pass, (name, run.stdout)
            assert gate["deployment_authorized"] is should_pass
            results.append({
                "case": name, "verified": metrics.verified,
                "fabricated": metrics.fabricated, "unresolved": metrics.unresolved,
                "fabrication_rate": metrics.fabrication_rate,
                "effective_coverage": metrics.effective_coverage,
                "unresolved_rate": metrics.unresolved_rate,
                "stored_decision": stored, "computed_decision": gate["computed_decision"],
                "gate_exit_code": run.exit_code,
                "deployment_authorized": gate["deployment_authorized"],
            })
    return results


if __name__ == "__main__":
    print(json.dumps(reproduce(), indent=2, sort_keys=True))
