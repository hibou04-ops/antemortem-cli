# Pre-existing Intellectual Property Declaration

> **Purpose**: This document is a tamper-evident timestamped declaration that the
> work in this repository constitutes pre-existing personal intellectual property
> of the Primary Author, authored prior to and independent of any current or
> future employment relationship.

## Repository Identification

- **Repository**: [hibou04-ops/antemortem-cli](https://github.com/hibou04-ops/antemortem-cli)
- **License**: Apache License 2.0
- **Primary Author**: **Kyunghoon Gwak (곽경훈)** — operating as [@hibou04-ops](https://github.com/hibou04-ops)
  - Primary contact email: `hibouaile04@gmail.com`
  - Git author email on commits prior to 2026-04-28: `hibou04@gmail.com`
  - Both email addresses are verified personal accounts of the Primary Author

## Authorship Timeline (Tamper-Evident)

The following git artifacts establish the authorship timeline. The git commit graph
and the public GitHub remote (`github.com/hibou04-ops/antemortem-cli`) provide
independent timestamp witnesses.

| Anchor | Commit Hash | Date (KST) | Description |
|---|---|---|---|
| First commit | `0a2af730d18ae2ce00b0035d3541b8bb816bb272` | 2026-04-21 23:05:28 +0900 | Initial scaffold for antemortem v0.2.0 CLI |
| v0.2.0 release | (see CHANGELOG.md) | 2026-04-22 | First public CLI release |
| Apache 2.0 license | `LICENSE` (committed 2026-04-22) | 2026-04-22 | Apache 2.0 with patent grant |
| Pre-employment snapshot | (tagged on commit) | 2026-04-28 | This declaration committed; tagged `pre-employment-ip-snapshot-2026-04-28` |

## Scope of Pre-existing IP

The following work product is declared as pre-existing personal intellectual property:

1. **CLI Implementation**: All source code under `src/antemortem/`, including:
   - Command structure (`init`, `run`, `lint`)
   - Provider abstraction layer (Anthropic, OpenAI providers; factory pattern)
   - Pydantic schema for Antemortem run artifacts
   - Citation re-verification logic (on-disk file:line resolution)
   - Decision-classification post-processing and critic logic
   - Prompt templates for LLM interaction
2. **Test Suite**: All materials under `tests/`.
3. **Examples**: All materials under `examples/`.
4. **Documentation**: README, README_KR, EASY_README, EASY_README_KR, CHANGELOG.
5. **Package Metadata**: `pyproject.toml` configuration and PyPI distribution.

## Companion Methodology Repository

The methodology that this CLI implements is published in the companion repository
[hibou04-ops/Antemortem](https://github.com/hibou04-ops/Antemortem), which is
also covered by its own `PRE_EXISTING_IP.md`. Both repositories are authored by
the same Primary Author.

## Development Conditions

This work was developed:

- Using **personal time** (outside of any third-party working hours)
- Using **personal equipment** (no employer-issued hardware)
- Using **personal accounts** (no employer-issued cloud, LLM, or API credentials)
- **Without reference** to any third party's confidential or proprietary information

## Use in Future Employment Agreements

This declaration is intended to be attached as a Schedule / Exhibit (commonly
"Schedule A: Pre-existing IP") to any future employment, contractor, or
consulting agreement, to clarify that:

- The work in this repository remains the personal property of the Primary Author.
- Future development on this codebase, conducted on personal time and outside the
  scope of any employment, continues to be the Primary Author's personal IP.
- Any contributions from a future employer's domain, made on employer time using
  employer resources, would be governed by the relevant employment agreement —
  the boundary is preserved by maintaining a separate repository, fork, or
  branch for any such employer-domain contributions.

## Verification

To independently verify this declaration:

1. Inspect git log:
   ```
   git log --format="%H | %ai | %an <%ae>" | grep "Hibou04-ops"
   ```
2. Confirm tag (when committed):
   ```
   git tag -l "pre-employment-ip-snapshot-*"
   git show pre-employment-ip-snapshot-2026-04-28
   ```
3. Cross-reference with public GitHub timestamps:
   - https://github.com/hibou04-ops/antemortem-cli/commit/0a2af730d18ae2ce00b0035d3541b8bb816bb272
   - https://github.com/hibou04-ops/antemortem-cli/releases

---

**Declaration date**: 2026-04-28
**License**: Apache License 2.0
**Document version**: 1.0
