# NoWreck v0.12.0 — Provider Consolidation + Scan Caching

**Release date:** August 2026
**Previous release:** v0.11.1 (Bugfix Release)
**Focus:** Two infrastructure improvements — consolidate provider resolution
into a single function and add file-level scan caching for large repositories.

---

## What's new in v0.12.0

### Provider consolidation ✅

Provider detection was split between two independent functions —
`_auth_header()` in `provider.py` and `detect_adapter()` in `adapters.py` —
both doing URL-matching independently. A new provider required updating both,
and they had to agree.

Now a single `resolve_provider(base_url, override)` function returns both
the adapter and the auth header type in one call:

```
ModelProvider._default_http_call()
    │
    └── resolve_provider(base_url, provider) → ProviderInfo
            Single URL matching in adapters.py:
            "api.anthropic.com" → (AnthropicAdapter, x-api-key)
            "generativelanguage.googleapis.com" → (GeminiAdapter, x-goog-api-key)
            else → (OpenAIAdapter, Authorization: Bearer)
```

One call. One URL match. Adapter and auth header always agree.

**New:** `ProviderInfo` dataclass, `resolve_provider()` function.
**Removed:** `_auth_header()` standalone function (replaced by `_auth_header_from_type()`).
**Deprecated:** `detect_adapter()` (still works, delegates to `resolve_provider()`).

### Scan caching ✅

Every `nowreck fix` run re-scans every file in the repository from scratch.
For a repository with 500+ source files, this means 500+ parse operations
per run.

Now `RepositoryScanner.scan()` caches per-file results in `.nowreck/cache/`.
On subsequent runs, only files that actually changed are re-parsed:

```
RepositoryScanner.scan()
    → ScanCache.get(file_path, mtime, size, content_hash)
    → If hit: use cached result (no parse needed)
    → If miss: parse, then cache result
    → ScanCache.save() (atomic write to .nowreck/cache/scan_cache.json)
```

**Cache key:** `(path, mtime, size, content_hash)` — MD5 of file contents
catches same-size rewrites within the same filesystem timestamp quantum.

**Cache format:**
- Python files: source text stored; `ast.Module` reconstructed via `ast.parse()` on load
- JS/TS/Rust/Go files: symbol lists stored directly

**Invalidation:** mtime, size, content hash, or version mismatch → re-parse.
Version bump forces full re-parse. Cache is gitignored by `.nowreck/`.

**New:** `ScanCache`, `CacheEntry`, `file_content_hash()` in `scanner/scan_cache.py`.
**Modified:** `RepositoryScanner.scan()` integrates cache transparently.
**New:** `Symbol.to_dict()` / `Symbol.from_dict()` for JSON round-tripping.

---

## What's unchanged

| What | Why |
|------|-----|
| All 13 claim types | No new types needed |
| `ClaimVerifier.verify()` | Already correct |
| `ChangeDetector.detect()` | Already correct |
| `PromptModeVerifier` | Adapter is transparent |
| `SnapshotManager` | Already correct |
| `PatchApplier` | Already correct |
| CLI commands and flags | No new flags needed |
| JSON output schema | Same fields |
| Pre/Post mode | Already correct |
| Prompt mode | Already correct — adapter is transparent |

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Full pytest suite | 719 | ✅ all pass |
| New resolve_provider tests | 21 | ✅ all pass |
| New scan cache tests | 35 | ✅ all pass |
| ruff check + format | 0 issues | ✅ clean |
| basedpyright (strict) | 0 errors | ✅ clean |

## Files modified

| File | Change |
|------|--------|
| `nowreck/model/adapters.py` | Added `ProviderInfo`, `resolve_provider()`; `detect_adapter()` now delegates |
| `nowreck/model/provider.py` | Replaced `_auth_header()` with `_auth_header_from_type()`; uses `resolve_provider()` |
| `nowreck/scanner/scan_cache.py` | **New** — `ScanCache`, `CacheEntry`, `file_content_hash()` |
| `nowreck/scanner/repository_scanner.py` | Integrated cache into `scan()` for all 5 languages |
| `nowreck/scanner/symbol_index.py` | Added `Symbol.to_dict()` / `Symbol.from_dict()` |
| `tests/test_adapters.py` | Rewrote `_auth_header()` tests → `resolve_provider()` |
| `tests/test_scan_cache.py` | **New** — 35 cache tests |
| `docs/nowreck-v12-scope.md` | Marked done |
| `pyproject.toml`, `nowreck/__init__.py` | Version bump to 0.12.0 |

---

## Definition of Done

| Criterion | Status |
|-----------|--------|
| `resolve_provider()` is single source of truth | ✅ |
| `_auth_header()` removed, replaced by `_auth_header_from_type()` | ✅ |
| Unknown overrides fail loudly (ValueError) | ✅ |
| `ScanCache` caches per-file results | ✅ |
| Cache transparent — identical output warm or cold | ✅ |
| Cache invalidation works (mtime, size, content hash, version) | ✅ |
| Cache persists across process restarts | ✅ |
| Cache is gitignored | ✅ |
| All existing tests pass (719/719) | ✅ |
| New tests pass (21 + 35) | ✅ |
| ruff: 0 issues, basedpyright: 0 errors | ✅ |
| Documentation updated | ✅ |
| Version bumped to 0.12.0 | ✅ |

---

## Upgrade notes

No breaking changes. Every existing command and configuration works
identically.

The scan cache is created automatically on first run in `.nowreck/cache/`.
To clear it:

```bash
rm -rf .nowreck/cache/
```

---

*NoWreck v0.12.0 — August 2026*
