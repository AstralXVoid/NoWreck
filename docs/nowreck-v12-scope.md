# NoWreck — v12 Scope (Provider Consolidation + Scan Caching)

**Status:** Done. Released as v0.12.0.

## Principle

Same rule as every prior increment: one small thing at a time, proven before
expanding. v11.1 (bugfix release) is done and its Definition of Done is
fulfilled. v12 is **two infrastructure improvements** — provider resolution
consolidation and file-level scan caching — that reduce fragility and improve
performance without changing the verification model.

## The Problems

### Problem 1: Provider resolution is split and fragile

Currently, provider inference happens in two independent places:

1. **`_auth_header()`** in `nowreck/model/provider.py` — infers the provider
   from the URL to select the correct auth header (`Authorization: Bearer`,
   `x-api-key`, or `x-goog-api-key`).

2. **`detect_adapter()`** in `nowreck/model/adapters.py` — infers the provider
   from the URL to select the correct request builder (`OpenAIAdapter`,
   `AnthropicAdapter`, or `GeminiAdapter`).

Both do URL-matching independently. A new provider requires updating both
functions — and they must agree. If they drift, the adapter sends a request in
one format but the auth header uses another format's convention.

The code itself documents this:
```python
# provider.py, _auth_header() docstring:
# ... Full ``resolve_provider()`` consolidation is deferred to v0.12.
```

### Problem 2: No caching for large repositories

Every `nowreck fix` run re-scans every file in the repository from scratch:

```
RepositoryScanner.scan()
    → _discover_files() for each language
    → _parse_file() / _parse_js_file() / _parse_ts_file() / etc.
        → ast.parse() or tree-sitter parse for every single file
```

For a repository with 500+ source files, this means 500+ parse operations per
run. The tree-sitter grammar objects are cached in module-level globals within a
single process, but the parsed results are not persisted between runs.

This makes repeated verification runs (common in CI and iterative development)
unnecessarily slow.

## Architectural Principles

1. **Provider resolution must be a single function.** One call returns both the
   adapter and the auth header type. No duplicate URL-matching.

2. **Caching is transparent.** The cache must be invisible to every other
   component. `ScanResult` and `SymbolIndex` produced from cache must be
   identical to those produced from a fresh scan.

3. **Cache invalidation is simple.** File mtime + size is sufficient. No
   content hashing, no tree-sitter fingerprinting. If mtime or size changed,
   re-parse.

4. **Cache never changes verification behavior.** Identical inputs (same repo
   state) must produce identical `DetectedChange` output whether the cache is
   warm or cold.

5. **Backwards compatibility preserved.** All existing config, CLI flags, and
   tests must pass unchanged.

## What Changes in v12

### Added

| What | Why |
|------|-----|
| `resolve_provider(base_url, override)` in `adapters.py` | Single source of truth for provider detection; returns adapter + auth header type |
| `ScanCache` class in `scanner/scan_cache.py` | File-level scan result cache keyed on path + mtime + size |
| `.nowreck/cache/` directory | Persistent cache storage (auto-created, gitignored) |
| Cache invalidation on format version bump | Ensures cache upgrades cleanly across versions |

### Modified

| What | Why |
|------|-----|
| `ModelProvider._default_http_call()` | Uses `resolve_provider()` instead of separate `_auth_header()` + `detect_adapter()` |
| `RepositoryScanner.scan()` | Checks cache before parsing; writes cache after parsing |
| `ScanResult` | No field changes — cache reconstructs `modules` from source text on load |
| `pyproject.toml` | Version bump to 0.12.0 |

### Removed

| What | Why |
|------|-----|
| `_auth_header()` standalone function | Replaced by `resolve_provider()` |
| Duplicate URL-matching in `provider.py` | Consolidated into `adapters.py` |

### Unchanged

| What | Why |
|------|-----|
| `ClaimVerifier.verify()` | Already correct |
| `ChangeDetector.detect()` | Already correct |
| `PromptModeVerifier` | Adapter is transparent |
| `SnapshotManager` | Already correct |
| `PatchApplier` | Already correct |
| All 13 claim types | No new types needed |
| `SymbolIndex` | Already correct |
| `TerminalReporter` | Already correct |
| CLI commands and flags | No new flags needed |
| JSON output schema | Same fields |
| Pre/Post mode | Already correct |
| Prompt mode | Already correct — adapter is transparent |
| All existing tests | Must pass unchanged |

---

## Part 1: Provider Consolidation

### Current Architecture (fragile)

```
ModelProvider._default_http_call()
    │
    ├── detect_adapter(base_url, provider) → adapter
    │       URL matching in adapters.py:
    │       "api.anthropic.com" → AnthropicAdapter
    │       "generativelanguage.googleapis.com" → GeminiAdapter
    │       else → OpenAIAdapter
    │
    └── _auth_header(api_key, base_url, provider) → headers
            URL matching in provider.py:
            "api.anthropic.com" → x-api-key
            "generativelanguage.googleapis.com" → x-goog-api-key
            else → Authorization: Bearer
```

Two independent URL-matching codepaths that must agree.

### Proposed Architecture (consolidated)

```
ModelProvider._default_http_call()
    │
    └── resolve_provider(base_url, provider) → (adapter, auth_header_fn)
            Single URL matching in adapters.py:
            "api.anthropic.com" → (AnthropicAdapter, x-api-key)
            "generativelanguage.googleapis.com" → (GeminiAdapter, x-goog-api-key)
            else → (OpenAIAdapter, Authorization: Bearer)
```

One call. One URL match. Adapter and auth header always agree.

### Implementation Details

**New function in `adapters.py`:**

```python
@dataclass(frozen=True)
class ProviderInfo:
    """Resolved provider: adapter + auth header type."""
    adapter: ProviderAdapter
    auth_type: str  # "bearer", "x-api-key", "x-goog-api-key"

def resolve_provider(
    base_url: str,
    provider_override: str | None = None,
) -> ProviderInfo:
    """Single source of truth for provider detection.

    Returns both the adapter and the auth header type, ensuring
    they always agree.
    """
    # ... consolidated URL matching ...
```

**Modified `_default_http_call()` in `provider.py`:**

```python
@staticmethod
def _default_http_call(
    messages: list[dict[str, str]],
    config: ModelConfig,
) -> str:
    api_key = config.resolve_api_key()
    if not api_key:
        raise ModelError(...)

    provider_info = resolve_provider(config.base_url, config.provider)
    url_suffix, headers, body = provider_info.adapter.build_request(
        messages=messages,
        model=config.model,
        temperature=config.temperature,
    )

    req = urllib_request.Request(
        url=_join_url(config.base_url, url_suffix),
        data=body,
        headers={
            **headers,
            **_auth_header_from_type(api_key, provider_info.auth_type),
        },
        method="POST",
    )
    # ... rest unchanged ...
```

**Behavior note:** `_auth_header()` silently falls through to Bearer for
unrecognized provider overrides, while `detect_adapter()` raises `ValueError`.
The consolidated `resolve_provider()` should adopt `detect_adapter()`'s strict
behavior — unknown overrides must fail loudly, not silently send
OpenAI-format requests to the wrong endpoint.

**`detect_adapter()` call sites to update:**

| File | Line | Usage |
|------|------|-------|
| `nowreck/model/provider.py` | 21 | `from nowreck.model.adapters import detect_adapter` |
| `nowreck/model/provider.py` | 475 | `adapter = detect_adapter(config.base_url, config.provider)` |
| `tests/test_adapters.py` | 22 | `from nowreck.model.adapters import detect_adapter` |
| `tests/test_adapters.py` | 225-276 | 12+ test calls (`detect_adapter(url)` patterns) |

**Removed:**
- `_auth_header()` standalone function (replaced by `_auth_header_from_type()`
  which is a simple type→header mapping, no URL inference)
- `detect_adapter()` standalone function (absorbed into `resolve_provider()`)
- Duplicate URL matching in `provider.py`
- `adapters.py` docstring references to `_auth_header()` (lines 31, 199, 315)
  updated to reference `resolve_provider()`

### Files Affected

| File | Change |
|------|--------|
| `nowreck/model/adapters.py` | Add `ProviderInfo` dataclass, `resolve_provider()` function |
| `nowreck/model/provider.py` | Replace `_auth_header()` + `detect_adapter()` with `resolve_provider()` |
| `tests/test_adapters.py` | Rewrite `_auth_header()` tests (15+ call sites at lines 27, 293-321, 906-926, 938) to use `resolve_provider()` | 
| `tests/test_model.py` | No changes — existing `TestPhase4AdapterSelection` and `TestPhase1AdapterFixes` serve as regression gate |

### Tests

| Test | What it proves |
|------|----------------|
| `test_resolve_provider_openai` | OpenAI URL → OpenAIAdapter + bearer |
| `test_resolve_provider_anthropic` | Anthropic URL → AnthropicAdapter + x-api-key |
| `test_resolve_provider_anthropic_eu` | Anthropic EU URL → AnthropicAdapter + x-api-key |
| `test_resolve_provider_gemini` | Gemini URL → GeminiAdapter + x-goog-api-key |
| `test_resolve_provider_override` | Explicit override selects correct provider |
| `test_resolve_provider_unknown_override` | Unknown override raises ValueError |
| `test_resolve_provider_unknown_url` | Unknown URL defaults to OpenAIAdapter + bearer |
| `test_all_existing_adapter_tests_pass` | Regression gate — no behavior change |

---

## Part 2: Scan Caching

### How Scanning Works Today

```
RepositoryScanner.scan()
    → _discover_files(".py")       # rglob
    → _parse_file(f) for each f    # ast.parse
    → _discover_files(".js")       # rglob
    → _parse_js_file(f) for each f # tree-sitter
    → _discover_files(".ts", ".tsx")
    → _parse_ts_file(f) for each f
    → _discover_files(".rs")
    → _parse_rust_file(f) for each f
    → _discover_files(".go")
    → _parse_go_file(f) for each f
    → ScanResult(modules, js_files, ts_files, rust_files, go_files, failed)
```

Every file is discovered and parsed fresh. For 500 files across 5 languages,
this means 5 rglob passes + 500 parse operations.

### Proposed: File-Level Scan Cache

**Key insight:** The scanner already produces a deterministic mapping from
`file_path → parsed output`. If the file hasn't changed since the last scan,
the parsed output is identical. We can cache per-file results.

**Cache key:** `(file_path, mtime, file_size)` — cheap to compute, no content
hashing needed.

**Cache format:** A JSON file stored in `.nowreck/cache/`:

```json
{
  "version": 1,
  "repo_root": "/absolute/path/to/repo",
  "entries": {
    "src/auth.py": {
      "mtime": 1693000000.0,
      "size": 1234,
      "language": "python",
      "source": "def validate_email(email):\n    ..."
    },
    "src/utils.js": {
      "mtime": 1693000001.0,
      "size": 567,
      "language": "javascript",
      "symbols": [
        {"name": "helper", "type": "function", "file": "src/utils.js", "line": 1}
      ]
    }
  }
}
```

Python entries store `source` (the file text) so `ast.Module` can be
reconstructed on load. JS/TS/Rust/Go entries store `symbols` directly.

**Cache Schema (v1):**

Language enum values: `"python"`, `"javascript"`, `"typescript"`,
`"rust"`, `"go"`.

Python source encoding: JSON string with escaped newlines (standard
JSON encoding). No base64 — debuggability matters more than minor
size savings from escaping.

Symbol serialization format (JS/TS/Rust/Go entries):
```json
{
  "name": "function_name",
  "type": "function|class|method|interface|enum|type_alias",
  "file": "relative/path.ext",
  "line": 42,
  "parent_class": null
}
```

`Symbol` is `@dataclass(frozen=True, order=True)`. Phase 2 must add
`to_dict()` / `from_dict()` class methods for JSON round-tripping.
The `file_path` field (a `Path`) is serialized as a string;
`symbol_type` (a `SymbolType` IntEnum) is serialized as its string
name.

Version-bump policy: bump `version` when the cache schema changes
(field added/removed/renamed, encoding changes, or language enum
values change). A version mismatch on load triggers a full re-parse
and overwrites the old cache.

**Cache invalidation rules:**
1. File mtime changed → re-parse
2. File size changed → re-parse
3. Cache format version bumped → full re-parse
4. File deleted from disk → remove from cache
5. File new (not in cache) → parse and cache

**What gets cached:**

1. **Discovered file paths** per language — eliminates repeated `rglob` calls
   (the largest per-run cost for large repos)
2. **Python source text** — stored so `ast.Module` can be re-parsed on cache
   load (needed because `ChangeDetector._extract_calls()` walks `ast.Module`
   objects from `ScanResult.modules` for Python call detection)
3. **Symbol lists** for JS/TS/Rust/Go — avoids re-parsing for symbol
   detection

**What doesn't get cached:** `SymbolIndex` — always built fresh from
`ScanResult`. `ScanResult.repo_root` — stored separately in the cache
metadata (needed by JS/TS/Rust/Go call detection). `failed_files` —
reconstructed on cache load: files on disk but not in cache are
re-parsed (may succeed or fail); files in cache but not on disk are
deleted (not re-parsed).

**Why source text, not just symbols?** `ScanResult.modules` stores
`ast.Module` objects (not just symbols). The change detector walks these
ASTs directly for Python call detection (`_extract_calls()` calls
`ast.walk(module)` on each module). Caching symbols alone would break
this — the cache must provide enough data to reconstruct `ast.Module`
objects. Storing source text (a few KB per file) and re-parsing on load
is the simplest correct approach.

**JS/TS/Rust/Go call detection:** The change detector re-reads these
files from disk for call detection (`scan_js_calls()`, etc. call
`path.read_bytes()`). This happens regardless of caching. The scan cache
still helps by eliminating `rglob` and symbol parsing for these files.

### Implementation Details

**New file: `nowreck/scanner/scan_cache.py`**

```python
class ScanCache:
    """File-level scan result cache.

    Caches per-file parsed output keyed on (path, mtime, size).
    Stored in .nowreck/cache/ under the repository root.
    """

    CACHE_DIR = ".nowreck/cache"
    CACHE_VERSION = 1

    def __init__(self, repo_root: Path) -> None:
        self._cache_dir = repo_root / self.CACHE_DIR
        self._cache_file = self._cache_dir / "scan_cache.json"
        self._entries: dict[str, CacheEntry] = {}
        self._load()

    def get(self, file_path: Path, mtime: float, size: int) -> CacheEntry | None:
        """Return cached result if valid, None if missing or stale."""
        ...

    def put(self, file_path: Path, mtime: float, size: int, entry: CacheEntry) -> None:
        """Store a parsed result in the cache."""
        ...

    def save(self) -> None:
        """Persist cache to disk."""
        ...

    def invalidate(self, file_path: Path) -> None:
        """Remove a single entry."""
        ...
```

**Modified `RepositoryScanner.scan()`:**

```python
def scan(self) -> ScanResult:
    cache = ScanCache(self._repo_path) if self._use_cache else None

    # For each file:
    #   1. Check cache (mtime + size)
    #   2. If hit → use cached symbols
    #   3. If miss → parse, then cache result
    # After all files:
    #   cache.save()

    # ... rest of scan logic unchanged ...
```

### Serialization of Parsed Results

**Python files:** The `ast.Module` is not natively serializable. Two options:

1. **Cache source text, re-parse on load.** Store the file's source text in
   cache; on load, `ast.parse(cached_source)`. This is safe because Python's
   `ast.parse` is deterministic for valid source.

2. **Cache Symbol list only.** Store the `Symbol` objects produced by
   `SymbolIndexBuilder._process_module()`. On load, reconstruct the symbol
   list without re-parsing.

**Decision: Cache source text for Python, symbols for JS/TS/Rust/Go.**

- **Python:** Cache the source text (`str`). On cache load, `ast.parse()`
  reconstructs the `ast.Module` needed by both `SymbolIndexBuilder` and
  `ChangeDetector._extract_calls()`. `ast.parse()` is fast for single
  files (sub-millisecond) — the savings come from skipping `rglob` and
  disk reads.
- **JS/TS/Rust/Go:** Cache the `Symbol` list. The change detector
  re-reads these from disk for call detection regardless — but the
  cache still eliminates `rglob` and symbol parsing.

**Why not cache `ast.Module` directly?** It's not JSON-serializable.
Source text is a few KB per file and `ast.parse()` is fast — this is
the simplest correct approach.

### Files Affected

| File | Change |
|------|--------|
| `nowreck/scanner/scan_cache.py` | **New** — `ScanCache`, `CacheEntry` |
| `nowreck/scanner/repository_scanner.py` | Integrate cache into `scan()` |
| `tests/test_scan_cache.py` | **New** — cache tests |

**Note:** `.gitignore` already has `.nowreck/` which covers `.nowreck/cache/`
— no `.gitignore` change needed.

### Tests

| Test | What it proves |
|------|----------------|
| `test_cache_hit_returns_same_symbols` | Cached scan produces identical symbols |
| `test_cache_hit_returns_same_ast` | Cached Python scan produces identical `ast.Module` (via `ast.dump()`) |
| `test_cache_hit_returns_same_file_set` | Cached file discovery matches fresh `rglob` |
| `test_cache_miss_parses_and_caches` | New file is parsed and cached |
| `test_cache_invalidated_by_mtime` | Changed file triggers re-parse |
| `test_cache_invalidated_by_size` | Changed file size triggers re-parse |
| `test_cache_invalidated_by_version` | Version bump triggers full re-parse |
| `test_cache_deleted_file_removed` | Deleted file removed from cache |
| `test_cache_deterministic_output` | Same repo → same `ScanResult` with or without cache |
| `test_cache_change_detector_compat` | `ChangeDetector.detect()` produces identical output with warm vs cold cache |
| `test_cache_cache_hit_skips_parse` | Mock `_discover_files` and `_parse_*`; assert 0 calls for cached files |
| `test_cache_persists_across_runs` | Cache survives process restart |
| `test_all_existing_scanner_tests_pass` | Regression gate |

---

## Implementation Phases

**Regression gate (all phases):** `pytest tests/ -q --tb=short` must pass
before any phase is considered done.

### Phase 1: Provider Consolidation

**Objective:** Single source of truth for provider detection.

**Files affected:**
- `nowreck/model/adapters.py` (add `resolve_provider()`)
- `nowreck/model/provider.py` (replace `_auth_header()` + `detect_adapter()`)
- `tests/test_adapters.py` (rewrite `_auth_header()` tests → `resolve_provider()`)
- `tests/test_model.py` (no changes — existing tests serve as regression gate)

**Completion criteria:**
- `resolve_provider()` returns both adapter and auth type
- `_auth_header()` standalone function removed
- All existing adapter and model tests pass
- New `resolve_provider()` tests pass

### Phase 2: Scan Cache

**Objective:** File-level scan result cache with persistence.

**Files affected:**
- `nowreck/scanner/scan_cache.py` (new)
- `nowreck/scanner/repository_scanner.py` (integrate cache)
- `tests/test_scan_cache.py` (new)

**Completion criteria:**
- `ScanCache` can store and retrieve per-file results
- `RepositoryScanner.scan()` uses cache when available
- Cached scan produces identical `ScanResult` to fresh scan
- Cache invalidation works for mtime, size, and version changes
- Cache saves to `.nowreck/cache/` and loads on next run
- Cache is gitignored (already covered by `.nowreck/` in `.gitignore`)
- All existing scanner tests pass

**Save Semantics:**

1. **Trigger:** Cache is saved at the end of a *successful* `scan()` call.
   Failed scans (exceptions during parsing) do not persist partial
   results — the next run re-parses from scratch.

2. **Atomic write:** Write to `.nowreck/cache/scan_cache.tmp`, then
   `rename()` to `.nowreck/cache/scan_cache.json`. A crash mid-write
   leaves either the old cache or the new cache intact — never a
   half-written file. This is a **correctness requirement**: a corrupt
   cache would cause silent verification failures.

3. **Concurrency:** Nowreck assumes a single scan process per repo at
   a time. No file locking. If parallel scans are needed in the
   future, add a `.nowreck/cache/.lock` file with `fcntl.flock()`.

### Phase 3: Integration + Release

**Objective:** Wire everything together, run full suite, release.

**Files affected:**
- `docs/release12.md` (new)
- `docs/nowreck-v12-scope.md` (mark as done)
- `README.md` (update roadmap)
- `pyproject.toml` (version bump)
- `nowreck/__init__.py` (version bump)
- `nowreck/main.py` (banner version)

**Completion criteria:**
- Full test suite green
- ruff: 0 issues, basedpyright: 0 errors
- Documentation updated
- Version bumped to 0.12.0

---

## Definition of Done

1. `resolve_provider()` is the single source of truth for provider detection —
   returns both adapter and auth header type.
2. `_auth_header()` standalone function removed — no duplicate URL matching.
3. Unknown provider overrides fail loudly (adopt `detect_adapter()`'s strict
   behavior, not `_auth_header()`'s silent fallthrough).
4. `ScanCache` caches per-file scan results keyed on `(path, mtime, size)`.
5. `RepositoryScanner.scan()` uses cache transparently — identical output
   whether cache is warm or cold.
6. Cache invalidation works correctly (mtime, size, version, deletion).
7. Cache persists across process restarts.
8. Cache is gitignored (already covered by `.nowreck/` in `.gitignore`).
9. All existing tests pass (regression gate).
10. `tests/test_adapters.py` `_auth_header()` tests rewritten to use
    `resolve_provider()`.
11. New scan cache tests pass.
12. ruff: 0 issues, basedpyright: 0 errors.
13. Documentation updated (README, release notes).
14. Version bumped to 0.12.0.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cache stale data causes false verification | High | mtime + size check is sufficient; version bump forces full re-parse |
| Provider consolidation breaks existing providers | High | OpenAIAdapter is passthrough; all existing tests must pass |
| Cache serialization loses precision | Medium | Cache source text for Python (re-parse to AST); symbols for JS/TS/Rust/Go are frozen dataclasses |
| Cache grows unbounded | Low | Cache directory is gitignored; users can `rm -rf .nowreck/cache/` |
| Cache format incompatible across versions | Medium | Version field in cache; version bump invalidates all entries |

## Explicitly not a roadmap

This covers exactly two things — provider consolidation and scan caching, same
phase-by-phase discipline, human-checked at every step. When it's done and
proven, the next increment gets its own equally narrow scoping conversation.

---

*NoWreck v0.12 scope — August 2026 — DONE*
