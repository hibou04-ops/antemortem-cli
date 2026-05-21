# Release Candidate Freeze Checklist

Run this before cutting a release-candidate branch or tag:

```bash
python scripts/rc_freeze_check.py
```

For local development only, use:

```bash
python scripts/rc_freeze_check.py --allow-dirty --continue-on-error
python scripts/rc_freeze_check.py --json
```

`--allow-dirty` is not a release setting. It exists so a developer can see the full inventory before committing.

## What It Checks

1. `pytest -q` passed, or the passing step is represented in `python scripts/release_audit.py --json`.
2. `python scripts/check_repo_consistency.py` passed.
3. `python scripts/generate_readme_claims.py --check` passed.
4. `python scripts/release_audit.py` passed, or the checker is running under release audit as the parent command.
5. `antemortem eval benchmarks/golden_cases --json` produced machine-readable benchmark metrics.
6. `README.md`, `README_KR.md`, `EASY_README.md`, and `EASY_README_KR.md` reference `docs/generated/claims.md` and `docs/generated/claims_kr.md`.
7. `CHANGELOG.md` has an entry for the current `pyproject.toml` version.
8. `pyproject.toml` version is release-shaped, not a dev placeholder such as `0.0.0`, `dev`, `snapshot`, or local `+` metadata.
9. `dist/` artifacts are absent or newer than checked source files.
10. No unallowlisted `TODO` or `FIXME` appears in public README variants.

## TODO/FIXME Allowlist

Avoid TODO/FIXME in public README text. If a marker is intentional, add `scripts/rc_freeze_allowlist.toml`:

```toml
[[allow]]
path = "README.md"
contains = "TODO marker text that is intentional"
reason = "Why this public marker is acceptable for this RC."
```

The checker only matches explicit text. Broad allowlist entries should not be used for release candidates.

## Failure Handling

Every failure prints:

- the failed check
- the command or file that failed
- the next command or file to inspect

Use `--continue-on-error` to collect the full failure inventory before fixing.
