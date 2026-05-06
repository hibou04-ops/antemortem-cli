"""Provider factory + adapter tests. Mocked SDK clients, no network."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from antemortem.providers import (
    DEFAULT_MODELS,
    ProviderError,
    make_provider,
    supported_providers,
)
from antemortem.providers.anthropic_provider import AnthropicProvider
from antemortem.providers.base import normalize_usage
from antemortem.providers.gemini_provider import GeminiProvider
from antemortem.providers.openai_provider import OpenAIProvider
from antemortem.schema import AntemortemOutput, Classification


def test_supported_providers_lists_all_native_providers():
    names = supported_providers()
    assert "anthropic" in names
    assert "openai" in names
    assert "gemini" in names


def test_default_models_per_provider():
    assert DEFAULT_MODELS["anthropic"].startswith("claude-")
    assert DEFAULT_MODELS["openai"].startswith("gpt-")
    assert DEFAULT_MODELS["gemini"] == "gemini-2.5-flash"


def test_make_provider_rejects_unknown_name():
    with pytest.raises(ProviderError, match="Unknown provider"):
        make_provider("bogus-provider")


def test_make_provider_anthropic_uses_default_model_when_none():
    client = MagicMock()
    p = make_provider("anthropic", client=client)
    assert p.name == "anthropic"
    assert p.model == DEFAULT_MODELS["anthropic"]


def test_make_provider_anthropic_override_model():
    client = MagicMock()
    p = make_provider("anthropic", model="claude-sonnet-4-6", client=client)
    assert p.model == "claude-sonnet-4-6"


def test_make_provider_openai_accepts_base_url():
    client = MagicMock()
    p = make_provider("openai", client=client, base_url="http://localhost:11434/v1")
    assert p.name == "openai"
    assert p.base_url == "http://localhost:11434/v1"


def test_make_provider_gemini_uses_default_model_when_none():
    client = MagicMock()
    p = make_provider("gemini", client=client)
    assert isinstance(p, GeminiProvider)
    assert p.name == "gemini"
    assert p.model == DEFAULT_MODELS["gemini"]


def test_make_provider_gemini_override_model():
    client = MagicMock()
    p = make_provider("gemini", model="gemini-2.5-flash", client=client)
    assert isinstance(p, GeminiProvider)
    assert p.model == "gemini-2.5-flash"


def test_make_provider_strips_anthropic_only_kwargs_for_openai():
    client = MagicMock()
    # Should not raise even though OpenAI adapter doesn't accept these.
    p = make_provider("openai", client=client, enable_thinking=True, effort="high")
    assert p.name == "openai"


# ----------------------------- AnthropicProvider -----------------------------


def _anthropic_response(parsed, usage_tuple=(100, 50, 4096, 0)):
    input_tok, output_tok, cache_write, cache_read = usage_tuple
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason="end_turn",
        content=[],
        usage=SimpleNamespace(
            input_tokens=input_tok,
            output_tokens=output_tok,
            cache_creation_input_tokens=cache_write,
            cache_read_input_tokens=cache_read,
        ),
    )


def test_anthropic_provider_builds_expected_kwargs():
    client = MagicMock()
    client.messages.parse.return_value = _anthropic_response(
        AntemortemOutput(
            classifications=[Classification(id="t1", label="REAL", citation="a.py:1", note="")]
        )
    )
    p = AnthropicProvider(model="claude-test", client=client)
    parsed, usage = p.structured_complete(
        system_prompt="SP",
        user_content="UC",
        output_schema=AntemortemOutput,
    )

    kw = client.messages.parse.call_args.kwargs
    assert kw["model"] == "claude-test"
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"] == {"effort": "high"}
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["output_format"] is AntemortemOutput
    assert usage["cache_creation_input_tokens"] == 4096


def test_anthropic_provider_disables_thinking_when_flag_false():
    client = MagicMock()
    client.messages.parse.return_value = _anthropic_response(AntemortemOutput())
    p = AnthropicProvider(model="claude-test", client=client, enable_thinking=False)
    p.structured_complete(
        system_prompt="SP",
        user_content="UC",
        output_schema=AntemortemOutput,
    )
    kw = client.messages.parse.call_args.kwargs
    assert "thinking" not in kw
    assert "output_config" not in kw


def test_anthropic_provider_raises_on_refusal():
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=None,
        stop_reason="refusal",
        content=[SimpleNamespace(type="text", text="no")],
        usage=None,
    )
    p = AnthropicProvider(model="x", client=client)
    with pytest.raises(ProviderError, match="refused"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


def test_anthropic_provider_raises_on_missing_parsed_output():
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=None,
        stop_reason="end_turn",
        content=[],
        usage=None,
    )
    p = AnthropicProvider(model="x", client=client)
    with pytest.raises(ProviderError, match="no parsed_output"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


def test_anthropic_provider_coerces_dict_parsed_output():
    client = MagicMock()
    dict_out = {"classifications": [], "new_traps": [], "spec_mutations": []}
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=dict_out,
        stop_reason="end_turn",
        content=[],
        usage=None,
    )
    p = AnthropicProvider(model="x", client=client)
    parsed, _ = p.structured_complete(
        system_prompt="SP",
        user_content="UC",
        output_schema=AntemortemOutput,
    )
    assert isinstance(parsed, AntemortemOutput)


# ------------------------------ OpenAIProvider -------------------------------


def _openai_response(
    parsed,
    *,
    finish_reason: str = "stop",
    input_tokens: int = 200,
    output_tokens: int = 80,
    cached_tokens: int = 0,
):
    message = SimpleNamespace(parsed=parsed)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    prompt_tokens_details = SimpleNamespace(cached_tokens=cached_tokens)
    usage = SimpleNamespace(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        prompt_tokens_details=prompt_tokens_details,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def test_openai_provider_builds_expected_kwargs():
    client = MagicMock()
    client.beta.chat.completions.parse.return_value = _openai_response(
        AntemortemOutput(), cached_tokens=4096
    )
    p = OpenAIProvider(model="gpt-test", client=client)
    parsed, usage = p.structured_complete(
        system_prompt="SP",
        user_content="UC",
        output_schema=AntemortemOutput,
    )

    kw = client.beta.chat.completions.parse.call_args.kwargs
    assert kw["model"] == "gpt-test"
    assert kw["response_format"] is AntemortemOutput
    assert kw["messages"][0] == {"role": "system", "content": "SP"}
    assert kw["messages"][1] == {"role": "user", "content": "UC"}
    assert isinstance(parsed, AntemortemOutput)
    # OpenAI cached_tokens maps to cache_read_input_tokens
    assert usage["cache_read_input_tokens"] == 4096
    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 80


def test_openai_provider_raises_on_content_filter():
    client = MagicMock()
    client.beta.chat.completions.parse.return_value = _openai_response(
        AntemortemOutput(), finish_reason="content_filter"
    )
    p = OpenAIProvider(model="x", client=client)
    with pytest.raises(ProviderError, match="content_filter"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


def test_openai_provider_raises_when_parsed_missing():
    client = MagicMock()
    client.beta.chat.completions.parse.return_value = _openai_response(None)
    p = OpenAIProvider(model="x", client=client)
    with pytest.raises(ProviderError, match="no parsed object"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


def test_openai_provider_raises_when_no_choices():
    client = MagicMock()
    client.beta.chat.completions.parse.return_value = SimpleNamespace(choices=[], usage=None)
    p = OpenAIProvider(model="x", client=client)
    with pytest.raises(ProviderError, match="no choices"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


# ------------------------------ GeminiProvider -------------------------------


def _gemini_response(text: str, *, usage: object | None = None):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason="STOP")],
        usage_metadata=usage,
    )


def _valid_antemortem_json() -> str:
    return (
        '{"classifications":[{"id":"t1","label":"REAL","citation":"a.py:1",'
        '"note":"validated"}],"new_traps":[],"spec_mutations":[]}'
    )


def test_gemini_provider_builds_expected_request_shape():
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(_valid_antemortem_json())
    p = GeminiProvider(model="gemini-test", client=client)
    parsed, _ = p.structured_complete(
        system_prompt="SP",
        user_content="UC",
        output_schema=AntemortemOutput,
    )

    kw = client.models.generate_content.call_args.kwargs
    assert kw["model"] == "gemini-test"
    assert kw["contents"] == "UC"
    assert kw["config"]["system_instruction"] == "SP"
    assert kw["config"]["response_mime_type"] == "application/json"
    assert kw["config"]["response_schema"] is AntemortemOutput
    assert isinstance(parsed, AntemortemOutput)


def test_gemini_provider_parses_valid_json_into_schema():
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(_valid_antemortem_json())
    p = GeminiProvider(model="gemini-test", client=client)

    parsed, _ = p.structured_complete(
        system_prompt="SP",
        user_content="UC",
        output_schema=AntemortemOutput,
    )

    assert parsed.classifications[0].id == "t1"
    assert parsed.classifications[0].label == "REAL"


def test_gemini_provider_raises_on_malformed_json():
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response("{not json")
    p = GeminiProvider(model="gemini-test", client=client)

    with pytest.raises(ProviderError, match="invalid JSON"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


def test_gemini_provider_raises_on_schema_invalid_json():
    client = MagicMock()
    invalid = (
        '{"classifications":[{"id":"t1","label":"REAL","citation":null,'
        '"note":"missing citation"}],"new_traps":[],"spec_mutations":[]}'
    )
    client.models.generate_content.return_value = _gemini_response(invalid)
    p = GeminiProvider(model="gemini-test", client=client)

    with pytest.raises(ProviderError, match="schema validation"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


def test_gemini_provider_maps_usage_metadata():
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(
        _valid_antemortem_json(),
        usage=SimpleNamespace(prompt_token_count=123, candidates_token_count=45),
    )
    p = GeminiProvider(model="gemini-test", client=client)

    _, usage = p.structured_complete(
        system_prompt="SP",
        user_content="UC",
        output_schema=AntemortemOutput,
    )

    assert usage == {
        "input_tokens": 123,
        "output_tokens": 45,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def test_gemini_provider_raises_on_safety_block():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text="",
        candidates=[],
        prompt_feedback=SimpleNamespace(block_reason="SAFETY"),
        usage_metadata=None,
    )
    p = GeminiProvider(model="gemini-test", client=client)

    with pytest.raises(ProviderError, match="safety-blocked"):
        p.structured_complete(
            system_prompt="SP",
            user_content="UC",
            output_schema=AntemortemOutput,
        )


# -------------------------- normalize_usage helper ---------------------------


def test_normalize_usage_from_anthropic_shape():
    raw = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_creation_input_tokens=100,
        cache_read_input_tokens=200,
    )
    u = normalize_usage(raw)
    assert u == {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 200,
    }


def test_normalize_usage_from_openai_shape():
    raw = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        prompt_tokens_details=SimpleNamespace(cached_tokens=7),
    )
    u = normalize_usage(raw)
    assert u["input_tokens"] == 10
    assert u["output_tokens"] == 5
    assert u["cache_read_input_tokens"] == 7


def test_normalize_usage_handles_none():
    assert normalize_usage(None) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def test_normalize_usage_from_gemini_shape():
    raw = {"prompt_token_count": 10, "candidates_token_count": 5}
    u = normalize_usage(raw)
    assert u["input_tokens"] == 10
    assert u["output_tokens"] == 5
    assert u["cache_creation_input_tokens"] == 0
    assert u["cache_read_input_tokens"] == 0


def test_normalize_usage_from_gemini_total_token_count():
    raw = {"prompt_token_count": 10, "total_token_count": 14}
    u = normalize_usage(raw)
    assert u["input_tokens"] == 10
    assert u["output_tokens"] == 4
