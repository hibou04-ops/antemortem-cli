# Release Hygiene

Run the local release audit before publishing:

```bash
python scripts/release_audit.py
```

The audit is intentionally local. It does not upload packages and does not call provider APIs. It stops on the first failure by default and prints the exact failing command with its exit code.

## Steps

The audit runs:

```bash
python -m pip install -e ".[dev]"
pytest -q
python scripts/check_repo_consistency.py
python scripts/generate_readme_claims.py --check
python scripts/check_claim_ledger.py
antemortem eval benchmarks/golden_cases --json
python -m antemortem.cli --help
antemortem --version
python -m build
python -m twine check dist/*
python scripts/smoke_wheel_install.py
```

Use full inventory mode when preparing a release branch:

```bash
python scripts/release_audit.py --continue-on-error
```

Use JSON output for CI artifacts:

```bash
python scripts/release_audit.py --json
```

## Scope Freeze

The next release is frozen as a verification and release-hygiene release. New
feature work should be deferred unless it fixes failing tests, broken packaging,
stale README claims, safety regressions, or release-blocking documentation drift.

Before release-candidate review, run:

```bash
python scripts/scope_freeze_check.py
```

See [Scope Freeze](scope_freeze.md).

## Release Notes

Generate release notes before publishing:

```bash
python scripts/generate_release_notes.py --from <previous-ref> --to <release-ref> --output docs/release-notes/v<version>.md
```

If git metadata is unavailable, pass explicit file input:

```bash
python scripts/generate_release_notes.py --version <version> --files A:scripts/example.py M:README.md
```

The generator does not infer semantic changes from filenames. It renders semantic bullets from `CHANGELOG.md`, changed-file inventory from git or `--files`, benchmark metrics from generated benchmark JSON, and the consistency checker result from `python scripts/check_repo_consistency.py`. See [Release Notes Template](release_notes_template.md).

Generate a GitHub Release draft without publishing:

```bash
python scripts/generate_github_release_draft.py --output docs/github_release_draft.md
```

The draft is markdown only. It does not call the GitHub API, create tags, upload artifacts, or mark a release publish-ready unless package build, `twine check`, wheel smoke install, and release audit have passed in the generated status table.

Run the publish readiness gate before any manual publish action:

```bash
python scripts/publish_readiness.py
```

This gate is stricter than a draft generator. It fails if git state, README/generated claims, benchmark evaluation, package build, `twine check`, wheel smoke install, or release audit are not actually verified. See [Publish Readiness Gate](publish_readiness.md).

## Packaging Tooling

Final package verification needs the build backend and release tooling installed locally:

```bash
python -m pip install -e ".[dev]"
```

The `dev` extra includes `hatchling`, `build`, and `twine`. `hatchling` is also declared in `build-system.requires` because isolated PEP 517 builds resolve the backend independently. Do not treat a sandbox that cannot fetch those tools as release approval; that state is `ENVIRONMENT_BLOCKED` or `TOOLING_MISSING`, not a pass.

Run the network-enabled package verification path before any publish action:

```bash
python -m pip install -e ".[dev]"
python -m build
python -m twine check dist/*
python scripts/smoke_wheel_install.py
```

The first three commands exercise the normal isolated build and PyPI rendering check. The smoke script then builds a wheel with `python -m build --wheel --no-isolation` after the dev tooling has been installed, creates a fresh temporary virtual environment, installs the local wheel with `pip --no-index --no-deps`, and runs installed CLI commands. This no-isolation smoke path is intentional: it verifies the wheel entrypoint without making the temporary venv contact a package index.

## Post-Release Verification

Before publishing, use dry run mode. It does not contact PyPI or GitHub and it
does not prove the release is live:

```bash
python scripts/post_release_check.py --version <version> --dry-run --json
```

After publishing, run the network-enabled post-release check from a clean
checkout:

```bash
python scripts/post_release_check.py --version <version> --json
```

This verifies PyPI metadata, the GitHub release tag, a clean PyPI install, CLI
version/help, and offline `doctor` / `lint` / `eval` commands without provider
API keys. Use `--skip-network` only for local preflight runs before upload. See
[Post-Release Verification](post_release_verification.md).

## Dist Isolation

The audit temporarily moves any existing `dist/` directory aside before `python -m build`, runs `python -m twine check dist/*` against the newly built artifacts, removes the audit-built `dist/`, and restores the original `dist/`.

This keeps release checks reproducible without deleting pre-existing local artifacts.

## PyPI Rendering Check

Check the PyPI long description before publishing:

```bash
python -m build
python -m twine check dist/*
```

`twine check` validates the package metadata and README rendering used by PyPI. This is a local verification step only; it does not upload artifacts.

## CI Trust Checks

The GitHub Actions workflow is named `CI`; the README badge points at `.github/workflows/ci.yml`. The `trust-checks` job runs on Ubuntu and Windows across the supported Python versions: install `.[dev]`, `pytest -q`, repository consistency, generated README claim check, offline benchmark, `python -m build`, and `python -m twine check dist/*`.

The offline benchmark JSON is uploaded as a workflow artifact when GitHub artifact upload is available. Wheel installation is verified in the separate `wheel-smoke` job. Normal CI does not configure provider API keys; any live-provider tests must remain explicit opt-in and skipped by default.

## Wheel Smoke Test

Run the installed-wheel smoke test directly when changing packaging metadata:

```bash
python scripts/smoke_wheel_install.py
```

The smoke test builds a wheel with `python -m build --wheel --no-isolation`, creates a temporary virtual environment, installs the wheel with `pip --no-index --no-deps`, and runs:

```bash
antemortem --version
antemortem --help
antemortem doctor examples/demo_recon.md --repo . --json
antemortem eval benchmarks/golden_cases --json
```

The wheel smoke test treats `examples/`, `benchmarks/`, and other repository fixtures as repository fixtures, not wheel package data. The wheel must provide the installed CLI and package modules; fixture directories are consumed by explicit filesystem paths from the checkout. Generated docs under `docs/generated/` and release notes under `docs/release-notes/` are repository documentation for claim checks and release review; they are not imported package data and are intentionally not included in the wheel.

## Publish Boundary

This command is a readiness check only. Publishing remains a separate explicit action outside this script.
