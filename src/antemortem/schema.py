"""Pydantic v2 schemas for the antemortem data contract.

These models flow end-to-end through the CLI:

- ``Frontmatter`` parses the YAML block at the top of every antemortem doc.
- ``Trap`` is one row of the pre-recon Traps table.
- ``Classification`` and ``NewTrap`` are the per-trap results from ``run``.
- ``AntemortemOutput`` is the full structured payload Claude returns — passed
  to ``client.messages.parse()`` so the SDK validates it automatically.
- ``AntemortemDocument`` bundles the parsed doc for ``lint`` and ``run``.
"""

from datetime import date as _date
from datetime import datetime as _datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
        description="trap | worry | unknown — confidence in the hypothesis.",
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


class NewTrap(BaseModel):
    """A risk surfaced by the model that was not on the user's input list."""

    id: str = Field(..., pattern=r"^t_new_\d+$")
    hypothesis: str
    label: Literal["NEW"] = "NEW"
    citation: str
    note: str = Field(default="")


class AntemortemOutput(BaseModel):
    """Structured JSON returned by Claude and validated by the SDK.

    This is the schema the model is instructed to conform to. It flows through
    ``client.messages.parse(output_format=AntemortemOutput)``, so a malformed
    response raises a Pydantic ``ValidationError`` before the CLI sees it.
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
