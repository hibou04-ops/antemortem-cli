"""Tests for generated README claim blocks."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate_readme_claims.py"
CHECKER_PATH = ROOT / "scripts" / "check_repo_consistency.py"


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generate_readme_claims = _load_script(GENERATOR_PATH, "generate_readme_claims")
check_repo_consistency = _load_script(CHECKER_PATH, "check_repo_consistency_for_claims")


def _claim_facts(**overrides):
    defaults = {
        "package_name": "antemortem",
        "package_version": "0.9.4",
        "cli_commands": ("init", "doctor", "run", "lint", "evidence", "gate", "eval"),
        "decision_labels": (
            "SAFE_TO_PROCEED",
            "PROCEED_WITH_GUARDS",
            "NEEDS_MORE_EVIDENCE",
            "DO_NOT_PROCEED",
        ),
        "providers": ("anthropic", "gemini", "openai"),
        "benchmark_metrics": {
            "citation_valid_rate": 0.8,
            "decision_accuracy": 1.0,
            "schema_parse_success_rate": 0.8333333333333334,
        },
        "benchmark_totals": {"cases": 6, "schema_success": 5},
        "evidence_bound_status": (
            "`evidence_hash` and `evidence_snippet` supported; "
            "`lint --strict-evidence` and `evidence --write-missing` available."
        ),
    }
    defaults.update(overrides)
    return generate_readme_claims.ClaimFacts(**defaults)


def _repo_facts(claim_facts):
    return check_repo_consistency.RepositoryFacts(
        package_name=claim_facts.package_name,
        package_version=claim_facts.package_version,
        cli_commands=tuple(sorted(claim_facts.cli_commands)),
        decision_labels=claim_facts.decision_labels,
        providers=claim_facts.providers,
        test_count=0,
    )


def test_generated_command_list_changes_when_fixture_registry_changes():
    fake_app = SimpleNamespace(
        registered_commands=[
            SimpleNamespace(name="init", callback=lambda: None),
            SimpleNamespace(name="doctor", callback=lambda: None),
        ]
    )
    commands = generate_readme_claims.extract_commands_from_typer_app(fake_app)
    first = generate_readme_claims.render_english_claims(
        _claim_facts(cli_commands=commands)
    )

    fake_app.registered_commands.append(
        SimpleNamespace(name="eval", callback=lambda: None)
    )
    changed_commands = generate_readme_claims.extract_commands_from_typer_app(fake_app)
    second = generate_readme_claims.render_english_claims(
        _claim_facts(cli_commands=changed_commands)
    )

    assert "`init` / `doctor`" in first
    assert "`init` / `doctor` / `eval`" in second
    assert first != second


def test_stale_generated_readme_block_is_detected_by_consistency_checker(tmp_path: Path):
    facts = _claim_facts()
    (tmp_path / "docs" / "generated").mkdir(parents=True)
    (tmp_path / "README.md").write_text(
        "Current release: v0.9.4\n"
        "[claims](docs/generated/claims.md) [claims_kr](docs/generated/claims_kr.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "generated" / "claims.md").write_text(
        "stale\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "generated" / "claims_kr.md").write_text(
        generate_readme_claims.render_korean_claims(facts),
        encoding="utf-8",
    )

    issues = check_repo_consistency.check_repository(
        tmp_path,
        readme_files=("README.md",),
        facts=_repo_facts(facts),
        check_generated_claims=True,
        claim_facts=facts,
    )

    assert [issue.code for issue in issues] == ["generated-claims"]
    assert "stale" in issues[0].message


def test_generated_korean_and_english_blocks_share_decision_enums():
    facts = _claim_facts()
    english = generate_readme_claims.render_english_claims(facts)
    korean = generate_readme_claims.render_korean_claims(facts)

    for label in facts.decision_labels:
        assert label in english
        assert label in korean
    enum_re = re.compile(r"`(SAFE_TO_PROCEED|PROCEED_WITH_GUARDS|NEEDS_MORE_EVIDENCE|DO_NOT_PROCEED)`")
    assert set(enum_re.findall(english)) == set(enum_re.findall(korean))


def test_benchmark_metrics_are_read_from_machine_readable_output(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_runner(command: list[str], cwd: Path, env: dict[str, str]) -> str:
        calls.append(command)
        return json.dumps(
            {
                "metrics": {
                    "decision_accuracy": 0.42,
                    "citation_valid_rate": 1.0,
                },
                "totals": {"cases": 2},
            }
        )

    benchmark = generate_readme_claims.load_benchmark_output(
        tmp_path,
        runner=fake_runner,
    )
    facts = _claim_facts(
        benchmark_metrics={
            key: float(value) for key, value in benchmark["metrics"].items()
        },
        benchmark_totals={
            key: int(value) for key, value in benchmark["totals"].items()
        },
    )
    block = generate_readme_claims.render_english_claims(facts)

    assert calls
    assert calls[0][-4:] == ["antemortem.cli", "eval", "benchmarks/golden_cases", "--json"]
    assert "decision_accuracy=0.420" in block
    assert "citation_valid_rate=1.000" in block


def test_generated_claims_do_not_depend_on_pytest_collection(monkeypatch):
    def fail_pytest_collection(*args, **kwargs):  # pragma: no cover - should never run
        raise AssertionError("generated claims must not run pytest collection")

    def fake_benchmark_runner(command: list[str], cwd: Path, env: dict[str, str]) -> str:
        return json.dumps(
            {
                "metrics": {"decision_accuracy": 1.0},
                "totals": {"cases": 1},
            }
        )

    monkeypatch.setattr(generate_readme_claims.subprocess, "run", fail_pytest_collection)

    with_tests = generate_readme_claims.collect_claim_facts(
        ROOT,
        collect_tests=True,
        benchmark_runner=fake_benchmark_runner,
    )
    without_tests = generate_readme_claims.collect_claim_facts(
        ROOT,
        collect_tests=False,
        benchmark_runner=fake_benchmark_runner,
    )

    assert generate_readme_claims.render_english_claims(with_tests) == (
        generate_readme_claims.render_english_claims(without_tests)
    )
    rendered = generate_readme_claims.render_english_claims(with_tests)
    assert "Tests collected" not in rendered
    assert "pytest --collect-only" not in rendered
    assert "python -m pytest -q" in rendered
