# Citation verification: I/O, evidence and migration

## Scope

`verified` establishes a real repo-contained file/line range and agreement with supplied evidence hashes/snippets. It does not establish semantic entailment, claim truth or program correctness. For compatibility the JSON bucket remains `fabricated`; its reason distinguishes malformed paths, missing files, bad ranges, stale hashes, absent snippets, read failures and observed concurrent edits. None of these diagnoses the model's intent. `unresolved` remains separate.

## One operation, bounded source reuse

`CitationVerifier(repo_root)` reuses file content within one command. CLI lint/gate JSON share that reader with their metrics; metrics, runtime audit and CLI/MCP hash attachment also reuse it. A fresh command or an ordinary helper call creates a fresh reader. There is no global cache to return a prior command's verification success.

Every lookup resolves the path under the repo root, checks regular-file status and compares device/file identity, size and nanosecond mtime. POSIX also compares ctime. Python 3.12 Windows `stat` and `fstat` may expose different legacy ctime values; these are deliberately not compared across Windows handles. Before/after reads, descriptor metadata, path metadata and resolved location are checked. A detected edit invalidates that file for the rest of the operation. Permission/read errors become a failed verification, not a successful empty evidence check.

The default 8 MiB budget covers cached text and line tuples, not result output or per-file identity metadata. Files that exceed the budget are streamed; only the requested range may be retained if it fits. Different ranges in an oversized file may need another scan. Cache reuse therefore improves repeated references that fit the budget; it is not a universal constant-memory or constant-I/O claim. Limits on provider payloads and citation evidence ranges remain unchanged.

This is ordinary concurrent-edit detection, not an atomic repository snapshot or protection against an adversary restoring all file metadata. Freeze the input checkout when an atomic, reproducible audit is required.

## Reproducible comparison

The recorded public baseline is antemortem version **0.11.2**; the modified package in the recorded results is version **0.12.0**. The baseline source checkout in the rewritten history is commit `2d0fbf1eabf2b2e28e69170f3b040088c00ba6d8`, corresponding to the original commit `95a49e75a03b2289c1015b72b09cbc4cfbae8310` retained in the raw results. At measurement time, baseline HEAD and the then-latest release were identical; no unpublished change is credited. The two packages ran in separate virtual environments with Python 3.12.10 on Windows 11, without provider calls. These are historical results, not measurements of the current 0.12.5 release.

[`scripts/benchmark_citation_io.py`](../scripts/benchmark_citation_io.py) fixes the workloads before running them: a 2,000-line UTF-8 file, 1/20/200 findings, ten distinct cited ranges, matching hashes, one operation per input, and instrumentation of actual `Path.open` calls to the source file. It compares the complete metrics/lint/gate command paths, including JSON metrics. Source-write setup, artifact/document reads and installation are excluded from the source-open counter. No timing benchmark or speed ratio is claimed.

| Citations | metrics source opens, before → after | lint/gate JSON source opens, before → after |
|---:|---:|---:|
| 1 | 2 → 1 | 4 → 1 |
| 20 | 40 → 1 | 80 → 1 |
| 200 | 400 → 1 | 800 → 1 |

All workloads preserve verified counts and exit 0. Ten known development regression cases change from 7 correct to 10: metrics previously accepted a wrong snippet and stale legacy hash, and Unicode vertical tabs made line verification disagree with evidence selection. These are cases used during development, not a blind evaluation or a real-world accuracy rate. Mutation, deletion, movement, permission errors, invalid UTF-8, LF/CRLF/CR, cache eviction and symlink escape have separate regression coverage. Symlink tests may skip where OS permissions prohibit creating one; the existing Linux CI runs that case.

Raw results and environment details: [`citation_io_results.json`](citation_io_results.json). Run the script using each installed environment's Python from outside the source checkout to reproduce the comparison.

### Current installation and archived comparison packages

For current use:

```bash
python -m pip install "antemortem==0.12.5"
```

Historical package recovery requires access to the maintainer's saved local archive; this is not a public download. Set `ARCHIVE_ROOT` to the directory containing `ARCHIVE_MANIFEST.json`. The manifest SHA-256 is `0da4513cff8a0d2a85f113c49484b164c95166b58636c784097193828c2c7c3b`.

| Recorded version | Wheel path relative to `ARCHIVE_ROOT` | SHA-256 |
|---|---|---|
| 0.11.2 baseline | `packages/antemortem/0.11.2/antemortem-0.11.2-py3-none-any.whl` | `bfec36d79b01cf2ec33e0d4190653ce787ec4768c1246a287c8b24c147e3d690` |
| 0.12.0 comparison | `packages/antemortem/0.12.0/antemortem-0.12.0-py3-none-any.whl` | `22f30dac97d89630915ebdd0902ee5c9a38a77634170672a67b067419f301eac` |

The following package-only recovery example verifies the archive manifest and baseline wheel before installing that wheel into the active isolated environment:

```python
import hashlib
import os
from pathlib import Path
import subprocess
import sys

archive = Path(os.environ["ARCHIVE_ROOT"])
wheel = archive / "packages/antemortem/0.11.2/antemortem-0.11.2-py3-none-any.whl"
expected = {
    archive / "ARCHIVE_MANIFEST.json": "0da4513cff8a0d2a85f113c49484b164c95166b58636c784097193828c2c7c3b",
    wheel: "bfec36d79b01cf2ec33e0d4190653ce787ec4768c1246a287c8b24c147e3d690",
}
for path, digest in expected.items():
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"Archive hash mismatch: {path.name}")
subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], check=True)
```

Use the comparison wheel and its matching hash in a separate environment for version 0.12.0. This restores the saved package bytes only; dependencies must already be prepared. The original results do not contain a complete transitive dependency lock, so these wheels alone do not guarantee reconstruction of the entire original environment. Keep any new measurements separate from `citation_io_results.json`; do not relabel the recorded results.

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
