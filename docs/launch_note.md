# Launch Note

`antemortem-cli` is a CLI and CI tool for checking implementation-plan risks
before writing the diff. You write the spec, traps, and files to inspect; the
tool classifies each risk as `REAL`, `GHOST`, `NEW`, or `UNRESOLVED` and requires
repo-grounded citations for non-`UNRESOLVED` findings.

This is not an AI code review replacement. It runs before code review, while
the implementation plan is still cheap to change.

## What Is Verifiable

- Pre-implementation risk classification: see [Trust Model](trust_model.md).
- Repo-grounded citations and evidence-bound checks: run `antemortem lint`.
- Offline golden benchmarks: run `antemortem eval benchmarks/golden_cases --json`.
- Release hygiene checks: run `python scripts/release_audit.py`.
- Public claim drift checks: run `python scripts/check_repo_consistency.py`.

## Reproduce Locally

```bash
pip install antemortem
antemortem --version
antemortem --help
```

Run the provider-free demo replay:

```bash
PYTHONIOENCODING=utf-8 python examples/demo_replay.py
```

Run offline verification commands from a checkout:

```bash
antemortem doctor examples/demo_recon.md --repo . --json
antemortem lint examples/demo_antemortem.md --repo .
antemortem eval benchmarks/golden_cases --json
python scripts/check_repo_consistency.py
python scripts/generate_readme_claims.py --check
```

Run release checks before publishing:

```bash
python scripts/release_audit.py
```

Run the post-release dry run before upload, or the full post-release check after
upload:

```bash
python scripts/post_release_check.py --version 0.10.0 --skip-pypi-network
python scripts/post_release_check.py --version 0.10.0
```

## Boundaries

- No superiority claim is made here.
- No adoption or production-usage claim is made here.
- Benchmark metrics are repo-local fixtures, not general model scores.
- Citations prove that a claim is grounded to source text; they do not prove
  absolute truth.
- Provider behavior can vary by vendor, model, endpoint, refusal mode, and
  structured-output fidelity.
- Normal offline checks do not require provider API keys. `antemortem run` does
  require a configured provider unless a test supplies a stub.

## Links

- [Trust Model](trust_model.md)
- [Evidence-bound citations](../README.md#evidence-bound-citations)
- [Benchmark-backed claims](../README.md#benchmark-backed-claims)
- [Repository self-checks](../README.md#repository-self-checks)
- [Release Hygiene](release_hygiene.md)
- [Post-Release Verification](post_release_verification.md)
