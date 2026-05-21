"""Provider support contract tests.

These tests use offline injected clients. They verify the behavior behind the
public provider support matrix without importing or calling live provider SDKs.
"""

from __future__ import annotations

import builtins
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from antemortem.providers import ProviderError
from antemortem.providers.anthropic_provider import AnthropicProvider
from antemortem.providers.capabilities import (
    DEFAULT_MODELS,
    provider_capabilities,
)
from antemortem.providers.gemini_provider import GeminiProvider
from antemortem.providers.openai_provider import OpenAIProvider
from antemortem.schema import AntemortemOutput


def _valid_payload() -> dict:
    return {
        "classifications": [
            {"id": "t1", "label": "REAL", "citation": "a.py:1", "note": "validated"}
        ],
        "new_traps": [],
        "spec_mutations": [],
    }


def _invalid_payload() -> dict:
    payload = _valid_payload()
    payload["classifications"][0]["citation"] = None
    return payload


def _anthropic_client(payload=None, *, error: Exception | None = None):
    def parse(**kwargs):
        if error is not None:
            raise error
        return SimpleNamespace(
            parsed_output=payload,
            stop_reason="end_turn",
            content=[],
            usage=None,
        )

    return SimpleNamespace(messages=SimpleNamespace(parse=parse))


def _openai_client(payload=None, *, error: Exception | None = None):
    def parse(**kwargs):
        if error is not None:
            raise error
        message = SimpleNamespace(parsed=payload)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None)

    completions = SimpleNamespace(parse=parse)
    chat = SimpleNamespace(completions=completions)
    beta = SimpleNamespace(chat=chat)
    return SimpleNamespace(beta=beta)


def _gemini_client(payload=None, *, error: Exception | None = None):
    def generate_content(**kwargs):
        if error is not None:
            raise error
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return SimpleNamespace(
            text=text,
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=None,
        )

    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def _provider_cases(payload=None, *, error: Exception | None = None):
    return {
        "anthropic": AnthropicProvider(
            model=DEFAULT_MODELS["anthropic"],
            client=_anthropic_client(payload, error=error),
        ),
        "openai": OpenAIProvider(
            model=DEFAULT_MODELS["openai"],
            client=_openai_client(payload, error=error),
        ),
        "gemini": GeminiProvider(
            model=DEFAULT_MODELS["gemini"],
            client=_gemini_client(payload, error=error),
        ),
        "openai-compatible": OpenAIProvider(
            model="local-structured-model",
            base_url="http://localhost:11434/v1",
            client=_openai_client(payload, error=error),
        ),
    }


def _complete(provider):
    return provider.structured_complete(
        system_prompt="system",
        user_content="user",
        output_schema=AntemortemOutput,
    )


@contextmanager
def _fail_provider_sdk_imports():
    original_import = builtins.__import__
    blocked = ("anthropic", "openai", "google")

    def guarded_import(name, *args, **kwargs):
        if name == "google" or name.startswith(blocked):
            raise AssertionError(f"offline provider contract test imported SDK: {name}")
        return original_import(name, *args, **kwargs)

    builtins.__import__ = guarded_import
    try:
        yield
    finally:
        builtins.__import__ = original_import


def test_capability_registry_covers_contract_tested_providers():
    assert {cap.key for cap in provider_capabilities()} == set(_provider_cases(_valid_payload()))
    for cap in provider_capabilities():
        assert cap.structured_output_path
        assert cap.local_schema_validation
        assert cap.retry_error_handling
        assert cap.api_key_env
        assert cap.known_caveats


@pytest.mark.parametrize("provider_key", ["anthropic", "openai", "gemini", "openai-compatible"])
def test_provider_contract_accepts_schema_compatible_output(provider_key: str):
    provider = _provider_cases(_valid_payload())[provider_key]

    parsed, usage = _complete(provider)

    assert isinstance(parsed, AntemortemOutput)
    assert parsed.classifications[0].id == "t1"
    assert usage["input_tokens"] == 0


@pytest.mark.parametrize("provider_key", ["anthropic", "openai", "gemini", "openai-compatible"])
def test_provider_contract_rejects_malformed_output(provider_key: str):
    provider = _provider_cases(_invalid_payload())[provider_key]

    with pytest.raises((ProviderError, ValueError)):
        _complete(provider)


@pytest.mark.parametrize("provider_key", ["anthropic", "openai", "gemini", "openai-compatible"])
def test_provider_contract_surfaces_provider_errors(provider_key: str):
    provider = _provider_cases(_valid_payload(), error=RuntimeError("offline boom"))[provider_key]

    with pytest.raises(ProviderError, match="API call failed: offline boom"):
        _complete(provider)


def test_provider_contracts_do_not_import_provider_sdks():
    with _fail_provider_sdk_imports():
        for provider in _provider_cases(_valid_payload()).values():
            parsed, _ = _complete(provider)
            assert isinstance(parsed, AntemortemOutput)
