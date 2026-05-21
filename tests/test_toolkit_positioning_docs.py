"""Documentation contract tests for toolkit positioning."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
ENGLISH_DOC = ROOT / "docs" / "toolkit_positioning.md"
KOREAN_DOC = ROOT / "docs" / "toolkit_positioning_kr.md"
README_FILES = (
    ROOT / "README.md",
    ROOT / "README_KR.md",
    ROOT / "EASY_README.md",
    ROOT / "EASY_README_KR.md",
)
ALLOWED_EXTERNAL_LINKS = {
    "https://www.omega-plc.com/",
}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_toolkit_positioning_docs_cover_required_roles():
    english = ENGLISH_DOC.read_text(encoding="utf-8")
    korean = KOREAN_DOC.read_text(encoding="utf-8")

    required_english = (
        "pre-implementation reconnaissance",
        "risk classification before code changes",
        "citation/evidence verified CLI artifacts",
        "omegaprompt",
        "Calibration / optimization layer",
        "omega-lock",
        "Audit / post-optimization lock layer",
        "mini-omega-lock",
        "Empirical live API preflight",
        "mini-antemortem-cli",
        "Deterministic analytical preflight",
        "https://www.omega-plc.com/",
        "This repository does not host a dashboard",
        "This document does not claim",
    )
    required_korean = (
        "구현 전 reconnaissance",
        "코드 변경 전 risk classification",
        "citation/evidence가 검증된 CLI artifact",
        "omegaprompt",
        "Calibration / optimization layer",
        "omega-lock",
        "Audit / post-optimization lock layer",
        "mini-omega-lock",
        "Empirical live API preflight",
        "mini-antemortem-cli",
        "Deterministic analytical preflight",
        "https://www.omega-plc.com/",
        "dashboard, SaaS control plane, 범용 agent framework를 포함하지 않습니다",
        "주장하지 않습니다",
    )

    for needle in required_english:
        assert needle in english
    for needle in required_korean:
        assert needle in korean


def test_readme_variants_link_toolkit_positioning_docs():
    for path in README_FILES:
        text = path.read_text(encoding="utf-8")
        assert "docs/toolkit_positioning.md" in text
        assert "docs/toolkit_positioning_kr.md" in text


def test_toolkit_positioning_links_are_local_or_allowlisted():
    for path in (ENGLISH_DOC, KOREAN_DOC):
        text = path.read_text(encoding="utf-8")
        for raw_link in MARKDOWN_LINK_RE.findall(text):
            link = raw_link.split("#", 1)[0]
            parsed = urlparse(link)
            if parsed.scheme in {"http", "https"}:
                assert link in ALLOWED_EXTERNAL_LINKS
                continue
            if not link or link.startswith("mailto:"):
                continue
            target = (path.parent / link).resolve()
            assert target.is_file(), f"{path.relative_to(ROOT)} links to missing file {link}"


def test_toolkit_positioning_avoids_hype_claims():
    combined = (
        ENGLISH_DOC.read_text(encoding="utf-8")
        + "\n"
        + KOREAN_DOC.read_text(encoding="utf-8")
    ).lower()

    banned = (
        "revolutionary",
        "unbeatable",
        "enterprise-ready",
        "production-proven",
        "adopted by",
        "최고",
        "프로덕션 검증",
    )
    for token in banned:
        assert token not in combined
