# CLI Exit Codes

`antemortem` uses stable process exit codes so local scripts and CI can branch
without parsing human-readable output.

| Code | Meaning | Typical cause |
|---:|---|---|
| 0 | success | Command completed and all requested checks passed. |
| 1 | validation failure | Document schema, citations, evidence hashes, doctor readiness, or artifact shape failed validation. |
| 2 | usage or configuration error | Invalid option value, unknown provider, missing API key, or invalid benchmark threshold name. |
| 3 | provider failure | Provider call failed or returned schema-invalid output before an artifact could be trusted. |
| 4 | policy gate failure | `gate` evidence/coverage/decision-consistency or allowlist checks blocked; `metrics` evidence policy failed; or `eval --fail-under` threshold was not met. |
| 70 | internal error | Reserved for unexpected tool bugs. Report the command, artifact, and traceback if seen. |

The constants live in `src/antemortem/exit_codes.py`.

`metrics` always rejects empty evidence, fabricated citations, and coverage below
its configured minimum (default 0.8). `gate` recomputes current disk evidence and
the decision; its coverage floor can only be strengthened above 0.8. `--allow`
does not override those checks. A missing artifact fails even when the legacy
`--no-require-artifact` flag is supplied; `lint` remains the schema-only command.

---

This page is part of the [`antemortem-cli`](../README.md) documentation set.
