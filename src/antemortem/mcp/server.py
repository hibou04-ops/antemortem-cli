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
from antemortem.commands.lint import run_lint
from antemortem.critic import apply_critic_results, run_critic_pass
from antemortem.decision import compute_decision
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
    template_label = "enhanced" if enhanced else "basic"
    return (
        "---\n"
        f"name: {name}\n"
        f"date: {today}\n"
        "scope: change-local\n"
        "reversibility: high\n"
        "status: draft\n"
        f"template: {template_label}\n"
        "---\n\n"
    )


def _load_repo_files(doc, repo_root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    files: list[tuple[str, str]] = []
    warnings: list[str] = []
    try:
        repo_resolved = repo_root.resolve()
    except FileNotFoundError:
        return files, [f"--repo does not exist: {repo_root}"]

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
        try:
            content = full.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = full.read_text(encoding="utf-8", errors="replace")
            warnings.append(f"{rel_path}: not valid UTF-8, replaced bad bytes")
        files.append((rel_path, content))
    return files, warnings


def _build_traps_table(traps) -> str:
    rows = ["| ID | Hypothesis | A-priori chance |", "|---|---|---|"]
    for t in traps:
        rows.append(f"| {t.id} | {t.hypothesis} | {t.a_priori_chance} |")
    return "\n".join(rows)


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
    no_decision: bool = False,
) -> dict:
    """Run LLM classification on a filled-in antemortem document.

    Reads the document, loads cited repo files, calls the configured LLM
    provider to classify each trap as REAL / GHOST / NEW / UNRESOLVED with
    file:line citations, optionally runs a 2-pass critic that downgrades
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

    Returns:
        Dict with the AntemortemOutput artifact: ``classifications``,
        ``new_traps``, ``critic_results`` (if run), ``decision`` /
        ``decision_rationale`` (unless skipped), ``usage``.
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

    files, warnings = _load_repo_files(doc, repo_root)

    try:
        provider_obj = make_provider(provider_key, model=model, base_url=base_url)
    except ProviderError as exc:
        raise RuntimeError(str(exc)) from exc

    output, usage = run_classification(
        provider_obj,
        spec=doc.spec,
        traps_table_md=_build_traps_table(doc.traps),
        files=files,
        max_tokens=max_tokens,
    )

    critic_summary: dict | None = None
    if critic:
        critic_results = run_critic_pass(provider_obj, output, max_tokens=max_tokens)
        output = apply_critic_results(output, critic_results)
        critic_summary = {
            "ran": True,
            "downgrades_applied": sum(
                1 for r in critic_results if r.status in {"WEAKENED", "CONTRADICTED"}
            ),
        }

    decision_block: dict | None = None
    if not no_decision:
        decision = compute_decision(output)
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
