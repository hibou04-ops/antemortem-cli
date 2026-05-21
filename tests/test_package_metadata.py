"""PyPI-facing package metadata checks."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
RELEASE_HYGIENE = ROOT / "docs" / "release_hygiene.md"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_package_description_is_concise_and_trust_focused():
    project = _pyproject()["project"]
    description = project["description"]
    hype_terms = {"revolutionary", "best", "superior", "unbeatable"}

    assert len(description) <= 120
    assert "citation" in description.lower()
    assert not any(term in description.lower() for term in hype_terms)


def test_readme_long_description_is_explicit_markdown():
    readme = _pyproject()["project"]["readme"]

    assert readme == {"file": "README.md", "content-type": "text/markdown"}
    assert (ROOT / readme["file"]).is_file()


def test_project_urls_cover_pypi_navigation_targets():
    urls = _pyproject()["project"]["urls"]

    for label in ("Source", "Issues", "Documentation", "Changelog"):
        assert label in urls
        assert urls[label].startswith("https://github.com/hibou04-ops/")


def test_python_classifiers_match_supported_ci_versions():
    project = _pyproject()["project"]
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    classifiers = set(project["classifiers"])
    supported = set(re.findall(r'"(3\.\d+)"', workflow))

    for version in supported:
        assert f"Programming Language :: Python :: {version}" in classifiers


def test_release_hygiene_documents_pypi_render_check_command():
    text = RELEASE_HYGIENE.read_text(encoding="utf-8")

    assert "## PyPI Rendering Check" in text
    assert "python -m build" in text
    assert "python -m twine check dist/*" in text
