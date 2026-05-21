# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Pydantic v2 schemas for the antemortem data contract.

These models flow end-to-end through the CLI:

- ``Frontmatter`` parses the YAML block at the top of every antemortem doc.
- ``Trap`` is one row of the pre-recon Traps table.
- ``Classification`` and ``NewTrap`` are the per-trap results from ``run``.
- ``AntemortemOutput`` is the full structured payload Claude returns -- passed
  to ``client.messages.parse()`` so the SDK validates it automatically.
- ``AntemortemDocument`` bundles the parsed doc for ``lint`` and ``run``.
"""

from datetime import date as _date
from datetime import datetime as _datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Label = Literal["REAL", "GHOST", "NEW", "UNRESOLVED"]
"""Valid classification labels.

- ``REAL``: the code confirms the risk.
- ``GHOST``: the code contradicts the risk (or an existing mitigation handles it).
- ``NEW``: a risk the model surfaced that was not on the user's traps list.
- ``UNRESOLVED``: no evidence in the provided files. Valid outcome, not a failure.
"""


class Frontmatter(BaseModel):
    """YAML frontmatter on every antemortem document."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Short identifier for the change.")
    date: str = Field(..., description="ISO date (YYYY-MM-DD).")
    scope: str = Field(default="change-local")
    reversibility: str = Field(default="high")
    status: str = Field(default="draft", description="draft | classified | decided")
    template: str = Field(default="basic", description="basic | enhanced")
    schema_version: str | None = Field(
        default=None,
        description=(
            "Data-contract schema version the document was scaffolded "
            "against. Optional for backward compat with pre-v0.7 docs; "
            "lint validates against SUPPORTED_SCHEMA_VERSIONS when present."
        ),
    )
    parser_contract: str | None = Field(
        default=None,
        description=(
            "Markdown grammar contract the document targets, e.g. "
            "'antemortem-v1'. Lets the parser refuse stale formats "
            "explicitly. Optional for backward compat."
        ),
    )

    @field_validator("date", mode="before")
    @classmethod
    def _coerce_date_to_iso(cls, value: Any) -> Any:
        """YAML parsers auto-convert ``YYYY-MM-DD`` literals to ``datetime.date``;
        normalize those back to an ISO string so downstream code can treat date
        as a plain string without leaking the Python type of the YAML loader.
        """
        if isinstance(value, _datetime):
            return value.date().isoformat()
        if isinstance(value, _date):
            return value.isoformat()
        return value


class Trap(BaseModel):
    """A single row from the pre-recon Traps table."""

    id: str = Field(..., description="Trap id, e.g. 't1', 't2'.")
    hypothesis: str = Field(..., description="What the user suspects might fail.")
    type: str = Field(
        default="trap",
        description="trap | worry | unknown -- confidence in the hypothesis.",
    )
    notes: str = Field(default="")


class Classification(BaseModel):
    """The ``run`` command's classification of one user-supplied trap."""

    id: str = Field(..., description="Trap id matching an input trap.")
    label: Label
    citation: str | None = Field(
        default=None,
        description="file:line or file:line-line; null only when label is UNRESOLVED.",
    )
    note: str = Field(default="", description="1-2 sentences explaining the label.")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model's self-reported confidence in [0, 1]. Optional; "
        "v0.3.x classifications may omit this field.",
    )
    remediation: str | None = Field(
        default=None,
        description="Optional: concrete mitigation suggestion for REAL findings. "
        "Ignored on GHOST / UNRESOLVED.",
    )
    severity: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Optional: model's severity assessment. Input trap's type "
        "(trap/worry/unknown) is a hint; severity is a post-classification read.",
    )
    evidence_snippet: str | None = Field(
        default=None,
        description="Optional exact snippet expected to appear inside the cited "
        "line range. Lint checks this when present.",
    )
    evidence_hash: str | None = Field(
        default=None,
        description="SHA-256 evidence binding in `sha256:<hex>` format for the "
        "citation's normalized line range. Populated by the CLI, not the LLM. "
        "Null on UNRESOLVED or older artifacts.",
    )
    evidence_sha256: str | None = Field(
        default=None,
        description="Deprecated compatibility field for pre-evidence_hash "
        "artifacts that stored the bare SHA-256 digest without the `sha256:` "
        "prefix.",
    )

    @model_validator(mode="after")
    def _citation_label_invariant(self) -> "Classification":
        """Enforce the citation/label contract at parse time.

        Reviewer P0: pre-fix this invariant lived only in ``lint``. A
        provider could return ``label=GHOST`` with ``citation=None`` and
        Pydantic would accept it; the decision gate would then build on
        a structurally-invalid finding (GHOST without evidence). Lint
        catches it later, but agents that key off the run artifact would
        already be downstream of the bad data.

        - ``UNRESOLVED`` requires ``citation=None`` (no evidence to cite).
        - Any other label requires a non-empty ``citation`` string.
        """
        if self.label == "UNRESOLVED":
            if self.citation is not None:
                raise ValueError(
                    f"Classification {self.id!r}: UNRESOLVED must have "
                    f"citation=None, got {self.citation!r}. Use a different "
                    "label if there's actual evidence to cite."
                )
        else:
            if not self.citation:
                raise ValueError(
                    f"Classification {self.id!r}: label={self.label} requires "
                    "a non-empty citation. Use UNRESOLVED if no evidence is "
                    "available."
                )
        return self


class NewTrap(BaseModel):
    """A risk surfaced by the model that was not on the user's input list."""

    id: str = Field(..., pattern=r"^t_new_\d+$")
    hypothesis: str
    label: Literal["NEW"] = "NEW"
    citation: str = Field(
        ...,
        min_length=1,
        description="file:line or file:line-line. Required (NEW findings "
        "must cite specific evidence — there's no 'unresolved new trap').",
    )
    note: str = Field(default="")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    remediation: str | None = Field(default=None)
    severity: Literal["low", "medium", "high"] | None = Field(default=None)
    evidence_snippet: str | None = Field(
        default=None,
        description="Optional exact snippet expected to appear inside the cited "
        "line range. Lint checks this when present.",
    )
    evidence_hash: str | None = Field(
        default=None,
        description="SHA-256 evidence binding in `sha256:<hex>` format for the "
        "citation's normalized line range. Populated by the CLI, not the LLM.",
    )
    evidence_sha256: str | None = Field(
        default=None,
        description="Deprecated compatibility field for pre-evidence_hash "
        "artifacts that stored the bare SHA-256 digest.",
    )


class CriticStatus(str):
    """Outcomes from the critic (second-pass) review of a finding."""

    CONFIRMED = "CONFIRMED"
    WEAKENED = "WEAKENED"
    CONTRADICTED = "CONTRADICTED"
    DUPLICATE = "DUPLICATE"


class CriticResult(BaseModel):
    """Second-pass adversarial review of a single REAL or NEW finding.

    The classifier pass issues first-draft labels; the critic pass
    adversarially checks each REAL / NEW finding against the same evidence
    and issues one of four statuses. Downstream policy downgrades findings
    whose critic status is ``WEAKENED`` / ``CONTRADICTED`` / ``DUPLICATE`` -- typically to ``UNRESOLVED`` -- before the decision gate runs.

    The critic is an opt-in v0.4 feature (``--critic`` flag on ``run``).
    When enabled, the CLI issues a second provider call with the critic
    system prompt. Opt-in because it roughly doubles per-run API cost.
    """

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(
        ...,
        description="Id of the Classification or NewTrap being reviewed.",
    )
    status: Literal["CONFIRMED", "WEAKENED", "CONTRADICTED", "DUPLICATE"] = Field(
        ...,
        description=(
            "CONFIRMED: first-pass finding holds. WEAKENED: evidence is real but "
            "doesn't support the label strongly; downgrade to UNRESOLVED. "
            "CONTRADICTED: different evidence disproves the finding; flip to GHOST "
            "or UNRESOLVED based on the counterevidence. DUPLICATE: finding "
            "restates another one; drop."
        ),
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific reasons the critic flagged this finding.",
    )
    counterevidence: list[str] = Field(
        default_factory=list,
        description="file:line citations the critic found that contradict or "
        "weaken the first-pass classification.",
    )
    recommended_label: Label | None = Field(
        default=None,
        description="Label the critic recommends after its review. "
        "None means 'keep the original label'.",
    )


class DecisionStatus(str):
    """Four-level decision gate applied after classification + critic."""

    SAFE_TO_PROCEED = "SAFE_TO_PROCEED"
    PROCEED_WITH_GUARDS = "PROCEED_WITH_GUARDS"
    NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"
    DO_NOT_PROCEED = "DO_NOT_PROCEED"


class LoadedFile(BaseModel):
    """Metadata for one file that survived the recon loader.

    Reviewer P1: artifact provenance. Pre-fix the artifact carried only
    the LLM's classifications, not which files actually fed the model.
    A reviewer reading the artifact later couldn't tell whether the
    .env file was excluded by deny-glob (good) or never even tried
    (less good). LoadedFile captures the loader's verdict per file.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str
    byte_len: int


class RunMetadata(BaseModel):
    """Provenance metadata for one ``antemortem run`` invocation.

    Captures everything a reviewer needs to verify or reproduce the
    run after the fact: tool version, provider/model, repo state,
    prompt + payload hashes, files loaded, loader warnings, timestamps.

    Pre-fix the CLI summary printed provider/model/usage to stdout
    but the artifact JSON didn't carry them — so a CI artifact from
    a run six months ago couldn't be replayed against a newer model
    or re-verified against the same git commit.
    """

    model_config = ConfigDict(extra="forbid")

    antemortem_version: str
    provider: str
    model: str
    repo_root: str
    repo_git_commit: str | None = None
    repo_git_dirty: bool | None = None
    prompt_sha256: str
    payload_sha256: str
    created_at: str  # ISO-8601 UTC
    files_loaded: list[LoadedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AntemortemOutput(BaseModel):
    """Structured JSON returned by the LLM and validated by the SDK.

    This is the schema the model is instructed to conform to. It flows through
    ``provider.structured_complete(output_schema=AntemortemOutput)``, so a
    malformed response raises a Pydantic ``ValidationError`` before the CLI
    sees it.

    v0.4 adds optional fields for the critic pass and the decision gate.
    These are populated by the CLI post-processing, not by the LLM directly,
    so the schema stays stable from the model's perspective: the LLM still
    returns classifications + new_traps + spec_mutations.
    """

    classifications: list[Classification] = Field(
        default_factory=list,
        description="One entry per input trap.",
    )
    new_traps: list[NewTrap] = Field(
        default_factory=list,
        description="Risks surfaced by the recon that were not on the input list.",
    )
    spec_mutations: list[str] = Field(
        default_factory=list,
        description="Concrete edits the user should make to the spec before implementing.",
    )
    critic_results: list[CriticResult] = Field(
        default_factory=list,
        description="Optional second-pass reviews. Only populated when --critic is "
        "used. Each entry is a critic review of one first-pass finding.",
    )
    decision: Literal[
        "SAFE_TO_PROCEED",
        "PROCEED_WITH_GUARDS",
        "NEEDS_MORE_EVIDENCE",
        "DO_NOT_PROCEED",
    ] | None = Field(
        default=None,
        description="Optional final decision from the four-level decision gate. "
        "Populated by the CLI after critic review and severity weighing.",
    )
    decision_rationale: str = Field(
        default="",
        description="One or two sentences explaining why the decision came out the "
        "way it did. Empty when decision is null.",
    )
    run_metadata: RunMetadata | None = Field(
        default=None,
        description="Provenance: which version of the tool, which provider/model, "
        "which repo commit, which files were actually loaded, etc. Optional for "
        "backward compat — pre-v0.7 artifacts have null here.",
    )


class AntemortemDocument(BaseModel):
    """A parsed antemortem document: frontmatter + extracted sections."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    frontmatter: Frontmatter
    spec: str = Field(default="", description="Text of '## 1. The change' section.")
    files_to_read: list[str] = Field(
        default_factory=list,
        description="File paths enumerated under 'Files handed to the model'.",
    )
    traps: list[Trap] = Field(
        default_factory=list,
        description="Parsed rows from the pre-recon Traps table.",
    )
    raw_markdown: str = Field(default="", description="Full original markdown content.")
