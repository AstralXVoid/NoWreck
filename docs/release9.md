# NoWreck v0.9.0 — Rust + Go Language Support

**Release date:** August 2026
**Previous release:** v0.8.0 (Type-Level Claim Types)
**Focus:** Rust and Go language support via tree-sitter grammars. Two new scanner modules, extended repository scanner, change detector, and symbol index — all following the existing architecture pattern exactly. Zero new claim types, zero changes to the verification engine, reporter, or JSON schema.

---

## What's new in v0.9.0

### Rust scanning ✅

Rust source files (`.rs`) are now parsed with the `tree-sitter-rust` grammar. The scanner extracts:

```rust
fn add(a: i32, b: i32) -> i32 { a + b }           → FUNCTION "add"
pub fn connect(addr: &str) -> Result<()> { ... }   → FUNCTION "connect"
struct User { name: String, age: u32 }              → CLASS "User"
impl User { fn display(&self) { ... } }             → METHOD "display" (parent_class: "User")
trait Display { fn fmt(&self); }                    → INTERFACE "Display"
impl Display for User { fn fmt(&self) { ... } }    → METHOD "fmt" (parent_class: "User")
enum Role { Admin, Member, Guest }                  → ENUM "Role"
type Result<T> = std::result::Result<T, Error>      → TYPE_ALIAS "Result"
```

- `pub`/`pub(crate)` visibility modifiers are unwrapped (like `export` in TS)
- `mod` declarations are skipped (structural namespaces, not symbols)
- `impl` block methods are extracted with `parent_class` set to the impl target
- `trait` methods are NOT extracted as METHOD symbols (same one-level-deep philosophy)
- Macro invocations (`println!`, `format!`) are NOT treated as function calls

### Go scanning ✅

Go source files (`.go`) are parsed with the `tree-sitter-go` grammar:

```go
func Add(a, b int) int { return a + b }            → FUNCTION "Add"
func (u *User) Display() { fmt.Println(u.Name) }   → METHOD "Display" (parent_class: "User")
type User struct { Name string; Age int }           → CLASS "User"
type Reader interface { Read(p []byte) (n int, err error) }  → INTERFACE "Reader"
type Status string                                  → TYPE_ALIAS "Status"
```

- `type X struct` → CLASS (structs are Go's primary data-carrying type)
- `type X interface` → INTERFACE (method sets)
- `type X string` → TYPE_ALIAS (type renames)
- Receiver types extracted from method declarations for `parent_class`
- `const` and `var` declarations are skipped (value bindings, not symbols)
- Selector expressions (`fmt.Println()`) are NOT treated as simple function calls

### Architecture

Both scanners follow the exact same pattern as the TypeScript scanner:

1. Lazy-load grammar on first call (per-process singleton)
2. Parse file with tree-sitter
3. Walk CST, collect top-level declarations
4. Return `Symbol` objects compatible with the shared pipeline
5. Call detection via `call_expression` with simple `identifier` targets

The repository scanner discovers `.rs` and `.go` files alongside `.py`, `.js`, `.ts`, and `.tsx`. The symbol index, change detector, and verification engine all work unchanged — they see `Symbol` objects and `DetectedChange` objects, never knowing which language produced them.

---

## Scope boundary

- `.py`/`.js`/`.ts`/`.tsx` existing behaviour — **byte-identical to v0.8.0** (hard gate)
- Same 13 claim types — Rust/Go use the existing types
- No new SymbolType, ChangeType, or ClaimType members
- Verifier, reporter, prompts — zero changes
- JSON schema — zero changes (additive language support)
- **2 new dependencies:** `tree-sitter-rust`, `tree-sitter-go`

---

## Test suite

| Suite | v0.8.0 | v0.9.0 | Growth |
|-------|--------|--------|--------|
| pytest (project unit tests) | 453 | **453** | — |
| Milestone 1 checkpoint | 60 tests | **80 tests** | **+20** |
| Change detector | 57 tests | 57 tests | — |
| Verifier | 55 tests | 55 tests | — |
| Terminal reporter | 45 tests | 45 tests | — |
| ruff | 0 issues | **0 issues** | — |
| basedpyright | 0 errors | **0 errors** | — |

**+20 new milestone tests:**

- **`TestPureRustRepo` (9 tests):** file discovery, greeter symbols, calculator class+methods, models types (struct, trait, enum, type alias), symbol index counts, call detection, file changes, no-change determinism, cross-run determinism
- **`TestPureGoRepo` (9 tests):** file discovery, greeter symbols, calculator class+methods, models types (struct, interface, type alias), symbol index counts, call detection, file changes, no-change determinism, cross-run determinism
- **`TestAllReposDeterministic` extended:** Rust and Go repos added to cross-repo determinism parametrize (7 repos total)

---

## File changes

### New files

| File | What it covers |
|------|---------------|
| `nowreck/scanner/rust_scanner.py` | Rust scanner (lazy grammar, `scan_rust_file`, `scan_rust_calls`) |
| `nowreck/scanner/go_scanner.py` | Go scanner (lazy grammar, `scan_go_file`, `scan_go_calls`) |
| `test_milestone1/repos/pure-rust/src/` | Milestone repo: `greeter.rs`, `calculator.rs`, `models.rs` |
| `test_milestone1/repos/pure-go/src/` | Milestone repo: `greeter.go`, `calculator.go`, `models.go` |
| `docs/nowreck-v9-scope.md` | Full scope document |
| `docs/release9.md` | This release notes file |

### Modified files

| File | What changed |
|------|-------------|
| `nowreck/scanner/repository_scanner.py` | Added `rust_files`/`go_files` to `ScanResult`; added `_discover_rust_files`, `_discover_go_files`, `_parse_rust_file`, `_parse_go_file` |
| `nowreck/scanner/symbol_index.py` | `build_symbol_index` now processes `rust_files` and `go_files` |
| `nowreck/detector/change_detector.py` | `_detect_file_changes` includes Rust/Go files; `_extract_calls` includes Rust/Go call detection |
| `test_milestone1/test_milestone1_checkpoint.py` | `TestPureRustRepo`, `TestPureGoRepo` classes; extended `TestAllReposDeterministic` |
| `pyproject.toml` | Dependencies: +`tree-sitter-rust>=0.23`, +`tree-sitter-go>=0.25` |

### Unchanged

- `nowreck/scanner/javascript_scanner.py` — **0 changes**
- `nowreck/scanner/typescript_scanner.py` — **0 changes**
- `nowreck/scanner/_tree_sitter_helpers.py` — **0 changes**
- `nowreck/claims/` — **0 changes**
- `nowreck/verifier/verifier.py` — **0 changes**
- `nowreck/model/prompts.py` — **0 changes**
- `nowreck/reporter/terminal_reporter.py` — **0 changes** (version bump only)
- `nowreck/picker.py`, CLI — **0 changes**
- JSON output schema — **0 changes**
- `.py`/`.js`/`.ts`/`.tsx` existing scanning behaviour — **byte-identical** (hard gate)

---

## Installing / upgrading

```bash
pipx install .    # fresh install from repo
pip install -e .  # or editable install
```

Requires Python 3.10+. No new system dependencies (tree-sitter grammars ship as Python wheels).

```bash
nowreck --version
# → nowreck 0.9.0
```

---

## Definition of Done ✅

1. A `.rs` file with functions, structs, impl methods, traits, enums, and type aliases scans to the correct `SymbolType`s and line numbers — verified by hand — and `nowreck fix --pre <empty> --post <pure-rust>` detects expected changes matching reality.
2. A `.go` file with functions, methods, structs, interfaces, and type aliases scans to the correct `SymbolType`s and line numbers — verified by hand — and `nowreck fix --pre <empty> --post <pure-go>` detects expected changes matching reality.
3. `.py`/`.js`/`.ts`/`.tsx` repos produce output **byte-identical** to v0.8.0 for all previously-supported symbols.
4. The full existing test battery passes, plus the new Rust/Go milestone tests.
5. ruff: 0 issues, basedpyright: 0 errors.

**Result (verified):**

- Pure-Rust milestone repo: 3 files, 19 symbols detected (functions, structs, methods, trait, enum, type alias). CLI detects all 19 as ADD_FUNCTION/ADD_CLASS/ADD_INTERFACE/ADD_ENUM/ADD_TYPE_ALIAS changes.
- Pure-Go milestone repo: 3 files, 18 symbols detected (functions, methods, structs, interface, type alias). CLI detects all 18 as ADD_FUNCTION/ADD_CLASS/ADD_INTERFACE/ADD_TYPE_ALIAS changes.
- All existing repos (pure-python, pure-js, pure-ts, pure-tsx, mixed) produce identical output to v0.8.0.
- 453 pytest tests pass, 80 milestone tests pass, ruff clean, basedpyright clean.

---

## What's next

The roadmap remains focused on narrow, testable increments, each with its own scope document and phase-by-phase build discipline.

- `explanation` field on claims — model + prompt change (README documents it, the `Claim` model doesn't have it yet) — deferred from v6
- Scan-summary expansion in verbose mode (per-language file counts) — deferred from v6
- TS polish (from v5): abstract methods, constructor parameter properties, decorators — separate polish increment
- Interface method signatures / enum members as symbols — polish increment, not done yet
- Python type-level capture — Python's `Enum`/`TypeAlias`/`TypedDict` mapping needs its own design conversation
- Independent verification architecture (fix Prompt Mode circularity) 🗓 *(planned for v0.10.0 — see `docs/nowreck-v10-scope.md`)*
- Additional model providers (Anthropic, Gemini)
- Caching for large repositories
- CI/CD integration
