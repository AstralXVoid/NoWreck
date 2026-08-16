# NoWreck — v8 Scope (Interfaces, Enums, Type Aliases as Claim Types)

**Status:** Draft. Local development only — not published, not merged into the
public repo, until proven and deliberately released. Same discipline as v2
through v7.

## Principle

Same rule as every prior increment: one small thing at a time, proven before
expanding. v7 (`.tsx` files) is done and its Definition of Done is fulfilled.
v8 is **interface / enum / type-alias claim types — the oldest deferred item**
(from v5's scope doc, re-deferred in v7). Nothing else.

TypeScript codebases define contracts at the type level (`interface`,
`enum`, `type` aliases) that are invisible to Nowreck today: the scanner
ignores them, so they never appear as symbols, changes, or claims. v8 makes
them first-class — captured, detected, claimable, and verifiable — for the
TS/TSX family.

## What this increment actually is

Today the pipeline knows three `SymbolType`s (FUNCTION, CLASS, METHOD), seven
`ClaimType`s, and seven `ChangeType`s. Type-level declarations parse fine in
the TS/TSX grammars (`interface_declaration`, `enum_declaration`,
`type_alias_declaration`) — the helpers just never collect them. v8:

1. **Collects them** in `collect_top_level_symbols` (grammar-agnostic helper —
   these node types only ever appear in TS/TSX grammars, so JS behaviour is
   untouched by construction).
2. **Gives them identity** — three new `SymbolType` members (INTERFACE, ENUM,
   TYPE_ALIAS).
3. **Detects their changes** — three new `ChangeType` pairs (ADD/REMOVE ×
   INTERFACE/ENUM/TYPE_ALIAS).
4. **Makes them claimable** — three new `ClaimType` pairs mirroring the
   change types, wired through the parser, prompt, verifier, and reporter.
5. **Verifies them** — the verifier's same-type / opposite-type matching is
   purely field-based and type-agnostic; adding mappings is mechanical.

### What gets captured (TS/TSX only)

```ts
interface User { id: number; name: string }        → INTERFACE "User"
enum Color { Red, Green, Blue }                     → ENUM "Color"
type Status = "active" | "inactive"                 → TYPE_ALIAS "Status"
export interface Props { ... }                      → (unwrapped, same as above)
export default interface Thing { ... }              → (named, collected)
```

- `export interface/enum/type` already unwraps through the existing
  `export_statement` handling.
- **Members are NOT captured.** Interface method signatures
  (`method_signature` nodes), enum members (`Red`/`Green`), and generic
  parameters are structural detail, not symbols — same one-level-deep
  philosophy as class methods today. Interface *methods* do **not** become
  METHOD symbols in v8 (the class-method path uses `method_definition`,
  which interfaces don't produce; adding signature capture is a polish
  increment, not v8).
- **Python is untouched.** Python's `class Color(Enum)` stays `ADD_CLASS`
  (byte-identity gate — changing it would break existing Python output).
  Python has no `interface`/`type` keyword equivalents that map cleanly, so
  the new claim types are TS/TSX-only in practice; a model claiming
  `ADD_INTERFACE` against a `.py` file simply gets UNVERIFIABLE, which is
  correct.

## The one design decision: per-kind claim types (recommended)

**Three distinct pairs** — `ADD_INTERFACE` / `REMOVE_INTERFACE`,
`ADD_ENUM` / `REMOVE_ENUM`, `ADD_TYPE_ALIAS` / `REMOVE_TYPE_ALIAS` — rather
than one folded `ADD_TYPE` / `REMOVE_TYPE` pair.

Rationale: the existing taxonomy is per-kind (FUNCTION ≠ CLASS). The
scanner knows the exact declaration kind from the CST node type, so
detection is precise with zero extra effort, and the model's prompt can say
"interface User" and claim exactly that. Folding into a single TYPE pair
would blur interface-vs-alias in the JSON report, the terminal report, and
the prompt, and would make a model's mislabel *less* detectable (an
`ADD_TYPE User` claim would confirm against an interface OR an alias,
hiding real confusion).

If this is contested during review, the folded alternative costs one pair
instead of three through every wiring point and makes claims more tolerant
of model mislabelling — but it is not the recommended path.

## The real work: wiring six new types through eight touch points

Each is a mechanical, additive change (no existing mapping altered):

| # | Location | Change |
|---|----------|--------|
| 1 | `nowreck/scanner/symbol_index.py` | `SymbolType`: +INTERFACE, +ENUM, +TYPE_ALIAS; add `interfaces` / `enums` / `type_aliases` index properties (symmetry with `functions`/`classes`/`methods`) |
| 2 | `nowreck/scanner/_tree_sitter_helpers.py` | `collect_top_level_symbols`: collect `interface_declaration`, `enum_declaration`, `type_alias_declaration` (name field) |
| 3 | `nowreck/detector/change_detector.py` | `ChangeType`: +6; `_symbol_to_change`: map INTERFACE/ENUM/TYPE_ALIAS |
| 4 | `nowreck/claims/models.py` | `ClaimType`: +6; `CLAIM_TYPE_NAMES`: +6 entries |
| 5 | `nowreck/verifier/verifier.py` | `_SAME_CHANGE`: +6; `_OPPOSITE_CHANGE`: +6 |
| 6 | `nowreck/model/prompts.py` | `_CLAIM_TO_CHANGE_TYPE`: +6; JSON schema example + field notes updated; "7 claim types" wording → 13 |
| 7 | `nowreck/reporter/terminal_reporter.py` | `_CLAIM_TYPE_LABELS`: +6; evidence-line builders for the new add/remove kinds |
| 8 | `nowreck/claims/parser.py` | inherits `CLAIM_TYPE_NAMES` from models (verify no local copy) |

**No JSON schema break.** The `type` field gains six new allowed string
values; every existing value and field is unchanged. Additive, not breaking
— old CI consumers keep working. (Flagged explicitly because v6 froze the
schema; v8 extends it deliberately and documents the addition in
`release8.md`.)

## Scope boundary

- TS/TSX type-level scanning, symbol extraction, change detection,
  claims, and verification — in.
- **`.ts` / `.tsx` / `.js` / `.py` existing behaviour must remain
  byte-identical to v7** for everything already captured (regression gate).
- Python enums/typed-anything — **out** (stays `ADD_CLASS`/uncaptured).
- Interface members, enum members, generic parameters — **out** (polish
  increment later).
- **No new dependencies**, **no caching**, **no new model providers**,
  **no reporter/CLI/picker feature changes** beyond the additive labels.
- JSX elements — still not symbols (unchanged from v7).

## Phases

### Phase 1: Scanner — type-level symbols

- `_tree_sitter_helpers.py`: collect the three declaration node types.
- Hand-build samples under `test_ts_samples/` (interface, enum, type alias,
  exports, generics, both `.ts` and `.tsx`) and verify symbols + line
  numbers by hand before any tests.

**Human checkpoint: stop & report.** Show the extracted symbols per sample;
confirm `.ts`/`.js` output unchanged for existing samples.

### Phase 2: Claim + change + symbol types

- `SymbolType` (+3 + index properties), `ChangeType` (+6),
  `ClaimType` (+6 + names), verifier mappings, prompt mapping + schema,
  reporter labels + evidence lines.
- Update the milestone repos (pure-ts and/or pure-tsx) with an interface,
  an enum, and a type alias so detection has real material.

**Human checkpoint: stop & report.** A hand-written claim set covering
ADD/REMOVE × INTERFACE/ENUM/TYPE_ALIAS verifies CONFIRMED/CONTRADICTED/
UNVERIFIABLE correctly against the real repos.

### Phase 3: Tests

- `test_ts_samples/`: extend the TSX comprehensive suite (or add a focused
  type-level suite) — interface/enum/type-alias positives, exports, line
  numbers, negatives (members not captured), `.ts` parity.
- `tests/test_change_detector.py`: add/remove/replace an interface, enum,
  type alias → expected `ADD_INTERFACE` / `REMOVE_ENUM` / etc.
- `tests/test_verifier.py` (or existing): same-type CONFIRMED, opposite-type
  CONTRADICTED, missing → UNVERIFIABLE for the new claim types.
- `tests/test_model.py`: `claims_to_changes` for the new types.
- `tests/test_terminal_reporter.py`: labels + evidence lines for new kinds.
- `test_milestone1/test_milestone1_checkpoint.py`: new symbol/change
  assertions on the updated repos (existing counts unchanged for old
  symbols).
- `test_claims.py` already asserts every `ClaimType` member exists in
  `CLAIM_TYPE_NAMES` — automatically covers the new six.

**Human checkpoint: stop & report.** Full battery + new suites green.

### Phase 4: Milestone checkpoint + release

- Run the real CLI on the updated pure-tsx repo with a real pre/post change
  (add an interface + remove an enum) and claims covering the type-level
  changes; cross-check every reported symbol/line against the actual source.
- Confirm `.ts`/`.js`/`.py`-only repos produce output identical to v7
  (regression gate).
- Live DoD test (real model, induced false type-level claim) — same design
  as v5/v7 live tests; needs the user's key, run at release time.
- Re-run full battery + ruff + basedpyright; write `docs/release8.md`;
  update README roadmap (interfaces/enums/type aliases → ✅ done in v0.8.0)
  and release7.md's "What's next".

**Human checkpoint: stop & report.**

## Deferred (documented, not built)

- **Interface method signatures / enum members as symbols** — polish
  increment, not v8.
- **Python type-level capture** — Python's `Enum`/`TypeAlias`/`TypedDict`
  mapping needs its own design conversation (would touch Python byte-identity);
  not v8.
- **`explanation` field on claims** — model + prompt change (README documents
  it, the `Claim` model doesn't have it yet); deferred from v6, still deferred.
- **Scan-summary expansion**, **caching**, **additional model providers**,
  **CI/CD integration** — unchanged, still deferred.

## Claim types: 7 → 13

| Current (7) | v8 adds (6) |
|-------------|-------------|
| ADD_FUNCTION | ADD_INTERFACE |
| REMOVE_FUNCTION | REMOVE_INTERFACE |
| ADD_CLASS | ADD_ENUM |
| REMOVE_CLASS | REMOVE_ENUM |
| FILE_CREATED | ADD_TYPE_ALIAS |
| FILE_DELETED | REMOVE_TYPE_ALIAS |
| CALLS_FUNCTION | |

## Dependencies

**None.** No new packages.

## Files (new / modified)

| File | What it covers |
|------|---------------|
| `nowreck/scanner/symbol_index.py` | `SymbolType` +3; `interfaces`/`enums`/`type_aliases` properties |
| `nowreck/scanner/_tree_sitter_helpers.py` | Collect interface/enum/type-alias declarations |
| `nowreck/detector/change_detector.py` | `ChangeType` +6; `_symbol_to_change` mapping |
| `nowreck/claims/models.py` | `ClaimType` +6; `CLAIM_TYPE_NAMES` +6 |
| `nowreck/verifier/verifier.py` | `_SAME_CHANGE` +6; `_OPPOSITE_CHANGE` +6 |
| `nowreck/model/prompts.py` | `_CLAIM_TO_CHANGE_TYPE` +6; schema example + field notes |
| `nowreck/reporter/terminal_reporter.py` | Labels + evidence lines for new kinds |
| `test_ts_samples/` | New type-level samples + suite updates |
| `test_milestone1/repos/pure-tsx/` (and/or pure-ts) | Add interface/enum/type-alias to a repo file |
| `test_milestone1/test_milestone1_checkpoint.py` | Type-level scan/index/detect assertions |
| `test_milestone1/live_tsx_hallucination_test.py` *(or new live test)* | Live DoD with induced false type-level claim (Phase 4) |
| `docs/release8.md` *(new)* | Release notes (Phase 4) |

## Unchanged

- `javascript_scanner.py`, `typescript_scanner.py` — **0 changes** (helpers
  are grammar-agnostic; discovery already covers `.ts`/`.tsx`)
- `repository_scanner.py`, `picker.py`, CLI, JSON schema structure — **0 changes**
- Claim parser logic — **0 changes** (inherits names from models)
- `.ts` / `.tsx` / `.js` / `.py` existing scanning behaviour — **byte-identical** (hard gate)
- Existing milestone repos' existing symbol counts — **unchanged** (additions only)
- Dependencies — **0 new packages**

## Definition of done

1. A `.ts`/`.tsx` file with interfaces, enums, and type aliases scans to the
   correct `SymbolType`s and line numbers — verified by hand against the
   source — and `nowreck fix --pre <empty> --post <repo>` detects the
   expected `ADD_INTERFACE` / `ADD_ENUM` / `ADD_TYPE_ALIAS` changes matching
   reality.
2. `.ts`/`.tsx`/`.js`/`.py` repos produce output **byte-identical** to v7 for
   all previously-supported symbols.
3. The full existing test battery passes, plus the new type-level suites and
   assertions.
4. ruff: 0 issues, basedpyright: 0 errors.
5. Live DoD test (real model, induced false type-level claim) passes at
   release time with the user's key.

## Explicitly not a roadmap

This covers exactly one thing — type-level claim types for TS/TSX, same
phase-by-phase discipline, human-checked at every step. When it's done and
proven, the next increment gets its own equally narrow scoping conversation.
