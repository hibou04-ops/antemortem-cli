"""Documentation contract tests for the restrained public launch kit."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "docs" / "launch_note.md",
    ROOT / "docs" / "launch_note_kr.md",
    ROOT / "docs" / "social_short.md",
    ROOT / "docs" / "social_short_kr.md",
)
COMMANDS = (
    "PYTHONIOENCODING=utf-8 python examples/demo_replay.py",
    "antemortem lint examples/demo_antemortem.md --repo .",
    "antemortem eval benchmarks/golden_cases --json",
    "python scripts/check_repo_consistency.py",
)
BANNED = (
    "best",
    "unbeatable",
    "outperform",
    "adopted by",
    "production-proven",
    "replaces ai code review",
    "replacement for ai code review",
)


def _combined_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_launch_kit_docs_exist_and_cover_required_focus():
    combined = _combined_text()
    required = (
        "pre-implementation risk classification",
        "repo-grounded citations",
        "evidence-bound",
        "offline golden benchmark",
        "release hygiene",
        "구현 전 risk classification",
        "repo-grounded citation",
        "offline golden benchmark",
        "release hygiene",
    )

    for path in DOCS:
        assert path.is_file()
    for needle in required:
        assert needle in combined


def test_launch_kit_has_reproducible_commands_and_current_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    combined = _combined_text()

    for command in COMMANDS:
        assert command in combined
    assert f"python scripts/post_release_check.py --version {version} --skip-pypi-network" in combined
    assert f"python scripts/post_release_check.py --version {version}" in combined
    assert "python scripts/generate_readme_claims.py --check" in combined
    assert "python scripts/release_audit.py" in combined


def test_launch_kit_avoids_banned_public_claims():
    combined = _combined_text().lower()

    for token in BANNED:
        assert token.lower() not in combined


def test_launch_kit_mentions_limitations_clearly():
    combined = _combined_text()
    required_limitations = (
        "Benchmark metrics are repo-local fixtures",
        "Citations prove",
        "Provider behavior can vary",
        "provider API keys",
        "benchmark metric은 repo-local fixture",
        "absolute truth",
        "provider behavior",
    )

    for needle in required_limitations:
        assert needle in combined


def test_launch_kit_links_are_local_and_existing():
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in DOCS:
        for raw_link in link_re.findall(path.read_text(encoding="utf-8")):
            link = raw_link.split("#", 1)[0]
            if not link:
                continue
            assert not link.startswith(("http://", "https://"))
            target = (path.parent / link).resolve()
            assert target.is_file(), f"{path.relative_to(ROOT)} links to missing file {link}"
