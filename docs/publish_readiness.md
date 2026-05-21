# Publish Readiness Gate

Publishing is a separate manual action. The readiness gate answers only one
question: is the current checkout safe to publish right now?

```bash
python scripts/publish_readiness.py
```

The command does not upload to PyPI, create git tags, push commits, call the
GitHub API, or call provider APIs.

## Checks

The gate verifies:

- clean working tree, unless `--allow-dirty` is passed
- no existing git tag for the current version, unless `--skip-git-checks` is passed
- current `pyproject.toml` version has a `CHANGELOG.md` section
- existing `dist/` artifacts are absent or match the current version
- `python scripts/check_repo_consistency.py`
- `python scripts/generate_readme_claims.py --check`
- `antemortem eval benchmarks/golden_cases --json`
- `python -m build`
- fresh current-version artifacts in `dist/`
- `python -m twine check dist/*`
- `python scripts/smoke_wheel_install.py`
- `python scripts/release_audit.py`

## Failure Classes

| Class | Meaning |
| --- | --- |
| `PASS` | Check completed successfully. |
| `FAIL` | Repository or package behavior failed. Inspect the command output. |
| `ENVIRONMENT_BLOCKED` | Local environment blocked the check, such as socket policy preventing dependency resolution. |
| `TOOLING_MISSING` | Required local tooling such as `build`, `twine`, or `hatchling` is unavailable. |
| `NETWORK_BLOCKED` | A required packaging dependency could not be resolved because network access is disabled. |
| `GIT_STATE_BLOCKED` | Git state prevents a publish decision, such as a dirty tree or an existing release tag. |

A blocked packaging check is not release approval.

## JSON Output

Use JSON output for CI artifacts or release review notes:

```bash
python scripts/publish_readiness.py --json
```

For local diagnostics on a dirty worktree:

```bash
python scripts/publish_readiness.py --allow-dirty --continue-on-error --json
```

`--allow-dirty` and `--skip-git-checks` are local diagnostic options. Do not use
them as final publish approval.

## Network-Enabled Final Path

In a network-enabled release environment, run:

```bash
python -m pip install -e ".[dev]"
python scripts/publish_readiness.py
```

If the current sandbox cannot fetch `hatchling`, `build`, or `twine`, the gate
must fail with `ENVIRONMENT_BLOCKED` or `TOOLING_MISSING`. That result means
package build, metadata rendering, and installed-wheel behavior have not been
verified.
