"""Trust model documentation contract tests."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README_FILES = (
    ROOT / "README.md",
    ROOT / "README_KR.md",
    ROOT / "EASY_README.md",
    ROOT / "EASY_README_KR.md",
)


def test_trust_model_docs_cover_required_topics():
    english = (ROOT / "docs" / "trust_model.md").read_text(encoding="utf-8")
    korean = (ROOT / "docs" / "trust_model_kr.md").read_text(encoding="utf-8")

    required_english = (
        "What It Verifies",
        "What It Does Not Verify",
        "Why You Write The Traps First",
        "Citation Validation",
        "Evidence Hashes",
        "Offline Golden Benchmarks",
        "Provider Output Is Not Trusted Until Linted",
        "CI Use",
        "Known Limitations",
        "The model may miss risks",
        "Benchmark cases are repo-local fixtures",
        "Citations prove grounding",
        "Provider behavior may vary",
    )
    required_korean = (
        "무엇을 검증하는가",
        "무엇을 검증하지 않는가",
        "왜 사용자가 trap을 먼저 쓰는가",
        "Citation validation",
        "Evidence hash",
        "Offline golden benchmark",
        "Provider output은 lint 전까지 신뢰하지 않는다",
        "CI 사용 방식",
        "알려진 한계",
        "모델은 리스크를 놓칠 수 있습니다",
        "repo-local fixture",
        "absolute truth",
        "Provider behavior",
    )

    for needle in required_english:
        assert needle in english
    for needle in required_korean:
        assert needle in korean


def test_trust_model_docs_are_referenced_from_readme_variants():
    for path in README_FILES:
        text = path.read_text(encoding="utf-8")
        assert "docs/trust_model.md" in text
        assert "docs/trust_model_kr.md" in text


def test_trust_model_avoids_unbacked_comparative_claims():
    combined = (
        (ROOT / "docs" / "trust_model.md").read_text(encoding="utf-8")
        + "\n"
        + (ROOT / "docs" / "trust_model_kr.md").read_text(encoding="utf-8")
    ).lower()

    banned = (
        "superior",
        "best",
        "outperform",
        "unbeatable",
        "우월",
        "최고",
    )
    for token in banned:
        assert token not in combined
