"""Tier B docking invariant (omega-lock <- antemortem-cli, doc-citation seam).

After de-namespacing the one fictional few-shot (prompts.py, Tier B Edit 5:
`src/omega_lock/core.py` -> `src/example_pkg/core.py`), the invariant
"any `src/omega_lock/*` citation in the corpus is a REAL claim" holds repo-wide.
That lets the README citation-drift check (B3/B4) verify every omega-lock
citation against a pinned omega-lock checkout with NO allowlist.

This test is the durable, offline enforcement of that invariant: the few-shot
prompt corpus (prompts.py, templates.py) must carry ZERO `src/omega_lock/`
namespace. Real omega-lock citations live only in README.md / README_KR.md.
No omega-lock import, no checkout -- runs in the existing trust-checks pytest.
"""

from pathlib import Path

_ANTEMORTEM_SRC = Path(__file__).resolve().parents[1] / "src" / "antemortem"

# The few-shot corpus: example traps/citations shown to the model. These are
# illustrative, NOT real-code claims, so they must never reference omega-lock's
# real namespace (a stale or fictional `src/omega_lock/...` there would defeat
# the README citation-drift guard's no-allowlist invariant).
_CORPUS_FILES = ("prompts.py", "templates.py")


def test_few_shot_corpus_has_no_omega_lock_namespace() -> None:
    offenders = []
    for name in _CORPUS_FILES:
        text = (_ANTEMORTEM_SRC / name).read_text(encoding="utf-8")
        if "src/omega_lock/" in text:
            offenders.append(name)
    assert not offenders, (
        f"{offenders} contain a 'src/omega_lock/' citation. The few-shot corpus must "
        "carry NO omega-lock namespace so 'any src/omega_lock/* citation == real claim' "
        "holds (the README citation-drift check relies on it with no allowlist). "
        "De-namespace illustrative examples (e.g. 'src/example_pkg/...'), like "
        "prompts.py Tier B Edit 5."
    )
