# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem run` - LLM-assisted classification.

Model-agnostic: the ``--provider`` flag selects the adapter (Anthropic,
OpenAI, or any OpenAI-compatible endpoint via ``--base-url``), and
``--model`` overrides the per-provider default. The discipline (schema
enforcement, file:line citations, disk-verified lint) is identical across
providers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer

from antemortem.api import run_classification
from antemortem.citations import audit_output_citations, evidence_sha256_for_citation
from antemortem.critic import (
    apply_critic_results,
    run_critic_pass,
    run_ghost_critic_pass,
)
from antemortem.decision import DecisionPolicy, compute_decision
from antemortem.file_safety import (
    DEFAULT_DENY_GLOBS,
    DEFAULT_MAX_FILE_BYTES,
    FileSafetyConfig,
    evaluate_file,
    load_gitignore_patterns,
    load_safe_text,
)
from antemortem.parser import DocumentParseError, parse_document
from antemortem.providers import (
    DEFAULT_MODELS,
    ProviderError,
    make_provider,
    supported_providers,
)
from antemortem.schema import AntemortemDocument, Trap


_ENV_KEY_FOR_PROVIDER: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _check_classification_coverage(
    expected_trap_ids: set[str],
    output_classifications,
) -> None:
    """Hard-fail when classification IDs don't match input trap IDs exactly.

    Without this, a provider that returns an empty or partial
    classification list would still produce a SAFE_TO_PROCEED artifact
    (decision.compute_decision returns SAFE when there are no REAL
    findings, including the case of zero classifications). The lint
    command catches the mismatch later, but only if the user runs it —
    the run-time artifact is the artifact CI consumes.

    Raises:
        ProviderError when expected != actual.
    """
    actual_ids = {c.id for c in output_classifications}
    missing = expected_trap_ids - actual_ids
    extra = actual_ids - expected_trap_ids
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing classifications for trap(s) {sorted(missing)}")
        if extra:
            parts.append(f"unknown trap id(s) {sorted(extra)}")
        raise ProviderError(
            "classification coverage mismatch: " + "; ".join(parts) +
            ". The provider returned a partial or off-target response. "
            "No artifact written. Re-run, or shrink the trap set if some "
            "are intentionally out-of-scope."
        )


def _attach_evidence_hashes(output, repo_root: Path):
    """Stamp each cited classification / new_trap with an evidence_sha256.

    Evidence hashing detects stale citations: a future `lint` run can
    recompute the hash and flag mismatches that mean the cited line
    content has changed since artifact-write time. Citations on
    UNRESOLVED classifications stay null (no citation to hash).

    Failures (unparseable citation, missing file, line out of range)
    leave the field unset rather than failing the run — the existing
    citation verifier in lint already reports those.
    """
    new_classifications = []
    for c in output.classifications:
        if c.label == "UNRESOLVED" or not c.citation:
            new_classifications.append(c)
            continue
        digest = evidence_sha256_for_citation(c.citation, repo_root)
        new_classifications.append(
            c.model_copy(update={"evidence_sha256": digest}) if digest else c
        )

    new_new_traps = []
    for nt in output.new_traps:
        digest = evidence_sha256_for_citation(nt.citation, repo_root)
        new_new_traps.append(
            nt.model_copy(update={"evidence_sha256": digest}) if digest else nt
        )

    return output.model_copy(
        update={
            "classifications": new_classifications,
            "new_traps": new_new_traps,
        }
    )


def _build_traps_table(traps: list[Trap]) -> str:
    """Render the traps list as the markdown table the system prompt expects."""
    rows = ["| id | hypothesis | type |", "|----|-----------|------|"]
    for t in traps:
        hypothesis = t.hypothesis.replace("|", r"\|")
        rows.append(f"| {t.id} | {hypothesis} | {t.type} |")
    return "\n".join(rows)


def load_files_for_recon(
    doc: AntemortemDocument,
    repo_root: Path,
    safety: FileSafetyConfig | None = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Public helper for resolving and safely loading recon files.

    The CLI ``run`` command and the MCP ``run`` tool share this loader so
    both code paths apply the same FileSafetyConfig (deny-globs, max bytes,
    .gitignore, secret redaction). Pre-fix the MCP path had its own
    bare-bones loader that bypassed every safety control — an agent could
    list ``.env`` in the Recon protocol and it would get sent to the LLM.

    `safety` is the privacy / resource policy applied per file. When
    omitted, the default config (deny-globs + gitignore respect + 200KB
    cap, no secret redaction) is used. Files denied by any rule are
    surfaced as warnings — the user sees what was held back and why.
    """
    safety = safety or FileSafetyConfig()
    files: list[tuple[str, str]] = []
    warnings: list[str] = []
    try:
        repo_resolved = repo_root.resolve()
    except FileNotFoundError:
        warnings.append(f"--repo does not exist: {repo_root}")
        return files, warnings

    gitignore_patterns = (
        load_gitignore_patterns(repo_resolved) if safety.respect_gitignore else ()
    )

    for rel_path in doc.files_to_read:
        full = (repo_root / rel_path).resolve()
        try:
            full.relative_to(repo_resolved)
        except ValueError:
            warnings.append(f"skipped {rel_path!r}: path escapes --repo root")
            continue
        if not full.exists() or not full.is_file():
            warnings.append(f"skipped {rel_path!r}: file does not exist in --repo")
            continue
        decision = evaluate_file(rel_path, full, safety, gitignore_patterns)
        if not decision.allowed:
            warnings.append(f"skipped {rel_path!r}: {decision.reason}")
            continue
        try:
            content, redactions = load_safe_text(full, safety)
        except UnicodeDecodeError:
            content, redactions = load_safe_text(full, safety)
            warnings.append(f"{rel_path}: not valid UTF-8, replaced bad bytes")
        if redactions:
            warnings.append(
                f"{rel_path}: --redact-secrets applied {redactions} substitution(s)"
            )
        files.append((rel_path, content))

    return files, warnings


# Backward-compat alias for callers (tests, downstream code) that imported
# the function by its original underscore-prefixed name. The MCP server
# now imports the public ``load_files_for_recon`` form to make the
# safety contract visible.
_load_files_from_repo = load_files_for_recon


def run(
    document: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the antemortem document to classify.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    repo: Path = typer.Option(  # noqa: B008
        Path.cwd(),
        "--repo",
        "-r",
        help="Repository root to read cited files from. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    provider_name: str = typer.Option(  # noqa: B008
        "anthropic",
        "--provider",
        "-p",
        help=(
            "LLM provider to use. One of: "
            + ", ".join(supported_providers())
            + ". The OpenAI provider also accepts compatible endpoints (Azure, Groq, "
            "Together.ai, OpenRouter, local Ollama) via --base-url."
        ),
        case_sensitive=False,
    ),
    model: str | None = typer.Option(  # noqa: B008
        None,
        "--model",
        "-m",
        help=(
            "Model string override. If omitted, uses the provider default "
            f"(anthropic={DEFAULT_MODELS['anthropic']}, "
            f"openai={DEFAULT_MODELS['openai']})."
        ),
    ),
    base_url: str | None = typer.Option(  # noqa: B008
        None,
        "--base-url",
        help=(
            "Custom endpoint for OpenAI-compatible providers. Example: "
            "http://localhost:11434/v1 for local Ollama."
        ),
    ),
    max_tokens: int = typer.Option(  # noqa: B008
        16000,
        "--max-tokens",
        help="Upper bound on output tokens. Default 16000 suits typical classifications.",
        min=1024,
        max=128000,
    ),
    critic: bool = typer.Option(  # noqa: B008
        False,
        "--critic",
        "-c",
        help=(
            "Run a second-pass critic review of REAL / NEW findings. Roughly "
            "doubles per-run API cost. Findings the critic weakens or "
            "contradicts are downgraded to UNRESOLVED before the decision "
            "gate runs."
        ),
    ),
    critic_ghosts: str = typer.Option(  # noqa: B008
        "none",
        "--critic-ghosts",
        help=(
            "Inverse-critic pass over GHOST findings. False-GHOSTs (real "
            "risks waved through) are more dangerous than false-REALs. "
            "Modes: 'none' (default), 'high' (review high-severity OR "
            "low-confidence GHOSTs), 'all' (review every GHOST). Mode "
            "'all' adds another full critic call per run."
        ),
    ),
    no_decision: bool = typer.Option(  # noqa: B008
        False,
        "--no-decision",
        help="Skip the four-level decision gate. Artifact still records classifications.",
    ),
    max_file_bytes: int = typer.Option(  # noqa: B008
        DEFAULT_MAX_FILE_BYTES,
        "--max-file-bytes",
        help=(
            "Per-file size cap (bytes). Files over the cap are skipped with a "
            f"warning. Default: {DEFAULT_MAX_FILE_BYTES}."
        ),
        min=1,
    ),
    deny_glob: str = typer.Option(  # noqa: B008
        ",".join(DEFAULT_DENY_GLOBS),
        "--deny-glob",
        help=(
            "Comma-separated globs that REFUSE to load (e.g. credentials, "
            "PEM keys). The default deny-list covers .env, .ssh, *.pem, "
            "*.key, secrets/, credentials/. Pass an empty string to disable, "
            "or override with your own list."
        ),
    ),
    respect_gitignore: bool = typer.Option(  # noqa: B008
        True,
        "--respect-gitignore/--no-respect-gitignore",
        help=(
            "Honor the repo's top-level .gitignore patterns when loading "
            "files. ON by default — if .gitignore wouldn't ship the file, "
            "neither does antemortem. Disable only with intent."
        ),
    ),
    redact_secrets: bool = typer.Option(  # noqa: B008
        False,
        "--redact-secrets",
        help=(
            "Apply pattern-based redaction to file text (AWS keys, GitHub "
            "PATs, Slack tokens, PEM blocks, bearer tokens) before sending "
            "to the LLM provider. OFF by default — regex redaction can mask "
            "real code. Enable only when the file set is broad."
        ),
    ),
    strict_unresolved: bool = typer.Option(  # noqa: B008
        False,
        "--strict-unresolved",
        help=(
            "Treat ANY UNRESOLVED finding as preventing SAFE_TO_PROCEED. "
            "Default policy allows SAFE when the unresolved ratio is small. "
            "Use this flag in CI when SAFE_TO_PROCEED should mean every "
            "trap was resolved (REAL/GHOST/NEW), not 'mostly resolved'."
        ),
    ),
    strict_citations: bool = typer.Option(  # noqa: B008
        False,
        "--strict-citations",
        help=(
            "Refuse to write the artifact when any non-UNRESOLVED finding "
            "has an invalid citation. Default behaviour (off) writes the "
            "artifact and forces decision=NEEDS_MORE_EVIDENCE — useful for "
            "postmortem inspection. Pass this flag in CI when you want the "
            "build to fail outright on a bad citation, with no artifact "
            "produced."
        ),
    ),
) -> None:
    """Run LLM classification on an antemortem document."""
    provider_key = provider_name.lower().strip()
    if provider_key not in supported_providers():
        typer.secho(
            f"Unknown --provider {provider_name!r}. Supported: "
            + ", ".join(supported_providers()),
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    expected_env = _ENV_KEY_FOR_PROVIDER.get(provider_key)
    if expected_env is not None and not os.getenv(expected_env):
        typer.secho(
            f"{expected_env} is not set. Export it before running "
            f"`antemortem run --provider {provider_key}`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        doc = parse_document(document)
    except DocumentParseError as exc:
        typer.secho(f"Cannot parse {document.name}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if not doc.traps:
        typer.secho(
            "No traps parsed from the document - nothing to classify. "
            "Fill in the pre-recon Traps table first.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    deny_globs_tuple = tuple(g.strip() for g in deny_glob.split(",") if g.strip())
    safety = FileSafetyConfig(
        max_file_bytes=max_file_bytes,
        deny_globs=deny_globs_tuple,
        respect_gitignore=respect_gitignore,
        redact_secrets=redact_secrets,
    )
    files, warnings = load_files_for_recon(doc, repo, safety)
    for w in warnings:
        typer.secho(f"warning: {w}", fg=typer.colors.YELLOW, err=True)
    if not files:
        typer.secho(
            "No readable files resolved from the Recon protocol section. "
            "Check the `--repo` path and the file paths in the document.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        provider = make_provider(
            provider_key,
            model=model,
            base_url=base_url,
        )
    except ProviderError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.secho(
        f"Reading {len(files)} file(s) from {repo} ...",
        fg=typer.colors.BRIGHT_BLACK,
    )
    typer.secho(
        f"Calling {provider.name} model {provider.model} "
        f"(this can take 30-90s for multi-file recon) ...",
        fg=typer.colors.BRIGHT_BLACK,
    )

    traps_table = _build_traps_table(doc.traps)
    try:
        output, usage = run_classification(
            provider,
            spec=doc.spec,
            traps_table_md=traps_table,
            files=files,
            max_tokens=max_tokens,
        )
    except ProviderError as exc:
        typer.secho(f"Classification failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    expected_ids = {t.id for t in doc.traps}
    try:
        _check_classification_coverage(expected_ids, output.classifications)
    except ProviderError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    output = _attach_evidence_hashes(output, repo)

    critic_usage: dict[str, int] | None = None
    if critic:
        typer.secho(
            "Running critic pass (adversarial review of REAL / NEW findings) ...",
            fg=typer.colors.BRIGHT_BLACK,
        )
        try:
            critic_results, critic_usage = run_critic_pass(
                provider,
                spec=doc.spec,
                traps_table_md=traps_table,
                files=files,
                first_pass=output,
                max_tokens=8000,
            )
        except ProviderError as exc:
            typer.secho(
                f"Critic pass failed: {exc}. First-pass classifications preserved; "
                "decision gate will run without critic adjustments.",
                fg=typer.colors.YELLOW,
                err=True,
            )
        else:
            output = apply_critic_results(output, critic_results)
            _sum_usage(usage, critic_usage)

    # Reviewer P1: inverse-critic over GHOST findings. False-GHOSTs
    # (real risks waved through) are more dangerous than false-REALs.
    # Mode is opt-in: 'none' default, 'high' for severity/confidence-
    # filtered, 'all' for every GHOST.
    if critic_ghosts in ("high", "all"):
        typer.secho(
            f"Running ghost-critic pass (inverse-adversarial review of GHOST "
            f"findings, mode={critic_ghosts}) ...",
            fg=typer.colors.BRIGHT_BLACK,
        )
        try:
            ghost_results, ghost_usage = run_ghost_critic_pass(
                provider,
                spec=doc.spec,
                traps_table_md=traps_table,
                files=files,
                first_pass=output,
                mode=critic_ghosts,  # type: ignore[arg-type]
                max_tokens=8000,
            )
        except ProviderError as exc:
            typer.secho(
                f"Ghost-critic pass failed: {exc}. GHOST classifications "
                "preserved unchanged.",
                fg=typer.colors.YELLOW,
                err=True,
            )
        else:
            if ghost_results:
                output = apply_critic_results(output, ghost_results)
                _sum_usage(usage, ghost_usage)
    elif critic_ghosts != "none":
        typer.secho(
            f"Unknown --critic-ghosts mode: {critic_ghosts!r}. "
            "Use one of: none, high, all.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # Reviewer P0: audit citations BEFORE the decision gate runs.
    # Pre-fix the decision gate could emit SAFE_TO_PROCEED based on
    # classifications whose citations didn't resolve — lint catches it
    # later, but agents reading the run artifact directly trust the
    # decision field. Now the gate refuses to mark SAFE_TO_PROCEED on
    # an output that has any unresolved/non-existent citations.
    citation_audit = audit_output_citations(output, repo)
    if not citation_audit.ok:
        for violation in citation_audit.violations:
            typer.secho(f"  - {violation}", fg=typer.colors.YELLOW, err=True)
        if strict_citations:
            typer.secho(
                f"FAIL: --strict-citations is set and {len(citation_audit.violations)} "
                f"of {citation_audit.checked} non-UNRESOLVED findings have invalid "
                "citations. Refusing to write artifact. Re-run without --strict-citations "
                "to inspect the artifact, or fix the citations and retry.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    if not no_decision:
        if not citation_audit.ok:
            decision_value = "NEEDS_MORE_EVIDENCE"
            rationale = (
                "Citation audit failed: "
                f"{len(citation_audit.violations)} of {citation_audit.checked} "
                "non-UNRESOLVED findings have invalid citations. SAFE_TO_PROCEED "
                "requires every finding to cite a real file:line range. Fix "
                "the citations or downgrade the affected findings to UNRESOLVED."
            )
            output = output.model_copy(
                update={
                    "decision": decision_value,
                    "decision_rationale": rationale,
                }
            )
        else:
            policy = DecisionPolicy(
                unresolved_policy=(
                    "any_blocks_safe" if strict_unresolved else "ratio"
                )
            )
            decision = compute_decision(output, policy=policy)
            output = output.model_copy(
                update={
                    "decision": decision.decision,
                    "decision_rationale": decision.rationale,
                }
            )

    artifact_path = document.with_suffix(".json")
    artifact_path.write_text(
        output.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    label_counts: dict[str, int] = {}
    for c in output.classifications:
        label_counts[c.label] = label_counts.get(c.label, 0) + 1
    summary = ", ".join(f"{count} {label}" for label, count in sorted(label_counts.items()))
    new_count = len(output.new_traps)

    typer.secho(
        f"Classified {len(output.classifications)} traps"
        + (f" ({summary})" if summary else "")
        + (f"; surfaced {new_count} new trap(s)" if new_count else ""),
        fg=typer.colors.GREEN,
    )
    typer.secho(f"Artifact: {artifact_path}", fg=typer.colors.GREEN)

    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_write = usage.get("cache_creation_input_tokens", 0)
    typer.secho(
        f"Tokens: {usage.get('input_tokens', 0)} input (+{cache_read} cached read, "
        f"+{cache_write} cached write), {usage.get('output_tokens', 0)} output",
        fg=typer.colors.BRIGHT_BLACK,
    )

    if cache_read == 0 and cache_write == 0:
        typer.secho(
            "note: prompt cache did not engage on this call. Expected on the very "
            "first run; if repeated, the system prompt may have a silent invalidator "
            "or the provider's cache threshold wasn't met.",
            fg=typer.colors.YELLOW,
        )

    if output.decision:
        color = {
            "SAFE_TO_PROCEED": typer.colors.GREEN,
            "PROCEED_WITH_GUARDS": typer.colors.YELLOW,
            "NEEDS_MORE_EVIDENCE": typer.colors.YELLOW,
            "DO_NOT_PROCEED": typer.colors.RED,
        }.get(output.decision, typer.colors.BRIGHT_BLACK)
        typer.secho(f"Decision: {output.decision}", fg=color)
        if output.decision_rationale:
            typer.secho(f"  {output.decision_rationale}", fg=typer.colors.BRIGHT_BLACK)

    if os.getenv("ANTEMORTEM_JSON_SUMMARY"):
        typer.echo(json.dumps({
            "artifact": str(artifact_path),
            "provider": provider.name,
            "model": provider.model,
            "classifications": len(output.classifications),
            "new_traps": new_count,
            "decision": output.decision,
            "critic_ran": critic,
            "usage": usage,
        }))


def _sum_usage(acc: dict[str, int], delta: dict[str, int]) -> None:
    """Accumulate usage counters in-place."""
    for k in ("input_tokens", "output_tokens",
              "cache_creation_input_tokens", "cache_read_input_tokens"):
        acc[k] = (acc.get(k, 0) or 0) + int(delta.get(k, 0) or 0)
