# antemortem 0.10.0

## Summary

Draft release notes for `antemortem` `0.10.0`. This draft is not publish-ready until package build, `twine check`, wheel smoke install, and release audit pass.

## Install

After publication:

```bash
pip install antemortem==0.10.0
```

## Quick Smoke Test

From a clean checkout after installing the package:

```bash
antemortem --version
antemortem --help
antemortem doctor examples/demo_recon.md --repo . --json
antemortem eval benchmarks/golden_cases --json
```

## Added

- Added repository consistency checks for README drift across versions, command lists, decision labels, provider matrix rows, package names, and generated claim blocks.
- Added generated README claim blocks in English and Korean, backed by `pyproject.toml`, the Typer command registry, decision enums, provider capabilities, pytest collection, and offline benchmark output.
- Added offline golden benchmark harness with adversarial trust cases for classification labels, citation validity, schema parsing, decision accuracy, critic-pass behavior, and filesystem safety.
- Added `doctor`, `eval`, and `evidence` CLI commands for provider-free preflight, offline benchmark evaluation, and local evidence hash maintenance.
- Added evidence-bound citation fields and strict evidence linting for citation hash/snippet verification.
- Added release hygiene automation: release audit, wheel smoke install, release-candidate freeze check, post-release verification, deterministic release notes generation, claim ledger, scope freeze check, and GitHub issue/PR templates.
- Added a GitHub Release draft generator that renders markdown only and includes verification status, benchmark metrics, links, and packaging blockers without publishing.
- Added a publish readiness gate that separates final local verification from the manual publish action and fails on blocked packaging checks.
- Added post-release verification dry-run/skip-network status reporting and cautious download analytics notes for public release follow-up.
- Added provider capability registry and offline provider contract tests for Anthropic, OpenAI, Gemini, and OpenAI-compatible endpoints.
- Added trust model, provider compatibility, example gallery, launch notes, toolkit positioning, release hygiene, and scope freeze documentation.

## Changed

- README variants now foreground pre-diff risk classification, the doctor/run/lint/eval/gate trust loop, generated source-of-truth claims, benchmark-backed claims, evidence-bound citations, release checks, and CLI examples.
- Public version, test count, command list, decision labels, provider support, and benchmark claims are now checked against source-backed or generated inputs.
- CI is documented and tested as a deterministic offline trust-check path with a separate wheel smoke job and no normal provider API key requirement.
- Release packaging checks now classify missing local tooling and sandbox/network blocks as explicit non-passing states.
- The development extra now declares `hatchling`, `build`, and `twine` so local release verification can run after `python -m pip install -e ".[dev]"`.

## Fixed

- Prevented release preparation from reusing an already-published version by requiring version, changelog, README, generated claims, and release notes to align before release.
- Added guardrails against public documentation drift, unimplemented command promises, unbacked roadmap language, stale provider matrices, and current-version mismatch.
- Hardened wheel smoke and release audit paths so packaging verification cannot pass unless a wheel is actually built, installed, and smoke-tested.

## Verification Commands

- `pytest -q`
- `python scripts/check_repo_consistency.py`
- `python scripts/generate_readme_claims.py --check`
- `antemortem eval benchmarks/golden_cases --json`
- `python -m build`
- `python -m twine check dist/*`
- `python scripts/smoke_wheel_install.py`
- `python scripts/release_audit.py --json`

## Verification Status

| Check | Command | Status | Classification | Exit |
| --- | --- | --- | --- | --- |
| pytest | `pytest -q` | passed | `PASSED` | `0` |
| consistency checker | `python scripts/check_repo_consistency.py` | passed | `PASSED` | `0` |
| generated claims check | `python scripts/generate_readme_claims.py --check` | passed | `PASSED` | `0` |
| golden benchmark eval | `antemortem eval benchmarks/golden_cases --json` | passed | `PASSED` | `0` |
| package build | `python -m build` | failed | `TOOLING_MISSING` | `1` |
| twine check | `python -m twine check dist/*` | failed | `TOOLING_MISSING` | `1` |
| wheel smoke install | `python scripts/smoke_wheel_install.py` | failed | `TOOLING_MISSING` | `1` |
| release audit | `python scripts/release_audit.py --json` | failed | `ENVIRONMENT_BLOCKED` | `1` |

## Benchmark Snapshot

- Source: `antemortem eval benchmarks/golden_cases --json`
- Provenance: generated machine-readable benchmark JSON.
- Totals: `cases=16`, `citation_checked=14`, `label_total=16`, `schema_success=15`
- Metrics: `citation_valid_rate=0.643`, `critic_flip_rate=0.333`, `decision_accuracy=1.000`, `false_ghost_rate=0.000`, `false_real_rate=0.000`, `high_severity_block_rate=1.000`, `new_trap_precision=1.000`, `schema_parse_success_rate=0.938`, `trap_label_accuracy=1.000`, `unresolved_rate=0.250`

## Known Limitations

- Packaging verification is incomplete. Do not publish until package build, `twine check`, wheel smoke install, and release audit pass.
- `python -m build` did not pass: `TOOLING_MISSING`. Run the documented release verification path in a network-enabled environment.
- `python -m twine check dist/*` did not pass: `TOOLING_MISSING`. Run the documented release verification path in a network-enabled environment.
- `python scripts/smoke_wheel_install.py` did not pass: `TOOLING_MISSING`. Run the documented release verification path in a network-enabled environment.
- `python scripts/release_audit.py --json` did not pass: `ENVIRONMENT_BLOCKED`. Run the documented release verification path in a network-enabled environment.

## Links

- [README](../README.md)
- [CHANGELOG](../CHANGELOG.md)
- [Trust model](trust_model.md)
- [Release hygiene](release_hygiene.md)
- [Benchmark-backed claims](../README.md#benchmark-backed-claims)
