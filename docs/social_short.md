antemortem-cli is a CLI for pre-implementation risk classification.

You write the implementation plan, traps, and repo files to inspect. The tool
classifies risks as REAL, GHOST, NEW, or UNRESOLVED, then `lint` verifies schema,
citations, evidence snippets, and evidence hashes against disk.

Reproduce the offline checks:

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
antemortem lint examples/demo_antemortem.md --repo .
antemortem eval benchmarks/golden_cases --json
python scripts/check_repo_consistency.py
```

Boundaries: not an AI code review replacement, no adoption claim, no superiority
claim. Benchmarks are repo-local fixtures. Citations prove grounding, not
absolute truth.

Docs: [launch_note.md](launch_note.md), [trust_model.md](trust_model.md),
[release_hygiene.md](release_hygiene.md).
