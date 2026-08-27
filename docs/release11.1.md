# NoWreck v0.11.1 — Bugfix Release

**Date:** August 2026
**Type:** Bugfix release (no new features)

---

## What's Fixed

### Critical (v0.11.0 post-ship)

- **Prompt Mode restores repo after verification** — `_restore_from_patch()` was a no-op stub; now calls `SnapshotManager.restore()` in a `finally` block
- **Interactive picker uses independent verification** — was circular (claims verified against themselves); now uses `verify_prompt()` v10 pipeline
- **Stash restore failure surfaced** — `restore()` return value is checked; warns with recovery instructions on failure

### Adapter Correctness

- **Provider override sets auth headers** — `_auth_header()` now accepts `provider` parameter; `x-api-key` for Anthropic, `x-goog-api-key` for Gemini even with custom `base_url`
- **Anthropic max_tokens increased to 16384** — prevents truncation loop on long responses; `stop_reason=max_tokens` now raises a clear error
- **Unknown provider raises ValueError** — typos like `provider=cluad` fail fast instead of silently falling back to OpenAI
- **Anthropic EU endpoint detected** — `api.anthropic.eu` now selects `AnthropicAdapter`
- **Double-path URL resolved** — `base_url` with trailing `/v1` no longer produces `/v1/v1/messages`
- **Gemini model names URL-encoded** — special characters in model names are properly escaped
- **System-only message guard** — adapters raise `_AdapterError` instead of sending empty `messages`/`contents` to the API

### Security

- **API key masked in `config show`** — uses `_mask_key()` for display
- **Config file permissions set to 0o600** — owner-only read/write via `os.fchmod()`
- **Temperature validated** — out-of-range values caught before API call

### Patch Pipeline

- **Multi-hunk diffs handled correctly** — rewritten patch applier with anchor+context matching replaces the broken `_split_patch_sections()`
- **Deprecation warnings removed** — `claims_to_changes()` and `_mask_messages()` cleaned up

### Verification Architecture

- **Line-shift phantom changes eliminated** — `Symbol.line_number` excluded from `__eq__`/`__hash__`; pure line shifts no longer produce fake ADD/REMOVE pairs
- **Removed calls now CONTRADICTED** — `CALL_REMOVED` change type added; vanished call sites produce `CONTRADICTED` instead of `UNVERIFIABLE`

### Code Quality

- **Scanner file discovery deduplicated** — 5 language-specific `_discover_*_files()` methods replaced with one shared `_discover_files(*suffixes)`
- **Assert statements removed** — `assert error is not None` replaced with `elif error is not None` (safe under `python -O`)
- **Exception handling narrowed** — `except Exception` in provider response parsing limited to `(json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError)`
- **Config helpers type-safe** — `_get_str_or`, `_get_float_or`, `_get_int_or` log debug on unexpected types instead of silently coercing
- **Scan failure rate reported** — aggregate parse health logged after scan completes

### Documentation

- **Auth responsibility clarified** — cross-referencing notes in `adapters.py` and `provider.py` document the single source of truth for auth headers
- **Test docstrings updated** — adapter test file correctly references "Phases 1-3"

---

## Upgrade Notes

- No breaking changes from v0.11.0
- All v0.11.0 config keys and CLI flags remain compatible
- `provider` config key now correctly affects auth headers (previously ignored when `base_url` didn't match)

---

*NoWreck v0.11.1 — August 2026*
