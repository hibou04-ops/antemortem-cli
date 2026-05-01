# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""FastMCP server wrapping antemortem-cli's three commands.

Each tool accepts JSON-friendly input (str paths, primitives) and returns
the result as a serialized dict. The agent-facing tool descriptions are
short and action-oriented; the long-form rationale lives in the discipline
documentation.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from antemortem.api import run_classification
from antemortem.citations import audit_output_citations
from antemortem.commands.lint import run_lint
from antemortem.commands.run import (
    _attach_evidence_hashes,
    _build_traps_table,
    _check_classification_coverage,
    load_files_for_recon,
)
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
)
from antemortem.parser import DocumentParseError, parse_document
from antemortem.providers import (
    DEFAULT_MODELS,
    ProviderError,
    make_provider,
    supported_providers,
)
from antemortem.templates import get_template

mcp_app = FastMCP(
    name="antemortem",
    instructions=(
        "Pre-implementation reconnaissance for software changes. Use these "
        "tools BEFORE editing code: scaffold an antemortem doc describing "
        "the change, run LLM classification to surface REAL / GHOST / NEW / "
        "UNRESOLVED risks against actual repo files, lint to catch "
        "hallucinated file:line citations. Proceed with edits only once "
        "the four-level decision gate clears (SAFE_TO_PROCEED or "
        "PROCEED_WITH_GUARDS). Discipline by hibou04-ops/Antemortem."
    ),
)


_ENV_KEY_FOR_PROVIDER: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _build_frontmatter(name: str, today: str, enhanced: bool) -> str:
    from antemortem._versions import PARSER_CONTRACT, SCHEMA_VERSION

    template_label = "enhanced" if enhanced else "basic"
    return (
        "---\n"
        f"name: {name}\n"
        f"date: {today}\n"
        "scope: change-local\n"
        "reversibility: high\n"
        "status: draft\n"
        f"template: {template_label}\n"
        f"schema_version: \"{SCHEMA_VERSION}\"\n"
        f"parser_contract: {PARSER_CONTRACT}\n"
        "---\n\n"
    )


# NOTE: file loading is delegated to ``load_files_for_recon`` so the
# MCP path inherits CLI's deny-glob / .gitignore / max-byte / secret-
# redaction safety. Pre-fix this module had its own bare loader that
# called ``read_text()`` directly, which let an agent ship ``.env``
# contents through the MCP boundary.


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp_app.tool()
def scaffold(
    name: str,
    enhanced: bool = False,
    output_dir: str = "antemortem",
    force: bool = False,
) -> dict:
    """Create an antemortem document from a template.

    Run this FIRST when starting a non-trivial change. The scaffolded
    document collects the change spec, hypothesized risks ("traps"), and
    files the LLM should read to classify each trap.

    Args:
        name: Short identifier (letters, digits, hyphens). Used as filename.
        enhanced: If True, use the enhanced template (calibration dimensions,
            skeptic pass, decision-first output). Default: False (basic).
        output_dir: Directory to create the document in. Created if missing.
        force: Overwrite existing document if present.

    Returns:
        Dict with ``path`` (created file), ``template`` (basic/enhanced),
        and ``message``.
    """
    if not name or any(ch in name for ch in ("/", "\\", "..")):
        raise ValueError(
            f"Invalid name {name!r}: use a simple identifier "
            "(letters, digits, hyphens)."
        )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{name}.md"
    if target.exists() and not force:
        raise FileExistsError(
            f"{target} already exists. Pass force=true to overwrite."
        )

    today = date.today().isoformat()
    body = _build_frontmatter(name, today, enhanced) + get_template(enhanced=enhanced)
    target.write_text(body, encoding="utf-8")

    return {
        "path": str(target),
        "template": "enhanced" if enhanced else "basic",
        "message": f"Wrote {target}. Fill in spec, traps, and files_to_read, then call `run`.",
    }


@mcp_app.tool()
def run(
    document: str,
    provider: str = "anthropic",
    model: str | None = None,
    base_url: str | None = None,
    repo: str | None = None,
    max_tokens: int = 16000,
    critic: bool = False,
    critic_ghosts: str = "none",
    strict_unresolved: bool = False,
    no_decision: bool = False,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    deny_glob: str = ",".join(DEFAULT_DENY_GLOBS),
    respect_gitignore: bool = True,
    redact_secrets: bool = False,
) -> dict:
    """Run LLM classification on a filled-in antemortem document.

    Reads the document, loads cited repo files (under the same file-safety
    contract as ``antemortem run`` — deny-globs for .env / credentials /
    SSH / AWS keys, .gitignore respected by default, 200KB per-file cap,
    optional secret redaction), calls the configured LLM provider to
    classify each trap as REAL / GHOST / NEW / UNRESOLVED with file:line
    citations, optionally runs a 2-pass critic that downgrades
    weakly-supported REAL/NEW findings, and computes the four-level
    decision gate (SAFE_TO_PROCEED / PROCEED_WITH_GUARDS /
    NEEDS_MORE_EVIDENCE / DO_NOT_PROCEED).

    Args:
        document: Path to the filled-in antemortem document (.md).
        provider: One of ``anthropic``, ``openai``, ``openai_compatible``.
        model: Provider-specific model id. Defaults from ``DEFAULT_MODELS``.
        base_url: Custom endpoint for OpenAI-compatible providers
            (Azure OpenAI, Groq, Together.ai, OpenRouter, local Ollama).
        repo: Repository root for resolving cited files. Defaults to CWD.
        max_tokens: Output token budget (1024-128000). Default 16000.
        critic: Run a second-pass critic review of REAL/NEW findings
            (roughly doubles per-run API cost).
        no_decision: Skip the decision gate. Artifact still records
            classifications.
        max_file_bytes: Per-file size cap. Files exceeding this are
            skipped with a warning. Default 200KB.
        deny_glob: Comma-separated glob patterns. Files matching any
            pattern are skipped with a warning. Default covers .env,
            secrets/, credentials/, SSH/AWS/PEM keys.
        respect_gitignore: Skip files matched by repo .gitignore.
            Default True. Set False to ignore gitignore (rarely
            advisable — agents can request files an operator would
            never check in).
        redact_secrets: Replace common secret patterns (API keys, AWS
            access tokens, etc.) with ``[REDACTED]`` before sending to
            the provider. Default False (a deny-glob match is normally
            enough).

    Returns:
        Dict with the AntemortemOutput artifact: ``classifications``,
        ``new_traps``, ``critic_results`` (if run), ``decision`` /
        ``decision_rationale`` (unless skipped), ``usage``,
        ``repo_load_warnings``.
    """
    provider_key = provider.lower().strip()
    if provider_key not in supported_providers():
        raise ValueError(
            f"Unknown provider {provider!r}. Supported: "
            + ", ".join(supported_providers())
        )
    expected_env = _ENV_KEY_FOR_PROVIDER.get(provider_key)
    if expected_env is not None and not os.getenv(expected_env):
        raise RuntimeError(
            f"{expected_env} is not set; export it before calling `run` "
            f"with provider={provider_key!r}."
        )

    document_path = Path(document)
    repo_root = Path(repo) if repo else Path.cwd()

    try:
        doc = parse_document(document_path)
    except DocumentParseError as exc:
        raise ValueError(f"Cannot parse {document_path.name}: {exc}") from exc

    deny_globs_tuple = tuple(g.strip() for g in deny_glob.split(",") if g.strip())
    safety = FileSafetyConfig(
        max_file_bytes=max_file_bytes,
        deny_globs=deny_globs_tuple,
        respect_gitignore=respect_gitignore,
        redact_secrets=redact_secrets,
    )
    files, warnings = load_files_for_recon(doc, repo_root, safety)

    # Reviewer P0 #2: refuse to call the provider with zero grounded
    # files. The whole point of antemortem is "classify against actual
    # files"; without files the run degenerates to speculative review,
    # and an artifact written from such a run carries the same
    # decision-gate weight as a real one. CLI already enforces this;
    # pre-fix MCP did not.
    if not files:
        msg = (
            "No readable files resolved from the Recon protocol. "
            "Refusing to run model classification without grounded "
            "evidence. Check the document's `files_to_read` list and "
            f"the `repo` argument ({repo_root})."
        )
        if warnings:
            msg += " Loader warnings: " + "; ".join(warnings)
        raise RuntimeError(msg)

    try:
        provider_obj = make_provider(provider_key, model=model, base_url=base_url)
    except ProviderError as exc:
        raise RuntimeError(str(exc)) from exc

    traps_table = _build_traps_table(doc.traps)
    output, usage = run_classification(
        provider_obj,
        spec=doc.spec,
        traps_table_md=traps_table,
        files=files,
        max_tokens=max_tokens,
    )

    expected_ids = {t.id for t in doc.traps}
    try:
        _check_classification_coverage(expected_ids, output.classifications)
    except ProviderError as exc:
        raise RuntimeError(str(exc)) from exc

    output = _attach_evidence_hashes(output, repo_root)

    critic_summary: dict | None = None
    if critic:
        critic_results, _critic_usage = run_critic_pass(
            provider_obj,
            spec=doc.spec,
            traps_table_md=traps_table,
            files=files,
            first_pass=output,
            max_tokens=max_tokens,
        )
        output = apply_critic_results(output, critic_results)
        critic_summary = {
            "ran": True,
            "downgrades_applied": sum(
                1 for r in critic_results if r.status in {"WEAKENED", "CONTRADICTED"}
            ),
        }

    # Reviewer P1: inverse-critic over GHOST findings.
    if critic_ghosts not in ("none", "high", "all"):
        raise ValueError(
            f"critic_ghosts must be one of {{none, high, all}}, got {critic_ghosts!r}"
        )
    if critic_ghosts in ("high", "all"):
        ghost_results, _ghost_usage = run_ghost_critic_pass(
            provider_obj,
            spec=doc.spec,
            traps_table_md=traps_table,
            files=files,
            first_pass=output,
            mode=critic_ghosts,  # type: ignore[arg-type]
            max_tokens=max_tokens,
        )
        if ghost_results:
            output = apply_critic_results(output, ghost_results)
            ghost_upgrades = sum(
                1 for r in ghost_results if r.status == "CONTRADICTED"
            )
            if critic_summary is None:
                critic_summary = {"ran": True, "downgrades_applied": 0}
            critic_summary["ghost_upgrades_applied"] = ghost_upgrades

    # Reviewer P0: audit citations BEFORE the decision gate. Same
    # contract as CLI run — SAFE_TO_PROCEED requires every non-
    # UNRESOLVED finding to cite a real file:line range.
    citation_audit = audit_output_citations(output, repo_root)

    decision_block: dict | None = None
    if not no_decision:
        if not citation_audit.ok:
            decision_block = {
                "decision": "NEEDS_MORE_EVIDENCE",
                "rationale": (
                    "Citation audit failed: "
                    f"{len(citation_audit.violations)} of {citation_audit.checked} "
                    "non-UNRESOLVED findings have invalid citations. "
                    "SAFE_TO_PROCEED requires every finding to cite a real "
                    "file:line range."
                ),
            }
        else:
            policy = DecisionPolicy(
                unresolved_policy=(
                    "any_blocks_safe" if strict_unresolved else "ratio"
                )
            )
            decision = compute_decision(output, policy=policy)
            decision_block = {
                "decision": decision.decision,
                "rationale": decision.rationale,
            }

    artifact = output.model_dump(mode="json")
    if critic_summary:
        artifact["critic_summary"] = critic_summary
    if decision_block:
        artifact.update(decision_block)
    artifact["usage"] = usage
    artifact["citation_audit"] = {
        "ok": citation_audit.ok,
        "violations": list(citation_audit.violations),
        "checked": citation_audit.checked,
    }
    if warnings:
        artifact["repo_load_warnings"] = warnings
    return artifact


@mcp_app.tool()
def lint(document: str, repo: str | None = None) -> dict:
    """Verify the antemortem document and its artifact (if present).

    Checks that ``files_to_read`` paths exist on disk, that traps have the
    required fields, that the artifact (if a ``.json`` sibling exists)
    references real ``file:line`` locations, and that citations are not
    hallucinated. Pure deterministic verification — zero LLM calls.

    Args:
        document: Path to the antemortem document (.md).
        repo: Repository root for resolving cited files. Defaults to CWD.

    Returns:
        Dict with ``ok`` (bool), ``violations`` (list of strings), and
        ``checked`` (count of checks executed).
    """
    document_path = Path(document)
    repo_root = Path(repo) if repo else Path.cwd()
    result = run_lint(document_path, repo_root)
    return {
        "ok": result.ok,
        "violations": result.violations,
        "checked": result.checked,
    }
