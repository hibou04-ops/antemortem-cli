# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Offline golden benchmark evaluator for antemortem artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from antemortem.citations import verify_citation
from antemortem.citations import (
    compute_evidence_hash,
    compute_evidence_sha256,
    is_evidence_range_too_large,
    is_valid_evidence_hash,
    normalize_evidence_text,
    read_citation_text,
)
from antemortem.commands.doctor import build_doctor_report
from antemortem.exit_codes import POLICY_GATE_FAILURE, SUCCESS, USAGE_ERROR
from antemortem.schema import AntemortemOutput


METRIC_NAMES = (
    "trap_label_accuracy",
    "new_trap_precision",
    "citation_valid_rate",
    "false_real_rate",
    "false_ghost_rate",
    "unresolved_rate",
    "decision_accuracy",
    "critic_flip_rate",
    "high_severity_block_rate",
    "schema_parse_success_rate",
)

CRITIC_FLIP_STATUSES = frozenset({"WEAKENED", "CONTRADICTED", "DUPLICATE"})


@dataclass
class EvalCounters:
    cases_total: int = 0
    schema_success: int = 0

    label_correct: int = 0
    label_total: int = 0
    predicted_new: int = 0
    correct_new: int = 0
    citation_valid: int = 0
    citation_checked: int = 0
    false_real: int = 0
    false_ghost: int = 0
    unresolved: int = 0
    expected_traps: int = 0
    decision_correct: int = 0
    decision_total: int = 0
    critic_flips: int = 0
    critic_total: int = 0
    high_severity_blocked: int = 0
    high_severity_cases: int = 0

    def metrics(self) -> dict[str, float]:
        return {
            "trap_label_accuracy": _ratio(self.label_correct, self.label_total),
            "new_trap_precision": _ratio(self.correct_new, self.predicted_new, default=1.0),
            "citation_valid_rate": _ratio(self.citation_valid, self.citation_checked),
            "false_real_rate": _ratio(self.false_real, self.label_total),
            "false_ghost_rate": _ratio(self.false_ghost, self.label_total),
            "unresolved_rate": _ratio(self.unresolved, self.expected_traps),
            "decision_accuracy": _ratio(self.decision_correct, self.decision_total),
            "critic_flip_rate": _ratio(self.critic_flips, self.critic_total),
            "high_severity_block_rate": _ratio(
                self.high_severity_blocked,
                self.high_severity_cases,
                default=1.0,
            ),
            "schema_parse_success_rate": _ratio(self.schema_success, self.cases_total),
        }


@dataclass(frozen=True)
class CaseResult:
    name: str
    schema_parse_success: bool
    decision: str | None = None
    expected_decision: str | None = None
    unresolved_count: int | None = None
    expected_unresolved_count: int | None = None
    citation_valid: int = 0
    citation_checked: int = 0
    preflight_readiness: str | None = None
    preflight_warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema_parse_success": self.schema_parse_success,
            "decision": self.decision,
            "expected_decision": self.expected_decision,
            "unresolved_count": self.unresolved_count,
            "expected_unresolved_count": self.expected_unresolved_count,
            "citation_valid": self.citation_valid,
            "citation_checked": self.citation_checked,
            "preflight_readiness": self.preflight_readiness,
            "preflight_warnings": self.preflight_warnings,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class EvalResult:
    root: Path
    metrics: dict[str, float]
    cases: list[CaseResult]
    counters: EvalCounters

    def as_json(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "metrics": self.metrics,
            "totals": {
                "cases": self.counters.cases_total,
                "schema_success": self.counters.schema_success,
                "citation_checked": self.counters.citation_checked,
                "label_total": self.counters.label_total,
            },
            "cases": [case.as_json() for case in self.cases],
        }


def evaluate_golden_cases(root: Path) -> EvalResult:
    """Evaluate every golden case directory under ``root``."""
    case_dirs = _discover_cases(root)
    counters = EvalCounters(cases_total=len(case_dirs))
    case_results: list[CaseResult] = []
    for case_dir in case_dirs:
        case_result = _evaluate_case(case_dir, counters)
        case_results.append(case_result)
    return EvalResult(
        root=root,
        metrics=counters.metrics(),
        cases=case_results,
        counters=counters,
    )


def _discover_cases(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        raise ValueError(f"benchmark path is not a directory: {root}")
    case_dirs = [
        path
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "expected.json").exists()
    ]
    if not case_dirs:
        raise ValueError(f"no golden cases found under {root}")
    return case_dirs


def _evaluate_case(case_dir: Path, counters: EvalCounters) -> CaseResult:
    expected = _read_json(case_dir / "expected.json")
    payload_path = case_dir / "provider_output.json"
    repo_root = case_dir / "repo"
    errors: list[str] = []
    preflight_readiness, preflight_warnings = _audit_preflight(case_dir, expected, errors)

    try:
        payload = _read_json(payload_path)
        output = AntemortemOutput.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        errors.append(f"schema parse failed: {exc}")
        return CaseResult(
            name=case_dir.name,
            schema_parse_success=False,
            expected_decision=expected.get("decision"),
            expected_unresolved_count=expected.get("unresolved_count"),
            preflight_readiness=preflight_readiness,
            preflight_warnings=preflight_warnings,
            errors=errors,
        )

    counters.schema_success += 1

    by_id = {classification.id: classification for classification in output.classifications}
    expected_labels: dict[str, str] = expected.get("classifications", {})
    for trap_id, expected_label in expected_labels.items():
        counters.label_total += 1
        counters.expected_traps += 1
        actual = by_id.get(trap_id)
        actual_label = actual.label if actual else None
        if actual_label == expected_label:
            counters.label_correct += 1
        else:
            errors.append(
                f"{trap_id}: expected label {expected_label}, got {actual_label}"
            )
        if actual_label == "REAL" and expected_label != "REAL":
            counters.false_real += 1
        if actual_label == "GHOST" and expected_label != "GHOST":
            counters.false_ghost += 1
        if actual_label == "UNRESOLVED":
            counters.unresolved += 1

    expected_new_traps = set(expected.get("new_traps", []))
    for new_trap in output.new_traps:
        counters.predicted_new += 1
        if new_trap.id in expected_new_traps:
            counters.correct_new += 1
        else:
            errors.append(f"{new_trap.id}: unexpected new trap")

    expected_citations: dict[str, bool] = expected.get("citation_valid", {})
    citation_valid, citation_checked = _audit_citations(
        output,
        repo_root,
        expected_citations,
        errors,
    )
    counters.citation_valid += citation_valid
    counters.citation_checked += citation_checked

    expected_decision = expected.get("decision")
    if expected_decision is not None:
        counters.decision_total += 1
        if output.decision == expected_decision:
            counters.decision_correct += 1
        else:
            errors.append(
                f"decision: expected {expected_decision}, got {output.decision}"
            )

    expected_unresolved = expected.get("unresolved_count")
    actual_unresolved = sum(1 for c in output.classifications if c.label == "UNRESOLVED")
    if expected_unresolved is not None and actual_unresolved != expected_unresolved:
        errors.append(
            f"unresolved_count: expected {expected_unresolved}, got {actual_unresolved}"
        )

    for critic_result in output.critic_results:
        counters.critic_total += 1
        if critic_result.status in CRITIC_FLIP_STATUSES:
            counters.critic_flips += 1

    if _has_high_severity_unmitigated_finding(output):
        counters.high_severity_cases += 1
        if output.decision == "DO_NOT_PROCEED":
            counters.high_severity_blocked += 1
        else:
            errors.append("high-severity unmitigated finding did not block")

    return CaseResult(
        name=case_dir.name,
        schema_parse_success=True,
        decision=output.decision,
        expected_decision=expected_decision,
        unresolved_count=actual_unresolved,
        expected_unresolved_count=expected_unresolved,
        citation_valid=citation_valid,
        citation_checked=citation_checked,
        preflight_readiness=preflight_readiness,
        preflight_warnings=preflight_warnings,
        errors=errors,
    )


def _audit_preflight(
    case_dir: Path,
    expected: dict[str, Any],
    errors: list[str],
) -> tuple[str | None, list[str]]:
    expected_preflight = expected.get("preflight")
    if expected_preflight is None:
        return None, []

    try:
        report = build_doctor_report(case_dir / "recon.md", case_dir / "repo")
    except Exception as exc:  # pragma: no cover - defensive benchmark isolation
        errors.append(f"preflight failed: {exc}")
        return None, []

    readiness = str(report.get("readiness"))
    warnings = [str(item) for item in report.get("warnings", [])]
    expected_readiness = expected_preflight.get("readiness")
    if expected_readiness is not None and readiness != expected_readiness:
        errors.append(
            f"preflight readiness: expected {expected_readiness}, got {readiness}"
        )
    for needle in expected_preflight.get("warnings_contain", []):
        if not any(str(needle) in warning for warning in warnings):
            errors.append(f"preflight warning not found: {needle}")
    return readiness, warnings


def _audit_citations(
    output: AntemortemOutput,
    repo_root: Path,
    expected_citations: dict[str, bool],
    errors: list[str],
) -> tuple[int, int]:
    valid = 0
    checked = 0
    for classification in output.classifications:
        if classification.label == "UNRESOLVED":
            continue
        checked += 1
        is_valid = _finding_citation_valid(
            classification.citation or "",
            repo_root,
            evidence_hash=classification.evidence_hash,
            legacy_sha256=classification.evidence_sha256,
            evidence_snippet=classification.evidence_snippet,
        )
        if is_valid:
            valid += 1
        _compare_expected_citation(
            classification.id,
            is_valid,
            expected_citations,
            errors,
        )

    for new_trap in output.new_traps:
        checked += 1
        is_valid = _finding_citation_valid(
            new_trap.citation,
            repo_root,
            evidence_hash=new_trap.evidence_hash,
            legacy_sha256=new_trap.evidence_sha256,
            evidence_snippet=new_trap.evidence_snippet,
        )
        if is_valid:
            valid += 1
        _compare_expected_citation(new_trap.id, is_valid, expected_citations, errors)
    return valid, checked


def _finding_citation_valid(
    citation: str,
    repo_root: Path,
    *,
    evidence_hash: str | None,
    legacy_sha256: str | None,
    evidence_snippet: str | None,
) -> bool:
    result = verify_citation(citation, repo_root)
    if not result.ok or result.parsed is None:
        return False

    has_binding = bool(evidence_hash or legacy_sha256 or evidence_snippet)
    if has_binding and is_evidence_range_too_large(result.parsed):
        return False

    text = read_citation_text(result.parsed, repo_root)
    if text is None:
        return False

    if evidence_hash:
        actual = compute_evidence_hash(text)
        if not is_valid_evidence_hash(evidence_hash) or actual != evidence_hash:
            return False
    elif legacy_sha256:
        actual_sha256 = compute_evidence_sha256(text)
        if actual_sha256 != legacy_sha256:
            return False

    if evidence_snippet is not None:
        snippet = normalize_evidence_text(evidence_snippet)
        if not snippet or snippet not in text:
            return False

    return True


def _compare_expected_citation(
    finding_id: str,
    actual: bool,
    expected_citations: dict[str, bool],
    errors: list[str],
) -> None:
    if finding_id not in expected_citations:
        return
    expected = expected_citations[finding_id]
    if actual != expected:
        errors.append(f"{finding_id}: expected citation_valid={expected}, got {actual}")


def _has_high_severity_unmitigated_finding(output: AntemortemOutput) -> bool:
    for classification in output.classifications:
        if (
            classification.label == "REAL"
            and classification.severity == "high"
            and not _has_text(classification.remediation)
        ):
            return True
    for new_trap in output.new_traps:
        if new_trap.severity == "high" and not _has_text(new_trap.remediation):
            return True
    return False


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(numerator: int, denominator: int, *, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def _parse_threshold(raw: str) -> tuple[str, float]:
    if "=" not in raw:
        raise ValueError(f"expected metric=value, got {raw!r}")
    name, value_raw = raw.split("=", 1)
    name = name.strip()
    if name not in METRIC_NAMES:
        raise ValueError(
            f"unknown metric {name!r}. Known metrics: {', '.join(METRIC_NAMES)}"
        )
    try:
        value = float(value_raw)
    except ValueError as exc:
        raise ValueError(f"invalid threshold value for {name}: {value_raw!r}") from exc
    return name, value


def _format_table(result: EvalResult) -> str:
    rows = ["Metric                         Value", "-----------------------------  -----"]
    for name in METRIC_NAMES:
        rows.append(f"{name:<29}  {result.metrics[name]:.3f}")
    rows.append("")
    rows.append(
        f"Cases: {result.counters.cases_total} "
        f"({result.counters.schema_success} schema-valid)"
    )
    failed_cases = [case for case in result.cases if case.errors]
    if failed_cases:
        rows.append(f"Case warnings: {len(failed_cases)}")
    return "\n".join(rows)


def eval(  # noqa: A001
    path: Path = typer.Argument(  # noqa: B008
        ...,
        help="Directory containing golden benchmark case directories.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print machine-readable JSON metrics.",
    ),
    fail_under: list[str] | None = typer.Option(
        None,
        "--fail-under",
        help="Metric threshold in metric=value form. May be passed multiple times.",
    ),
) -> None:
    """Evaluate stored golden benchmark outputs without provider calls."""
    try:
        result = evaluate_golden_cases(path)
        thresholds = [_parse_threshold(raw) for raw in (fail_under or [])]
    except ValueError as exc:
        typer.secho(
            f"FAIL: benchmark arguments are invalid. Why: {exc}. "
            "Next: run `antemortem eval benchmarks/golden_cases --json` "
            "or inspect `antemortem eval --help`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=USAGE_ERROR) from exc

    failures = [
        (name, expected, result.metrics[name])
        for name, expected in thresholds
        if result.metrics[name] < expected
    ]

    if json_output:
        typer.echo(json.dumps(result.as_json(), indent=2, sort_keys=True))
    else:
        typer.echo(_format_table(result))

    if failures:
        for name, expected, actual in failures:
            typer.secho(
                f"FAIL: {name}={actual:.3f} below threshold {expected:.3f}. "
                "Why: offline benchmark metrics did not meet the requested policy floor. "
                f"Next: inspect `antemortem eval {path} --json` before changing code or thresholds.",
                fg=typer.colors.RED,
                err=True,
            )
        raise typer.Exit(code=POLICY_GATE_FAILURE)

    raise typer.Exit(code=SUCCESS)
