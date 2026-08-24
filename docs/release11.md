# NoWreck v0.11.0 — Multi-Provider Support (Anthropic + Gemini)

**Release date:** August 2026
**Previous release:** v0.10.0 (Independent Verification Architecture)
**Focus:** Extend NoWreck beyond the OpenAI-compatible format to two major
providers with different API shapes — Anthropic (Claude) and Google Gemini —
via isolated provider adapters, with zero changes for existing
OpenAI-compatible users.

---

## What's new in v0.11.0

### Provider adapters ✅

Non-OpenAI providers get adapters, not rewrites. The existing
`ModelProvider` core logic (retries, parsing, failure saving) is untouched.
Adapters translate between the provider's native format and the internal
format:

```
ModelProvider
    ├── _detect_adapter(base_url) → adapter
    ├── OpenAIAdapter    — passthrough (OpenAI, Groq, OpenRouter, Grok,
    │                      Kimi, Ollama, LM Studio, any compatible endpoint)
    ├── AnthropicAdapter — /v1/messages, x-api-key auth, top-level system
    └── GeminiAdapter    — /v1beta/models/{model}:generateContent,
                           x-goog-api-key auth, systemInstruction
```

### Anthropic support ✅

- Endpoint: `POST /v1/messages`
- Auth: `x-api-key` header (+ required `anthropic-version` header)
- System messages extracted from the messages array into the top-level
  `system` field
- Response parsed from the `content` block array

```bash
nowreck config set base_url https://api.anthropic.com
nowreck config set api_key sk-ant-...
nowreck config set model claude-sonnet-4-20250514
nowreck fix "Add email validation to auth.py"
```

### Gemini support ✅

- Endpoint: `POST /v1beta/models/{model}:generateContent` (model in URL path)
- Auth: `x-goog-api-key` header
- Messages translated to `contents` with `parts`; system messages go to
  `systemInstruction`; assistant role maps to `model`
- Response parsed from `candidates[0].content.parts[*].text`

```bash
nowreck config set base_url https://generativelanguage.googleapis.com
nowreck config set api_key AIza...
nowreck config set model gemini-2.0-flash
nowreck fix "Add email validation to auth.py"
```

### Auto-detection + explicit override ✅

The adapter is inferred from `base_url` (`api.anthropic.com` → Anthropic,
`generativelanguage.googleapis.com` → Gemini, anything else → OpenAI).
An optional `provider` config key overrides auto-detection when needed:

```bash
nowreck config set provider anthropic   # or: gemini, openai
```

No new CLI flags. The same commands work with every provider.

### Phase 4 integration tests ✅

Six behavioral tests drive the real `_default_http_call` HTTP path
(`urlopen` patched) and prove per-provider request shape, auth headers,
and response round-trip through the correct adapter.

---

## What's unchanged

| What | Why |
|------|-----|
| All OpenAI-compatible providers | `OpenAIAdapter` is passthrough — zero transformation |
| `ClaimParser`, `ClaimVerifier`, `ChangeDetector` | Already correct |
| `PromptModeVerifier` | Adapter is transparent |
| Pre/Post mode | No model needed |
| CLI commands and flags | No new flags needed |
| JSON schema | Unchanged |
| All 13 claim types | No new types needed |
| Independent verification architecture (v0.10.0) | Untouched |

## Security

| Area | What changes |
|------|-------------|
| API key storage | Same (config file or env var) |
| API key display | Same masking behavior as v0.10.0 |
| Anthropic auth | Sent via `x-api-key` header (never in URL or body) |
| Gemini auth | Sent via `x-goog-api-key` header (never in URL or body) |

No new security surface — adapters only transform request/response bodies.

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Full pytest suite | 638 | ✅ all pass |
| New adapter tests (Phases 1–3) | 84 | ✅ all pass |
| New Phase 4 integration tests | 6 | ✅ all pass |
| ruff check + format | 0 issues | ✅ clean |
| basedpyright (strict) | 0 errors | ✅ clean |

## Files modified

| File | Change |
|------|--------|
| `nowreck/model/adapters.py` | **New** — `ProviderAdapter`, `OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter`, `detect_adapter()` |
| `nowreck/model/provider.py` | `_default_http_call()` uses adapters; `_auth_header()`; `provider` field on `ModelConfig` |
| `nowreck/main.py` | Reads `provider` from saved config; banner version bump |
| `tests/test_adapters.py` | **New** — adapter unit tests (Phases 1–3) |
| `tests/test_model.py` | Extended with Phase 4 adapter-selection tests |
| `pyproject.toml`, `nowreck/__init__.py` | Version bump to 0.11.0 |
| `README.md`, `use.md` | Provider tables + Claude/Gemini setup docs |
| `docs/nowreck-v11-scope.md` | Marked done |

---

## Definition of Done

| Criterion | Status |
|-----------|--------|
| `OpenAIAdapter` works identically (passthrough) | ✅ |
| `AnthropicAdapter` translates and parses correctly | ✅ |
| `GeminiAdapter` translates and parses correctly | ✅ |
| Auto-detection selects the correct adapter | ✅ |
| Provider override from config works | ✅ |
| All existing tests pass (regression gate) | ✅ |
| New adapter tests pass | ✅ |
| ruff: 0 issues, basedpyright: 0 errors | ✅ |
| Documentation updated (README, use.md, release notes) | ✅ |
| Version bumped to 0.11.0 | ✅ |

---

## Upgrade notes

No breaking changes. Every existing command and configuration works
identically.

To use Claude or Gemini:

```bash
# Point base_url at the provider's bare domain (no /v1 suffix)
nowreck config set base_url https://api.anthropic.com
nowreck config set api_key sk-ant-...
nowreck config set model claude-sonnet-4-20250514
```

If auto-detection ever picks the wrong format, force it:

```bash
nowreck config set provider anthropic
```

### Known limitations

- Use bare domains (`https://api.anthropic.com`,
  `https://generativelanguage.googleapis.com`) as base URLs — adding a
  `/v1` or `/v1beta` suffix will double the versioned path segment.
- The interactive picker still labels configuration as
  "OpenAI-compatible"; it works with all providers but does not yet ask
  for a provider override.
- Anthropic responses are requested with a default `max_tokens` of 4096;
  very large patches may truncate.
