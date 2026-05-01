# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Second-pass adversarial review of first-pass findings.

The classifier pass (``api.run_classification``) returns an
``AntemortemOutput`` with one ``Classification`` per input trap plus any
``NewTrap`` s the model surfaced. That output is a best-effort draft. The
critic pass re-reads the same evidence and asks a harder question: *does
each REAL/NEW finding actually hold under adversarial scrutiny?*

For each REAL / NEW finding, the critic returns one of:

- ``CONFIRMED`` ??first-pass finding holds. No change.
- ``WEAKENED`` ??the evidence is real but doesn't support the label
  strongly. Policy: downgrade to ``UNRESOLVED``.
- ``CONTRADICTED`` ??different evidence disproves the finding. Policy:
  flip to ``GHOST`` (or to ``UNRESOLVED`` if counterevidence is itself
  uncertain).
- ``DUPLICATE`` ??finding restates another one. Policy: drop.

The critic is opt-in (``--critic`` on ``run``) because it roughly doubles
per-run API cost. When enabled, the decision gate weighs final (post-
critic) findings, not first-pass findings.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from antemortem.prompts import CRITIC_SYSTEM_PROMPT, GHOST_CRITIC_SYSTEM_PROMPT
from antemortem.providers.base import LLMProvider
from antemortem.schema import (
    AntemortemOutput,
    Classification,
    CriticResult,
    NewTrap,
)


GhostCriticMode = Literal["none", "high", "all"]


class _CriticBatch(AntemortemOutput):
    """Container the critic fills in. Reuses AntemortemOutput's critic_results
    so the same Pydantic model can be the output_schema for this call too.
    """


def _findings_to_review(output: AntemortemOutput) -> list[tuple[str, str, str | None]]:
    """Yield (id, label, citation) for every REAL or NEW finding.

    GHOST and UNRESOLVED are not reviewed by default ??GHOST needs a
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
    are passed through unchanged ??GHOST needs an inverse adversarial
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


def _ghost_findings_to_review(
    output: AntemortemOutput,
    mode: GhostCriticMode,
) -> list[Classification]:
    """Pick which GHOST classifications to send to the inverse-critic.

    Reviewer P1: false-GHOSTs are more dangerous than false-REALs in
    Prompt CI — a false-REAL slows down a real change, a false-GHOST
    waves a real risk through. The first-pass classifier may be too
    eager to mark something GHOST because the cited code looks
    superficially handled.

    Modes:
      - ``none`` (default): no GHOSTs reviewed. Backward-compat with
        pre-v0.7 behaviour.
      - ``high``: review only GHOSTs whose severity is ``high`` or
        whose self-reported confidence is below 0.7. Cheapest non-zero
        coverage.
      - ``all``: review every GHOST. Maximum coverage; ~doubles
        critic API cost.
    """
    if mode == "none":
        return []
    candidates = [c for c in output.classifications if c.label == "GHOST"]
    if mode == "all":
        return candidates
    # mode == "high": severity-aware filtering
    selected: list[Classification] = []
    for c in candidates:
        is_high_severity = c.severity == "high"
        is_low_confidence = c.confidence is not None and c.confidence < 0.7
        if is_high_severity or is_low_confidence:
            selected.append(c)
    return selected


def build_ghost_critic_payload(
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
    ghosts: list[Classification],
) -> str:
    """Render the inverse-critic payload listing only GHOSTs to re-examine."""
    file_blocks: list[str] = []
    for path, content in sorted(files, key=lambda item: item[0]):
        normalized = path.replace("\\", "/")
        file_blocks.append(f'<file path="{normalized}">\n{content}\n</file>')
    files_section = "\n".join(file_blocks)

    ghost_lines: list[str] = []
    for c in ghosts:
        ghost_lines.append(
            f"- id={c.id} citation={c.citation or 'null'} "
            f"note={c.note!r}"
        )
    ghost_block = "\n".join(ghost_lines) if ghost_lines else "(none)"

    return (
        f"<files>\n{files_section}\n</files>\n\n"
        f"<spec>\n{spec.strip()}\n</spec>\n\n"
        f"<traps>\n{traps_table_md.strip()}\n</traps>\n\n"
        f"<ghosts>\n{ghost_block}\n</ghosts>"
    )


def run_ghost_critic_pass(
    provider: LLMProvider,
    *,
    spec: str,
    traps_table_md: str,
    files: list[tuple[str, str]],
    first_pass: AntemortemOutput,
    mode: GhostCriticMode,
    max_tokens: int = 8000,
) -> tuple[list[CriticResult], dict[str, int]]:
    """Adversarial review of GHOST findings.

    Returns critic results that, applied via ``apply_critic_results``,
    upgrade GHOSTs the inverse-critic finds suspect:

    - ``CONTRADICTED`` here means the inverse-critic produced credible
      counterevidence that the risk IS real after all. Policy:
      ``recommended_label`` is REAL (or UNRESOLVED if counterevidence
      is partial).
    - ``WEAKENED``: the GHOST's evidence is weak enough that
      \"already mitigated\" isn't supportable; downgrade to UNRESOLVED.
    - ``CONFIRMED``: the GHOST stands.

    Mode ``none`` returns ([], empty usage) without calling the
    provider — the caller handles the no-op.
    """
    ghosts = _ghost_findings_to_review(first_pass, mode)
    if not ghosts:
        return [], {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    payload = build_ghost_critic_payload(spec, traps_table_md, files, ghosts)
    result, usage = provider.structured_complete(
        system_prompt=GHOST_CRITIC_SYSTEM_PROMPT,
        user_content=payload,
        output_schema=_CriticBatch,
        max_tokens=max_tokens,
    )
    return list(result.critic_results), usage


def apply_critic_results(
    output: AntemortemOutput,
    critic_results: Iterable[CriticResult],
) -> AntemortemOutput:
    """Apply critic policy to first-pass output.

    Policy per status:

    - ``CONFIRMED``  ??no change.
    - ``WEAKENED``   ??downgrade to ``UNRESOLVED`` (citation cleared to
      None to match the schema rule that non-UNRESOLVED labels require
      a citation).
    - ``CONTRADICTED`` ??if ``recommended_label`` is set, use it; else
      downgrade to ``UNRESOLVED``.
    - ``DUPLICATE``  ??remove the finding entirely.

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
            # Citation handling depends on the upgrade direction:
            # - Inverse-critic on a GHOST recommends REAL with new
            #   counterevidence; use the first counterevidence cite if
            #   present (the original GHOST's citation supported the
            #   wrong direction).
            # - Otherwise keep the original citation, or null it on
            #   downgrade to UNRESOLVED.
            if c.label == "GHOST" and target_label == "REAL" and crit.counterevidence:
                citation = crit.counterevidence[0]
            elif target_label == "UNRESOLVED":
                citation = None
            else:
                citation = c.citation
            new_classifications.append(
                c.model_copy(
                    update={
                        "label": target_label,
                        "citation": citation,
                        "note": _downgrade_note(
                            c.note, crit,
                            reason=(
                                "ghost_contradicted"
                                if c.label == "GHOST"
                                else "contradicted"
                            ),
                        ),
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
