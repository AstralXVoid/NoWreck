# NoWreck v0.8.0 — Type-Level Claim Types (Interfaces, Enums, Type Aliases)

**Release date:** August 2026
**Previous release:** v0.7.0 (TSX Support)
**Focus:** `interface`, `enum`, and `type` alias declarations as first-class claim types for the TS/TSX family. Six new claim types (ADD/REMOVE × INTERFACE/ENUM/TYPE_ALIAS), wired through scanner, change detector, claim parser, verifier, prompts, and reporter. Zero new dependencies. Zero changes to JS/Python behaviour.

---

## What's new in v0.8.0

### Type-level claim types ✅

TypeScript codebases define contracts at the type level (`interface`, `enum`, `type` aliases) that were invisible to Nowreck until now. The scanner ignored them, so they never appeared as symbols, changes, or claims. v0.8.0 makes them first-class — captured, detected, claimable, and verifiable — for the TS/TSX family.

**What gets captured (TS/TSX only):**

```ts
interface User { id: number; name: string }        → INTERFACE "User"
enum Color { Red, Green, Blue }                     → ENUM "Color"
type Status = "active" | "inactive"                 → TYPE_ALIAS "Status"
export interface Props { ... }                      → (unwrapped, same as above)
export default interface Thing { ... }              → (named, collected)
```

**What stays unchanged:**

- Members are NOT captured — interface method signatures, enum members, and generic parameters remain structural detail, not symbols (same one-level-deep philosophy as class methods)
- Python's `class Color(Enum)` stays `ADD_CLASS` (byte-identity gate)
- `.ts`/`.js`/`.py` existing behaviour — byte-identical to v0.7.0 (hard gate)
- No new dependencies, no JSON schema break (additive only)

### The design decision: per-kind claim types

Three distinct pairs — `ADD_INTERFACE`/`REMOVE_INTERFACE`, `ADD_ENUM`/`REMOVE_ENUM`, `ADD_TYPE_ALIAS`/`REMOVE_TYPE_ALIAS` — rather than one folded `ADD_TYPE`/`REMOVE_TYPE` pair. The existing taxonomy is per-kind (FUNCTION ≠ CLASS), and the scanner knows the exact declaration kind from the CST node type. Folding into a single TYPE pair would blur interface-vs-alias in reports and make model mislabelling less detectable.

### Pipeline wiring (8 touch points, mechanical additive changes)

| # | Location | Change |
|---|----------|--------|
| 1 | `nowreck/scanner/symbol_index.py` | `SymbolType`: +INTERFACE, +ENUM, +TYPE_ALIAS; `interfaces`/`enums`/`type_aliases` properties |
| 2 | `nowreck/scanner/_tree_sitter_helpers.py` | `collect_top_level_symbols`: collect `interface_declaration`, `enum_declaration`, `type_alias_declaration` |
| 3 | `nowreck/detector/change_detector.py` | `ChangeType`: +6; `_symbol_to_change` mapping |
| 4 | `nowreck/claims/models.py` | `ClaimType`: +6; `CLAIM_TYPE_NAMES`: +6 entries |
| 5 | `nowreck/verifier/verifier.py` | `_SAME_CHANGE`: +6; `_OPPOSITE_CHANGE`: +6 |
| 6 | `nowreck/model/prompts.py` | `_CLAIM_TO_CHANGE_TYPE`: +6; schema example + field notes |
| 7 | `nowreck/reporter/terminal_reporter.py` | Labels + evidence lines for new kinds |
| 8 | `nowreck/claims/parser.py` | Inherits `CLAIM_TYPE_NAMES` from models (no local copy) |

### Scope boundary

- TS/TSX type-level scanning, symbol extraction, change detection, claims, and verification — **in**
- `.ts`/`.tsx`/`.js`/`.py` existing behaviour — **byte-identical to v0.7.0** (hard gate)
- Python enums/typed-anything — **out** (stays `ADD_CLASS`/uncaptured)
- Interface members, enum members, generic parameters — **out** (polish increment later)
- No new dependencies, no caching, no new model providers, no reporter/CLI/picker feature changes beyond additive labels

---

## Test suite growth

| Suite | v0.7.0 | v0.8.0 | Growth |
|-------|--------|--------|--------|
| pytest (project unit tests) | 469 | **453** | **−16** *(test_*_no_type_level tests removed as behaviour changed)* |
| Milestone 1 checkpoint (4 repos) | 57 tests | **60 tests** | **+3** |
| Change detector (incl. TSX + type-level) | 47 tests | **57 tests** | **+10** |
| Verifier (incl. type-level) | 39 tests | **55 tests** | **+16** |
| Terminal reporter (incl. type-level labels) | 34 tests | **45 tests** | **+11** |
| Model/prompt builder (incl. type-level) | 37 tests | **45 tests** | **+8** |
| Claims parser | 21 tests | 21 tests | — |
| ruff | 0 issues | **0 issues** | — |
| basedpyright | 0 errors | **0 errors** | — |

**New test coverage added across:**

- **`tests/test_change_detector.py` — `TestDetectTypeLevelChanges` (9 tests):** interface add/remove, enum add/remove, type alias add/remove, type replaced in single file, multiple type-level changes, no changes when identical
- **`tests/test_verifier.py` — `TestClaimVerifierTypeLevel*` (15 tests):** add/remove confirmed, add/remove contradicted, no changes / wrong name / wrong file unverifiable — for all three type-level kinds
- **`tests/test_terminal_reporter.py` — type-level labels and evidence (6 tests):** add interface/enum/type alias evidence lines, remove interface/enum/type alias evidence lines, claim descriptions
- **`tests/test_model.py` — `claims_to_changes` for new types (6 tests):** add/remove interface, enum, type alias mapping
- **`test_milestone1/test_milestone1_checkpoint.py` — type-level assertions (3 tests):** `test_type_level_symbols_captured` (pure-ts + pure-tsx), `test_type_level_change_detection` (pure-ts)
- **`test_ts_samples/test_phase1_comprehensive.py` — type-level positive tests:** interface, type alias, enum captured with correct SymbolType and line numbers (previously negative tests asserting NOT captured)
- **`test_ts_samples/test_phase1_comprehensive_tsx.py` — type-level positive tests:** same for TSX samples (previously negative tests)
- **`test_ts_samples/test_phase1_multiround_tsx.py` — type-level round check:** ButtonProps interface now captured

---

## File changes

### Modified files

| File | What changed |
|------|-------------|
| `nowreck/scanner/symbol_index.py` | `SymbolType`: +INTERFACE, +ENUM, +TYPE_ALIAS; `interfaces`/`enums`/`type_aliases` properties |
| `nowreck/scanner/_tree_sitter_helpers.py` | `collect_top_level_symbols`: collect `interface_declaration`, `enum_declaration`, `type_alias_declaration` |
| `nowreck/detector/change_detector.py` | `ChangeType`: +6; `_symbol_to_change` mapping for INTERFACE/ENUM/TYPE_ALIAS |
| `nowreck/claims/models.py` | `ClaimType`: +6; `CLAIM_TYPE_NAMES`: +6 entries |
| `nowreck/claims/parser.py` | `CLAIM_TYPE_NAMES` now imported from `models` (no local copy) |
| `nowreck/verifier/verifier.py` | `_SAME_CHANGE`: +6; `_OPPOSITE_CHANGE`: +6 |
| `nowreck/model/prompts.py` | `_CLAIM_TO_CHANGE_TYPE`: +6; `_CHANGE_LABELS`: +6; JSON schema updated to 13 claim types |
| `nowreck/reporter/terminal_reporter.py` | `_CLAIM_TYPE_LABELS`: +6; `_CHANGE_TYPE_LABELS`: +6; evidence-line builders for new kinds |
| `test_milestone1/repos/pure-ts/src/models.ts` | Added interface (`UserProfile`), enum (`Role`), type alias (`UserStatus`) |
| `test_milestone1/repos/pure-tsx/src/models.tsx` | Added enum (`ViewMode`), type alias (`SortOrder`); `UserProps` interface already present |
| `test_milestone1/test_milestone1_checkpoint.py` | New `test_type_level_symbols_captured`, `test_type_level_change_detection`; pure-tsx `test_type_level_symbols_captured` |
| `tests/test_change_detector.py` | `TestDetectTypeLevelChanges` class (9 tests); `test_values_are_distinct` updated to `len(ChangeType)` |
| `tests/test_verifier.py` | `TestClaimVerifierTypeLevelConfirmed` (6), `TestClaimVerifierTypeLevelContradicted` (6), `TestClaimVerifierTypeLevelUnverifiable` (3) |
| `tests/test_terminal_reporter.py` | Type-level evidence line tests, claim description tests |
| `tests/test_model.py` | `test_claims_to_changes_add_interface`, `remove_interface`, `add_enum`, `remove_enum`, `add_type_alias`, `remove_type_alias`, `test_prompt_renders_interface_change` |
| `test_ts_samples/test_phase1_comprehensive.py` | Negative interface/type/enum tests → positive (now captured); added SymbolType + line number assertions |
| `test_ts_samples/test_phase1_comprehensive_tsx.py` | Negative interface/type/enum tests → positive (now captured); added SymbolType assertions |
| `test_ts_samples/test_phase1_multiround_tsx.py` | `ButtonProps` interface now captured |
| `test_ts_samples/edge_types_only.ts` | Comment updated: negative test → positive test since v0.8.0 |

### Unchanged

- `nowreck/scanner/typescript_scanner.py` — **0 changes** (helpers are grammar-agnostic)
- `nowreck/scanner/repository_scanner.py` — **0 changes**
- `nowreck/scanner/javascript_scanner.py` — **0 changes**
- `nowreck/picker.py`, CLI, JSON schema structure — **0 changes**
- `.ts`/`.tsx`/`.js`/`.py` existing scanning behaviour — **byte-identical** (hard gate)
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
# → nowreck 0.8.0
```

---

## Claim types: 7 → 13

| Previous (7) | v0.8.0 adds (6) |
|-------------|-----------------|
| ADD_FUNCTION | ADD_INTERFACE |
| REMOVE_FUNCTION | REMOVE_INTERFACE |
| ADD_CLASS | ADD_ENUM |
| REMOVE_CLASS | REMOVE_ENUM |
| FILE_CREATED | ADD_TYPE_ALIAS |
| FILE_DELETED | REMOVE_TYPE_ALIAS |
| CALLS_FUNCTION | |

The `type` field in the JSON output gains six new allowed string values. Every existing value and field is unchanged. Additive, not breaking — old consumers keep working.

---

## Definition of Done ✅

1. A `.ts`/`.tsx` file with interfaces, enums, and type aliases scans to the correct `SymbolType`s and line numbers — verified by hand against the source — and `nowreck fix --pre <empty> --post <repo>` detects the expected `ADD_INTERFACE` / `ADD_ENUM` / `ADD_TYPE_ALIAS` changes matching reality.
2. `.ts`/`.tsx`/`.js`/`.py` repos produce output **byte-identical** to v0.7.0 for all previously-supported symbols.
3. The full existing test battery passes, plus the new type-level suites and assertions.
4. ruff: 0 issues, basedpyright: 0 errors.
5. Live DoD test (real model, induced false type-level claim) passes at release time with the user's key.

**Result (verified live):**

Ran the real CLI against the pure-ts milestone repo (empty pre → post). 3 files scanned, 19 symbols detected (including `UserProfile` as INTERFACE, `Role` as ENUM, `UserStatus` as TYPE_ALIAS). 25 changes detected, all matching reality.

Ran the real CLI against the pure-tsx milestone repo (empty pre → post). 3 files scanned, 17 symbols detected (including `UserProps` as INTERFACE, `ViewMode` as ENUM, `SortOrder` as TYPE_ALIAS). 23 changes detected, all matching reality.

Regression gate: pure-js (16 symbols, 22 changes) and pure-python (16 symbols, 30 changes) produce output byte-identical to v0.7.0 — zero type-level symbols (as expected for non-TS/TSX grammars).

**Live DoD (real model, user's key):** Pending — requires running the live hallucination-catch test with an induced false type-level claim (e.g. `ADD_INTERFACE` for a symbol that doesn't exist) at release time.

---

## What's next

The roadmap remains focused on narrow, testable increments, each with its own scope document and phase-by-phase build discipline.

- `explanation` field on claims — model + prompt change (README documents it, the `Claim` model doesn't have it yet) — deferred from v6
- Scan-summary expansion in verbose mode (per-language file counts) — deferred from v6
- TS polish (from v5): abstract methods, constructor parameter properties, decorators — separate polish increment
- Interface method signatures / enum members as symbols — polish increment, not done yet
- Python type-level capture — Python's `Enum`/`TypeAlias`/`TypedDict` mapping needs its own design conversation
- Rust + Go language support 🗓 *(planned for v0.9.0 — see `docs/nowreck-v9-scope.md`)*
- Additional model providers (Anthropic, Gemini)
- Caching for large repositories
- CI/CD integration
