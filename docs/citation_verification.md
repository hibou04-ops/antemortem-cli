# Citation verification: I/O, evidence and migration

## Scope

`verified` establishes a real repo-contained file/line range and agreement with supplied evidence hashes/snippets. It does not establish semantic entailment, claim truth or program correctness. For compatibility the JSON bucket remains `fabricated`; its reason distinguishes malformed paths, missing files, bad ranges, stale hashes, absent snippets, read failures and observed concurrent edits. None of these diagnoses the model's intent. `unresolved` remains separate.

## One operation, bounded source reuse

`CitationVerifier(repo_root)` reuses file content within one command. CLI lint/gate JSON share that reader with their metrics; metrics, runtime audit and CLI/MCP hash attachment also reuse it. A fresh command or an ordinary helper call creates a fresh reader. There is no global cache to return a prior command's verification success.

Every lookup resolves the path under the repo root, checks regular-file status and compares device/file identity, size and nanosecond mtime. POSIX also compares ctime. Python 3.12 Windows `stat` and `fstat` may expose different legacy ctime values; these are deliberately not compared across Windows handles. Before/after reads, descriptor metadata, path metadata and resolved location are checked. A detected edit invalidates that file for the rest of the operation. Permission/read errors become a failed verification, not a successful empty evidence check.

The default 8 MiB budget covers cached text and line tuples, not result output or per-file identity metadata. Files that exceed the budget are streamed; only the requested range may be retained if it fits. Different ranges in an oversized file may need another scan. Cache reuse therefore improves repeated references that fit the budget; it is not a universal constant-memory or constant-I/O claim. Limits on provider payloads and citation evidence ranges remain unchanged.

This is ordinary concurrent-edit detection, not an atomic repository snapshot or protection against an adversary restoring all file metadata. Freeze the input checkout when an atomic, reproducible audit is required.

## Reproducible comparison

Baseline: public `antemortem==0.11.2`, commit `95a49e75a03b2289c1015b72b09cbc4cfbae8310`. Baseline HEAD and latest release were identical; no unpublished change is credited. Baseline and modified package run in separate virtual environments with Python 3.12.10 on Windows 11. No provider is called.

[`scripts/benchmark_citation_io.py`](../scripts/benchmark_citation_io.py) fixes the workloads before running them: a 2,000-line UTF-8 file, 1/20/200 findings, ten distinct cited ranges, matching hashes, one operation per input, and instrumentation of actual `Path.open` calls to the source file. It compares the complete metrics/lint/gate command paths, including JSON metrics. Source-write setup, artifact/document reads and installation are excluded from the source-open counter. No timing benchmark or speed ratio is claimed.

| Citations | metrics source opens, before → after | lint/gate JSON source opens, before → after |
|---:|---:|---:|
| 1 | 2 → 1 | 4 → 1 |
| 20 | 40 → 1 | 80 → 1 |
| 200 | 400 → 1 | 800 → 1 |

All workloads preserve verified counts and exit 0. Ten known development regression cases change from 7 correct to 10: metrics previously accepted a wrong snippet and stale legacy hash, and Unicode vertical tabs made line verification disagree with evidence selection. These are cases used during development, not a blind evaluation or a real-world accuracy rate. Mutation, deletion, movement, permission errors, invalid UTF-8, LF/CRLF/CR, cache eviction and symlink escape have separate regression coverage. Symlink tests may skip where OS permissions prohibit creating one; the existing Linux CI runs that case.

Raw results and environment details: [`citation_io_results.json`](citation_io_results.json). Run the script using each installed environment's Python from outside the source checkout to reproduce the comparison.

## Compatibility and migration

- JSON schemas `antemortem-citation-metrics-v1`, `antemortem-lint-v1`, `antemortem-gate-v1`, existing fields, MCP tool names and CLI exit-code meanings remain.
- metrics now checks supplied legacy `evidence_sha256`, snippets and bound-range limits using the same rules as lint. A previously accepted invalid binding may become `fabricated`. Runtime citation audit also refuses such evidence before selecting a safe decision. Review the reason and regenerate/re-review the artifact; do not loosen thresholds to preserve a false pass.
- A file's lines are separated by LF, CRLF or CR for both verification and evidence hashing. VT, FF and Unicode paragraph separators inside a line no longer shift cited text. Regenerate old artifacts affected by those characters.
- Missing evidence fields on older artifacts remain permitted unless `--strict-evidence` is requested. Strict mode still requires modern `evidence_hash`.
- `lint` and `gate` exit 1 on validation failure; `gate` exits 4 on policy rejection and 2 for invalid options. `metrics` without `--fail-over` reports even failed evidence with exit 0; `--fail-over 0` turns any fabricated count into exit 4. A reporting command's successful execution is not a quality pass.
- No runtime `omega-lock` dependency is added; its pinned CI source-citation relationship is unchanged.

```python
from pathlib import Path
from antemortem.citations import CitationVerifier, verify_citation

root = Path(".")
verifier = CitationVerifier(root)
result = verify_citation("src/antemortem/citations.py:1", root, verifier=verifier)
assert result.ok, result.reason
```

Reuse a verifier only for one logical audit and its bound repo root. Create a new one after editing files.
