# GitHub Action: antemortem gate in CI

`antemortem-cli` ships a composite GitHub Action (`action.yml` at the repo
root) so you can fail a pull request when an AI-written change plan is
blocked or cites fabricated `file:line` evidence — without writing any
glue code.

## Quick use

```yaml
# .github/workflows/antemortem.yml
name: Antemortem gate
on: pull_request
permissions:
  contents: read
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hibou04-ops/antemortem-cli@v0.11.0
        with:
          document: antemortem/feat.md
          repo: .
          allow: SAFE_TO_PROCEED,PROCEED_WITH_GUARDS
```

The action assumes the antemortem document (`antemortem/feat.md`) and its
companion run artifact (`antemortem/feat.json`, produced by
`antemortem run`) are present on the branch. The job fails when:

- `lint` fails (schema invalid, missing classifications, or a citation
  that does not resolve on disk), **or**
- the artifact's `decision` is not in the `allow` list.

A working example, including a variant that generates the artifact in CI
from a live provider against the PR's git diff, is at
[`examples/github_action_gate.yml`](../examples/github_action_gate.yml).

## Inputs

| Input | Default | Description |
|---|---|---|
| `document` | *(required)* | Path to the antemortem document to gate. |
| `repo` | `.` | Repository root to resolve cited files against. |
| `allow` | `SAFE_TO_PROCEED,PROCEED_WITH_GUARDS` | Comma-separated decisions allowed to ship. |
| `require-artifact` | `true` | Fail when no `<doc>.json` artifact is present. Set `false` for schema-only gating. |
| `version` | `0.11.0` | antemortem version to install from PyPI. Use `latest` for the newest release. |
| `python-version` | `3.12` | Python version to set up. |
| `summary-file` | `antemortem-gate-summary.json` | Where to write the machine-readable gate JSON. |

## Outputs

| Output | Description |
|---|---|
| `summary` | The full gate JSON summary (`schema: antemortem-gate-v1`) — verdict, decision, allowlist, and fabricated-citation metrics. |
| `decision` | The artifact's gated decision value. |

## How it works

The action runs `antemortem gate <document> --format json` so the verdict
is both human-readable in the job log and machine-readable for downstream
steps. The `--format json` summary embeds the fabricated-citation metrics:

```json
{
  "schema": "antemortem-gate-v1",
  "status": "fail",
  "decision": "DO_NOT_PROCEED",
  "allowlist": ["PROCEED_WITH_GUARDS", "SAFE_TO_PROCEED"],
  "exit_code": 4,
  "citation_metrics": {
    "schema": "antemortem-citation-metrics-v1",
    "verified": 3,
    "fabricated": 1,
    "fabrication_rate": 0.25,
    "ok": false,
    "...": "..."
  }
}
```

The gate's process exit code (frozen: `0` pass, `1` lint/validation
failure, `2` usage error, `4` policy-gate failure) drives the job result,
so no extra `if:` logic is needed to fail the build.

## Auditing an agent's actual patch

To gate the files an agent *actually changed* rather than a hand-listed
set, generate the artifact with `--diff` before gating:

```bash
antemortem run antemortem/feat.md --repo . --diff origin/main --strict
antemortem gate antemortem/feat.md --repo . --format json
```

`--diff` accepts `staged`, `working`, or any git ref/range (`HEAD~1`,
`origin/main`, `a..b`). See the example workflow's
`antemortem-run-then-gate` job.

---

This page is part of the [`antemortem-cli`](../README.md) documentation set.
