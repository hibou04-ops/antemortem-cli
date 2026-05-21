# Toolkit Positioning

`antemortem-cli` is the CLI and CI verification tool in this toolkit. Its scope is intentionally narrow: pre-implementation reconnaissance, risk classification before code changes, and citation/evidence verified CLI artifacts.

This repository does not host a dashboard, SaaS control plane, or general agent framework.

## This Repository

Use `antemortem-cli` when the next useful question is:

> Before writing the diff, which risks in this implementation plan are `REAL`, `GHOST`, `NEW`, or `UNRESOLVED`, and what source lines support that answer?

The local trust boundary is:

- `doctor` previews the files, parsed traps, and payload before any provider call.
- `run` produces the structured recon artifact.
- `lint` verifies schema, citations, path bounds, snippets, and evidence hashes against disk.
- `evidence` recomputes or fills missing local evidence hashes.
- `eval` measures behavior against committed offline golden cases.
- `gate` enforces the decision policy in CI.

## Related Tools

These names describe adjacent roles. They are not claims about adoption, production usage, or external validation.

| Tool | Neutral role | Boundary |
|---|---|---|
| `omegaprompt` | Calibration / optimization layer | Prompt and workflow calibration. It does not replace `antemortem lint` or `gate`. |
| `omega-lock` | Audit / post-optimization lock layer | Audit and lock criteria after calibration work. It is not the pre-diff risk classifier in this repository. |
| `mini-omega-lock` | Empirical live API preflight | Live API behavior checks when network/provider access is explicitly available. It is outside the deterministic offline test path here. |
| `mini-antemortem-cli` | Deterministic analytical preflight | If used, a narrow analytical preflight surface. It is not the packaged CLI/CI tool maintained in this repository. |
| `omega-plc.com` | Link-only external surface | [https://www.omega-plc.com/](https://www.omega-plc.com/) is referenced only as an external surface. This repository makes no SaaS capability claim from that link. |

## Composition

A conservative composition is:

1. Use `omegaprompt` where the work is prompt or workflow calibration.
2. Use a `mini-*` preflight only when its narrower preflight matches the question.
3. Use `antemortem-cli` before code changes to classify plan risks with citations and evidence.
4. Use `omega-lock` after optimization/audit work when criteria or audit state need to be locked.

Each tool owns a different stage. This repository remains focused on CLI artifacts that can be checked locally and in CI.

## Claim Boundaries

This document does not claim:

- enterprise adoption
- production usage
- external validation
- comparative quality over other tools
- SaaS behavior beyond the link-only reference above

Public claims in this repository should remain backed by source-of-truth generation, deterministic tests, committed artifacts, or reproducible commands.

## Link Verification

The repository does not perform network link checks in the offline CI path. Local positioning links and the external allowlist are covered by:

```bash
python -m pytest tests/test_toolkit_positioning_docs.py -q
```

Run the broader repository check with:

```bash
python scripts/check_repo_consistency.py
```
