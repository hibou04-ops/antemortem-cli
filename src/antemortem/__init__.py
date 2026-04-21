"""Antemortem CLI - tooling for the Antemortem pre-implementation reconnaissance discipline.

Model-agnostic: the CLI speaks to the LLM through an ``LLMProvider``
Protocol. Bundled adapters cover Anthropic, OpenAI, and any
OpenAI-compatible endpoint (Azure OpenAI, Groq, Together.ai, OpenRouter,
local Ollama) via ``--base-url``.

See https://github.com/hibou04-ops/Antemortem for the methodology.
"""

__version__ = "0.3.0"
