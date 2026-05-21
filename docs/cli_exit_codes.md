# CLI Exit Codes

`antemortem` uses stable process exit codes so local scripts and CI can branch
without parsing human-readable output.

| Code | Meaning | Typical cause |
|---:|---|---|
| 0 | success | Command completed and all requested checks passed. |
| 1 | validation failure | Document schema, citations, evidence hashes, doctor readiness, or artifact shape failed validation. |
| 2 | usage or configuration error | Invalid option value, unknown provider, missing API key, or invalid benchmark threshold name. |
| 3 | provider failure | Provider call failed or returned schema-invalid output before an artifact could be trusted. |
| 4 | policy gate failure | `gate` decision allowlist blocked, or `eval --fail-under` threshold was not met. |
| 70 | internal error | Reserved for unexpected tool bugs. Report the command, artifact, and traceback if seen. |

The constants live in `src/antemortem/exit_codes.py`.
