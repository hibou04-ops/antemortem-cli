# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Single source of truth for the antemortem document contract version.

Three coupled identifiers travel together in every freshly-scaffolded
document so a future parser can refuse stale formats explicitly instead
of silently mis-parsing them.

  parser_contract    — overall markdown grammar / heading layout the
                       parser expects. Bumps to "antemortem-v2" when
                       any heading text or table column changes.
  schema_version     — Pydantic model contract for AntemortemDocument /
                       AntemortemOutput. Bumps when we add a required
                       field, rename one, or tighten a constraint.
  template_version   — frontmatter `template` key (basic | enhanced).
                       Independent of the other two; tracked here so
                       lint can surface unknown labels.

Lint validates `parser_contract` and `schema_version` against the
`SUPPORTED_*` sets when the fields are present. They are optional in
the schema so older documents (pre-v0.7) still round-trip — the lint
violation only fires for unrecognized values, not missing ones.
"""

from __future__ import annotations

PARSER_CONTRACT: str = "antemortem-v1"
"""Current parser contract emitted by `antemortem init`."""

SCHEMA_VERSION: str = "0.6"
"""Current data-contract schema version emitted by `antemortem init`."""

SUPPORTED_PARSER_CONTRACTS: frozenset[str] = frozenset({"antemortem-v1"})
"""Parser contracts the current binary can read. Add older versions here
when introducing a backward-compatible parser path."""

SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"0.6"})
"""Schema versions the current Pydantic models accept. Add older versions
here when migrating fields with a compatibility shim."""

KNOWN_TEMPLATE_LABELS: frozenset[str] = frozenset({"basic", "enhanced"})
"""Templates the current binary scaffolds and lint understands."""
