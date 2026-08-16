# NoWreck v0.7.0 — TSX (`.tsx`) Support Release

**Release date:** August 2026  \
**Previous release:** v0.6.0 (Verbose Mode)  \
**Focus:** `.tsx` files (TypeScript + JSX) scan, symbol-extract, call-extract, change-detect, and verify — folded into the existing TypeScript family. Zero new dependencies (the TSX grammar ships with the already-used `tree-sitter-typescript` package), zero changes to the verifier, reporter, claim types, or JSON schema.

---

## What's new in v0.7.0

### `.tsx` file support ✅

React components are ordinary functions, arrow-function consts, and classes — all already covered by the existing `SymbolType` set. The scanner now parses `.tsx` files with the TSX grammar (`language_tsx()`, from the same package v5 already depends on) and feeds the exact same symbols and calls through the existing pipeline:

- `function App() { return <div/> }` → FUNCTION
- `const App = () => <div/>` → FUNCTION (arrow assignee)
- `class App extends React.Component { render() { return <div/> } }` → CLASS + METHOD (`render`)
- `onClick={() => doThing()}` → nested named arrows are collected as callers; identifier handlers (`onClick={handleClick}`) and member calls (`this.toggle()`) are ignored — same rules as `.ts`/`.js`
- `export default function App() {...}` → collected; anonymous `export default () => <div/>` → ignored (no name)
- Fragments, generics, interfaces, nested components — parsed, no crashes

**JSX elements are expressions, not symbols or calls.** `<div>`, `<Component/>`, and JSX attributes never become symbols or calls — verified by hand and by test.

### The design decision: fold into the TS family

`.tsx` is the same language as `.ts` — same grammar package, same symbol shapes, same 7 claim types. So `.tsx` files **fold into the existing `ScanResult.ts_files` field** rather than getting a parallel `tsx_files` field. `scan_ts_file()` / `scan_ts_calls()` dispatch on file extension; `_discover_ts_files()` matches both `*.ts` and `*.tsx`; `symbol_index`, `change_detector`, `picker`, and the JSON schema needed **zero changes**.

### Scope boundary

- `.ts` / `.js` / `.py` behaviour — **byte-identical to v0.6.0** (hard gate)
- Same 7 claim types — interfaces, enums, and type aliases in `.tsx`/`.ts` remain uncaptured (they need new claim types first; still deferred)
- No JSX-element symbols — markup is not a symbol
- No new dependencies, no verifier/reporter changes, no JSON schema changes

---

## Test suite growth

| Suite | v0.6.0 | v0.7.0 | Growth |
|-------|--------|--------|--------|
| pytest (project unit tests) | 449 | **469** | **+20** |
| TS comprehensive | 42 tests | 42 tests | — |
| TS multi-round | 29 tests | 29 tests | — |
| TSX comprehensive *(new)* | — | **54 tests** | **+54** |
| TSX multi-round *(new, 7 rounds)* | — | **36 tests** | **+36** |
| JS comprehensive | 101 tests | 101 tests | — |
| JS multi-round | 80 tests | 80 tests | — |
| Milestone 1 checkpoint (4 repos) | 45 tests | **57 tests** | **+12** |
| Milestone 1 demo (5 repos incl. pure-tsx) | Clean | Clean | — |
| Change detector (incl. new TSX class) | 39 tests | **47 tests** | **+8** |
| Live hallucination-catch tests (JS + TS + TSX) | PASS | PASS | — |
| ruff | 0 issues | **0 issues** | — |
| basedpyright | 0 errors | **0 errors** | — |

**+20 new pytest tests**, broken down as:

- **`tests/test_change_detector.py` — `TestDetectTsxChanges` (8 tests):** component add → `ADD_FUNCTION`, component remove → `REMOVE_FUNCTION`, replace in single file → add + remove, class component → `ADD_CLASS` + method (folds to `ADD_FUNCTION` with `parent_class`, same as `.ts`/`.js`), TSX call detected, `<Child/>` usage NOT a call, identical pre/post → no changes, file create/delete
- **`test_milestone1/test_milestone1_checkpoint.py` — `TestPureTsxRepo` (12 tests):** discovery (3 files), greeter components, calculator class + methods, models components, symbol counts, call detection, `console.log` excluded, JSX-element-usage-not-a-call, file changes, no-change, determinism; pure-tsx added to cross-repo determinism and pre/post no-change loops

**New sample suites** (`test_ts_samples/`):

- **`test_phase1_comprehensive_tsx.py` — 54 tests:** component shapes, handlers and nested arrows, exports/generics/interfaces, anonymous default exports, mixed edge cases (IIFE skip, interface/type/enum negatives, calls in JSX-in-body), error handling, `repo_root` relativisation, determinism
- **`test_phase1_multiround_tsx.py` — 36 tests across 7 rounds:** symbol repeatability ×3, call repeatability ×3 + known-call set, 660-symbol stress file, path variants, real-world React patterns, line-number accuracy, chaos test

New sample files: `edge_tsx_components.tsx`, `edge_tsx_handlers.tsx`, `edge_tsx_exports.tsx`, `edge_tsx_anon_default.tsx`, `edge_tsx_mixed.tsx`.

---

## File changes

### Modified files

| File | What changed |
|------|-------------|
| `nowreck/scanner/typescript_scanner.py` | `_get_tsx_language()` (lazy `language_tsx()`); `_new_parser(language)`; `scan_ts_file` / `scan_ts_calls` dispatch on `.tsx` extension; docstrings → TS family |
| `nowreck/scanner/repository_scanner.py` | `_discover_ts_files()` matches both `*.ts` and `*.tsx` (via `itertools.chain`); `ScanResult.ts_files` docstring → TS family |
| `test_milestone1/test_milestone1_checkpoint.py` | `PURE_TSX_REPO`, `EXPECTED_TSX_FILES`, fixture, `TestPureTsxRepo` class, added to cross-repo determinism + pre/post loops |
| `test_milestone1/demo_milestone1.py` | Pure TSX repo added to the demo list; TS print line relabeled `TS files:` |
| `tests/test_change_detector.py` | `TestDetectTsxChanges` class (8 tests) |
| `README.md` | Roadmap: TSX marked done in v0.7.0 |
| `docs/nowreck-v7-scope.md` | Full scope document tracing the increment |
| `docs/release7.md` | This release notes file |

### New files

| File | What it covers |
|------|---------------|
| `test_milestone1/repos/pure-tsx/src/` | New milestone repo: `greeter.tsx`, `calculator.tsx`, `models.tsx` (React-style equivalents of pure-ts) |
| `test_ts_samples/test_phase1_comprehensive_tsx.py` | 54-test comprehensive TSX suite |
| `test_ts_samples/test_phase1_multiround_tsx.py` | 36-test, 7-round TSX suite |
| `test_ts_samples/edge_tsx_*.tsx` | 5 TSX sample files |
| `test_milestone1/live_tsx_hallucination_test.py` | Live-model TSX DoD test (Phase 4) |
| `docs/nowreck-v7-scope.md` | Full scope document |
| `docs/release7.md` | This release notes file |

### Unchanged

- `_tree_sitter_helpers.py`, `symbol_index.py`, `change_detector.py` — **0 changes**
- Claim parser, claim verifier, reporter, CLI, picker — **0 changes**
- JSON output schema — **0 changes**
- Claim types — exactly the same 7
- `.ts` / `.js` / `.py` scanning behaviour — **byte-identical** (hard gate)
- Existing milestone repos (pure-python, pure-js, pure-ts, mixed) — **0 changes**
- Dependencies — **0 new packages**

---

## Installing / upgrading

```bash
pipx install .    # fresh install from repo
pip install -e .  # or editable install
```

Requires Python 3.10+. No new dependencies.

```bash
nowreck --version
# → nowreck 0.7.0
```

---

## Definition of Done ✅

1. A `.tsx` file with JSX (function components, class components, arrow components, JSX-in-body, handlers) scans to the correct symbols and calls — verified by hand against the source, and `nowreck fix --pre <empty> --post <pure-tsx repo>` detects the expected changes matching reality.
2. `.ts`-only repos produce output **byte-identical** to v0.6.0 for the same inputs.
3. The full existing test battery passes, plus the new TSX sample suites and milestone-checkpoint assertions.
4. ruff: 0 issues, basedpyright: 0 errors.
5. Live TSX DoD test (real model, induced false claim) passes at release time with the user's key.

**Result (verified live):** ran the real CLI against the pure-tsx milestone repo (empty pre → post with a real added component `WelcomeBanner`). 14 hand-written claims → **12 CONFIRMED / 1 CONTRADICTED** (the induced false call `Farewell → notify`, which doesn't exist — correctly caught) **/ 1 UNVERIFIABLE** (`GhostComponent`, which doesn't exist). Verbose output showed every `Matched:` block with `line_number` values cross-checked against the actual `.tsx` source — all 10 matched definitions exact (e.g. `Greeting` line 3, `formatGreeting` line 8, `Farewell` line 12, `WelcomeBanner` line 17 of `greeter.tsx`; `Calculator` line 3, `computeAverage` line 30 of `calculator.tsx`; `UserCard` line 8, `AdminCard` line 17, `UserList` line 31 of `models.tsx`). All 70 non-verbose output lines preserved verbatim in verbose mode (only the one-line `Evidence:` / unexplained summaries replaced by detail blocks, per v0.6.0 design). The `.ts`-only pure-ts repo scans identically (3 files, 16 symbols, 0 failures, extensions strictly `.ts`).

**Live DoD (real model, user's key, `nvidia/nemotron-3-ultra-550b-a55b:free`):** TSX live test **PASS** ×2 rounds — round 1: 18 claims → 17 CONFIRMED / 1 CONTRADICTED (induced false call caught) / 0 UNVERIFIABLE; round 2: 12 claims → 11/1/0. Identical catch both times.

---

## What's next

The roadmap remains focused on narrow, testable increments, each with its own scope document and phase-by-phase build discipline.

- `explanation` field on claims — model + prompt change (README documents it, the `Claim` model doesn't have it yet) — deferred from v6
- Scan-summary expansion in verbose mode (per-language file counts) — deferred from v6
- Interfaces / enums / type aliases as claim types (`ADD_INTERFACE` / `REMOVE_INTERFACE`) — still deferred; needs new claim types first
- TS polish (from v5): abstract methods, constructor parameter properties, decorators — separate polish increment
- Additional model providers (Anthropic, Gemini)
- Caching for large repositories
- CI/CD integration
