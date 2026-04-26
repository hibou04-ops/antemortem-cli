"""Paced replay of the antemortem-cli demo for screencast recording.

Reads `_demo_output.txt` (real output of `examples/demo_recon.py`) and reprints
each line with deliberate pauses so a 60-second video can capture each phase.
No fabricated data — the file is a verbatim capture of the real demo run, and
every citation in the doc was verified by `antemortem lint`.

Total wall time tuned for ~60 seconds. Adjust SECTION_PAUSES to taste.

Usage::

    PYTHONIOENCODING=utf-8 python examples/demo_replay.py

Regenerate the capture before re-recording if you change the demo doc::

    PYTHONIOENCODING=utf-8 python examples/demo_recon.py > examples/_demo_output.txt 2>&1

For higher-quality recording (no scrollback flicker), open a fresh terminal,
size it to 110x35 minimum, set font size 16-18pt, then run.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Pacing rules — substring -> pause AFTER printing that line (seconds).
# First match wins. Order matters.
SECTION_PAUSES: list[tuple[str, float]] = [
    # Cue 1 (0:00-0:04) — hook
    ("=== antemortem-cli demo ===", 0.5),
    ("document: examples/demo_antemortem.md", 0.5),
    ("recon:    4 traps", 2.5),
    # Cue 2 (0:04-0:12) — enumerate traps
    ("Traps (pre-recon)", 0.6),
    ("[trap]", 0.7),
    ("[worry]", 0.7),
    ("Decision enum drifts", 0.7),  # second [trap] line
    ("[unknown]", 4.0),
    # Cue 3 (0:12-0:18) — REAL / GHOST / NEW / UNRESOLVED
    ("Classifications (post-recon)", 0.5),
    ("t1   GHOST", 0.9),
    ("t2   REAL", 1.8),  # extra dwell — REAL is the headline
    ("t3   GHOST", 0.9),
    ("t4   UNRESOLVED", 2.0),
    # Cue 4 (0:18-0:25) — model surfaced new finding
    ("New finding", 0.6),
    ("t_new_1  NEW", 1.2),
    ("note: The decision field", 4.5),
    # Cue 5 (0:25-0:30) — decision
    ("---- Decision ----", 0.4),
    ("verdict:   PROCEED_WITH_GUARDS", 1.5),
    ("rationale: One high-severity", 3.0),
    # Cue 6-7 (0:30-0:42) — lint re-verifies citations on disk
    ("Lint (re-verify", 0.5),
    ("$ antemortem lint", 1.2),
    ("PASS — demo_antemortem.md", 2.5),
    ("schema: frontmatter", 1.4),
    ("classifications: 4/4 trap ids", 1.4),
    ("citations: 4/4 paths exist", 2.0),
    ("UNRESOLVED: citation correctly null", 3.0),
    # Cue 8 (0:42-0:52) — four-level gate
    ("Decision gate (four-level enum)", 0.5),
    ("SAFE_TO_PROCEED", 1.5),
    ("PROCEED_WITH_GUARDS", 2.5),  # this is THIS RUN
    ("NEEDS_MORE_EVIDENCE", 1.5),
    ("DO_NOT_PROCEED", 2.5),
    # Cue 9 (0:52-1:00) — install
    ("---- Install ----", 0.4),
    ("pip install antemortem", 2.5),
    ("Apache 2.0", 4.0),
]

DEFAULT_PAUSE = 0.05


def _pause_for(line: str) -> float:
    for pattern, pause in SECTION_PAUSES:
        if pattern in line:
            return pause
    return DEFAULT_PAUSE


def main() -> int:
    here = Path(__file__).resolve().parent
    capture = here / "_demo_output.txt"
    if not capture.exists():
        print(f"ERROR: capture missing at {capture}", file=sys.stderr)
        print(
            "Regenerate with: "
            "PYTHONIOENCODING=utf-8 python examples/demo_recon.py "
            "> examples/_demo_output.txt 2>&1",
            file=sys.stderr,
        )
        return 1

    text = capture.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    started = time.perf_counter()
    for line in lines:
        print(line, flush=True)
        time.sleep(_pause_for(line))

    elapsed = time.perf_counter() - started
    time.sleep(0.5)
    print(f"\n[demo_replay] elapsed: {elapsed:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
