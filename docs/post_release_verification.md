# Post-Release Verification

Release work does not end at upload. After a manual publish, verify the package
from public surfaces and from a clean install path. This script does not
publish, upload, tag, or push anything.

## Before Publish

Before upload, only local checks can run. Use dry run mode:

```bash
python scripts/post_release_check.py --version 0.10.0 --dry-run --json
```

Dry run mode does not call PyPI, does not call GitHub, and does not install from
the remote package index. It reports network-backed checks as `PENDING` or
`NOT_RUN`, so it is not proof of a successful PyPI release.

For environments that need the older network-skip spelling:

```bash
python scripts/post_release_check.py --version 0.10.0 --skip-network --json
python scripts/post_release_check.py --version 0.10.0 --skip-pypi-network --json
```

`--skip-pypi-network` is a compatibility alias for `--skip-network`.

## After Publish

After the package has been manually published and the GitHub tag exists, run the
network-enabled check from a clean checkout:

```bash
python scripts/post_release_check.py --version 0.10.0 --json
```

The network-enabled path verifies:

1. PyPI reports the expected package version.
2. A clean virtual environment can install `antemortem==0.10.0` from PyPI.
3. `antemortem --version` reports the expected version.
4. `antemortem --help` runs.
5. Offline `doctor`, `lint`, and `eval` commands still run after the PyPI
   install.
6. The remote GitHub tag `v0.10.0` exists.
7. README release references remain consistent with the expected version.
8. Provider API key environment variables are removed for offline commands.

## Local Consistency Commands

The post-release path depends on the same repository claim checks used before
publish:

```bash
python scripts/check_repo_consistency.py
python scripts/generate_readme_claims.py --check
```

Run these before publish and again if README or generated claim files change.

## Offline Commands

The post-release check runs these commands without provider keys:

```bash
antemortem doctor examples/demo_recon.md --repo . --json
antemortem lint examples/demo_antemortem.md --repo .
antemortem eval benchmarks/golden_cases --json
```

The commands use repository fixtures and stored artifacts. They must not require
live provider calls.

## Failure Handling

Treat any failure as release-blocking until explained. Common causes:

- PyPI has not finished serving the uploaded version.
- The README badge or current-release text was not updated.
- The GitHub release tag was not pushed.
- The installed package cannot run offline CLI commands against repository
  fixtures.
- An offline command unexpectedly depends on a provider API key.

Dry run success only means the local preflight path is coherent. Final
post-release verification must run after manual publish in a network-enabled
environment.
