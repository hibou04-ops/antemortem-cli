# Trust Model

`antemortem-cli` is a CLI and CI tool for checking implementation-plan risks
against repository evidence before a diff exists. It is useful only when the
input document names the change, the traps, and the files the model may inspect.

## What It Verifies

- The recon document parses: frontmatter, spec, trap table, and file list.
- Requested files stay inside the repository root and pass the file-safety policy.
- Provider output conforms to the Pydantic schema before it is written.
- Non-`UNRESOLVED` findings cite disk-verifiable `path:line` or `path:line-line` ranges.
- Optional `evidence_snippet` and `evidence_hash` fields match the cited source text.
- The decision gate is derived from the artifact and can be enforced in CI.
- Offline golden cases still produce the measured repo-local benchmark metrics.

## What It Does Not Verify

- It does not prove the model found every risk.
- It does not prove the implementation plan is strategically correct.
- It does not prove runtime behavior, security, performance, or platform behavior.
- It does not prove a cited claim is absolutely true; citations prove grounding to a
  source location, not total correctness.
- It does not make provider behavior identical across vendors or models.
- It does not make repo-local benchmark metrics generalize to other repositories.

## Why You Write The Traps First

The user writes the traps before the model sees the code. That is the anchoring
control. The model is asked to classify the user-declared risks as `REAL`,
`GHOST`, or `UNRESOLVED`, and it may add `NEW` findings only when it can cite
repository evidence. This keeps the model from framing the risk list from
scratch and makes omissions visible: if a trap was not named and the model did
not surface it, the tool cannot claim it was checked.

## Citation Validation

`lint` treats provider citations as claims to verify, not facts. It parses
`path:line` and `path:line-line` citations, resolves the path under `--repo`,
follows symlinks or reparse points, rejects paths that escape the repository
root, checks that the target is a regular file, and verifies the line range is
within bounds. `UNRESOLVED` classifications must have `citation: null`.

## Evidence Hashes

Line bounds prove that a cited location exists. Evidence hashes reduce drift by
binding the artifact to the cited source text. The tool normalizes cited text to
LF line endings, strips trailing whitespace only, computes SHA-256 locally, and
stores it as `sha256:<hex>`. Later, `lint --strict-evidence` recomputes the hash
and fails when the cited source has changed. The model does not need to invent
hashes; `antemortem run` and `antemortem evidence --write-missing` compute them
locally after citation validation.

## Offline Golden Benchmarks

The benchmark harness uses committed golden cases and stored provider outputs.
It makes no network calls and does not construct provider SDK clients. The goal
is regression detection: classification labels, citation validity, decision
quality, schema parsing, and critic-pass effects are measured against repo-local
fixtures. These metrics support local claims only; they are not comparative
quality claims about other tools or performance claims for arbitrary
repositories.

## Provider Output Is Not Trusted Until Linted

Provider output can be malformed, partial, safety-blocked, or overconfident.
`run` validates the schema and classification coverage before writing an
artifact. The artifact still must pass `lint` before it should be used as
evidence in CI, because only `lint` reopens the repository and verifies the
citations, evidence snippets, and hashes against disk.

## CI Use

Use the commands as separate checks:

```bash
antemortem doctor antemortem/my-feature.md --repo .
antemortem lint antemortem/my-feature.md --repo . --strict-evidence
antemortem eval benchmarks/golden_cases --json
antemortem gate antemortem/my-feature.md --repo .
```

`doctor` is a provider-free preflight. `lint` verifies schema, citations, and
evidence. `eval` checks the offline benchmark harness. `gate` enforces the
decision policy from the artifact. Normal CI should not require provider API
keys unless it intentionally runs live `antemortem run`.

## Known Limitations

- The model may miss risks.
- Benchmark cases are repo-local fixtures, not general-purpose model scores.
- Citations prove grounding to source text, not absolute truth.
- Provider behavior may vary by vendor, model, endpoint, refusal mode, and
  structured-output fidelity.
