"""Tests for the API wrapper — mocked Anthropic client, no network."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from antemortem.api import _build_user_content, run_classification
from antemortem.schema import AntemortemOutput, Classification


def _mock_response(output: AntemortemOutput) -> SimpleNamespace:
    """Build a stand-in for the SDK's Message response object."""
    return SimpleNamespace(
        parsed_output=output,
        stop_reason="end_turn",
        content=[],
        usage=SimpleNamespace(
            input_tokens=120,
            output_tokens=350,
            cache_creation_input_tokens=4200,
            cache_read_input_tokens=0,
        ),
    )


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


def test_run_classification_returns_parsed_output_and_usage():
    expected = AntemortemOutput(
        classifications=[
            Classification(id="t1", label="REAL", citation="foo.py:10", note="x"),
        ]
    )
    client = MagicMock()
    client.messages.parse.return_value = _mock_response(expected)

    output, usage = run_classification(
        client,
        spec="Add feature X.",
        traps_table_md="| id | hypothesis | type |\n|----|----|----|\n| t1 | risk | trap |",
        files=[("foo.py", "line1\nline2\nline3\n")],
    )

    assert output == expected
    assert usage["cache_creation_input_tokens"] == 4200
    assert usage["output_tokens"] == 350

    call = client.messages.parse.call_args
    kwargs = call.kwargs
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "high"}
    assert kwargs["output_format"] is AntemortemOutput

    system = kwargs["system"]
    assert isinstance(system, list)
    assert len(system) == 1
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "Antemortem" in system[0]["text"]


def test_run_classification_raises_on_refusal():
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=None,
        stop_reason="refusal",
        content=[SimpleNamespace(type="text", text="I can't help with that.")],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )
    with pytest.raises(RuntimeError, match="refused"):
        run_classification(
            client,
            spec="x",
            traps_table_md="| id | hypothesis | type |",
            files=[("a.py", "a\n")],
        )


def test_run_classification_raises_when_parsed_output_missing():
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=None,
        stop_reason="end_turn",
        content=[],
        usage=SimpleNamespace(
            input_tokens=1,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )
    with pytest.raises(RuntimeError, match="no parsed_output"):
        run_classification(
            client,
            spec="x",
            traps_table_md="| id | hypothesis | type |",
            files=[("a.py", "a\n")],
        )


def test_run_classification_coerces_dict_parsed_output():
    """Some SDK versions may pass a dict through parsed_output."""
    raw_dict = {
        "classifications": [
            {"id": "t1", "label": "GHOST", "citation": "a.py:1", "note": "n"},
        ],
        "new_traps": [],
        "spec_mutations": [],
    }
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=raw_dict,
        stop_reason="end_turn",
        content=[],
        usage=SimpleNamespace(
            input_tokens=1,
            output_tokens=1,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )
    output, _ = run_classification(
        client,
        spec="x",
        traps_table_md="| id | hypothesis | type |",
        files=[("a.py", "a\n")],
    )
    assert isinstance(output, AntemortemOutput)
    assert output.classifications[0].id == "t1"
