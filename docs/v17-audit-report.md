# v0.17.0 Phase 0 — Differential Audit Report

**Status:** COMPLETE — audit infrastructure built, first audit executed, every
divergence classified, Phase 1 fix list frozen.

The audit compares a deliberately dumb regex checker
(`tests/helpers/differential.py`) against the **real production pipeline**
(`RepositoryScanner` → `build_symbol_index` → `ChangeDetector._extract_calls`)
over 60 authored corpus files (12 per language × 5 languages). Every divergence
between the two is either a fixed checker bug or a classified finding. The
checker and the audit test are permanent — they run in the main suite forever,
for all 9 languages by the end of v17.

---

## 1. Performance baseline (Phase 6 gate reference)

Recorded at Phase 0 start, before any infrastructure landed:

| Snapshot | Result | Wall-clock |
|---|---|---|
| Baseline (Phase 0 start, 1004 tests) | `1004 passed` | **29.74 s** |
| Phase 0 complete (1068 tests) | `1068 passed` | 33.67 s |

The Phase 6 `> 2× baseline = fail` gate uses **29.74 s** as its reference
number.

---

## 2. Infrastructure delivered

| Artifact | What it is |
|---|---|
| `tests/helpers/differential.py` | 5-language regex checker: symbol extraction + called-name extraction, keyword sets, per-language caller-scope masks, string/comment/macro/template strippers |
| `tests/differential_corpus/<lang>/` | 12 files × 5 languages, each probing named audit dimensions (basic/classes/async/closures/decorators/errors/realworld/edge_strings/edge_calls/edge_formatting/inheritance/generics/...) |
| `tests/test_differential_audit.py` | 64 permanent tests: per-file checker-vs-parser parity, map hygiene (no stale keys, no empty justifications), minimum corpus size, parse-clean enforcement |
| `pyproject.toml` | `[tool.ruff] exclude = ["tests/differential_corpus/**"]` — the corpus deliberately contains formatting variety (the audit dimension under test), so it is carved out of check/format; the checker and tests themselves stay lint-clean |
| `tests/helpers/__init__.py` | Makes `tests/helpers` a package so the checker is importable |

**Ground truth:** the parser side runs the real scanners end-to-end per corpus
directory (no mocks, no re-implementations). A corpus file that fails to parse
fails the audit (`assert scan.failure_count == 0`).

---

## 3. Findings — REAL GAPS (Phase 1 fix list, frozen)

All three share one root cause: the JS/TS caller walker
(`collect_tree_sitter_callers` / `find_tree_sitter_calls_in_body`) only
collects **named** function-like nodes. Anonymous arrows in non-assignment
positions are skipped during body walks and never become callers, so every
call inside them is invisible to the parser — and therefore to every CHANGED /
CALL claim a user would expect.

| # | Gap | Evidence | Trigger |
|---|---|---|---|
| G1 | Calls inside anonymous arrows passed as call **arguments** | `realworld.js` `publish`: `this.enqueue(() => handler(payload))` — `handler` never emitted | checker-only `handler` |
| G2 | Calls inside anonymous arrows in **return position** | `realworld.js` `subscribe`: `return () => this.unsubscribe(event, handler)`; `realworld.ts` `on`: `return () => this.off(...)` — `unsubscribe` / `off` never emitted | checker-only `unsubscribe`, `off` |
| G3 | Calls inside **class-field arrow values** | `classes.js` probe: `incrementBy = (step) => this.increment(step)` — tree-sitter models class fields as `public_field_definition`, which the caller walker does not handle (only `variable_declarator` arrows are collected) — `increment` never emitted | checker-only `increment` |

Each is mapped in `EXPECTED_DIVERGENCES` with its justification and has its
catching corpus file committed. **Phase 1 must fix these with tests that would
have caught them** (standing rule since v16 P5). Design direction (to be
finalized in Phase 1): collect anonymous arrows as callers and attribute their
calls to the nearest enclosing *named* caller — the evidence sets are already
per-file name sets, so the fix is walker-scoped and cannot change claim
semantics.

---

## 4. Findings — parser boundaries verified (ACCEPTED EDGES, evidence-backed)

These are deliberate, now-evidenced boundaries the checker mirrors. Each was
verified against the real scanners, not assumed from docs:

| Boundary | Evidence | Consequence |
|---|---|---|
| **Rust macro arguments are a flat `token_tree`** | CST dump of `format!("{}:{}", self.prefix(), self.label())` → `identifier`, `string_literal`, `self`, `identifier`, `token_tree` — no `call_expression` nodes exist inside macro args | Calls inside any `name!(...)` are structurally invisible. Checker blanks macro invocations (incl. `macro_rules!` definitions). This explains `edge_calls.rs` `self.prefix()`/`self.label()` and `traits.rs` `self.draw()` |
| **JS/TS `new X(...)` never emitted** | Probe: `new Error(...)`, `new Counter(seed)`, `new Map()`, `new Service()`, `new EventBus(capacity)` all absent from parser output | `new_expression` is not a `call_expression`. Checker excludes constructor targets |
| **JS/TS receiver-is-a-call is precise** | Probe: `a[0].bar()` (subscript), `"s".upper()` (string), `(x).foo()` (paren expr), `({k:1}).baz()` (object literal), `registry.fetch()!.id()` (non-null assertion) are **all captured**; only `f().bar()` is excluded | The v16-era "closer-dot" rule (any `).`/`].`/quote excluded) was **wrong** — the checker over-excluded. Replaced with paren-group resolution: exclude only when the receiver is a genuine call expression |
| **JS/TS `super.x()` is CAPTURED (identifier form)** | `inheritance.js`: `super.speak()` emitted — `super` is a plain identifier, not a call; `super(name)` constructor call excluded (keyword) | The v17 scope's *hypothesis* (JS `super.x()` excluded by receiver-is-a-call) is disproven. The v16 scope table's `super().foo()` row (paren form — a genuine call receiver) stays correct and unchanged; this report does not supersede it |
| **JS/TS optional chains captured** | `obj?.chain()`, `config.db?.connect(uri)`, `store.get("a")?.get("b")` — first `get` captured, second excluded (receiver is a call) | Mirrored; continuation-line `.b()` chains resolved against the previous line's tail |
| **Rust pattern position is not a call** | `let Some((k, v)) = ...`, `if let Some(x) = ...`, `match` arm `Some(x) => ...` — patterns; `return Err(...)`, `Err(x)?` are calls | Checker excludes `Some/Ok/Err/None` after `let`/`match`/`=>` and before `=>` (arm arrow) |
| **Rust qualified/turbofish targets never emitted** | `Vec::<i64>::new()` probe added to `edge_calls.rs`; `std::f64::consts::PI` in `traits.rs` — neither emitted | `scoped_identifier`/generic-qualified targets are not `identifier`/`field_expression`. Checker's `(?<!:)` guard mirrors it |
| **Python decorator calls ARE captured** | `@retry(times=5)` emits `retry`, attributed to the decorated function (`_find_call_names` walks the `FunctionDef` subtree incl. `decorator_list`); bare `@timed` emits nothing | Checker's Python mask counts `@`-lines as call sites |
| **Go `type (...)` groups map like top-level specs** | `types.go`: `Alpha struct{...}` → CLASS, `Beta = string` → TYPE_ALIAS inside the group | Checker gained group-relative regexes |
| **Rust trait default methods are callers** | `traits.rs` `trait Drawable { fn describe(...) }` body is walked | Their calls are still subject to the macro boundary above |
| **Rust closures are walked (unlike JS arrows)** | `closures.rs` `b.1.cmp(&a.1)`, `traits.rs` `s.area()` inside closure args — captured | The Rust walker skips only `function_item`; closure bodies are attributed to the enclosing fn |
| **Go `).`-paren receivers captured** | `structs.rs` `(dx * dx + dy * dy).sqrt()` emitted | Paren-group resolution: `(` preceded by an operator is a grouped expression, not a call |

---

## 5. Checker bugs found and fixed during the audit

The audit's first run produced ~60 failing files. The systematic causes (all in
the checker — the parser was the ground truth):

1. **Module-level call over-capture** — calls at module level have no caller and
   are never emitted; the checker originally captured them everywhere. Fixed
   with per-line caller-scope masks (Python indentation stack; JS/TS/Rust/Go
   brace-depth + body-start columns).
2. **Go corpus files lacked trailing newlines** — tree-sitter-go requires a
   trailing newline at EOF (gofmt enforces this); `has_error` with a
   `(MISSING "source_file_token1")` node. Corpus fixed; the parse-clean
   assertion makes this a permanent test.
3. **JS/TS keyword list bugs** — `get`/`set`/`from` are ordinary method names
   (`obj.get(x)`, `static from(seed)`) and were wrongly excluded; `as` stays a
   keyword in TS (`x as (T)` casts). Method-header regexes must not treat
   `if (x) {` control flow as methods.
4. **JS/TS method-header coverage** — async methods, static methods, generic
   methods (`on<T>(...)`), generic functions (`function f<T>(`), and
   multi-line signatures (`method(` + args on later lines + `) {`) were all
   missed; multi-line "methods" are distinguished from multi-line calls by
   paren balance + `;`-cancellation.
5. **TS arrow consts with return types** (`const f = (x: T): R => ...`) and
   typed consts (`const f: (x: T) => R = (x) => ...`) were not symbols.
6. **Template literal `${...}` interpolation** — calls inside `${this.foo()}`
   are real calls; the stripper was blanking them.
7. **Rust stripper bugs** — lifetimes (`'a`) were eaten as char literals
   (fixed with single-char char-literal matching); `r##"..."##` raw strings
   swallowed code when the closer-lookahead was `(?!\1#)` instead of `(?!\1)`;
   macro invocations now blanked (Section 4).
8. **Rust impl tracking** — `impl<K, V> X<K, V> where ... {` lost its pending
   state to a depth-0 reset; methods inside were missed.
9. **JS/TS symbol depth freeze** — a `continue` in the class-body branch
   skipped the depth update; every symbol after the first method in a class
   vanished (caught by re-running the full diff, not by unit-reading).
10. **Receiver rules** — closer-dot over-exclusion (Section 4) and
    indented leading-dot continuation lines (`.map(` on its own line).

The four below were found in the dedicated Phase 0 review pass. All are
checker-side; the parser was again the ground truth, confirmed by direct
probe, and each is pinned by corpus cases added in the same pass:

11. **Comment-inside-string ordering (JS/TS/Rust/Go)** — the first-pass
    strippers removed comments *before* strings, so a `//` inside a string
    (`const url = "https://x"`; `const n = call()`) started a line comment
    that swallowed the rest of the line and every call on it. Fixed by
    replacing the sequential substitutions with a **single left-to-right
    alternation regex** per language (block comment | line comment |
    template/raw string | string | char/rune): the leftmost match wins, so
    neither a comment marker inside a string nor a quote/backtick inside a
    comment can be misattributed. That same fix closed a second latent
    hazard the reordering exposed — a backtick inside a Go comment pairing
    with a backtick in later code and swallowing the lines between (caught
    by the new `commentMarkerInString` corpus case, which failed the audit
    until the tokenizer landed).
12. **Python f-string coverage** — only double-quoted single-line f-strings
    were interpolated; single-quoted (`f'{helper()}'`) and triple-quoted
    (`f"""{third()}"""`) forms fell through to whole-literal blanking, so
    their calls were invisible to the checker. Fixed with a single-quote
    branch in `_PY_FSTRING` plus a new `_PY_FTRIPLE` rule run before the
    plain triple-quoted rule. Parser-verified (it captures all three forms).
13. **`is_dunder_name` length parity** — the checker's mirror used `len > 4`
    while `_tree_sitter_helpers.is_dunder_name` uses `len >= 4`, so a
    four-character dunder name (`obj.____()`) was excluded by the parser but
    captured by the checker. Aligned to `>= 4`.
14. **Duplicate / shadowed definitions** — `_JS_METHOD` was defined twice
    (mask section + symbol section, byte-identical) and `_RS_FN` twice with
    *different* patterns (the later silently shadowing the earlier), so the
    "single source" comment was false and the two could drift. The
    `_JS_METHOD` duplicate was deleted (one shared definition); the Rust
    symbol-side pattern was renamed `_RS_FN_DECL` so the detection-only mask
    opener (`_RS_FN`) can never shadow it. The same pass removed a dead
    `_CALL_FILES_ATTR` map (defined, never referenced). A duplicate-assignment
    scan and an unused-name scan now both report zero hits.

**Documented checker limitations (accepted; the corpus avoids them):** JS/TS
regex literals are not stripped; an f-string with escaped literal braces
(`f"{{x}}"`) or a dict literal nested inside an interpolation falls back to
whole-literal blanking. Each is a checker limit, not a parser gap — the
parser handles the construct correctly.

---

## 6. Audit dimensions — coverage results

| Dimension | Result |
|---|---|
| Symbol extraction completeness | Nested functions/lambdas: not symbols (parser parity, verified). Getters/setters/static/async/generic methods: METHOD symbols. Arrow consts: FUNCTION. Class fields: not symbols. Rust trait methods/associated functions: not symbols (only `fn` items and impl methods). Go pointer/generic receivers: METHOD. `const f = function(){}`: not a symbol (parity). |
| Call-capture completeness | See Section 4 — super calls captured, constructors excluded, macros token-tree, turbofish excluded, patterns excluded, decorator calls captured, optional chains captured, receiver precision verified. |
| Hash normalization robustness | Not re-broken by any checker change; corpus formatting-variety files (`edge_formatting.*`) pass with identical symbol sets — the v16 pinned rows' spirit is preserved. (Body-hash level is outside the differential checker's scope by design — it compares symbols and calls, not hashes.) |
| Accepted-edges hygiene | Every Section 4 boundary is now written down with evidence — the v17 replacement for v16's §Accepted Edges, which stays true where it touches this audit. |
| Dead code / drift | `tests/helpers/pty_helper.py`: **zero importers** (repo-wide grep; 100 lines; PTY harness for `--interactive`, superseded by the tmux picker integration tests) → **Phase 1: delete**. Prompt drift: `SYSTEM_PROMPT` header claims "Python code repositories" (prompts.py:10) and the v10 claim list parenthesizes `(TS/TSX/Rust/Go)` (prompts.py:110) — both stale the moment a new language lands → updated in the language phase that introduces each language. |

---

## 7. Per-language roll-up

| Language | Corpus | Checker bugs found (Section 5) | REAL GAPs | Accepted edges verified (Section 4) |
|---|---|---|---|---|
| Python | 12 files | module-level over-capture; decorator `@name(...)` call sites | none | decorator calls captured; `super().m()` / `f().bar()` excluded (receiver-is-a-call); nested functions are not symbols (parity) |
| JavaScript | 12 files | `get`/`set`/`from` wrongly excluded; multi-line/async/static/generic method headers; template `${}` blanking; receiver-dot over-exclusion | **G2** (`realworld.js` `handler`, `unsubscribe`); **G3** (`classes.js` `increment`) | `new X()` excluded; `super.x()` captured; optional chains captured; subscript/string/paren/object-literal receivers captured |
| TypeScript | 12 files | `get`/`set`/`from`; generic methods + generic functions; arrow consts with return types; typed consts; class-body depth freeze | **G2** (`realworld.ts` `off`) | `as (T)` casts stay keywords; interface members are not symbols (parity); same call set as JS |
| Rust | 12 files | lifetimes eaten as char literals; `r##"..."##` raw-string closer; macro arguments not blanked; `impl … where … {` pending state; pattern-position `Some/Ok/Err`; leading-dot chain lines | none | macro args are a flat `token_tree`; turbofish/`::` targets excluded; closures walked; trait default methods are callers |
| Go | 12 files | trailing-newline-at-EOF parse requirement (corpus + permanent test); `type (...)` group form | none | pointer/generic receivers → METHOD; `).`-paren receivers captured |

Totals: **3 REAL GAPs** (all one JS/TS caller-walker class), **12 accepted
edges** evidence-verified, **14 checker defects fixed**, **60 corpus files**,
**64 permanent tests**.

---

## 8. Phase 1 fix list (frozen)

No new fixes enter Phase 1 without re-running the audit:

1. **G1 + G2**: anonymous arrows in argument/return position — collect as
   callers, attribute to nearest named caller. Tests: corpus files already
   exist (`realworld.js`, `realworld.ts`) — the map entries flip from REAL GAP
   to empty as the parser fix lands.
2. **G3**: class-field arrow values — extend the caller walker to
   `public_field_definition` arrow values. Test: `classes.js` `incrementBy`
   probe (committed).
3. **Delete `tests/helpers/pty_helper.py`** (dead code, Section 6).
4. **Tmux flake kill** — 10 consecutive green full-suite runs gate (scope
   requirement).

Everything else in this report is either a fixed checker bug (Section 5,
already green) or an accepted edge (Section 4, mirrored + documented).