# NoWreck v0.16.0 — Verifiable Body Edits + Method Call Detection

**Release date:** September 2026
**Previous release:** v0.15.0 (PyPI Publishing)
**Focus:** Claim "I modified X" and have it verified — structural body-diff
hashes (`CHANGED_FUNCTION` / `CHANGED_CLASS`), member/attribute call
detection across all five languages, Python `async` indexing, and four
pre-existing bug fixes (Part B).

---

## What's new in v0.16.0

### `CHANGED_FUNCTION` / `CHANGED_CLASS` — verifiable body edits ✅

Two new claim types let a model say "I *modified* this function/class"
instead of only add/remove:

| Claim type | Verified by |
|------------|-------------|
| `CHANGED_FUNCTION` | Structural body-diff (function / method body) |
| `CHANGED_CLASS` | Structural body-diff (class shell — fields, bases, decorators) |

Every symbol in all five languages (Python/JS/TS/TSX/Rust/Go) now carries a
**formatting-insensitive structural body hash**:

- A real edit always changes the hash → the claim **CONFIRMED**
- Reformat-only, comment-only, whitespace, and string quote-style edits do
  **not** → no false `CHANGED_*`
- Method body edits fire `CHANGED_FUNCTION` with the enclosing class, never
  `CHANGED_CLASS` (disjoint facts); class-shell edits fire only
  `CHANGED_CLASS`
- Method-call claims match evidence **strictly on `parent_class`** — a
  class-less claim cannot confirm against method evidence

### Method / attribute call detection ✅

`CALLS_FUNCTION` now captures member chains in every language:

- `self.foo()`, `obj.bar()`, `a.b.c()`, `this.foo()`, `pkg.Func()`,
  `s.foo()` — resolved to the final name, with the caller's enclosing class
- `console.log()` / `logger.info()` — captured now (previously excluded)
- Excluded by design: receivers that are themselves calls (`f().bar()`) and
  dunder-style names (`obj.__x__()`)

### Python `async def` is now indexed ✅

`async def` functions and methods were invisible to the symbol index —
every async claim was UNVERIFIABLE, even when true. They are now ordinary
`FUNCTION` / `METHOD` symbols: ADD / REMOVE / CHANGED all verify, and a
sync → async conversion of the same name is detected as a body change.

### Part B — pre-existing bug fixes folded in

- **P1 (major): Prompt Mode never restored the working tree on git repos.**
  On a clean tree the patch survived every prompt-mode run; on a dirty tree
  the patch survived the stash pop. `save_before()` now records exactly what
  it did (clean / stashed / copy), and `restore()` reverts **only the
  patch's applied files** to HEAD before popping a pushed stash — the
  same-file case succeeds by construction, user edits return intact, and a
  revert failure surfaces loudly with the stash preserved. New real-git test
  file (`tests/test_snapshot_manager_git.py`, 13 tests).
- **P2 (major): `async def` invisible** — see above; the pinning test was
  flipped and README limitations de-scoped.
- **P3 (medium): scans wrote `.nowreck/cache/` into the directories they
  scanned.** The persistent cache now runs only when the scanned root is the
  current working directory (the live project). External snapshot dirs
  (`--pre A --post B`, `--compare` git-archive temps) scan cache-free, and a
  run-created `.nowreck/cache/` is removed on restore when it did not
  pre-exist.
- **P4 (low): `CALL_REMOVED`** now renders with a human label in
  unexplained-change lists and the prompt builder.
- **TS/TSX method decorators:** a decorator edit on a method was invisible
  to both the method hash and the class shell. Decorators are now folded
  into the method's body hash — the edit fires `CHANGED_FUNCTION` (Python
  parity), never `CHANGED_CLASS`.

### Verification

- `CHANGED_FUNCTION` / `CHANGED_CLASS` claims verify CONFIRMED against real
  body edits, CONTRADICTED by ADD/REMOVE evidence, UNVERIFIABLE against
  nothing — in every language via the real `--pre --post` pipeline.
- Cache schema v2: stale v1 caches are ignored and rebuilt with hashes;
  `body_hash` round-trips through the cache.
- SARIF: two new rules — `NW016 HallucinatedFunctionChange`,
  `NW017 HallucinatedClassChange` (both `error`, on CONTRADICTED evidence).

## Not in this release

- No new languages, CLI flags, exit codes, or `--format` values
- No `CHANGED_*` claim types for INTERFACE / ENUM / TYPE_ALIAS (their
  bodies remain existence-checked exactly as before)
- No receiver tracking in call identity (`self.foo()` and `obj.foo()` both
  yield `called_name="foo"`)
- No semantic call-graph resolution; the three-verdict model is unchanged

## Compatibility

| What | Why |
|------|-----|
| CLI, flags, exit codes | Untouched — no new CLI surface |
| Existing 13 claim types | Byte-identical semantics (regression-pinned) |
| Old prompt / provider paths | Untouched |
| `--pre` / `--post` on external dirs | Cache-free, but output identical |
| License | Still FSL-1.1-MIT (auto-converts to MIT in July 2028) |

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Full pytest suite | 1001 | ✅ all pass |
| `ruff check` + `ruff format --check` | — | ✅ clean |
| `basedpyright` strict | — | ✅ 0 errors |

## Files modified

| File | Change |
|------|--------|
| `nowreck/scanner/symbol_index.py` | `body_hash` on `Symbol` (identity-exempt, cache round-trip); `AsyncFunctionDef` indexed (P2) |
| `nowreck/scanner/_tree_sitter_helpers.py` | Structural hash; class-shell hash (methods excluded); member-chain call capture; TS/TSX method-decorator folding |
| `nowreck/scanner/rust_scanner.py`, `go_scanner.py` | `CallEvidence` + receiver/selector capture |
| `nowreck/scanner/javascript_scanner.py`, `typescript_scanner.py` | `CallEvidence` returns |
| `nowreck/scanner/scan_cache.py` | `CACHE_VERSION = 2` (body-hash payloads) |
| `nowreck/scanner/snapshot_manager.py` | P1 git restore (clean/stashed modes, scoped revert-first, loud failures); P3 cache policy + run-cache cleanup |
| `nowreck/scanner/repository_scanner.py` | `body_hash` through cache; hash-normalization fixes |
| `nowreck/detector/change_detector.py` | `CHANGED_FUNCTION`/`CHANGED_CLASS` detection; call capture (dunder/call-receiver exclusions); `_resolve_call_file` |
| `nowreck/claims/models.py` | `ClaimType` + `CHANGED_FUNCTION`/`CHANGED_CLASS` (15 types) |
| `nowreck/verifier/verifier.py` | `_SAME_CHANGE`/`_OPPOSITE_CHANGE` widened for CHANGED; strict `parent_class` call matching |
| `nowreck/verifier/prompt_verifier.py` | P1 finalize flow (scoped revert + always-pop, run-cache settle) |
| `nowreck/model/prompts.py` | CHANGED taxonomy + JSON examples; `CALL_REMOVED` label; valid-JSON example fix |
| `nowreck/model/provider.py` | `_CLAIM_TYPE_TO_CHANGE` + CHANGED entries |
| `nowreck/reporter/terminal_reporter.py` | CHANGED evidence branches, `Class.method` call rendering, `CALL_REMOVED` label |
| `nowreck/reporter/sarif_reporter.py` | `NW016` / `NW017` rules |
| `nowreck/main.py`, `picker.py` | Cache-free external scans (P3); banner → v0.16.0 |
| `nowreck/__init__.py`, `pyproject.toml` | Version → `"0.16.0"` |
| `README.md`, `use.md` | Claim table (15 types), `CALLS_FUNCTION` field notes, limitations, roadmap, version surfaces |
| `tests/*` (12 files) | +86 tests: detector/verifier/claims/reporter/cache matrices, real-git restore, per-language E2E, async, P3 |
| `tests/test_snapshot_manager_git.py` | **New** — real-git restore matrix (13 tests) |
| `docs/nowreck-v16-scope.md` | **New** — v0.16.0 scope document |
| `docs/release16.md` | **New** — these release notes |