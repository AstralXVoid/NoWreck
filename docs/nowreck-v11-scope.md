# NoWreck — v11 Scope (Multi-Provider Support)

**Status:** Done. All five phases implemented and verified locally — full
suite green, ruff and basedpyright clean. Same discipline as v2 through v10:
local development only — not published, not merged into the public repo,
until proven and deliberately released. See `docs/release11.md`.

## Principle

Same rule as every prior increment: one small thing at a time, proven before
expanding. v10 (independent verification architecture) is done and its
Definition of Done is fulfilled. v11 is **adding Anthropic and Gemini provider
support** — extending NoWreck beyond the OpenAI-compatible format to two major
providers with different API shapes.

## The Problem

NoWreck currently works with any OpenAI-compatible endpoint (OpenAI, Groq,
OpenRouter, Grok, Kimi, Ollama, LM Studio). But Anthropic (Claude) and
Google Gemini use different API formats:

- **Anthropic:** `/v1/messages` endpoint, `x-api-key` auth header, different
  request/response schema
- **Gemini:** `/v1beta/models/{model}:generateContent` endpoint, different
  request/response schema, API key in URL or header

Users who want to use Claude or Gemini must currently proxy through
OpenRouter or similar. v11 adds native support.

## Architectural Principles

1. **OpenAI-compatible providers require zero code changes.** Grok, Kimi,
   OpenRouter, Groq, Ollama, LM Studio, and any OpenAI-compatible endpoint
   must continue to work identically.

2. **Non-OpenAI providers get adapters, not rewrites.** The existing
   `ModelProvider` stays intact. Adapters translate between the provider's
   native format and the internal OpenAI format.

3. **Adapters are isolated.** They live in `nowreck/model/adapters.py`.
   They do not touch the verifier, scanner, reporter, or any other component.

4. **Auto-detection from `base_url`.** The provider is inferred from the
   configured `base_url`. No new CLI flags needed.

5. **Backwards compatibility preserved.** All existing config, all existing
   commands, all existing tests must pass unchanged.

## What Changes in v11

### Added

| What | Why |
|------|-----|
| `ProviderAdapter` base class | Abstraction for non-OpenAI providers |
| `AnthropicAdapter` | Translate Claude's `/v1/messages` format |
| `GeminiAdapter` | Translate Gemini's `generateContent` format |
| Auto-detection in `ModelProvider` | Select adapter based on `base_url` |
| `provider` field in config (optional) | Explicit provider override when auto-detect fails |

### Unchanged

| What | Why |
|------|-----|
| `ModelProvider` core logic | Retries, parsing, failure saving — all reused |
| `ClaimParser` | Already correct |
| `ClaimVerifier.verify()` | Already correct |
| `ChangeDetector.detect()` | Already correct |
| `PromptModeVerifier` | Already correct |
| `RepositoryScanner` | Already correct |
| `SymbolIndex` | Already correct |
| All 13 claim types | No new types needed |
| Pre/Post mode | Already correct — no model needed |
| Prompt mode | Already correct — adapter is transparent |
| CLI | No new flags needed |
| JSON schema | Unchanged |
| All existing tests | Must pass unchanged |

## Adapter Architecture

```
ModelProvider (existing)
    │
    ├── _detect_adapter(base_url) → ProviderAdapter
    │
    ├── OpenAIAdapter (passthrough — no transformation)
    │       Used for: OpenAI, Groq, OpenRouter, Grok,
    │                 Kimi, Ollama, LM Studio, any
    │                 OpenAI-compatible endpoint
    │
    ├── AnthropicAdapter
    │       Input:  OpenAI-format messages
    │       Output: Anthropic-format request body
    │       Auth:   x-api-key header
    │       Endpoint: /v1/messages
    │
    └── GeminiAdapter
            Input:  OpenAI-format messages
            Output: Gemini-format request body
            Auth:   x-api-key header (or URL param)
            Endpoint: /v1beta/models/{model}:generateContent
```

### Provider Detection

The adapter is selected automatically from `base_url`:

| `base_url` contains | Adapter used |
|---------------------|--------------|
| `api.anthropic.com` | `AnthropicAdapter` |
| `generativelanguage.googleapis.com` | `GeminiAdapter` |
| anything else | `OpenAIAdapter` (default) |

Users can override with `provider` config key:

```bash
nowreck config set provider anthropic
nowreck config set provider gemini
nowreck config set provider openai  # explicit default
```

### Adapter Interface

```python
class ProviderAdapter(ABC):
    """Translates between provider native format and OpenAI format.

    The adapter receives OpenAI-format messages and returns a
    provider-specific request body.  It also provides auth headers
    and response parsing.
    """

    @abstractmethod
    def build_request(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
    ) -> tuple[str, dict[str, str], bytes]:
        """Build the HTTP request for this provider.

        Returns:
            (url, headers, body) — ready for urllib.request.urlopen()
        """

    @abstractmethod
    def parse_response(self, raw: bytes) -> str:
        """Extract the assistant's content from the provider response.

        Returns the plain text content, same as OpenAI's
        choices[0].message.content.
        """
```

### AnthropicAdapter Details

**Request format:**
```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 4096,
  "messages": [
    {"role": "user", "content": "..."}
  ],
  "system": "..."
}
```

**Auth:** `x-api-key: sk-ant-...` header (not `Authorization: Bearer`)

**Response format:**
```json
{
  "content": [{"type": "text", "text": "..."}],
  "stop_reason": "end_turn"
}
```

**Differences from OpenAI:**
- System message is a top-level `system` field, not a message
- Messages array cannot contain `system` role
- Auth uses `x-api-key` header, not `Authorization: Bearer`
- Response has `content` array with typed blocks, not `choices[0].message.content`
- Endpoint is `/v1/messages`, not `/v1/chat/completions`

### GeminiAdapter Details

**Request format:**
```json
{
  "contents": [
    {
      "role": "user",
      "parts": [{"text": "..."}]
    }
  ],
  "generationConfig": {
    "temperature": 0.0
  }
}
```

**Auth:** `x-goog-api-key: AIza...` header

**Response format:**
```json
{
  "candidates": [{
    "content": {
      "parts": [{"text": "..."}],
      "role": "model"
    }
  }]
}
```

**Differences from OpenAI:**
- Messages are `contents` with `parts` arrays
- Model name is in the URL, not the request body
- System instruction goes in `systemInstruction`, not as a message
- Response has `candidates[0].content.parts[0].text`
- Endpoint is `/v1beta/models/{model}:generateContent`

## Provider Compatibility Matrix

| Provider | Format | Adapter needed | Auth header | Endpoint |
|----------|--------|---------------|-------------|----------|
| OpenAI | OpenAI | No (passthrough) | `Authorization: Bearer` | `/v1/chat/completions` |
| Groq | OpenAI | No (passthrough) | `Authorization: Bearer` | `/v1/chat/completions` |
| OpenRouter | OpenAI | No (passthrough) | `Authorization: Bearer` | `/v1/chat/completions` |
| Grok (xAI) | OpenAI | No (passthrough) | `Authorization: Bearer` | `/v1/chat/completions` |
| Kimi (Moonshot) | OpenAI | No (passthrough) | `Authorization: Bearer` | `/v1/chat/completions` |
| Ollama | OpenAI | No (passthrough) | `Authorization: Bearer` | `/v1/chat/completions` |
| LM Studio | OpenAI | No (passthrough) | `Authorization: Bearer` | `/v1/chat/completions` |
| **Anthropic** | Anthropic | **Yes** | `x-api-key` | `/v1/messages` |
| **Gemini** | Gemini | **Yes** | `x-goog-api-key` | `/v1beta/models/{model}:generateContent` |

## CLI / UX

No changes. The same commands work with any provider:

```bash
# OpenAI-compatible (unchanged):
nowreck config set base_url https://api.openai.com/v1
nowreck config set api_key sk-...
nowreck config set model gpt-4o

# Anthropic (new):
nowreck config set base_url https://api.anthropic.com
nowreck config set api_key sk-ant-...
nowreck config set model claude-sonnet-4-20250514

# Gemini (new):
nowreck config set base_url https://generativelanguage.googleapis.com
nowreck config set api_key AIza...
nowreck config set model gemini-2.0-flash

# Then just run:
nowreck fix "Add email validation to auth.py"
```

The `base_url` determines which adapter is used. No new flags.

## Reporting Changes

None. The adapter is transparent — the model returns the same JSON format
regardless of which provider it uses. The `ClaimParser`, `ClaimVerifier`,
and `TerminalReporter` are unchanged.

## Security

| Area | What changes |
|------|-------------|
| API key storage | Same (config file or env var) |
| API key display | Same masking via `_mask_key()` |
| Anthropic auth | `x-api-key` header (not `Authorization: Bearer`) |
| Gemini auth | `x-goog-api-key` header (not `Authorization: Bearer`) |
| Error messages | Adapter-specific error bodies may contain different text |

No new security surface — the adapter only transforms request/response
bodies, it does not store or display keys differently.

## Test Strategy

### Unit tests

- `ProviderAdapter` base class contract
- `AnthropicAdapter.build_request()` — correct URL, headers, body
- `AnthropicAdapter.parse_response()` — extracts content correctly
- `GeminiAdapter.build_request()` — correct URL, headers, body
- `GeminiAdapter.parse_response()` — extracts content correctly
- Auto-detection from `base_url` — correct adapter selected
- Provider override from config — explicit `provider` key works

### Integration tests

- OpenAI-compatible providers still work (regression)
- Anthropic adapter with mock HTTP — full round-trip
- Gemini adapter with mock HTTP — full round-trip
- Provider override with mock HTTP — adapter selected correctly

### Regression tests

- All existing 544+ pytest tests pass unchanged
- Pre/Post mode unchanged (no model needed)
- Prompt mode with OpenAI-compatible provider unchanged
- JSON output unchanged

### Negative tests

- Unknown `base_url` falls back to `OpenAIAdapter`
- Invalid Anthropic response → `ModelError`
- Invalid Gemini response → `ModelError`
- Missing API key → `ModelError` with helpful message
- Network timeout → `ModelError` with timeout message

## Implementation Phases

### Phase 1: Adapter Base Class

**Objective:** Create `ProviderAdapter` abstraction.

**Files affected:**
- `nowreck/model/adapters.py` (new)
- `tests/test_adapters.py` (new)

**Implementation:**
- `ProviderAdapter` ABC with `build_request()` and `parse_response()`
- `OpenAIAdapter` — passthrough (no transformation)
- Factory function `_detect_adapter(base_url, provider_override)`

**Tests:**
- `OpenAIAdapter` passes through messages unchanged
- Auto-detection selects correct adapter for each URL pattern
- Unknown URL falls back to `OpenAIAdapter`

**Completion criteria:** `OpenAIAdapter` works identically to current behavior.

### Phase 2: Anthropic Adapter

**Objective:** Add `AnthropicAdapter` for Claude models.

**Files affected:**
- `nowreck/model/adapters.py` (extend)
- `tests/test_adapters.py` (extend)

**Implementation:**
- `AnthropicAdapter.build_request()` — translate messages to Anthropic format
- `AnthropicAdapter.parse_response()` — extract content from Anthropic response
- Handle system message extraction (top-level `system` field)
- Handle `x-api-key` auth header

**Tests:**
- System message extracted from messages array and placed in `system` field
- User/assistant messages converted to Anthropic format
- Response content extracted from `content[0].text`
- Auth header uses `x-api-key`, not `Authorization: Bearer`
- Endpoint is `/v1/messages`

**Completion criteria:** Anthropic adapter works with mock HTTP round-trip.

### Phase 3: Gemini Adapter

**Objective:** Add `GeminiAdapter` for Google Gemini models.

**Files affected:**
- `nowreck/model/adapters.py` (extend)
- `tests/test_adapters.py` (extend)

**Implementation:**
- `GeminiAdapter.build_request()` — translate messages to Gemini format
- `GeminiAdapter.parse_response()` — extract content from Gemini response
- Handle system instruction (top-level `systemInstruction` field)
- Handle model name in URL path
- Handle `x-goog-api-key` auth header

**Tests:**
- System instruction extracted and placed in `systemInstruction`
- Messages converted to `contents` with `parts` arrays
- Response content extracted from `candidates[0].content.parts[0].text`
- Auth header uses `x-goog-api-key`
- Endpoint includes model name in path

**Completion criteria:** Gemini adapter works with mock HTTP round-trip.

### Phase 4: Integration + Auto-Detection

**Objective:** Wire adapters into `ModelProvider`.

**Files affected:**
- `nowreck/model/provider.py` (modify)
- `tests/test_model.py` (extend)

**Implementation:**
- Import adapters in `ModelProvider._default_http_call()`
- Auto-detect adapter from `config.base_url`
- Use adapter's `build_request()` and `parse_response()` instead of
  hardcoded OpenAI format
- Support explicit `provider` config override

**Tests:**
- `ModelProvider` with `base_url=api.anthropic.com` uses `AnthropicAdapter`
- `ModelProvider` with `base_url=generativelanguage.googleapis.com` uses `GeminiAdapter`
- `ModelProvider` with `base_url=api.openai.com` uses `OpenAIAdapter`
- Explicit `provider` config overrides auto-detection
- All existing model tests pass unchanged

**Completion criteria:** `ModelProvider` transparently uses the correct adapter.

### Phase 5: Documentation + Release

**Objective:** Update docs, write release notes, bump version.

**Files affected:**
- `docs/release11.md` (new)
- `docs/nowreck-v11-scope.md` (this file — mark as done)
- `README.md` (update provider table)
- `use.md` (update provider table)
- `pyproject.toml` (version bump)
- `nowreck/__init__.py` (version bump)
- `nowreck/main.py` (banner version)

**Implementation:**
- Write release notes
- Update README provider table with Anthropic and Gemini
- Update use.md provider table
- Bump version to 0.11.0
- Run full test suite
- Run ruff + basedpyright

**Completion criteria:** Full suite green, release ready.

## Acceptance Criteria

### Test 1: OpenAI-compatible providers unchanged
- **Setup:** Run with OpenAI, Groq, or OpenRouter config
- **Expected:** Identical behavior to v0.10.0
- **Proof:** All existing model tests pass

### Test 2: Anthropic adapter works
- **Setup:** Configure `base_url=https://api.anthropic.com`, `api_key=sk-ant-...`
- **Expected:** `nowreck fix "Add a greet function"` calls Claude and returns claims
- **Proof:** Mock HTTP test with Anthropic-format request/response

### Test 3: Gemini adapter works
- **Setup:** Configure `base_url=https://generativelanguage.googleapis.com`, `api_key=AIza...`
- **Expected:** `nowreck fix "Add a greet function"` calls Gemini and returns claims
- **Proof:** Mock HTTP test with Gemini-format request/response

### Test 4: Auto-detection correct
- **Setup:** Set `base_url` to various provider URLs
- **Expected:** Correct adapter selected for each
- **Proof:** Unit test with each URL pattern

### Test 5: Provider override works
- **Setup:** Set `provider=anthropic` in config
- **Expected:** AnthropicAdapter used regardless of `base_url`
- **Proof:** Unit test with override

### Test 6: All existing tests pass
- **Setup:** Run full test suite
- **Expected:** 544+ tests pass, 0 failures
- **Proof:** pytest output

### Test 7: ruff + basedpyright clean
- **Setup:** Run linting and type checking
- **Expected:** 0 issues
- **Proof:** Tool output

## Definition of Done

1. `OpenAIAdapter` works identically to current behavior (passthrough).
2. `AnthropicAdapter` translates messages and parses responses correctly.
3. `GeminiAdapter` translates messages and parses responses correctly.
4. Auto-detection from `base_url` selects the correct adapter.
5. Provider override from config works.
6. All existing tests pass (regression gate).
7. New adapter tests pass.
8. ruff: 0 issues, basedpyright: 0 errors.
9. Documentation updated (README, use.md, release notes).
10. Version bumped to 0.11.0.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Anthropic API changes format | Medium | Adapter isolates format; only adapter needs update |
| Gemini API changes format | Medium | Adapter isolates format; only adapter needs update |
| Rate limits on free tiers | Low | Not our concern — user's API key, user's limits |
| Auth header differences | Low | Adapter provides correct headers per provider |
| Breaking OpenAI-compatible providers | High | `OpenAIAdapter` is passthrough — zero transformation |
| Existing tests break | High | Run full suite at every phase; regression gate |

## Explicitly not a roadmap

This covers exactly one thing — adding Anthropic and Gemini provider
support via adapters, same phase-by-phase discipline, human-checked at
every step. When it's done and proven, the next increment gets its own
equally narrow scoping conversation.
