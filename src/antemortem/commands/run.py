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
from antemortem.critic import apply_critic_results, run_critic_pass
from antemortem.decision import compute_decision
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


def _build_traps_table(traps: list[Trap]) -> str:
    """Render the traps list as the markdown table the system prompt expects."""
    rows = ["| id | hypothesis | type |", "|----|-----------|------|"]
    for t in traps:
        hypothesis = t.hypothesis.replace("|", r"\|")
        rows.append(f"| {t.id} | {hypothesis} | {t.type} |")
    return "\n".join(rows)


def _load_files_from_repo(
    doc: AntemortemDocument,
    repo_root: Path,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Resolve each listed file against ``repo_root`` and load its text."""
    files: list[tuple[str, str]] = []
    warnings: list[str] = []
    try:
        repo_resolved = repo_root.resolve()
    except FileNotFoundError:
        warnings.append(f"--repo does not exist: {repo_root}")
        return files, warnings

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
    no_decision: bool = typer.Option(  # noqa: B008
        False,
        "--no-decision",
        help="Skip the four-level decision gate. Artifact still records classifications.",
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

    files, warnings = _load_files_from_repo(doc, repo)
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

    if not no_decision:
        decision = compute_decision(output)
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
