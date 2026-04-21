"""Second-pass adversarial review of first-pass findings.

The classifier pass (``api.run_classification``) returns an
``AntemortemOutput`` with one ``Classification`` per input trap plus any
``NewTrap`` s the model surfaced. That output is a best-effort draft. The
critic pass re-reads the same evidence and asks a harder question: *does
each REAL/NEW finding actually hold under adversarial scrutiny?*

For each REAL / NEW finding, the critic returns one of:

- ``CONFIRMED`` — first-pass finding holds. No change.
- ``WEAKENED`` — the evidence is real but doesn't support the label
  strongly. Policy: downgrade to ``UNRESOLVED``.
- ``CONTRADICTED`` — different evidence disproves the finding. Policy:
  flip to ``GHOST`` (or to ``UNRESOLVED`` if counterevidence is itself
  uncertain).
- ``DUPLICATE`` — finding restates another one. Policy: drop.

The critic is opt-in (``--critic`` on ``run``) because it roughly doubles
per-run API cost. When enabled, the decision gate weighs final (post-
critic) findings, not first-pass findings.
"""

from __future__ import annotations

from collections.abc import Iterable

from antemortem.prompts import CRITIC_SYSTEM_PROMPT
from antemortem.providers.base import LLMProvider
from antemortem.schema import (
    AntemortemOutput,
    Classification,
    CriticResult,
    NewTrap,
)


class _CriticBatch(AntemortemOutput):
    """Container the critic fills in. Reuses AntemortemOutput's critic_results
    so the same Pydantic model can be the output_schema for this call too.
    """


def _findings_to_review(output: AntemortemOutput) -> list[tuple[str, str, str | None]]:
    """Yield (id, label, citation) for every REAL or NEW finding.

    GHOST and UNRESOLVED are not reviewed by default — GHOST needs a
    different adversarial prompt (arguing the risk back into existence),
    which is a v0.5 extension. UNRESOLVED is already the honest outcome.
    """
    out: list[tuple[str, str, str | None]] = []
    for c in output.classifications:
        if c.label in ("REAL", "NEW"):
            out.append((c.id, c.label, c.citation))
    for nt in output.new_traps:
        out.append((nt.id, "NEW", nt.citation))
    return out


def build_critic_payload(
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
    first_pass: AntemortemOutput,
) -> str:
    """Render the user-turn payload the critic system prompt expects.

    Includes the original spec + traps + files so the critic has identical
    context to the classifier, plus a ``<first_pass>`` block listing every
    finding the classifier produced.
    """
    file_blocks: list[str] = []
    for path, content in sorted(files, key=lambda item: item[0]):
        normalized = path.replace("\\", "/")
        file_blocks.append(f'<file path="{normalized}">\n{content}\n</file>')
    files_section = "\n".join(file_blocks)

    findings_lines: list[str] = []
    for c in first_pass.classifications:
        findings_lines.append(
            f"- id={c.id} label={c.label} citation={c.citation or 'null'} "
            f"note={c.note!r}"
        )
    for nt in first_pass.new_traps:
        findings_lines.append(
            f"- id={nt.id} label=NEW citation={nt.citation!r} "
            f"note={nt.note!r} hypothesis={nt.hypothesis!r}"
        )
    findings_block = "\n".join(findings_lines) if findings_lines else "(none)"

    return (
        f"<files>\n{files_section}\n</files>\n\n"
        f"<spec>\n{spec.strip()}\n</spec>\n\n"
        f"<traps>\n{traps_table_md.strip()}\n</traps>\n\n"
        f"<first_pass>\n{findings_block}\n</first_pass>"
    )


def run_critic_pass(
    provider: LLMProvider,
    *,
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
    first_pass: AntemortemOutput,
    max_tokens: int = 8000,
) -> tuple[list[CriticResult], dict[str, int]]:
    """Issue the critic call and return (critic_results, usage).

    Only REAL / NEW findings are reviewed. GHOST and UNRESOLVED findings
    are passed through unchanged — GHOST needs an inverse adversarial
    prompt (v0.5) and UNRESOLVED is already the conservative label.
    """
    payload = build_critic_payload(spec, traps_table_md, files, first_pass)
    result, usage = provider.structured_complete(
        system_prompt=CRITIC_SYSTEM_PROMPT,
        user_content=payload,
        output_schema=_CriticBatch,
        max_tokens=max_tokens,
    )
    # The critic fills in critic_results on _CriticBatch; other fields
    # are ignored (they may be empty defaults from the schema).
    return list(result.critic_results), usage


def apply_critic_results(
    output: AntemortemOutput,
    critic_results: Iterable[CriticResult],
) -> AntemortemOutput:
    """Apply critic policy to first-pass output.

    Policy per status:

    - ``CONFIRMED``  → no change.
    - ``WEAKENED``   → downgrade to ``UNRESOLVED`` (citation cleared to
      None to match the schema rule that non-UNRESOLVED labels require
      a citation).
    - ``CONTRADICTED`` → if ``recommended_label`` is set, use it; else
      downgrade to ``UNRESOLVED``.
    - ``DUPLICATE``  → remove the finding entirely.

    The returned ``AntemortemOutput`` is a new object; the original is
    not mutated. ``critic_results`` is attached for audit-trail
    completeness.
    """
    crits_by_id = {c.finding_id: c for c in critic_results}

    new_classifications: list[Classification] = []
    for c in output.classifications:
        crit = crits_by_id.get(c.id)
        if crit is None or crit.status == "CONFIRMED":
            new_classifications.append(c)
            continue
        if crit.status == "DUPLICATE":
            continue  # drop
        if crit.status == "WEAKENED":
            new_classifications.append(
                c.model_copy(
                    update={
                        "label": "UNRESOLVED",
                        "citation": None,
                        "note": _downgrade_note(c.note, crit, reason="weakened"),
                    }
                )
            )
            continue
        if crit.status == "CONTRADICTED":
            target_label = crit.recommended_label or "UNRESOLVED"
            citation = c.citation if target_label != "UNRESOLVED" else None
            new_classifications.append(
                c.model_copy(
                    update={
                        "label": target_label,
                        "citation": citation,
                        "note": _downgrade_note(c.note, crit, reason="contradicted"),
                    }
                )
            )
            continue
        # Unknown status: keep original but record it
        new_classifications.append(c)

    new_new_traps: list[NewTrap] = []
    for nt in output.new_traps:
        crit = crits_by_id.get(nt.id)
        if crit is None or crit.status == "CONFIRMED":
            new_new_traps.append(nt)
            continue
        if crit.status in ("DUPLICATE", "WEAKENED", "CONTRADICTED"):
            # NEW findings that don't hold are dropped entirely - they
            # were surfaced by the model and the critic is voting to
            # retract them. We don't have a pre-existing UNRESOLVED
            # slot to downgrade them into on the user's trap list.
            continue
        new_new_traps.append(nt)

    return output.model_copy(
        update={
            "classifications": new_classifications,
            "new_traps": new_new_traps,
            "critic_results": list(critic_results),
        }
    )


def _downgrade_note(original: str, crit: CriticResult, *, reason: str) -> str:
    """Compose a post-critic note that preserves the original with a suffix."""
    prefix = f"[critic {reason}: {'; '.join(crit.issues) or 'no detail'}]"
    if crit.counterevidence:
        prefix += f" counterevidence: {', '.join(crit.counterevidence)}"
    if not original:
        return prefix
    return f"{prefix} | {original}"
