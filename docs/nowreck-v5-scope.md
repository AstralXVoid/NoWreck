# NoWreck — v5 Scope (TypeScript Support Only)

**Status:** Draft. Local development only — not published, not merged into the
public repo, until proven and deliberately released. Same discipline as v2,
v3, and v4.

## Principle

Same rule as v2, v3, and v4: one small thing at a time, proven before
expanding. v5 was originally considered during the v4 planning conversation
as the next logical language increment, and that decision is confirmed here.
**v5 is TypeScript support only. Nothing else.**

Rust, Go, caching, JSX/TSX, and additional claim types are all real,
legitimate future directions — each gets its own scope document, later, only
after TypeScript is proven working.

## Parser choice: Tree-sitter TypeScript grammar, justified

JavaScript (v3) chose Tree-sitter because JS has no standard library parser.
TypeScript follows the same reasoning — there is no built-in TS parser, and
Tree-sitter has mature, well-maintained TypeScript grammar support.

The `tree-sitter-typescript` package bundles **two separate grammars**:
1. **TypeScript grammar** (`.ts` files) — this is what v5 uses
2. **TSX grammar** (`.tsx` files) — explicitly deferred to a later increment

The Python binding package `tree-sitter-typescript` exposes both via
`language_typescript()` and `language_tsx()` respectively. v5 uses only
`language_typescript()`.

Using Tree-sitter for TypeScript means:
- Same parser family as JS, same lazy-import pattern in the scanner
- Most of the JS scanner's helper infrastructure is reusable
- The same `Symbol` / `SymbolType` / `DetectedChange` data shapes apply
  unchanged — the verifier and reporter never need to know the difference

## What this increment actually is

v3 added the JavaScript `LanguageAdapter` and shipped it with JS scanner +
symbol index + change detector + verifier integration. v4 polished three
deferred JS gaps. **v5 adds a TypeScript LanguageAdapter** (a new scanner
module `typescript_scanner.py`) alongside the existing Python and JS
scanners, following the same phase-by-phase build discipline as v3.

The existing `.py` (Python) and `.js` (JavaScript) pipelines are untouched.
The new `.ts` pipeline mirrors the JS one structurally, reusing the same
Tree-sitter helper patterns (`_unwrap_parens`, `_is_iife`, call detection).

## Mandatory build discipline for this increment

This section exists because every prior scope doc (v1, v2, v3, and v4) each
reinforced the same lesson: narrow increments, human-checked at every step.
The following rules apply without exception:

1. **Build in phases, one component at a time** — following the same order
   as the JS pipeline from v3: scanner → symbol index integration → change
   detector integration → verified against milestone repos. Do not write
   code for a later phase before the current phase is complete, tested, and
   reviewed.

2. **No phase is "done" until it's been shown to work on a hand-built test
   file** — with actual output demonstrating the previously-unsupported
   pattern is now captured correctly, AND demonstrating that the existing
   test battery (388 pytest + 101 comprehensive + 80 multi-round) still
   passes.

3. **Stop and report after each phase**, don't continue straight into the
   next one unprompted. A human checkpoint between phases is required, not
   optional — same discipline as v3's Phase 1 through Phase 4 checkpoints.

4. **If asked to build multiple phases in one response, refuse and ask which
   single phase to focus on first.** Speed is not the goal. Correctness and
   verifiability are.

## What's in scope for v5

**TypeScript symbol scanning, added as a new scanner alongside the existing
Python and JavaScript scanners.**

### Phase 1: TypeScript scanner (tree-sitter)

A new `nowreck/scanner/typescript_scanner.py` module that:

- Uses the `tree-sitter-typescript` Python package with the TypeScript
  grammar (not the TSX grammar)
- Parses `.ts` files and produces `Symbol` objects structurally identical
  to those produced by the JS scanner
- Captures the same patterns as the JS scanner:
  - **Function declarations** (`function foo() {}`)
  - **Arrow functions assigned to variables** (`const foo = () => {}`)
  - **Classes** (`class Foo { ... }`)
  - **Class methods** (`bar() {}` inside a class body)
  - **Exported variants** (`export function foo() {}`, `export class Foo {}`,
    `export const foo = () => {}`)
  - **Generator functions** (`function* foo() {}`)
  - **Async functions** (`async function foo() {}`)
  - **Export default** (`export default function foo() {}`)
  - **IIFE skip** (explicit exclusion with debug logging)
- Implements the same call-detection helpers (`_collect_ts_callers`,
  `_find_ts_calls_in_body`) for the `CALLS_FUNCTION` claim type

#### Shared helpers: extracted into a common module

Because the TypeScript grammar uses **identical** node type names as
JavaScript for every in-scope pattern (`function_declaration`,
`arrow_function`, `class_declaration`, `method_definition`,
`generator_function_declaration`), the JS scanner's helper functions
are not JS-specific — they are tree-sitter-function-expression-specific.

**v5 extracts the following shared helpers** into
`nowreck/scanner/_tree_sitter_helpers.py`:

- `_unwrap_parens(node)` — unwrap parenthesized expression chains
- `_is_iife(node)` — detect immediately-invoked function expressions
- `_maybe_arrow_function_declarator(...)` — emit symbols for arrow/gen
  expressions assigned to variables
- `_collect_js_callers(...)` / `_collect_ts_callers(...)` — identical
  logic, renamed for language clarity (or unified as `_collect_callers`)
- `_find_js_calls_in_body(...)` / `_find_ts_calls_in_body(...)` — same
- `_extract_js_calls_from_tree(...)` / `_extract_ts_calls_from_tree(...)`
  — same

The JS scanner (`javascript_scanner.py`) is updated to import these
from the shared module. The TS scanner (`typescript_scanner.py`) does
the same. This avoids code duplication, reduces the TS scanner to
mostly grammar configuration + the TS-specific export-unwrapping path,
and makes future language scanners (Rust, Go) even simpler to add.

**Deferred TS-specific patterns** — not built in v5 (same discipline as v3's
deferred JS patterns):

| Pattern | Reason | Future |
|---------|--------|--------|
| **Interface declarations** | No interface-exists claim type exists yet | Future claim type increment |
| **Type aliases** | No type-alias-exists claim type exists yet | Future claim type increment |
| **Enums** | Structural members (not functions/classes) | Future polish increment |
| **Access modifiers** (`public`/`private`/`protected`) | The scanner captures symbols, not visibility | May never be needed |
| **Decorators** | Structural metadata, not symbol definition | Future polish increment |
| **Generic type parameters** | The name is the function/class name, not the type param | May never be needed |
| **Abstract classes / methods** | The `abstract` keyword modifies `class_declaration` / `method_definition` — investigate whether node type changes | Deferred to v5 polish |
| **Namespace / module declarations** | Structural grouping, not symbol definition | Future polish increment |
| **`declare` keyword** (ambient declarations) | No runtime code, no structural symbol to capture | May never be needed |
| **Constructor parameter properties** | `constructor(public name: string)` — not a class method | Future polish increment |
| **`as` expressions** / type assertions | Type-only, no structural symbol | May never be needed |
| **TSX (`.tsx` files)** | Requires the TSX grammar and JSX handling | Separate language increment |

### Phase 2: Symbol index integration

Add `.ts` file scanning to `RepositoryScanner`:
- New `_discover_ts_files()` method (mirrors `_discover_js_files()`)
- New `_parse_ts_file()` method that delegates to the TypeScript scanner
- `ScanResult` gets a new `ts_files: dict[Path, list[Symbol]]` field
- `SymbolIndexBuilder.build()` processes `ts_files` alongside `modules` and
  `js_files`

### Phase 3: Change detector integration

The change detector (`change_detector.py`) already works with
`Symbol`/`DetectedChange` objects — no language-specific logic. Adding
`.ts` symbols to the index means they flow through detection automatically.
No changes needed.

### Phase 4: Milestone 1 checkpoint (same as v3)

Build a pure-TypeScript test repo with the same structure as the pure-JS
milestone repo (3 files, add/remove/call patterns across them). Run the
full pipeline — scan → detect → verify → report — to confirm deterministic
correctness.

### Deferred to v5 Polish (not Phase 1-4)

Same discipline as v4: if v5 ships with documented gaps, they get their own
narrow polish increment later. The following are explicitly deferred:

- **Abstract methods** — investigate whether `abstract method_definition`
  uses a distinct node type or a modifier on `method_definition`
- **Constructor methods** — `constructor()` is a special method in TS. The
  JS scanner currently does not filter `constructor` out. Investigate whether
  TS treats it as `method_definition` or something else.
- **Parameter properties** (`constructor(public x: number)`) — not a method
  declaration.

### Claim types: unchanged

Exactly the same 7 claim types as v3/v4 — `ADD_FUNCTION`, `REMOVE_FUNCTION`,
`ADD_CLASS`, `REMOVE_CLASS`, `FILE_CREATED`, `FILE_DELETED`,
`CALLS_FUNCTION`. No new claim types. If a TypeScript-specific claim type
genuinely seems necessary later (e.g. `ADD_INTERFACE`), that's a future
scope decision, made deliberately, not something to add mid-build.

### New dependency

- `tree-sitter-typescript>=0.23.2` in `pyproject.toml`

### Test files (new)

| File | What it covers |
|------|---------------|
| `test_ts_samples/edge_basic.ts` | Basic function, arrow, class, method — core positive cases |
| `test_ts_samples/edge_export.ts` | Export function, export class, export const arrow, export default |
| `test_ts_samples/edge_generators.ts` | Generator function, async generator, generator expression |
| `test_ts_samples/edge_iife.ts` | IIFE patterns (same as JS — explicit exclusion) |
| `test_ts_samples/edge_types_only.ts` | **Negative test** — interfaces, type aliases, enums that must NOT be captured |
| `test_ts_samples/test_phase1_comprehensive.py` | Full suite mirroring the JS comprehensive test structure |
| `test_ts_samples/test_phase1_multiround.py` | Multi-round repeatability, stress, chaos tests |

### Unchanged

- Python scanner — **0 changes**
- JavaScript scanner — **0 changes** (unless the TS scanner reveals a shared
  helper worth extracting, which would be a deliberate refactor, not a side
  effect)
- Symbol index — one new field in `ScanResult` (`ts_files`), `build()`
  updated to process it. Otherwise unchanged.
- Change detector — **0 changes**
- Claim verifier — **0 changes**
- Reporter — **minor update in Phase 4**: `_build_scan_summary()` in
  `terminal_reporter.py` gains a `ts_count = len(result.ts_files)` line
  so scan summaries show TypeScript file counts alongside Python and
  JavaScript counts. This is a single-line addition, not a redesign. The
  `ScanResult.success_count` property is similarly updated to include
  `len(self.ts_files)`.
- CLI — **0 changes** (command structure, flags, interactive picker all
  unchanged)

## Do Not Build Yet

Everything from v4's "Do Not Build Yet" still applies, plus:

- **TSX (`.tsx` files)** — requires a separate TSX grammar. TSX handling
  also implies JSX element parsing, which is a separate concern. Deferred
  to its own increment.
- **Interface declarations** — there is no `ADD_INTERFACE` / `REMOVE_INTERFACE`
  claim type. Adding interface support without a claim type to verify would
  be work without a consumer.
- **Type alias declarations** — same reasoning as interfaces.
- **Enum declarations** — same reasoning as interfaces.
- **`declare` keyword handling** — ambient declarations have no runtime
  structural presence. They could cause false positives in the change
  detector. Deferred.
- **Access modifiers** — the scanner captures symbol existence, not
  visibility. Adding visibility awareness would be a new feature, not a
  bug fix.
- **Decorator support** — decorators are structural metadata, not symbol
  definitions. The scanner correctly captures the decorated function/class;
  the decorator itself is invisible. This is correct by design.
- **Caching of any kind** — independent problem, validated against proven
  language support (Python + JS), not against a brand-new TS integration.
- **Any claim type beyond the existing 7** — no new claims needed for this
  increment. Interface/enum/type support would require new claim types,
  which is a separate decision.

## Implementation notes

- **New dependency:** `tree-sitter-typescript>=0.23.2`
- **New module:** `nowreck/scanner/typescript_scanner.py`
- **Modified module:** `nowreck/scanner/repository_scanner.py` (new
  `_discover_ts_files`, `_parse_ts_file`, `ScanResult.ts_files` field)
- **Modified module:** `nowreck/scanner/symbol_index.py` (`build()` updated
  to process `ts_files`)
- **Build and test** in the local development copy only, same workflow as
  v3 and v4 — no git remote pushes until deliberately ready to share
- **Definition of done:** The same hallucination-catch test used for Python
  and JS (a real prompt, a real model, a deliberately induced false claim)
  succeeds on a TypeScript test file, with CONFIRMED/CONTRADICTED results
  matching reality

### Node type name mapping (from tree-sitter-typescript grammar)

These are the node type names the TypeScript grammar uses for the structures
we care about. Confirmed by inspecting the grammar's `node-types.json`:

| Pattern | Node type | Notes |
|---------|-----------|-------|
| `function foo() {}` | `function_declaration` | Same as JS |
| `function* foo() {}` | `generator_function_declaration` | Same as JS |
| `const foo = () => {}` | `arrow_function` (value) | Same as JS |
| `const foo = function() {}` | `function_expression` (value) | Same as JS |
| `class Foo {}` | `class_declaration` | Same as JS |
| `class method() {}` | `method_definition` | Same as JS |
| `interface Foo {}` | `interface_declaration` | ⛔ Deferred |
| `type Foo = ...` | `type_alias_declaration` | ⛔ Deferred |
| `enum Foo {}` | `enum_declaration` | ⛔ Deferred |
| `export function foo() {}` | `export_statement` → `function_declaration` | Same export-unwrap logic as JS |
| `export default function foo() {}` | `export_statement` → `function_declaration` | Same as JS |
| `export default class Foo {}` | `export_statement` → `class_declaration` | Same as JS |

## Explicitly not a roadmap

Same as v3's and v4's scope docs: this covers exactly one thing — TypeScript
support, same claim types, phase-by-phase, human-checked at every step. When
it's done and proven, the next increment (TSX, Rust, caching, or whatever
comes next) gets its own equally narrow scoping conversation.
