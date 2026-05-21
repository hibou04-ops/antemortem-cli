# Provider Compatibility

Provider support claims are source-backed by `src/antemortem/providers/capabilities.py` and contract-tested in `tests/test_provider_contracts.py`. The tests use injected offline stubs; they do not import or call live provider SDK clients.

<!-- provider-matrix:start -->
| Provider | CLI | Default model | API key env | Structured output path | Contract-tested behavior | Caveats |
|---|---|---|---|---|---|---|
| Anthropic | `--provider anthropic` | `claude-opus-4-7` | `ANTHROPIC_API_KEY` | `messages.parse(output_format=...)` | Pydantic validates parsed/dict output before artifact write. SDK exceptions and refusals surface as ProviderError. | Native Anthropic only; base_url is ignored. |
| OpenAI | `--provider openai` | `gpt-4o` | `OPENAI_API_KEY` | `beta.chat.completions.parse(response_format=...)` | Pydantic validates parsed/dict output before artifact write. SDK exceptions, content_filter, missing choices, and missing parsed output surface as ProviderError. | Requires models/endpoints that support the SDK structured parse path. |
| Gemini | `--provider gemini` | `gemini-2.5-flash` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `Google GenAI response_schema with application/json` | Returned JSON is parsed and validated with the same Pydantic artifact schema. SDK exceptions, invalid JSON, schema errors, safety blocks, and missing candidates surface as ProviderError. | Requires Google GenAI SDK; no OpenAI-compatible base_url path. |
| OpenAI-compatible | `--provider openai --base-url <url>` | `user-supplied via --model` | `OPENAI_API_KEY` / `or any string for unauthenticated local endpoints` | `Same OpenAI parse path via configured base_url` | Pydantic validates parsed/dict output before artifact write. Same OpenAI adapter ProviderError handling. | Not universal: endpoint must implement the structured parse path; local model fidelity varies and lint remains mandatory. |
<!-- provider-matrix:end -->

## Contract Boundary

The support contract is narrow:

- adapters must return an instance of the requested Pydantic schema or reject the response;
- malformed JSON, malformed parsed objects, refusal/content-filter/safety-block responses, missing choices, and missing parsed output must fail before artifact write;
- OpenAI-compatible endpoints are supported only when they implement the OpenAI SDK structured parse path used by `OpenAIProvider`;
- `lint` remains the local authority for citation validity regardless of provider.

## Reproduce

```bash
pytest -q tests/test_provider_contracts.py
python scripts/check_repo_consistency.py
```
