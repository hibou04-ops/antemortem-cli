# Release Notes Template

Use the deterministic generator before publishing:

```bash
python scripts/generate_release_notes.py --from <previous-ref> --to <release-ref> --output docs/release-notes/v<version>.md
```

If git metadata is unavailable, pass explicit changed files:

```bash
python scripts/generate_release_notes.py --version <version> --files A:scripts/example.py M:README.md
```

The generated notes must keep these sections:

- Summary
- Added
- Changed
- Fixed
- Verification commands
- Benchmark snapshot
- Breaking changes
- Known limitations

Semantic release bullets come from `CHANGELOG.md`. File lists come from git diff or explicit file input. Benchmark metrics come only from generated benchmark JSON, either by running `antemortem eval benchmarks/golden_cases --json` or by reading an explicit `--benchmark-json` file.
