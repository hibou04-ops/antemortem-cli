"""`antemortem run` — LLM-assisted classification.

Reads an antemortem document, loads the cited files from ``--repo``, calls
Claude Opus 4.7 via ``antemortem.api``, and writes a JSON audit artifact
next to the document (same stem, ``.json`` extension).

The markdown document itself is **not** modified — the artifact is the
machine-readable output. ``antemortem lint`` validates the artifact against
the repo state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer

from antemortem.api import run_classification
from antemortem.parser import DocumentParseError, parse_document
from antemortem.schema import AntemortemDocument, Trap


def _build_traps_table(traps: list[Trap]) -> str:
    """Render the traps list as a markdown table the system prompt expects."""
    rows = ["| id | hypothesis | type |", "|----|-----------|------|"]
    for t in traps:
        hypothesis = t.hypothesis.replace("|", r"\|")
        rows.append(f"| {t.id} | {hypothesis} | {t.type} |")
    return "\n".join(rows)


def _load_files_from_repo(
    doc: AntemortemDocument,
    repo_root: Path,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Resolve each listed file against ``repo_root`` and load its text.

    Returns ``(files, warnings)`` where ``files`` is ``[(path, content), ...]``
    and ``warnings`` is a list of human-readable messages for paths that were
    skipped (missing file, path traversal, etc.).
    """
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


def _make_client() -> Any:
    """Construct an Anthropic client. Kept behind a helper for test seams."""
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError(
            "The 'anthropic' package is not installed. Run `pip install antemortem` "
            "in a fresh environment, or `pip install anthropic` to add it manually."
        ) from exc
    return Anthropic()


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
    max_tokens: int = typer.Option(  # noqa: B008
        16000,
        "--max-tokens",
        help="Upper bound on output tokens. Default 16000 is ample for typical classifications.",
        min=1024,
        max=128000,
    ),
) -> None:
    """Run LLM classification on an antemortem document."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        typer.secho(
            "ANTHROPIC_API_KEY is not set. Get a key at https://console.anthropic.com "
            "and export it before running `antemortem run`.",
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
            "No traps parsed from the document — nothing to classify. "
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

    typer.secho(
        f"Reading {len(files)} file(s) from {repo} ...",
        fg=typer.colors.BRIGHT_BLACK,
    )
    typer.secho(
        "Calling claude-opus-4-7 (this can take 30-90s for multi-file recon) ...",
        fg=typer.colors.BRIGHT_BLACK,
    )

    traps_table = _build_traps_table(doc.traps)
    client = _make_client()
    try:
        output, usage = run_classification(
            client,
            spec=doc.spec,
            traps_table_md=traps_table,
            files=files,
            max_tokens=max_tokens,
        )
    except RuntimeError as exc:
        typer.secho(f"Classification failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

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
            "first run; if repeated, the system prompt may have a silent invalidator.",
            fg=typer.colors.YELLOW,
        )

    # json output to help scripts consume this invocation
    if os.getenv("ANTEMORTEM_JSON_SUMMARY"):
        typer.echo(json.dumps({
            "artifact": str(artifact_path),
            "classifications": len(output.classifications),
            "new_traps": new_count,
            "usage": usage,
        }))
