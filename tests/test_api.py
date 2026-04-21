"""API wrapper tests - mocked LLMProvider, no network."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from antemortem.api import _build_user_content, run_classification
from antemortem.providers.base import ProviderError
from antemortem.schema import AntemortemOutput, Classification


def test_build_user_content_sorts_files():
    payload = _build_user_content(
        spec="Short spec paragraph.",
        traps_table_md="| id | hypothesis | type |\n|----|----|----|\n| t1 | x | trap |",
        files=[("z_last.py", "zzz\n"), ("a_first.py", "aaa\n")],
    )
    idx_a = payload.index('<file path="a_first.py">')
    idx_z = payload.index('<file path="z_last.py">')
    assert idx_a < idx_z
    assert "<spec>" in payload and "<traps>" in payload


def test_build_user_content_normalizes_windows_paths():
    payload = _build_user_content(
        spec="x",
        traps_table_md="| id | hypothesis | type |",
        files=[(r"src\foo.py", "content\n")],
    )
    assert '<file path="src/foo.py">' in payload
    assert "src\\foo.py" not in payload


def _mock_provider(output: AntemortemOutput, usage: dict[str, int] | None = None) -> MagicMock:
    provider = MagicMock()
    provider.name = "mock"
    provider.model = "mock-model"
    provider.structured_complete.return_value = (
        output,
        usage
        or {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 4096,
            "cache_read_input_tokens": 0,
        },
    )
    return provider


def test_run_classification_delegates_to_provider():
    expected = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="foo.py:10", note="x"),
        ]
    )
    provider = _mock_provider(expected, {"input_tokens": 200, "output_tokens": 80})

    output, usage = run_classification(
        provider,
        spec="Add feature X.",
        traps_table_md="| id | hypothesis | type |\n|----|----|----|\n| t1 | risk | trap |",
        files=[("foo.py", "line1\nline2\nline3\n")],
    )

    assert output == expected
    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 80

    # The provider is called with the frozen system prompt + a structured
    # user payload. No vendor-specific kwargs leak through.
    call = provider.structured_complete.call_args
    assert call.kwargs["output_schema"] is AntemortemOutput
    assert "<files>" in call.kwargs["user_content"]
    assert "<spec>" in call.kwargs["user_content"]
    assert "<traps>" in call.kwargs["user_content"]
    # system_prompt should be the frozen antemortem SYSTEM_PROMPT (not empty)
    assert len(call.kwargs["system_prompt"]) > 1000


def test_run_classification_propagates_provider_errors():
    provider = MagicMock()
    provider.name = "mock"
    provider.model = "mock-model"
    provider.structured_complete.side_effect = ProviderError("simulated refusal")

    with pytest.raises(ProviderError, match="simulated refusal"):
        run_classification(
            provider,
            spec="x",
            traps_table_md="| id | hypothesis | type |",
            files=[("a.py", "a\n")],
        )


def test_run_classification_passes_max_tokens():
    expected = AntemortemOutput()
    provider = _mock_provider(expected)

    run_classification(
        provider,
        spec="x",
        traps_table_md="| id | hypothesis | type |",
        files=[("a.py", "a\n")],
        max_tokens=8000,
    )

    assert provider.structured_complete.call_args.kwargs["max_tokens"] == 8000
