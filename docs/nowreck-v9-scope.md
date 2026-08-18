# NoWreck — v9 Scope (Rust + Go Language Support)

**Status:** Draft. Local development only — not published, not merged into the
public repo, until proven and deliberately released. Same discipline as v2
through v8.

## Principle

Same rule as every prior increment: one small thing at a time, proven before
expanding. v8 (interface/enum/type-alias claim types for TS/TSX) is done and
its Definition of Done is fulfilled. v9 is **two new language families — Rust
and Go** — scanned via tree-sitter grammars already available on PyPI.

Rust and Go are both statically-typed, compiled languages with strong
structural conventions (functions, structs, impl blocks, traits, interfaces).
The scanner already knows how to walk tree-sitter CSTs and extract symbols —
v9 extends this to two new grammars with zero changes to the existing
pipeline.

## What this increment actually is

Today the pipeline knows three language families: Python (ast), JavaScript
(tree-sitter), and TypeScript/TSX (tree-sitter). Each family has its own
scanner module that produces `Symbol` objects fed into the shared pipeline.
v9 adds:

1. **Rust scanning** — `rust_scanner.py` using `tree-sitter-rust` (PyPI)
2. **Go scanning** — `go_scanner.py` using `tree-sitter-go` (PyPI)
3. **Repository discovery** — `.rs` and `.go` files discovered and dispatched
4. **ScanResult expansion** — new `rust_files` and `go_files` fields
5. **Symbol mapping** — Rust/Go constructs mapped to existing `SymbolType`s
6. **No new claim types** — Rust/Go use the existing 13 claim types

### What gets captured

**Rust (.rs):**

```rust
fn add(a: i32, b: i32) -> i32 { a + b }           → FUNCTION "add"
pub fn connect(addr: &str) -> Result<()> { ... }   → FUNCTION "connect"
struct User { name: String, age: u32 }              → CLASS "User"
impl User { fn display(&self) { ... } }             → METHOD "display" (parent_class: "User")
trait Display { fn fmt(&self); }                    → INTERFACE "Display"
impl Display for User { fn fmt(&self) { ... } }    → METHOD "fmt" (parent_class: "User")
enum Role { Admin, Member, Guest }                  → ENUM "Role"  (runtime enum, not type-level)
type Result<T> = std::result::Result<T, Error>      → TYPE_ALIAS "Result"
mod auth { ... }                                    → (skipped — modules are structural, not symbols)
pub struct Config { ... }                           → CLASS "Config" (pub is unwrapped)
```

**Go (.go):**

```go
func Add(a, b int) int { return a + b }            → FUNCTION "Add"
func (u *User) Display() { fmt.Println(u.Name) }   → METHOD "Display" (parent_class: "User")
type User struct { Name string; Age int }           → CLASS "User"
type Reader interface { Read(p []byte) (n int, err error) }  → INTERFACE "Reader"
type Status string                                  → TYPE_ALIAS "Status"
const MaxRetries = 3                                → (skipped — constants are not symbols)
var DefaultTimeout = 30 * time.Second               → (skipped — variables are not symbols)
```

### What stays unchanged

- **Existing 5 languages** (Python, JS, TS, TSX, mixed) — byte-identical
- **13 claim types** — Rust/Go use the same types (ADD_FUNCTION, ADD_CLASS, etc.)
- **SymbolType** — no new members needed (FUNCTION, CLASS, METHOD, INTERFACE, ENUM, TYPE_ALIAS already cover Rust/Go constructs)
- **ChangeType/ClaimType** — no new members (existing 13 map to Rust/Go changes)
- **Verifier, reporter, prompts** — zero changes (symbol-to-change mapping is type-agnostic)
- **JSON schema** — zero changes (additive language support, same claim types)
- **Dependencies** — 2 new packages only (`tree-sitter-rust`, `tree-sitter-go`)

### Design decisions

**Rust `impl` blocks → METHOD with parent_class.** Rust doesn't have "methods" in the OOP sense — `impl` blocks attach functions to a type. But from the symbol perspective, `impl User { fn display() }` is equivalent to `class User { display() }`. The scanner treats `impl` block methods the same as class methods: `SymbolType.METHOD` with `parent_class` set to the impl target.

**Rust traits → INTERFACE.** A `trait` defines a contract that types implement — structurally equivalent to a TypeScript `interface` or Java `interface`. Mapped to `SymbolType.INTERFACE`.

**Rust enums → ENUM.** Rust's `enum` is a sum type (runtime), not a TypeScript type-level enum. But from the symbol perspective, it's still a named declaration that can be added/removed. Mapped to `SymbolType.ENUM`. A model claiming `ADD_ENUM Role` against a `.rs` file is verifiable.

**Go `type X struct` → CLASS.** Go structs are the primary data-carrying type — equivalent to classes without inheritance. Mapped to `SymbolType.CLASS`.

**Go `type X interface` → INTERFACE.** Go interfaces define method sets — equivalent to TypeScript interfaces. Mapped to `SymbolType.INTERFACE`.

**Go `type X string` → TYPE_ALIAS.** Go type aliases/newtypes are simple type renames. Mapped to `SymbolType.TYPE_ALIAS`.

**Go constants and variables → NOT captured.** Same philosophy as other languages: only structural declarations (functions, types, methods) are symbols. `const` and `var` are value bindings, not symbols.

**Rust modules → NOT captured.** `mod` declarations are structural namespaces, not symbols. They don't have the same "add/remove a function" semantics.

**Rust `pub`/`pub(crate)` → unwrapped.** Visibility modifiers are like `export` — they don't change the symbol's identity.

**Go `func (receiver)` receiver types → parent_class.** The receiver type is extracted and stored as `parent_class`, same as Rust impl methods.

## Phases

### Phase 1: Scanner — Rust

- Create `nowreck/scanner/rust_scanner.py` following the `typescript_scanner.py` pattern
- Lazy-load `tree-sitter-rust` grammar
- Handle CST node types: `function_item`, `struct_item`, `impl_item`, `trait_item`, `enum_item`, `type_item`
- Extract methods from `impl_item` and `trait_item` bodies
- Hand-build `test_rust_samples/` with sample `.rs` files (functions, structs, impls, traits, enums, type aliases, pub variants)
- Verify symbols + line numbers by hand before any tests

**Human checkpoint: stop & report.**

### Phase 2: Scanner — Go

- Create `nowreck/scanner/go_scanner.py` following the same pattern
- Lazy-load `tree-sitter-go` grammar
- Handle CST node types: `function_declaration`, `method_declaration`, `type_declaration` (with `struct_type` / `interface_type` / `type`), `const_declaration`, `var_declaration` (skip last two)
- Extract receiver types from `method_declaration` for `parent_class`
- Hand-build `test_go_samples/` with sample `.go` files
- Verify symbols + line numbers by hand

**Human checkpoint: stop & report.**

### Phase 3: Repository scanner + ScanResult

- Add `rust_files` and `go_files` fields to `ScanResult`
- Add `_discover_rust_files()` and `_discover_go_files()` to `RepositoryScanner`
- Add `_parse_rust_file()` and `_parse_go_file()` dispatchers
- Update `success_count` to include new fields
- Create milestone repos: `pure-rust/src/` (greeter, calculator, models) and `pure-go/src/` (greeter, calculator, models)

**Human checkpoint: stop & report.**

### Phase 4: Tests + Milestone checkpoint

- `test_rust_samples/`: comprehensive Rust suite (functions, structs, impls, traits, enums, type aliases, pub variants, edge cases)
- `test_go_samples/`: comprehensive Go suite (functions, methods, structs, interfaces, type aliases, edge cases)
- `tests/test_change_detector.py`: Rust/Go change detection (add/remove function, class, method, etc.)
- `test_milestone1/test_milestone1_checkpoint.py`: new `TestPureRustRepo` and `TestPureGoRepo` classes
- Cross-repo determinism tests extended to include Rust and Go

**Human checkpoint: stop & report.**

### Phase 5: Milestone checkpoint + release

- Run the real CLI on pure-rust and pure-go repos with real pre/post changes
- Confirm existing 5 language families produce output identical to v0.8.0 (regression gate)
- Live DoD test (real model, induced false claim against Rust/Go repo)
- Re-run full battery + ruff + basedpyright; write `docs/release9.md`
- Update README roadmap (Rust + Go → ✅ done in v0.9.0)

**Human checkpoint: stop & report.**

## Claim types: unchanged (13)

Rust and Go use the same 13 claim types as TS/TSX/JS/Python:

| Claim Type | Rust example | Go example |
|------------|-------------|------------|
| ADD_FUNCTION | `fn add()` added | `func Add()` added |
| REMOVE_FUNCTION | `fn add()` removed | `func Add()` removed |
| ADD_CLASS | `struct User` added | `type User struct` added |
| REMOVE_CLASS | `struct User` removed | `type User struct` removed |
| ADD_INTERFACE | `trait Display` added | `type Reader interface` added |
| REMOVE_INTERFACE | `trait Display` removed | `type Reader interface` removed |
| ADD_ENUM | `enum Role` added | (rare — Go doesn't have enums) |
| REMOVE_ENUM | `enum Role` removed | |
| ADD_TYPE_ALIAS | `type Result<T>` added | `type Status string` added |
| REMOVE_TYPE_ALIAS | `type Result<T>` removed | `type Status string` removed |
| FILE_CREATED | new `.rs`/`.go` file | |
| FILE_DELETED | deleted `.rs`/`.go` file | |
| CALLS_FUNCTION | `add()` calls `compute()` | `Add()` calls `Compute()` |

## Dependencies

**2 new packages:**

```toml
"tree-sitter-rust>=0.23",
"tree-sitter-go>=0.25",
```

No other new dependencies. The existing `tree-sitter>=0.26` core is shared.

## Files (new / modified)

| File | What it covers |
|------|---------------|
| `nowreck/scanner/rust_scanner.py` | **New** — Rust scanner (lazy grammar, `scan_rust_file`, `scan_rust_calls`) |
| `nowreck/scanner/go_scanner.py` | **New** — Go scanner (lazy grammar, `scan_go_file`, `scan_go_calls`) |
| `nowreck/scanner/repository_scanner.py` | Add `rust_files`/`go_files` to `ScanResult`; add discovery + parse methods |
| `nowreck/scanner/_tree_sitter_helpers.py` | Add Rust/Go node type handling to `collect_top_level_symbols` and call helpers |
| `test_milestone1/repos/pure-rust/src/` | **New** — milestone repo: `greeter.rs`, `calculator.rs`, `models.rs` |
| `test_milestone1/repos/pure-go/src/` | **New** — milestone repo: `greeter.go`, `calculator.go`, `models.go` |
| `test_milestone1/test_milestone1_checkpoint.py` | New `TestPureRustRepo`, `TestPureGoRepo`; extended determinism |
| `test_rust_samples/` | **New** — comprehensive Rust test suite |
| `test_go_samples/` | **New** — comprehensive Go test suite |
| `tests/test_change_detector.py` | Rust/Go change detection tests |
| `pyproject.toml` | Dependencies: +`tree-sitter-rust`, +`tree-sitter-go` |
| `docs/release9.md` | **New** — release notes |

## Unchanged

- `nowreck/scanner/python_scanner.py` (if exists) / Python scanning — **0 changes**
- `nowreck/scanner/javascript_scanner.py` — **0 changes**
- `nowreck/scanner/typescript_scanner.py` — **0 changes**
- `nowreck/claims/` — **0 changes** (same 13 claim types)
- `nowreck/detector/change_detector.py` — **0 changes** (symbol-to-change mapping is type-agnostic)
- `nowreck/verifier/verifier.py` — **0 changes**
- `nowreck/model/prompts.py` — **0 changes**
- `nowreck/reporter/terminal_reporter.py` — **0 changes**
- `nowreck/picker.py`, CLI — **0 changes**
- JSON output schema — **0 changes**
- `.py`/`.js`/`.ts`/`.tsx` existing scanning behaviour — **byte-identical** (hard gate)

## Definition of done

1. A `.rs` file with functions, structs, impl methods, traits, enums, and type aliases scans to the correct `SymbolType`s and line numbers — verified by hand — and `nowreck fix --pre <empty> --post <pure-rust>` detects expected changes matching reality.
2. A `.go` file with functions, methods, structs, interfaces, and type aliases scans to the correct `SymbolType`s and line numbers — verified by hand — and `nowreck fix --pre <empty> --post <pure-go>` detects expected changes matching reality.
3. `.py`/`.js`/`.ts`/`.tsx` repos produce output **byte-identical** to v0.8.0 for all previously-supported symbols.
4. The full existing test battery passes, plus the new Rust/Go sample suites and milestone-checkpoint assertions.
5. ruff: 0 issues, basedpyright: 0 errors.
6. Live DoD test (real model, induced false claim against Rust/Go repo) passes at release time.

## Explicitly not a roadmap

This covers exactly one thing — Rust and Go language support via tree-sitter, same
phase-by-phase discipline, human-checked at every step. When it's done and
proven, the next increment gets its own equally narrow scoping conversation.
