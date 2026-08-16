# NoWreck — v7 Scope (TSX / `.tsx` Files Only)

**Status:** Draft. Local development only — not published, not merged into the
public repo, until proven and deliberately released. Same discipline as v2,
v3, v4, v5, and v6.

## Principle

Same rule as every prior increment: one small thing at a time, proven before
expanding. v6 (`--verbose`) is done and its Definition of Done is fulfilled.
v7 is **TSX (`.tsx` files) support only. Nothing else.**

TSX was decided as the **v7 increment** during the v6 planning conversation
and recorded in the v6 scope doc, release5.md, release6.md, and the README
roadmap. This document is that increment's scope.

## What this increment actually is

`.tsx` files are TypeScript files that may contain JSX syntax (React-style
`<div>...</div>` elements inside expressions). The scanner must parse them,
extract the same symbols and calls it already extracts from `.ts` files, and
feed them through the existing pipeline unchanged.

Key fact that makes this small: **the `tree-sitter-typescript` package
already ships the TSX grammar.** It exposes both `language_typescript()`
and `language_tsx()`, and v5 already depends on the package — so v7 adds
**zero new dependencies**. The TSX grammar was explicitly deferred in the v5
scope doc ("Separate language increment"), not because it needed new tooling,
but because v5 was scoped to `.ts` only.

### What `.tsx` files define — and what they don't

React components are ordinary functions, arrow-function consts, and classes —
all already covered by the existing `SymbolType` set:

- `function App() { return <div/> }` → FUNCTION
- `const App = () => <div/>` → FUNCTION (arrow assignee)
- `class App extends React.Component { render() { return <div/> } }` →
  CLASS + METHOD (`render`)
- Nested helpers inside components → collected as nested callers, same as today

**JSX elements are expressions, not symbols.** `<div>`, `<Component/>`,
fragments (`<>...</>`), and JSX attributes never become symbols or calls.
No new `SymbolType`, no new claim types.

## The one design decision: fold `.tsx` into the TS family

`.tsx` is the **same language** as `.ts` — same grammar package, same symbol
shapes, same claim types. Therefore **`.tsx` files fold into the existing
`ScanResult.ts_files` field** rather than getting a parallel `tsx_files`
field. Concretely:

- `scan_ts_file()` / `scan_ts_calls()` in `typescript_scanner.py` dispatch
  on file extension — `.tsx` → TSX grammar, `.ts` → TS grammar. Callers pass
  the file path and never think about the grammar.
- `RepositoryScanner._discover_ts_files()` matches both `*.ts` and `*.tsx`
  (hidden-dir exclusion unchanged). `_parse_ts_file()` already delegates to
  `scan_ts_file()`, so it needs no change beyond discovery.
- **Zero changes** to `symbol_index.py`, `change_detector.py` (including the
  call re-read, which calls `scan_ts_calls()` — the dispatch handles it),
  `picker.py`, or the JSON schema.
- `ts_files` is documented as "TypeScript family" (`.ts` + `.tsx`).

Rationale: a separate `tsx_files` field would force parallel changes through
symbol indexing, both change-detection file-set unions, the call re-read,
the picker summary, the demos, and the tests — all to represent the same
language. Folding keeps the risk surface minimal. If this decision is
contested during review, the alternative (parallel `tsx_files` field) is
documented in this doc's design history and costs one extra pass over the
integration points — but it is not the recommended path.

## The real work: proving JSX doesn't confuse the helpers

Both `collect_top_level_symbols` and `extract_tree_sitter_calls_from_tree`
in `_tree_sitter_helpers.py` are **grammar-agnostic** — they walk
`named_children` and match specific node types (`function_declaration`,
`class_declaration`, `method_definition`, `arrow_function`,
`variable_declarator`, `call_expression`, ...). JSX nodes (`jsx_element`,
`jsx_self_closing_element`, `jsx_expression`, `jsx_attribute`) match none of
those patterns, so they are simply recursed into and ignored. The v7 core is
**proving** that holds for real-world `.tsx`, not writing new traversal
logic:

- JSX inside a function body → function still collected, calls in the body
  still captured
- `onClick={() => doThing()}` → the inline arrow is a nested caller;
  `doThing()` inside it is captured as a call
- `onClick={handleClick}` → an identifier, not a call — correctly ignored
  (matches existing "simple identifier calls only" behaviour)
- `export default () => <div/>` → anonymous default export, ignored by name
  (same as today); `export default function App() {...}` → named, collected
- Class components with `render()` returning JSX → CLASS + METHOD
- Fragments, nested components, generics + interfaces in `.tsx` (valid TSX)
  → no crashes, correct symbol extraction

If any JSX shape does mislead the helpers, the fix stays inside
`typescript_scanner.py` or `_tree_sitter_helpers.py` — never in the verifier
or reporter.

## Scope boundary

- `.tsx` scanning, symbol extraction, call extraction, change detection,
  and verification — in.
- **`.ts` behaviour must remain byte-identical to v5** (regression gate).
- **No new claim types** — the same 7. Interfaces, enums, and type aliases
  in `.tsx`/`.ts` remain uncaptured (they need new claim types first; still
  deferred).
- **No JSX-element symbols** — markup is not a symbol.
- **No new dependencies**, **no verifier/reporter changes**, **no JSON
  schema changes**, **no new model providers**, **no caching**.

## Phases

### Phase 1: Scanner — TSX grammar path

- `typescript_scanner.py`: add `_get_tsx_language()` (same lazy-import
  pattern, loads `language_tsx()`), dispatch in `scan_ts_file()` and
  `scan_ts_calls()` by `path.suffix == ".tsx"`.
- Hand-build `.tsx` samples (components, class components, arrow components,
  JSX-in-body, `onClick={...}` handlers, fragments, `export default`) under
  `test_ts_samples/` and verify symbols + calls match expectations by hand
  before any tests are written.

**Human checkpoint: stop & report.** Show the extracted symbols/calls for
each sample; confirm `.ts` output unchanged.

### Phase 2: Integration — discovery + milestone repo

- `_discover_ts_files()` matches `*.tsx` too (rename or keep name —
  cosmetic; docstrings say "TS family").
- New milestone repo `test_milestone1/repos/pure-tsx/src/` — React-style
  `.tsx` files mirroring the pure-ts pattern (greeter/calculator/models
  equivalents with JSX).
- Add the repo to `demo_milestone1.py`'s repo list. `_print_scan_summary`
  needs no change (fold).

**Human checkpoint: stop & report.** Demo shows `.tsx` files counted under
TS, symbols indexed, changes detected on a real pre/post edit.

### Phase 3: Tests

- `test_ts_samples/`: new comprehensive TSX suite (parity with the TS
  suite's coverage: top-level symbols, exports, IIFE skip, call extraction,
  edge cases) + multi-round repeatability run. Sample files for every JSX
  shape in the "real work" list.
- `test_milestone1/test_milestone1_checkpoint.py`: `EXPECTED_TSX_FILES`
  (3) and the pure-tsx repo scan/index/detect assertions. Pure-ts's own
  counts stay unchanged (separate repo, so no drift).
- Change-detector tests: add/remove/replace a component in a `.tsx` repo →
  expected `ADD_FUNCTION` / `REMOVE_FUNCTION` / `ADD_CLASS` changes.

**Human checkpoint: stop & report.** Full battery + new suites green.

### Phase 4: Milestone checkpoint + release

- Run the real CLI on the pure-tsx repo with a real pre/post change and
  claims covering the component additions; cross-check every reported
  symbol/line against the actual `.tsx` source.
- Confirm `.ts`-only repos produce output identical to v5 (regression gate).
- Live TSX DoD test (real model, induced false claim on a component —
  same design as the v5 TS live test; needs the user's key, run at release
  time).
- Re-run full battery + ruff + basedpyright; write `docs/release7.md`;
  update README roadmap (TSX → ✅ done in v0.7.0) and release6.md's
  "What's next".

**Human checkpoint: stop & report.**

## Deferred (documented, not built)

- **Interfaces / enums / type aliases** — need `ADD_INTERFACE` /
  `REMOVE_INTERFACE`-style claim types first. Still deferred.
- **TS polish** (from v5): abstract methods, constructor parameter
  properties, decorators — separate polish increment, not v7.
- **JSX elements as symbols** — markup is not a symbol. Never planned.
- **Caching**, **additional model providers**, **new claim types**,
  **scan-summary expansion** — unchanged, still deferred.

## Claim types: unchanged

Exactly the same 7 claim types as v3/v4/v5/v6. `.tsx` files verify against
them; nothing is added or altered.

## Dependencies

**None.** No new packages. The TSX grammar ships with the existing
`tree-sitter-typescript` dependency.

## Files (new / modified)

| File | What it covers |
|------|---------------|
| `nowreck/scanner/typescript_scanner.py` | TSX grammar + extension dispatch in `scan_ts_file` / `scan_ts_calls` |
| `nowreck/scanner/repository_scanner.py` | `_discover_ts_files()` matches `*.tsx`; `ScanResult.ts_files` docstring → TS family |
| `test_ts_samples/` | New `.tsx` edge samples + comprehensive/multi-round suites |
| `test_milestone1/repos/pure-tsx/` | New milestone repo (`.tsx` files) |
| `test_milestone1/test_milestone1_checkpoint.py` | pure-tsx scan/index/detect assertions |
| `test_milestone1/demo_milestone1.py` | pure-tsx repo added to the demo list |
| `test_milestone1/live_tsx_hallucination_test.py` *(new)* | Live DoD test (Phase 4) |
| `docs/release7.md` *(new)* | Release notes (Phase 4) |

## Unchanged

- `_tree_sitter_helpers.py`, `symbol_index.py`, `change_detector.py`,
  claim parser, claim verifier, reporter, CLI, picker — **0 changes**
- JSON output schema — **0 changes**
- Claim types — **0 changes**
- `.ts` / `.js` / `.py` scanning behaviour — **byte-identical** (hard gate)
- Existing milestone repos (pure-python, pure-js, pure-ts, mixed) — **0
  changes**

## Definition of done

1. A `.tsx` file with JSX (function components, class components, arrow
   components, JSX-in-body, handlers) scans to the correct symbols and
   calls — verified by hand against the source, and `nowreck fix --pre
   <empty> --post <pure-tsx repo>` detects the expected changes matching
   reality.
2. `.ts`-only repos produce output **byte-identical** to v5 for the same
   inputs.
3. The full existing test battery passes, plus the new TSX sample suites
   and milestone-checkpoint assertions.
4. ruff: 0 issues, basedpyright: 0 errors.
5. Live TSX DoD test (real model, induced false claim) passes at release
   time with the user's key.

## Explicitly not a roadmap

This covers exactly one thing — `.tsx` file support, same claim types,
phase-by-phase, human-checked at every step. When it's done and proven, the
next increment gets its own equally narrow scoping conversation.
