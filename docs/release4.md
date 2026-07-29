# NoWreck v0.4.0 — JavaScript Polish Release

**Release date:** July 2026  
**Previous release:** v0.3.0 (JavaScript Core)  
**Focus:** Closing three deferred JavaScript gaps: generator functions, export default patterns, and IIFE awareness.

---

## What's new in v0.4.0

### Gap 1: Export default patterns ✅

Named default exports (`export default function foo() {}`, `export default class Foo {}`) were **already working** in v3 — the tree-sitter grammar provides a `declaration` field for these. The original scope doc's assumption that they were dropped was wrong. v0.4.0 adds proper test coverage and fixes a misleading comment that claimed they weren't captured.

No code logic changes were needed — just tests and documentation.

### Gap 2: Generator functions ✅

All `function*` generator patterns are now captured:

| Pattern | Captured as | Previously |
|---------|-------------|------------|
| `function* foo() {}` | FUNCTION `foo` | ❌ Dropped |
| `async function* bar() {}` | FUNCTION `bar` | ❌ Dropped |
| `const baz = function*() {}` | FUNCTION `baz` | ❌ Dropped |
| `export function* qux() {}` | FUNCTION `qux` | ❌ Dropped |
| `export default function* gen() {}` | FUNCTION `gen` | ❌ Dropped |

**What changed:** Added `generator_function_declaration` (for declarations) and `generator_function` (for expressions) alongside the existing `function_declaration` and `function_expression` checks in 6 sites across the scanner.

### Gap 3: IIFE awareness ✅

Immediately-invoked function expressions are now **explicitly excluded** from being captured as symbols, with debug logging so you can see why they were skipped:

| Pattern | Before v4 | After v4 |
|---------|-----------|----------|
| `const x = (function() { ... })()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `const x = (() => { ... })()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `(function() { ... })()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `void function() { ... }()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `const normal = () => {}` (positive control) | ✅ Captured | ✅ Still captured |

**What changed:** A new `_is_iife()` helper, explicit skip logic in both `_collect_top_level_symbols` and `_maybe_arrow_function_declarator`, and a **latent bug fix** in `_unwrap_parens` where `child(0)` returned the `(` token instead of the inner expression.

### Bonus fix: `_unwrap_parens` latent bug

Found and fixed a bug dating back to v3's JS scanner: `child(0)` on a `parenthesized_expression` node returned the `(` syntactic token — not the inner expression. Changed to `named_child(0)`, which correctly skips syntactic tokens. The old code worked by accident because `(` doesn't match any function type check, but it would have failed for genuinely parenthesized arrow functions like `const x = (() => 1)`.

---

## Test suite growth

| Suite | v0.3.0 | v0.4.0 | Growth |
|-------|--------|--------|--------|
| pytest (project unit tests) | 388 | 388 | — |
| JS comprehensive | 78 tests | **101 tests** | **+23** |
| JS multi-round | 80 tests | 80 tests | — |
| Milestone 1 (3 repos) | Clean | Clean | — |
| Phase 4a demo (14 claims) | Clean | Clean | — |
| Live hallucination-catch test | Clean | Clean | — |
| ruff | 0 issues | **0 issues** | — |
| basedpyright | 0 errors | **0 errors** | — |

**101 comprehensive tests** — covering every JS pattern NoWreck can parse, with positive and negative controls for each.

---

## File changes

### Modified files

| File | What changed |
|------|-------------|
| `nowreck/scanner/javascript_scanner.py` | Added generator types (6 sites), `_is_iife` helper, `_unwrap_parens` latent bug fix, explicit IIFE skip logic |
| `test_js_samples/edge_export_default.js` | Updated comments, added `export default class Bar` with method |
| `test_js_samples/edge_async_generators.js` | Added generator expression pattern, updated comments |
| `test_js_samples/test_phase1_comprehensive.py` | **+23 tests** — export default, generators, IIFEs |
| `test_js_samples/test_phase1_multiround.py` | Updated round 4 generator assertion |
| `README.md` | Updated Limitations and Roadmap for v0.4.0 |
| `nowreck/__init__.py` | Version bump to 0.4.0 |
| `pyproject.toml` | Version bump to 0.4.0 |
| `nowreck/main.py` | Banner updated to v0.4.0 |
| `nowreck/reporter/terminal_reporter.py` | Docstring updated to v0.4.0 |

### New files

| File | What it covers |
|------|---------------|
| `test_js_samples/edge_generators.js` | All generator patterns (declaration, async, expression, export, export default, positive/negative controls) |
| `test_js_samples/edge_iife.js` | All IIFE patterns (const, arrow, standalone, void, var, positive controls) |
| `docs/release4.md` | This release notes file |
| `docs/nowreck-v4-scope.md` | Full scope document tracing the increment |

### Unchanged

- All milestone repos (`test_milestone1/`)
- Symbol index, change detector, claim parser, claim verifier, reporter
- CLI interface, interactive picker, configuration
- Python scanner — **0 changes**
- No new dependencies

---

## Installing / upgrading

```bash
pipx install .    # fresh install from repo
pip install -e .  # or editable install
```

Requires Python 3.10+. JavaScript scanning requires `tree-sitter-javascript` (installed automatically with the package via optional dependency).

```bash
nowreck --version
# → nowreck 0.4.0
```

---

## What's next

The roadmap remains focused on narrow, testable increments:

- `--verbose` mode showing full deterministic evidence per claim
- Additional model providers (Anthropic, Gemini)
- Caching for large repositories
- **TypeScript support** — likely the next major language increment
- CI/CD integration

Each increment gets its own scope document, its own phase-by-phase build discipline, and its own human-checked checkpoints.
