"""Current source metadata and reproducible bilingual documentation contracts."""
import importlib
import importlib.metadata
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_current_source_runtime_and_installed_versions_agree():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert importlib.import_module("antemortem").__version__ == project["version"] == "0.12.2"
    assert importlib.metadata.version(project["name"]) == project["version"]


def test_canonical_korean_alias_and_reciprocal_links_agree():
    canonical = (ROOT / "README.ko.md").read_bytes()
    assert canonical == (ROOT / "README_KR.md").read_bytes()
    for path in (ROOT / "README.md", ROOT / "README.ko.md"):
        text = path.read_text(encoding="utf-8")
        assert "[English](README.md)" in text
        assert "[한국어](README.ko.md)" in text
        assert "README_KR.md" in text


def test_default_action_installs_checked_out_source_and_preserves_registry_overrides():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert f'default: "{version}"' in text
    assert 'ACTION_SOURCE: ${{ github.action_path }}' in text
    assert f'if [ "$INPUT_PACKAGE_VERSION" = "{version}" ]; then\n          python -m pip install "$ACTION_SOURCE"' in text
    assert 'python -m pip install --upgrade antemortem' in text
    assert 'python -m pip install "antemortem==$INPUT_PACKAGE_VERSION"' in text


def test_readme_stdout_matches_the_actual_keyless_script():
    result = subprocess.run([sys.executable, str(ROOT / "examples/reproduce_citation_traps.py")],
                            capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    output = result.stdout.replace("\r\n", "\n").rstrip()
    for name in ("README.md", "README.ko.md"):
        assert "```text\n" + output + "\n```" in (ROOT / name).read_text(encoding="utf-8")
