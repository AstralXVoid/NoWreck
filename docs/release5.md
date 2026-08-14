# NoWreck v0.5.0 — TypeScript Support Release

**Release date:** August 2026  \
**Previous release:** v0.4.0 (JavaScript Polish)  \
**Focus:** Adding TypeScript as a first-class language alongside Python and JavaScript — same 7 claim types, same deterministic pipeline, zero changes to the verifier.

---

## What's new in v0.5.0

### TypeScript support ✅

NoWreck now scans `.ts` files with the same structural pipeline it uses for
Python and JavaScript. Everything that works for JS symbols works for TS
symbols — the verifier, change detector, and reporter never need to know
which language produced the data.

| Pattern | Captured as |
|---------|-------------|
| `function foo() {}` | FUNCTION `foo` |
| `const foo = () => {}` | FUNCTION `foo` |
| `function* gen() {}` | FUNCTION `gen` |
| `async function foo() {}` | FUNCTION `foo` |
| `class Foo { bar() {} }` | CLASS `Foo` + METHOD `bar` |
| `export function foo() {}` | FUNCTION `foo` (export unwrapped) |
| `export default function foo() {}` | FUNCTION `foo` |
| `const x = (function() { ... })()` (IIFE) | ⛔ Explicitly excluded |

**Deferred (documented, not built):** interfaces, type aliases, enums,
TSX (`.tsx`) files, decorators, and access modifiers — each has its own
reasoning in `docs/nowreck-v5-scope.md`.

### Shared tree-sitter helpers

The JS scanner's helpers (`_unwrap_parens`, `_is_iife`, arrow-declarator
handling, call detection) were language-agnostic — the TypeScript grammar
uses identical node type names for every in-scope pattern. They were
extracted into `nowreck/scanner/_tree_sitter_helpers.py` and are now shared
by both the JS and TS scanners. This removes ~390 lines of duplication and
makes future language scanners (Rust, Go) even simpler to add.

### New dependency

- `tree-sitter-typescript>=0.23.2`

---

## Test suite growth

| Suite | v0.4.0 | v0.5.0 | Growth |
|-------|--------|--------|--------|
| pytest (project unit tests) | 388 | 388 | — |
| JS comprehensive | 101 tests | 101 tests | — |
| JS multi-round | 80 tests | 80 tests | — |
| **TS comprehensive (new)** | — | **42 tests** | **+42** |
| **TS multi-round (new)** | — | **29 tests** | **+29** |
| Milestone 1 (4 repos: py + js + ts + mixed) | Clean | Clean | — |
| Phase 4a demo (17 TS claims) | — | Clean | — |
| Live hallucination-catch test (JS) | Clean | Clean | — |
| **Live hallucination-catch test (TS, new)** | — | **PASS** (Nemotron 3 Ultra, free) | — |
| ruff | 0 issues | **0 issues** | — |
| basedpyright | 0 errors | **0 errors** | — |

**42 TS comprehensive tests** — covering every TS pattern in scope with
positive and negative controls, including a negative test proving that
interfaces, type aliases, and enums are **not** captured.

**29 TS multi-round tests** — repeatability (3 identical runs), a 1100-symbol
stress file, path variants, real-world TS patterns, line-number accuracy,
JS regression, and chaos sampling.

---

## File changes

### Modified files

| File | What changed |
|------|-------------|
| `nowreck/scanner/javascript_scanner.py` | Import shared helpers from `_tree_sitter_helpers.py`; removed duplicated local copies |
| `nowreck/scanner/repository_scanner.py` | `ScanResult.ts_files` field, `_discover_ts_files()`, `_parse_ts_file()`, `success_count` includes TS |
| `nowreck/scanner/symbol_index.py` | `build()` processes `ts_files` alongside `modules` and `js_files` |
| `nowreck/detector/change_detector.py` | TS files included in file diffs + TS call re-read for `CALL_DETECTED` |
| `nowreck/picker.py` | Scan summary shows TS file counts |
| `test_milestone1/test_milestone1_checkpoint.py` | `TestPureTsRepo` class + TS in cross-repo determinism |
| `test_milestone1/demo_milestone1.py` | Shows `.ts` files in scan output |
| `pyproject.toml` | Version 0.5.0, new `tree-sitter-typescript>=0.23.2` dependency |
| `nowreck/__init__.py` | Version bump to 0.5.0 |
| `nowreck/main.py` | Banner updated to v0.5.0 |
| `README.md` | Limitations + Roadmap + scan description updated for TS |
| `use.md` | Version + troubleshooting updated for TS |

### New files

| File | What it covers |
|------|---------------|
| `nowreck/scanner/typescript_scanner.py` | The TS scanner (`scan_ts_file`, `scan_ts_calls`) |
| `nowreck/scanner/_tree_sitter_helpers.py` | Shared tree-sitter helpers (symbol collection, IIFE detection, call extraction) |
| `test_ts_samples/edge_basic.ts` | Basic function, arrow, class, method |
| `test_ts_samples/edge_export.ts` | Export function/class/const-arrow, export default |
| `test_ts_samples/edge_generators.ts` | Generator/async-generator patterns |
| `test_ts_samples/edge_iife.ts` | IIFE exclusion patterns |
| `test_ts_samples/edge_types_only.ts` | Negative test — interfaces/types/enums NOT captured |
| `test_ts_samples/test_phase1_comprehensive.py` | 42-test comprehensive suite |
| `test_ts_samples/test_phase1_multiround.py` | 29-test multi-round/stress suite |
| `test_milestone1/repos/pure-ts/` | Pure-TypeScript milestone repo (3 files) |
| `test_milestone1/demo_phase4a_ts.py` | End-to-end pipeline demo on pure-ts repo |
| `test_milestone1/live_ts_hallucination_test.py` | Definition-of-Done live-model test (needs API key) |
| `docs/nowreck-v5-scope.md` | Full scope document tracing the increment |
| `docs/release5.md` | This release notes file |

### Unchanged

- Python scanner — **0 changes**
- Claim verifier — **0 changes**
- Claim parser — **0 changes**
- Claim types — exactly the same 7
- CLI interface, interactive picker structure, configuration
- All existing milestone repos (`pure-python`, `pure-js`, `mixed`)

---

## Installing / upgrading

```bash
pipx install .    # fresh install from repo
pip install -e .  # or editable install
```

Requires Python 3.10+. TypeScript scanning requires `tree-sitter-typescript`
(installed automatically with the package).

```bash
nowreck --version
# → nowreck 0.5.0
```

---

## Definition of Done ✅

The v5 Definition of Done — the same live-model hallucination-catch test
used for Python and JS, now on a TypeScript test file — is at
`test_milestone1/live_ts_hallucination_test.py`. It deliberately induces a
false `CALLS_FUNCTION` claim (`farewell() -> notify()`, where `notify` does
not exist) and expects the verifier to catch it as CONTRADICTED while real
TS symbols confirm.

**Result (verified live):** run against OpenRouter with the free
`nvidia/nemotron-3-ultra-550b-a55b:free` model — **20 claims, 19 CONFIRMED,
1 CONTRADICTED, 0 UNVERIFIABLE**. Real TS symbols confirmed; the induced
false call was caught. The JS DoD test passes on the same model, confirming
the shared-helper refactor did not regress v4.

```bash
NOWRECK_API_KEY=your-key python test_milestone1/live_ts_hallucination_test.py
```

---

## What's next

The roadmap remains focused on narrow, testable increments, each with its
own scope document and phase-by-phase build discipline:

- TSX (`.tsx` files) — separate TSX grammar + JSX handling
- `--verbose` mode showing full deterministic evidence per claim
- Additional model providers (Anthropic, Gemini)
- Caching for large repositories
- CI/CD integration
