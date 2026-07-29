# NoWreck — v4 Scope (JavaScript Polish: Generators, Export Default, IIFEs)

**Status:** ✅ **Complete.** All three gaps implemented, tested, and reviewed.
Local development only — not published, not merged into the public repo, until
deliberately released. Same discipline as v3.

## Principle

Same rule as v2 and v3: one small thing at a time, proven before expanding.
v4 was originally considered as TypeScript support, but that was caught and
rejected — v3 shipped with three documented JavaScript gaps (`export default`
patterns, generator functions, and IIFE awareness) that are small, safe to
fix, and affect real-world JS code daily. **v4 is JS polish only. Nothing
else.**

TypeScript, JSX/TSX, Rust, Go, and caching are all real, legitimate future
directions — each gets its own scope document, later, only after v4's gaps
are closed and proven.

## What this increment actually is

v3 added the JavaScript `LanguageAdapter` and shipped it with the explicit
note that three JS patterns were deferred. This increment closes those
deferred gaps. The scanner (`javascript_scanner.py`) is the only component
that changes — no new modules, no new dependencies, no infrastructure.

## Mandatory build discipline for this increment

This section exists because three earlier scope-doc v1, v2, and v3) each
reinforced the same lesson: narrow increments, human-checked at every step.
The following rules apply without exception:

1. **One gap at a time, in this order:** `export default` → generators →
   IIFEs. Complete, test, and review each before starting the next. Do not
   write code for a later gap while an earlier one is still open.
2. **No gap is "done" until it's been shown to work on a hand-built test
   file** — with before/after output demonstrating the previously-deferred
   pattern is now captured correctly, AND demonstrating that the existing
   test battery (388 pytest + 80 multi-round + 78 comprehensive) still
   passes.
3. **Stop and report after each gap**, don't continue straight into the next
   one unprompted. A human checkpoint between gaps is required. Trust is
   re-established by checking, not by assuming compliance.
4. **If asked to build multiple gaps in one response, refuse and ask which
   single gap to focus on first.** Speed is not the goal. Correctness and
   verifiability are.

## What's in scope for v4

### Gap 1: `export default` patterns *(already handled — test coverage only)*

**Investigation finding:** The scope-doc v3 assumption was wrong. Tree-sitter
DOES provide a ``declaration`` field for **named** default exports
(``export default function foo() {}`` → ``declaration`` field is
``function_declaration``). The existing export-unwrapping code in
``_collect_top_level_symbols`` already handles this correctly.

``export default function foo() {}`` and ``export default class Foo {}`` were
**already working** in v3 — they just lacked test coverage. Anonymous default
exports (``export default function() {}``, ``export default () => {}``,
``export default class {}``) correctly have no ``declaration`` field and no
name to capture.

**Actual work done (v4):**

| File | What changed |
|------|--------------|
| ``javascript_scanner.py`` | Fixed misleading comment that claimed default exports were dropped |
| ``edge_export_default.js`` | Fixed comments, added ``export default class Bar { barMethod() {} }`` |
| ``test_phase1_comprehensive.py`` | Added assertions for ``explicitDefault``, ``Bar``, ``barMethod`` |

**No code logic changes were needed.** Gap 1 is closed with test coverage only.

### Gap 2: Generator functions (`function*`) ✅ **Complete**

**Actual CST types discovered during implementation:**

| Pattern | Tree-sitter node type | Status |
|---------|----------------------|--------|
| `function* foo() {}` | `generator_function_declaration` | ✅ Captured as FUNCTION |
| `const x = function*() {}` | value = `generator_function` | ✅ Captured as FUNCTION |
| `async function* bar() {}` | `generator_function_declaration` (same type) | ✅ Captured as FUNCTION |
| `export function* qux() {}` | export → `generator_function_declaration` | ✅ Captured as FUNCTION |
| `export default function* gen() {}` | export → `generator_function_declaration` | ✅ Captured as FUNCTION |
| `class X { *gen() {} }` | `method_definition` (already worked) | ✅ Already captured |

**Implementation:** Added `"generator_function_declaration"` alongside
`"function_declaration"` in 3 places (`_collect_top_level_symbols`,
`_collect_js_callers`, `_find_js_calls_in_body`). Added
`"generator_function"` alongside `"arrow_function"` and
`"function_expression"` in 3 places (`_maybe_arrow_function_declarator`,
`_collect_js_callers`, `_find_js_calls_in_body`). No new dependencies
needed — all node types were already resolved by the existing grammar.

**New file:** `test_js_samples/edge_generators.js` — tests all 7 generator
patterns plus positive controls (normal function, arrow) and a negative
control (non-generator function expression).

### Gap 3: IIFE awareness (explicit skip) ✅ **Complete**

**Actual implementation:**

1. **`_is_iife(node)` helper** — New function that checks whether a node
   is a `call_expression` whose callee (after unwrapping parens via
   `_unwrap_parens`) is a `function_expression`, `arrow_function`, or
   `generator_function`. Also handles `void function() { ... }()` by
   recursing from `unary_expression` → `call_expression`.

2. **`_collect_top_level_symbols`** — Added explicit skip for top-level
   `expression_statement` nodes that contain an IIFE (both standalone
   `(function(){})()` and `void function(){}()` patterns). Logs a debug
   message when skipping.

3. **`_maybe_arrow_function_declarator`** — Added explicit `_is_iife(value)`
   check before the unwrapping check. If detected, logs a debug message and
   returns without emitting a symbol.

4. **Latent bug fix: `_unwrap_parens`** — Found and fixed a bug where
   `child(0)` returned the `(` syntactic token instead of the inner
   expression node. Changed to `named_child(0)` which correctly skips
   syntactic tokens. The old code worked by accident because `(` doesn't
   match any function type check, but it would have failed for genuinely
   parenthesized arrow functions like `const x = (() => 1)`.

**New file:** `test_js_samples/edge_iife.js` — tests 10 patterns including
IIFEs (const, arrow, standalone, void, var) and positive controls.

**Pattern results:**

| Pattern | Before v4 | After v4 |
|---------|-----------|----------|
| `const x = (function() { ... })()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `const x = (() => { ... })()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `(function() { ... })()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `void function() { ... }()` | ❌ Silently excluded | ✅ Explicitly excluded + tested |
| `const normal = () => {}` | ✅ Captured | ✅ Still captured (positive control) |

### Modified files (complete list)

- `nowreck/scanner/javascript_scanner.py` — generator types, `_is_iife`
  helper, `_unwrap_parens` fix, explicit IIFE skip logic
- `test_js_samples/edge_export_default.js` — updated comments, added
  `export default class Bar` with methods
- `test_js_samples/edge_generators.js` — **new** file with all generator
  patterns
- `test_js_samples/edge_iife.js` — **new** file with all IIFE patterns
- `test_js_samples/edge_async_generators.js` — added generator expression
  pattern, updated comments
- `test_js_samples/test_phase1_comprehensive.py` — added assertions for
  export default, generators, and IIFEs (23 new tests total)
- `test_js_samples/test_phase1_multiround.py` — updated round 4 generator
  assertion from deferred → captured

### Claim types: unchanged

Exactly the same 7 claim types as v3 — `ADD_FUNCTION`, `REMOVE_FUNCTION`,
`ADD_CLASS`, `REMOVE_CLASS`, `FILE_CREATED`, `FILE_DELETED`,
`CALLS_FUNCTION`. No new claim types. The fix is in the scanner, not in the
verifier. The rest of the pipeline (symbol index, change detector, verifier,
reporter) never needs to know that generators or default exports were
previously missed.

### Interaction with milestone repos

The existing milestone repos (`test_milestone1/repos/pure-js/src/`) do not
use generators, `export default`, or IIFEs, so they are unaffected. This is
intentional — the milestone repos validate end-to-end pipeline behavior, not
scanner coverage. Scanner coverage is validated by the comprehensive and
multi-round test suites.

## Do Not Build Yet

Everything from v3's "Do Not Build Yet" still applies, plus:

- **`export default () => {}` (anonymous arrow default)** — there is no name
  to capture at the definition site. The name is assigned at import time.
  If a deterministic way to represent "the default export" is genuinely
  needed later, that's a future scope decision, not something to invent here.
- **Arrow functions as object properties** (`{ foo: () => {} }`) — still
  deferred (v3 scope). Still uncommon enough to not warrant the complexity
  vs other JS patterns.
- **Generator methods in classes** (`class Foo { *bar() {} }`) — check
  whether tree-sitter-javascript uses `method_definition` with a `*`
  modifier or a separate node type. If it's the same `method_definition`
  node, they're already captured. If it's a separate type, defer — generator
  methods are less common than generator declarations.
- **Any TypeScript syntax** — explicitly deferred (still v3's decision).
- **JSX/TSX** — separate language increment, not part of JS polish.
- **Caching of any kind** — independent problem, validated against proven
  language support (which JS now is), not against a brand-new fix.
- **Any claim type beyond the existing 7** — no new claims needed for this
  increment.

## Implementation summary

- **No new dependencies.** All three gaps used the existing
  `tree-sitter-javascript` grammar. The tree-sitter library already resolves
  all relevant node types.
- **No new modules.** All production changes were in `javascript_scanner.py`
  only. Test files are additive (`test_js_samples/`).
- **Generator node type names were confirmed** by parsing test files and
  inspecting `node.type`:
  - Top-level: `generator_function_declaration`
  - Expression: `generator_function`
  - Methods: `method_definition` (unchanged — already worked)
  - Async generators: same `generator_function_declaration` type
- **Definition of done (fulfilled):** All three gaps pass on hand-built test
  files. The existing 388-pytest + 80-multi-round + 78-comprehensive battery
  all pass. The comprehensive test grew from 78 to **101 tests** with v4
  additions. The live-model hallucination-catch test (Phase 4d) is
  unaffected (no breakage).

## Explicitly not a roadmap

Same as v3's scope doc: this covers exactly three JS polish items, built
one at a time, gap-by-gap, human-checked at every step. When v4 is done and
proven, the next increment (TypeScript, Rust, caching, or whatever comes
next) gets its own equally narrow scoping conversation.
