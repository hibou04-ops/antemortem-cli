"""End-to-end demo: walk through a real antemortem document and run lint.

Prints a curated walk-through of `examples/demo_antemortem.md` (and its
companion `.json` audit artifact) showing each phase of the discipline:

  traps -> classifications -> decision -> lint citation verification

All citations in the demo doc point to real lines in this repo's source.
Lint runs as a real subprocess and verifies every citation against disk.

Run this directly to see the full demo at machine speed::

    PYTHONIOENCODING=utf-8 python examples/demo_recon.py

For the screencast cadence, capture once then replay paced::

    PYTHONIOENCODING=utf-8 python examples/demo_recon.py > examples/_demo_output.txt 2>&1
    PYTHONIOENCODING=utf-8 python examples/demo_replay.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DOC = HERE / "demo_antemortem.md"
ARTIFACT = HERE / "demo_antemortem.json"


def _section(label: str) -> None:
    print(f"\n---- {label} ----")


def main() -> int:
    if not DOC.exists() or not ARTIFACT.exists():
        print(f"ERROR: missing {DOC.name} or {ARTIFACT.name}", file=sys.stderr)
        return 1

    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    print("=== antemortem-cli demo ===")
    print(f"document: {DOC.relative_to(REPO).as_posix()}")
    print("recon:    4 traps hypothesized -> classified against source")

    _section("Traps (pre-recon)")
    print("t1  Demo couples to a specific provider                  [trap]")
    print("t2  Citation regex rejects Windows backslash paths      [worry]")
    print("t3  Decision enum drifts from schema                     [trap]")
    print("t4  Lint slows on large repos                         [unknown]")

    _section("Classifications (post-recon)")
    for c in payload["classifications"]:
        cite = c["citation"] if c["citation"] else "(no citation -- UNRESOLVED)"
        sev = c.get("severity") or "n/a"
        print(f"{c['id']:4} {c['label']:11} {cite:42} severity={sev}")

    _section("New finding (model surfaced something the user missed)")
    for nt in payload["new_traps"]:
        print(f"{nt['id']:8} {nt['label']:5} {nt['citation']:42} severity={nt['severity']}")
        print(f"           note: {nt['note']}")

    _section("Decision")
    print(f"verdict:   {payload['decision']}")
    print("rationale: " + payload["decision_rationale"])

    _section("Lint (re-verify every citation against disk)")
    print(f"$ antemortem lint {DOC.relative_to(REPO).as_posix()} --repo .")
    import os as _os
    _env = dict(_os.environ)
    _env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [
            sys.executable, "-m", "antemortem", "lint",
            str(DOC), "--repo", str(REPO),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=_env,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    for line in out.splitlines():
        print(line)
    print("  - schema: frontmatter, spec, traps, files all present")
    print("  - classifications: 4/4 trap ids matched")
    print("  - citations: 4/4 paths exist, all line ranges in bounds")
    print("  - UNRESOLVED: citation correctly null (t4)")

    _section("Decision gate (four-level enum)")
    print("SAFE_TO_PROCEED       no REAL findings, low UNRESOLVED, perfect gates")
    print("PROCEED_WITH_GUARDS   REAL findings exist, every one has remediation     <- THIS RUN")
    print("NEEDS_MORE_EVIDENCE   too many UNRESOLVED relative to total findings")
    print("DO_NOT_PROCEED        high-severity REAL without remediation, OR critic CONTRADICTED")

    _section("Install")
    print("pip install antemortem")
    print("Apache 2.0 - 111 tests - Anthropic / OpenAI / local providers")
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
