# Scope Freeze

The next release is a verification and release-hygiene release.

Until the release candidate is cut, new feature work is deferred unless it fixes
one of these release blockers:

- failing tests
- broken packaging
- stale README or generated claim content
- safety regressions in citation validation, evidence-bound checks, schema
  validation, path traversal protections, provider error handling, or offline
  benchmark behavior
- release-blocking documentation drift

## Allowed Work

During the freeze, changes should fit one of these categories:

- repair a failing deterministic test
- add missing regression coverage for an existing behavior
- fix packaging metadata, wheel smoke behavior, PyPI rendering, or post-release
  verification
- update generated claim blocks from source-of-truth data
- correct README, release, provider, benchmark, or trust-model drift
- clarify docs without promising a new command, surface, provider, dashboard, or
  integration

## Deferred Work

Feature requests remain valid, but they should be recorded for a later release.
Do not describe deferred work as a current capability. Roadmap language must make
the boundary explicit: planned work is not shipped behavior.

Deferred examples:

- new commands
- new provider surfaces
- dashboards or hosted services
- HTML renderers
- new artifact formats
- broad workflow integrations

## Public-Docs Guardrail

Run the scope freeze checker before release-candidate review:

```bash
python scripts/scope_freeze_check.py
```

The checker fails on public documentation that introduces:

- near-term feature promises
- unimplemented CLI command names presented as current behavior
- roadmap items written as shipped features
- comparative quality or hype claims

Legitimate roadmap sections may mention deferred work only when the text makes
the non-current status clear.

## Release Boundary

Before release, the safe default is:

1. fix blockers
2. update tests
3. update generated docs
4. rerun release checks
5. defer everything else

This scope freeze does not remove future work. It prevents unfinished feature
work from entering the release candidate under the appearance of shipped
behavior.
