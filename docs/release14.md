# NoWreck v0.14.0 — @file Claims Input

**Release date:** September 2026
**Previous release:** v0.13.0 (CI/CD Integration)
**Focus:** Read claims from a file with the `@` prefix instead of inline JSON only.

---

## What's new in v0.14.0

### `--claims @file.json` ✅

`--claims` now accepts a `@`-prefixed file path (like `curl -d @file`) and
reads the claims JSON from that file:

```bash
# New — read from file
nowreck fix --pre ./before --post ./after --claims @claims.json

# Old — inline JSON still works unchanged
nowreck fix --pre ./before --post ./after --claims '{"claims": [...]}'
```

Works in both claims-capable modes:
- Pre/Post mode (`--pre PATH --post PATH`)
- Compare mode (`--compare REF`)

**Why:** large claim sets suffer from shell-quoting hell, and CI pipelines
that generate claims files previously needed workarounds like
`cat claims.json | xargs -I{} nowreck fix ... --claims '{}'` — that
workaround is no longer necessary.

**Path handling:**
- `~` is expanded (`@~/claims.json`)
- Leading/trailing whitespace around the value is trimmed
- Symlinks inside the current directory are followed; symlinks pointing
  outside it are rejected (the path is resolved before the CWD check)

**Security:** paths are resolved and must stay inside the current
directory. Path traversal (`@/etc/passwd`, `@../...`) is rejected with a
clear error.

**Error handling** — all fail with a clear message and exit code 1, no
tracebacks:
- `@` with no path (`--claims @`)
- Missing file
- Empty file
- Unreadable file (permission denied)
- Path outside the current directory

**Implementation:** new `resolve_claims_input()` helper in `nowreck/main.py`,
wired into the two int-returning entry points (`handle_fix` pre/post path
and `_handle_compare_mode`) so errors surface before any scanning or git
work. The parse sites (`_detect_and_verify`, compare mode) are untouched.

---

## What's unchanged

| What | Why |
|------|-----|
| Inline `--claims '{"claims": [...]}'` | Still works — `@file` is opt-in |
| Prompt mode | Claims never resolved there (claims unused in that mode) |
| All 13 claim types | No new types needed |
| `ClaimVerifier.verify()` | Already correct |
| `ChangeDetector.detect()` | Already correct |
| Scanner, detector, verifier, reporters | Untouched |
| Exit codes | Unchanged (0 clean / 1 issues) |

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Full pytest suite | 801 | ✅ all pass |
| New `resolve_claims_input` unit tests | 10 | ✅ all pass |
| New `@file` integration tests (`handle_fix`) | 2 | ✅ all pass |

## Files modified

| File | Change |
|------|--------|
| `nowreck/main.py` | **New** `resolve_claims_input()` helper; wired into pre/post + compare mode; `_BANNER` → v0.14.0 |
| `nowreck/cli.py` | `--claims` help text mentions `@file` syntax |
| `nowreck/__init__.py` | `__version__` → `"0.14.0"` |
| `pyproject.toml` | Version → `"0.14.0"` |
| `tests/test_cli.py` | **New** `TestResolveClaimsInput` (10 tests) + 2 `@file` integration tests in `TestHandleFix` |
| `README.md` | Claims Mode section: `@file` example; replaced the "must be passed inline" paragraph |
| `use.md` | Claims Mode: replaced the `cat claims.json \| xargs` workaround with the `@file` one-liner; `--claims` row updated |
| `docs/release14.md` | **New** — these release notes |
