# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem doctor` - deterministic preflight for a recon document."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from antemortem.api import _build_user_content
from antemortem.commands.run import _build_traps_table
from antemortem.file_safety import (
    DEFAULT_DENY_GLOBS,
    DEFAULT_MAX_FILE_BYTES,
    FileSafetyConfig,
    evaluate_file,
    load_gitignore_patterns,
    load_safe_text_with_diagnostics,
    resolve_repo_path,
)
from antemortem.parser import (
    DocumentParseError,
    _find_section,
    _split_sections,
    parse_document,
    split_markdown_table_row,
)
from antemortem.schema import AntemortemDocument


SMALL_PAYLOAD_BYTES = 50_000
MEDIUM_PAYLOAD_BYTES = 250_000
DEFAULT_MAX_PAYLOAD_BYTES = 800_000


def build_doctor_report(
    document: Path,
    repo_root: Path,
    *,
    strict: bool = False,
    redact: bool = False,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    include_payload_preview: bool = False,
    max_preview_chars: int = 1200,
) -> dict[str, Any]:
    """Build a provider-free preflight report for an antemortem document."""
    document_path = document.resolve()
    try:
        repo_resolved = repo_root.resolve()
    except FileNotFoundError:
        repo_resolved = repo_root

    report: dict[str, Any] = {
        "document_path": str(document_path),
        "repo_root": str(repo_resolved),
        "schema_frontmatter_status": "ERROR",
        "frontmatter": {},
        "spec_length": 0,
        "trap_count": 0,
        "traps": [],
        "files_to_read": [],
        "missing_files": [],
        "files_excluded": [],
        "files_loaded": [],
        "total_payload_bytes": 0,
        "largest_file": None,
        "provider_payload_class": "small",
        "warnings": [],
        "readiness": "NOT_READY",
    }

    hard_failures: list[str] = []
    warnings: list[str] = []
    try:
        doc = parse_document(document_path)
    except DocumentParseError as exc:
        warning = f"schema/frontmatter parse failed: {exc}"
        warnings.append(warning)
        hard_failures.append(warning)
        report["warnings"] = warnings
        return report

    report["schema_frontmatter_status"] = "OK"
    report["frontmatter"] = doc.frontmatter.model_dump(mode="json")
    report["spec_length"] = len(doc.spec)
    report["trap_count"] = len(doc.traps)
    report["traps"] = [{"id": t.id, "type": t.type} for t in doc.traps]
    report["files_to_read"] = list(doc.files_to_read)

    warnings.extend(_document_warnings(doc))
    if not doc.spec.strip():
        hard_failures.append("empty spec")
    if not doc.traps:
        hard_failures.append("no traps")
    if not doc.files_to_read:
        hard_failures.append("no files")
    duplicate_ids = _duplicate_trap_ids(doc)
    if duplicate_ids and strict:
        hard_failures.append(f"duplicate trap ids: {', '.join(duplicate_ids)}")
    if _trap_table_looks_malformed(doc):
        hard_failures.append("malformed table")

    file_report = _inspect_files(
        doc,
        repo_resolved,
        redact=redact,
    )
    warnings.extend(file_report["warnings"])
    hard_failures.extend(file_report["hard_failures"])
    report["missing_files"] = file_report["missing_files"]
    report["files_excluded"] = file_report["files_excluded"]
    report["files_loaded"] = file_report["files_loaded"]

    files_for_payload = [
        (item["path"], item["content"]) for item in file_report["loaded_payload_files"]
    ]
    payload = ""
    if doc.traps and files_for_payload:
        payload = _build_user_content(doc.spec, _build_traps_table(doc.traps), files_for_payload)
    total_payload_bytes = len(payload.encode("utf-8"))
    report["total_payload_bytes"] = total_payload_bytes
    report["provider_payload_class"] = _payload_class(total_payload_bytes)
    if total_payload_bytes > max_payload_bytes:
        warning = (
            f"payload over configured limit: "
            f"{total_payload_bytes} > {max_payload_bytes} bytes"
        )
        warnings.append(warning)
        if strict:
            hard_failures.append(warning)
    largest = _largest_file(report["files_loaded"])
    report["largest_file"] = largest
    if include_payload_preview:
        report["payload_preview"] = payload[: max(0, max_preview_chars)]

    if strict:
        hard_failures.extend(warnings)
    report["warnings"] = _dedupe(warnings)
    report["readiness"] = _readiness(hard_failures, report["warnings"])
    return report


def _document_warnings(doc: AntemortemDocument) -> list[str]:
    warnings: list[str] = []
    duplicate_ids = _duplicate_trap_ids(doc)
    if duplicate_ids:
        warnings.append(f"duplicate trap ids: {', '.join(duplicate_ids)}")
    if not doc.spec.strip():
        warnings.append("empty spec")
    if not doc.traps:
        warnings.append("no traps")
    if not doc.files_to_read:
        warnings.append("no files")
    if _trap_table_looks_malformed(doc):
        warnings.append("malformed table")
    return warnings


def _duplicate_trap_ids(doc: AntemortemDocument) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for trap in doc.traps:
        if trap.id in seen:
            duplicates.add(trap.id)
        seen.add(trap.id)
    return sorted(duplicates)


def _trap_table_looks_malformed(doc: AntemortemDocument) -> bool:
    sections = _split_sections(doc.raw_markdown)
    body = _find_section(sections, "trap")
    if not body:
        return False
    data_rows = []
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_markdown_table_row(stripped)
        if not cells:
            continue
        first = cells[0].strip().lower()
        if first in ("#", "id", "") or set(first) <= set("-: "):
            continue
        data_rows.append(cells)
    if not data_rows:
        return False
    return any(len(row) < 3 for row in data_rows)


def _inspect_files(
    doc: AntemortemDocument,
    repo_root: Path,
    *,
    redact: bool,
) -> dict[str, Any]:
    safety = FileSafetyConfig(redact_secrets=redact)
    try:
        root_resolved = repo_root.resolve()
    except FileNotFoundError:
        return {
            "missing_files": [],
            "files_excluded": [],
            "files_loaded": [],
            "loaded_payload_files": [],
            "warnings": [f"--repo directory does not exist: {repo_root}"],
            "hard_failures": [f"--repo directory does not exist: {repo_root}"],
        }
    gitignore_patterns = load_gitignore_patterns(root_resolved) if safety.respect_gitignore else ()
    missing_files: list[str] = []
    files_excluded: list[dict[str, Any]] = []
    files_loaded: list[dict[str, Any]] = []
    loaded_payload_files: list[dict[str, str]] = []
    warnings: list[str] = []
    hard_failures: list[str] = []

    for rel_path in doc.files_to_read:
        resolution = resolve_repo_path(rel_path, root_resolved)
        if not resolution.allowed or resolution.path is None:
            warning = f"path traversal attempt: {rel_path}"
            warnings.append(warning)
            hard_failures.append(warning)
            files_excluded.append({"path": rel_path, "reason": resolution.reason})
            continue
        full = resolution.path
        if not full.exists() or not full.is_file():
            warning = f"missing file: {rel_path}"
            warnings.append(warning)
            hard_failures.append(warning)
            missing_files.append(rel_path)
            continue
        decision = evaluate_file(rel_path, full, safety, gitignore_patterns)
        if not decision.allowed:
            warning = (
                f"binary file skipped: {rel_path}"
                if decision.reason == "binary file skipped"
                else f"file excluded by safety policy: {rel_path}: {decision.reason}"
            )
            warnings.append(warning)
            files_excluded.append({"path": rel_path, "reason": decision.reason})
            continue
        content, redactions, used_replacement = load_safe_text_with_diagnostics(
            full,
            safety,
        )
        byte_len = len(content.encode("utf-8"))
        if used_replacement:
            warnings.append(f"invalid UTF-8 bytes replaced: {rel_path}")
        if redactions:
            warnings.append(
                f"redacted secrets: {rel_path}: {redactions} substitution(s)"
            )
        files_loaded.append(
            {
                "path": rel_path,
                "bytes": byte_len,
                "redactions": redactions,
            }
        )
        loaded_payload_files.append({"path": rel_path, "content": content})

    if doc.files_to_read and not loaded_payload_files:
        hard_failures.append("no files loaded")
    return {
        "missing_files": missing_files,
        "files_excluded": files_excluded,
        "files_loaded": files_loaded,
        "loaded_payload_files": loaded_payload_files,
        "warnings": warnings,
        "hard_failures": hard_failures,
    }


def _payload_class(payload_bytes: int) -> str:
    if payload_bytes <= SMALL_PAYLOAD_BYTES:
        return "small"
    if payload_bytes <= MEDIUM_PAYLOAD_BYTES:
        return "medium"
    return "large"


def _largest_file(files_loaded: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not files_loaded:
        return None
    return max(files_loaded, key=lambda item: int(item["bytes"]))


def _readiness(hard_failures: list[str], warnings: list[str]) -> str:
    if hard_failures:
        return "NOT_READY"
    if warnings:
        return "READY_WITH_WARNINGS"
    return "READY"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _render_text_report(
    report: dict[str, Any],
    *,
    show_files: bool,
    show_payload_preview: bool,
) -> str:
    traps = ", ".join(f"{t['id']}:{t['type']}" for t in report["traps"]) or "-"
    files = ", ".join(report["files_to_read"]) or "-"
    excluded = ", ".join(
        f"{item['path']} ({item['reason']})" for item in report["files_excluded"]
    ) or "-"
    largest = report["largest_file"]
    largest_text = "-" if largest is None else f"{largest['path']} ({largest['bytes']} bytes)"
    lines = [
        f"Document: {report['document_path']}",
        f"Repo: {report['repo_root']}",
        f"Schema/frontmatter: {report['schema_frontmatter_status']}",
        f"Spec length: {report['spec_length']}",
        f"Trap count: {report['trap_count']}",
        f"Traps: {traps}",
        f"Files to read: {files}",
        f"Missing files: {', '.join(report['missing_files']) or '-'}",
        f"Files excluded: {excluded}",
        f"Total payload bytes: {report['total_payload_bytes']}",
        f"Largest file: {largest_text}",
        f"Provider payload class: {report['provider_payload_class']}",
    ]
    if report["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in report["warnings"])
    else:
        lines.append("Warnings: -")
    if show_files:
        lines.append("Loaded files:")
        if report["files_loaded"]:
            lines.extend(
                f"  - {item['path']} ({item['bytes']} bytes, redactions={item['redactions']})"
                for item in report["files_loaded"]
            )
        else:
            lines.append("  -")
    if show_payload_preview and "payload_preview" in report:
        lines.append("Payload preview:")
        lines.append(report["payload_preview"])
    lines.append(f"Readiness: {report['readiness']}")
    return "\n".join(lines)


def doctor(
    document: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the antemortem document to inspect.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    repo: Path = typer.Option(  # noqa: B008
        Path.cwd(),
        "--repo",
        "-r",
        help="Repository root to resolve Recon protocol files against.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    json_output: bool = typer.Option(  # noqa: B008
        False,
        "--json",
        help="Print a stable JSON report.",
    ),
    show_files: bool = typer.Option(  # noqa: B008
        False,
        "--show-files",
        help="Include loaded and excluded file details in text output.",
    ),
    show_payload_preview: bool = typer.Option(  # noqa: B008
        False,
        "--show-payload-preview",
        help="Include the provider payload prefix. No provider call is made.",
    ),
    max_preview_chars: int = typer.Option(  # noqa: B008
        1200,
        "--max-preview-chars",
        help="Maximum payload preview characters when --show-payload-preview is set.",
        min=0,
    ),
    strict: bool = typer.Option(  # noqa: B008
        False,
        "--strict",
        help="Treat warnings as NOT_READY.",
    ),
    redact: bool = typer.Option(  # noqa: B008
        False,
        "--redact",
        help="Apply the same opt-in secret redaction used by run --redact-secrets.",
    ),
    json_output_path: Path | None = typer.Option(  # noqa: B008
        None,
        "--json-output",
        help="Write the JSON report to this path. Doctor writes no files unless set.",
        file_okay=True,
        dir_okay=False,
        writable=True,
    ),
) -> None:
    """Show what `run` would parse, read, send, and validate before provider use."""
    report = build_doctor_report(
        document,
        repo,
        strict=strict,
        redact=redact,
        include_payload_preview=show_payload_preview,
        max_preview_chars=max_preview_chars,
    )
    if json_output_path is not None:
        json_output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if json_output:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
    else:
        typer.echo(
            _render_text_report(
                report,
                show_files=show_files,
                show_payload_preview=show_payload_preview,
            )
        )
    raise typer.Exit(code=0 if report["readiness"] != "NOT_READY" else 1)
