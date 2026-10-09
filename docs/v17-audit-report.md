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
| **JS/TS class-field non-function initialisers are not calls** | Probe (Phase 1 review): `class A { n: number = compute(); }` → the parser emits nothing for `compute` and the checker independently agrees (both empty), unlike the arrow form of the same field (G3), which both capture | A class-field initialiser is class-shell content with no caller — the class-body form of the "a call must have a caller" boundary the corpus already pins for module-level statements. The asymmetry (arrow field = caller, expression field = not) is deliberate; pinned in `tests/test_call_edges.py` so it is visible rather than mistaken for a missed capture |

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
| Dead code / drift | `tests/helpers/pty_helper.py`: **zero importers** (repo-wide grep; PTY harness for `--interactive`, superseded by the tmux picker integration tests) → **deleted in Phase 1**. Prompt drift: `SYSTEM_PROMPT` header claims "Python code repositories" (prompts.py:10) and the v10 claim list parenthesizes `(TS/TSX/Rust/Go)` (prompts.py:110) — both stale the moment a new language lands → updated in the language phase that introduces each language. |

---

## 7. Per-language roll-up

| Language | Corpus | Checker bugs found (Section 5) | REAL GAPs | Accepted edges verified (Section 4) |
|---|---|---|---|---|
| Python | 12 files | module-level over-capture; decorator `@name(...)` call sites | none | decorator calls captured; `super().m()` / `f().bar()` excluded (receiver-is-a-call); nested functions are not symbols (parity) |
| JavaScript | 12 files | `get`/`set`/`from` wrongly excluded; multi-line/async/static/generic method headers; template `${}` blanking; receiver-dot over-exclusion | ~~**G2** (`realworld.js` `handler`, `unsubscribe`); **G3** (`classes.js` `increment`)~~ → **fixed in Phase 1** | `new X()` excluded; `super.x()` captured; optional chains captured; subscript/string/paren/object-literal receivers captured |
| TypeScript | 12 files | `get`/`set`/`from`; generic methods + generic functions; arrow consts with return types; typed consts; class-body depth freeze | ~~**G2** (`realworld.ts` `off`)~~ → **fixed in Phase 1** | `as (T)` casts stay keywords; interface members are not symbols (parity); same call set as JS |
| Rust | 12 files | lifetimes eaten as char literals; `r##"..."##` raw-string closer; macro arguments not blanked; `impl … where … {` pending state; pattern-position `Some/Ok/Err`; leading-dot chain lines | none | macro args are a flat `token_tree`; turbofish/`::` targets excluded; closures walked; trait default methods are callers |
| Go | 12 files | trailing-newline-at-EOF parse requirement (corpus + permanent test); `type (...)` group form | none | pointer/generic receivers → METHOD; `).`-paren receivers captured |

Totals: **3 REAL GAPs** (all one JS/TS caller-walker class), **13 accepted
edges** evidence-verified, **14 checker defects fixed**, **60 corpus files**,
**64 permanent tests**.

---

## 8. Phase 1 fix list (frozen)

No new fixes entered Phase 1 without re-running the audit. All four items are
closed — the resolution log is Section 9:

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

---

## 9. Phase 1 remediation — closed

### Production fix: G1 + G2 + G3 (one root cause)

The three REAL GAPs were one defect in the shared call walker
(`nowreck/scanner/_tree_sitter_helpers.py`), not three: the walker treated
*every* function-valued node as caller-owning, so (a) an anonymous arrow
(`fn(() => x())`, `return () => y()`) was skipped entirely — no caller to
attribute its calls to — and (b) JS/TS class-field arrows were never
collected as callers at all.

| Change | Effect |
|---|---|
| `_FUNCTION_VALUE_TYPES` / `_INITIALISER_NODE_TYPES` / `_NAMED_FUNCTION_TYPES` module constants | One named place for the node sets, shared by the collector and the body walker (the old logic duplicated the type tuples in both functions — the drift that hid G3) |
| `_function_valued_initialiser()` | Recognises `variable_declarator`, JS `field_definition`, TS `public_field_definition` — unwrapping parens — and returns `(name_node, function_node)` |
| `_has_own_caller()` | A caller owns its body only when it is genuinely named: named declarations/methods always; declarators and class fields only when their value is a function. An anonymous function expression does **not** — its calls belong to the nearest *enclosing named* caller |
| `find_tree_sitter_calls_in_body()` now skips only `_has_own_caller(child)` nodes | Anonymous-arrow calls are no longer dropped (G1/G2) and class-field arrow bodies are walked by their own collector entry (G3) |

Net effect: JS `realworld.js` (`handler`, `unsubscribe`), TS `realworld.ts`
(`off`) and JS `classes.js` (`increment`) all agree with the checker, so
`EXPECTED_DIVERGENCES` is now **empty** — with the map-hygiene test
(`test_map_keys_are_live_divergences`) keeping it honest, a fixed gap's entry
must be deleted rather than left to rot.

**Tests:** the corpus files above are the catching tests (they failed before
the fix, pass after); 23 additional pinning tests in
`tests/test_call_edges.py` freeze every documented boundary from Section 4 so
a boundary cannot drift silently — including one boundary the audit had not
probed and Phase 1's review surfaced (class-field initialisers whose value is
not a function: not a caller, on both checker and parser, Section 4). Neither the corpus nor the pins were
written to match the implementation — every assertion was verified against
the parsers first.

### Flake kill: `TestPickerTerminal` (the named Phase 1 item)

Root cause is a **race with process start-up**, not a fixed render delay: the
child `nowreck --interactive` interpreter needs ~7s (measured up to 8.4s under
load) just to import and draw the menu, so the previous fixed 15s deadline
had ~1.8x headroom — guaranteed to lose the race when the box is loaded (the
full suite itself ranged 19s → 103s in these runs). The old loop also had two
fast-failure paths: a `tmux` subprocess `TimeoutExpired` escaped as a test
*error*, and the wait returned the instant the expected token appeared.

| Change | Why |
|---|---|
| `_PANE_TIMEOUT` 30s (was 15s) | Sized to the measured start-up, not a guess |
| `_capture_pane()` tolerates `TimeoutExpired` → `""` | A slow `tmux` under load must mean "keep waiting", never an error |
| `_session_exists()` treats `TimeoutExpired` as "still alive" | Conservative answer: neither fails a test nor ends a wait early |
| `_wait_for_output_once()` stops early when the session is gone | The process exited — the pane is final, so do not burn the deadline |
| `_wait_for_output_once()` requires **settled** (4 identical captures) **after** matching | Scope's "pane-settled" condition: assertions see a complete frame |
| `_wait_for_output()` retries the whole wait once | A single slow start must not fail the test (the scope's one-retry rule) |
| `_poll_session_dead()` 20s, and its assertion message now interpolates the real timeout | The old message claimed "5s" while waiting 10s |

Two empirical findings drove the shape of the fix, and both are why the
obvious implementations are wrong:

- A **naive settle check is a bug**: the pane is stable-and-empty for the
  first ~2s before the menu exists, so "stop when stable" alone would exit
  early and fail. The settle condition is therefore gated on `matched`.
- The frames under test render **atomically** (prompt + all 5 choices; result
  text + pause text in one frame), which is why settle is a safety net rather
  than the fix for a half-render.

**Honest record:** one failure was observed in a 10-run batch *before* this
hardening (run 6, normal duration, identity not captured because only the
summary line was retained — the batch was not logging tracebacks). It did not
reproduce in ~25 subsequent runs around the same load, and the hardening
above closes every fast-failure path the code has. The final code was then
gated on:

**Gate evidence — 10 consecutive clean full-suite runs, final code:**

| Run | Result | Time |
|---|---|---|
| 1 | 1091 passed | 38.12s |
| 2 | 1091 passed | 39.00s |
| 3 | 1091 passed | 40.00s |
| 4 | 1091 passed | 39.31s |
| 5 | 1091 passed | 40.00s |
| 6 | 1091 passed | 39.41s |
| 7 | 1091 passed | 39.22s |
| 8 | 1091 passed | 39.11s |
| 9 | 1091 passed | 39.74s |
| 10 | 1091 passed | 38.87s |

All ten ran back-to-back on a 2-core host at load average 3.07 (i.e.
deliberately *inside* the regime that produced the original flake); the suite
was also observed at 103s under heavier load during this phase, so the
headroom is real rather than incidental. Counting the same production-and-
picker revision's earlier runs, that is **18 consecutive green full-suite
runs on the final code** (8 + 10), out of 52 green full-suite runs across the
phase's hardening batches (9/10, 15, 10, 8, 10) — against the one failure
recorded before hardening.

### Dead code

`tests/helpers/pty_helper.py` deleted (Section 6) — zero importers, verified
repo-wide before removal.

### Phase 1 verification

| Gate | Result |
|---|---|
| Differential audit | 64 passed, `EXPECTED_DIVERGENCES` empty and hygiene-enforced |
| Accepted edges pinned | 23 tests in `tests/test_call_edges.py` |
| Full suite | 1091 passed (1004 baseline + 64 differential + 23 pins) |
| `ruff check` / `ruff format --check` | All checks passed / 93 files already formatted |
| `basedpyright` | 0 errors, 0 warnings, 0 notes |
| Production code touched | `nowreck/scanner/_tree_sitter_helpers.py` only |
---

## 10. Phase 2 — Java remediation — closed

### Dependency floor (verified empirically before any collector code)

`tree-sitter-java>=0.23` pinned in `pyproject.toml`; installed 0.23.5 verified
against `tree-sitter` 0.26.0 (ABI 14, parses cleanly). Pinned permanently in
`tests/test_java_probes.py` (`TestDependencyFloor`).

### Fixture probes J1–J12 — resolved empirically, each pinned as a permanent test

Every grammar shape the scanner depends on was probed before collector code was
written and pinned in `tests/test_java_probes.py` (33 tests). Deviations from
the scope's assumptions are recorded in the `java_scanner.py` module docstring;
the two that changed behavior:

- **J7**: Java text blocks are `string_literal` nodes, not a `text_block`
  node type — the helper's Java string handling covers them as-is.
- **Compact constructors** are `compact_constructor_declaration` (distinct
  from `constructor_declaration`) — found while building the sample suite,
  added to the method set and the shell-hash skip set, pinned (J5).

### Scanner + pipeline integration

`nowreck/scanner/java_scanner.py` (new): symbols (`class`/`record` → CLASS,
`interface`/`@interface` → INTERFACE, `enum` → ENUM, all method-like decls →
METHOD with `parent_class`) and calls (`method_invocation` with the JS/TS
receiver rule: every receiver except a call resolves to its final name).
Wired through `repository_scanner` (`.java` discovery, cache, failure
accounting), `symbol_index` merge, `change_detector._extract_calls`,
`prompt_verifier` n_files counts, and the model/verifier prompt language lists.

### Family-policy parity (verified against the JS/TS production rule)

`this.foo()`, `A.B.foo()`, `super.foo()`, `a[0].bar()`, `"s".strip()` are
captured; `f().bar()` and `new Foo()` are excluded; `Foo::bar` is a reference,
not a call. Member dunder-name calls are excluded, bare `__x__()` is not.

### Adversarial parity probes (all exact parity, checker == parser)

Anonymous classes (nested in a method and field-level), field-initializer
lambdas, static/instance initializer blocks, explicit constructor invocations
(`this(...)`/`super()`), enum-constant bodies — probed through the real
`parse_corpus`/`extract_symbols`/`extract_called_names` API; zero divergence.
All shapes were already pinned in the Java corpus (`edge_lambdas`,
`edge_records`, `edge_negatives`).

### Phase 2 verification

| Gate | Result |
|---|---|
| Differential audit | 79 passed (64 + 15 Java corpus files), `EXPECTED_DIVERGENCES` empty |
| Java probe pins | 33 passed (`tests/test_java_probes.py`) |
| Full suite | 1190 passed (1091 + 33 probes + integration tests across scanner/symbol_index/detector/body_hash/cache/cli/dependency-errors + 6 milestone checkpoints) |
| Sample suites | types + comprehensive + multiround all green (run as scripts) |
| Milestone repo | `pure-java` checkpoint class green (94 passed in the checkpoint module) |
| `ruff check` / `ruff format --check` | All checks passed / 98 files already formatted |
| `basedpyright` | 0 errors, 0 warnings, 0 notes |
| Production code touched | `java_scanner.py` (new), `_tree_sitter_helpers.py` (Java comment/string node types + `_METHOD_NODE_TYPES`), pipeline wiring (repository_scanner, symbol_index, change_detector, prompt_verifier, model prompts), `pyproject.toml` (dependency) |
| API hygiene | `_class_shell_hash` → public `class_shell_hash` (shared cross-module, matching `structural_hash`) |

---

## 11. Phase 3 — Kotlin remediation — closed

### Dependency floor (corrected, then verified empirically)

The scope's `tree-sitter-kotlin>=0.22` **does not exist on PyPI**. The real
package is `tree-sitter-kotlin 1.1.0` (the `tree-sitter-grammars/kotlin-ng`
grammar), ABI 14, running on `tree-sitter` 0.26.0; the older `fwcd` grammar is
not distributed on PyPI at all. The correction is recorded here, pinned in
`pyproject.toml`, and enforced by `test_k12_dependency_floor_is_the_installed_grammar`
(version ≥ 1.1 and ABI 14 — a grammar bump fails the probe instead of quietly
changing scan results).

### Fixture probes K1–K16 — resolved empirically, each pinned as a permanent test

Every grammar shape the scanner depends on was probed before collector code was
written and pinned in `tests/test_kotlin_probes.py` (**86 tests**). This is the
most defect-dense grammar adopted so far: **seven confirmed misparses** on
ordinary source, only three of which set `has_error`. Probes K13–K16 were added
with the D7 fix (below); K1–K12 landed with the scanner.

| # | Defect | Signal | Handling |
|---|---|---|---|
| D1 | One-line class-like body holding a member (`class A { fun f() {} }`) fails to parse; the body is mislabelled `enum_class_body` and the member sits in an `ERROR` | loud | accepted edge — the multi-line body every Kotlin style guide mandates is unaffected, and a newline or `;` before the brace avoids it; the class symbol is still emitted |
| D2 | Annotated single-entry enum without a trailing comma loses the whole declaration (`annotated_expression → infix_expression(enum, class, call_expression)`) | silent | recovered by the blinded re-parse (D7) |
| D3 | Annotated `annotation class` loses the whole declaration the same way | silent | recovered the same way, mapped to `INTERFACE` (Java `@interface` parity) |
| D4 | A top-level `fun`/`object`/`enum class` whose annotation has a following sibling — a trailing comment counts — gets its annotation **detached** into a sibling `annotated_expression`, so the same source has two CST shapes | silent | annotations are hashed as a grouping-independent leaf-token signature, so attach/detach cannot differ |
| D5 | A `fun` named after a type soft keyword (`dynamic`/`suspend`) loses its name (MISSING node in a type body, `anonymous_function` + `ERROR` at top level) | loud | name recovered from the swallowed token / `ERROR` text; a symbol or caller is **never** emitted empty |
| D6 | The same two keywords in other identifier positions (`val dynamic = 1`, a bare `dynamic()`, a named argument, a lambda parameter) collapse the whole file into one `ERROR` | loud | accepted edge — and a loud one, so the family's parse warning fires. Every other soft keyword (`value`, `field`, `get`, `set`, `by`, `where`, `init`, `param`, …) is an ordinary identifier to this grammar (probe K12e) |
| D7 | **Stacked annotations dissolve declarations** — see below | silent | blinded re-parse (`_prepare_source`) |

### D7 — the silent data-loss family (found in adversarial review, fixed structurally)

With **two or more stacked annotations**, a plain top-level `class` / `interface` /
`annotation class` (also `sealed class` and `data object`, though not `data class`,
`value class`, `enum class`, `fun interface` or `object`) is destroyed as soon as
**any declaration follows**: it becomes an `annotated_expression` chain ending in
an `infix_expression` where `class` is read as an infix operator, the name as its
left operand and the body as a trailing lambda. `has_error` stays `False`, the
symbol disappears, and a **bodyless** destroyed declaration keeps *absorbing* the
next class-like declaration into the same chain — two declarations become one node
(probes K13/K14 pin both shapes; a trailing comment does not trigger the damage,
and the same stack nested in a class body is never damaged, so the shape is a
property of the file rather than of the declaration). The same "a sibling follows"
trigger detaches an argument-bearing `@Ann(1)` on a top-level `fun` into a sibling
`annotated_expression` (probe K15).

**Why not shape-by-shape recovery:** a single annotation stays attached; the same
declaration last in a file stays attached; which heads survive is grammar luck.
Recovery rules keyed on damage shapes would grow with the grammar and still miss
the next variant. The fix therefore removes the grammar's vote entirely:

1. collect every annotation span from the original parse (attached `annotation`
   nodes *and* detached `annotated_expression` chains, arguments included);
2. **blind** those spans in the source — replaced by spaces, newlines kept, so
   every byte offset and line number survives;
3. re-parse: the blinded file is ordinary, undamaged Kotlin, so declarations
   come back intact;
4. fold each annotation back into the declaration it owns via a **positional
   ownership map** — *preceding* (the run sits directly before a symbol
   declaration, with only whitespace/comments/other runs between) or *contained*
   (the run sits inside a declaration in front of a non-symbol declaration — a
   property, enum entry, parameter, type argument) → the enclosing declaration;
   a run that does neither (a file annotation, a top-level property annotation)
   owns nothing;
5. fold each annotation's canonical leaf-token signature into that
   declaration's hash — the same signature the attached spelling produces.

Files with no annotations take the original path byte for byte (`_prepare_source`
returns `None`), so the long-standing no-annotation behaviour is unchanged.

**Dead code removed with the fix:** the blinded re-parse made the earlier
shape-specific D2/D3 recovery (`_mangled_declaration`,
`_mangled_annotation_units`, `_RecoveredDeclaration`, `_recover_destroyed`,
`_leading_annotation_siblings`, ~170 lines) unreachable — a destroyed
`annotated_expression` implies annotations, which implies the blinded path,
which never produces that shape — so it was deleted rather than left to rot.
The same pass deleted `_attached_annotations` and the `skipped_named_types` /
`drop_if_empty_types` parameters added to the shared hash helpers for Kotlin:
with the annotations blanked before hashing, those hooks can never match a
node again. `basedpyright` and the full suite were re-run after each deletion.

**The trap that cost a red test:** the `annotation` **keyword** of
`annotation class` parses as a node of type `annotation` too — a childless leaf
under `class_modifier` (probe K16). Blinding "every node of type `annotation`"
would blank the keyword and the blinded parse would read `annotation class Ann`
as a plain `class Ann`; `_is_annotation_node` therefore requires children.

### Verification — D7

| Check | Result |
|---|---|
| Spelling independence (7 pairs: destroyed-vs-comment-only control, same layout) | annotated declaration identical in name/kind/parent/**line**/`body_hash`, and callers/calls identical — **0 problems** |
| Adversarial battery (28 sample + corpus files) | deterministic across repeat scans; no empty names; no empty caller/called names; every reported line inside the file |
| Appending a sibling after a double-annotated class | `ADD_CLASS` on the sibling only — no phantom `CHANGED_CLASS`, no disappearing symbol, no call churn |
| Annotation edit on a destroyed-shape class / second-stack-member edit | `CHANGED_CLASS` on the annotated class only |
| Bodyless destroyed class + next class, edit the absorbed class | `CHANGED_CLASS` on the absorbed class |
| Interplay with D2/D3 (annotated single-entry enum, annotated `annotation class`) | both recovered and stable across sibling appends |
| Perf: 1000 double-annotated methods | 0.79 s annotated vs 0.49 s unannotated, 1001 symbols (the ownership map was sorted per run at first — replaced with a bisect lookup, 1.73 s → 0.79 s) |

**Honest record — a D7 regression the sample suite caught:** the first folding
pass took the symbol's reported line from its first owned annotation, which moved
`fun tagged` to the line of a *local* `@Suppress` inside its own body. The
`pure-kotlin` sample suite's line-number round (`test_kotlin_multiround.py`,
round 5) failed on exactly that file, and the rule was corrected: only a
**preceding** annotation shifts the reported line; a contained annotation is
content, not a prefix. Regression-pinned in `tests/test_scanner.py`
(preceding ⇒ annotation line for both spellings; contained ⇒ declaration's own
line).

### Scanner + pipeline integration

`nowreck/scanner/kotlin_scanner.py` (new): symbols (`class`/`data class`/
`sealed class`/`value class`/`object` → CLASS, `interface`/`fun interface` →
INTERFACE, `enum class` → ENUM, `annotation class` → INTERFACE,
`typealias` → TYPE_ALIAS named by the `type` field; class-body `fun` and
`secondary_constructor` → METHOD with `parent_class`, top-level `fun` (extension
functions included) → FUNCTION) and calls (`call_expression` with the JS/TS
receiver rule — the last `navigation_expression` member; `Foo::bar` is a
reference, never a call; trailing-lambda calls counted). Callers: named bodies,
secondary constructors (named after the class) and property **accessors**
(`get()`/`set()` named after the property); `init` blocks, property initialisers
and bare lambdas own nothing. `companion object` is a type body with no symbol,
so its members belong to the outer class; enum-entry bodies and local functions
produce no symbols but are still callers. Wired through `repository_scanner`
(`.kt`/`.kts` discovery, cache `language="kotlin"`, failure accounting),
`symbol_index` merge, `change_detector._extract_calls`, `prompt_verifier`
n_files counts, and the model/verifier prompt language lists.

Hash model: CLASS/ENUM carry a class-shell hash with `function_declaration` and
`secondary_constructor` excluded (companion/instance-method edits fire
`CHANGED_FUNCTION` only); INTERFACE and TYPE_ALIAS carry no hash (no
`CHANGED_INTERFACE`/`CHANGED_TYPE_ALIAS` in the claim taxonomy); Kotlin takes the
JS/TS/Go ASI exclusion for `;` (the grammar drops optional semicolons and keeps
only the enum-entry terminator); raw strings (`multiline_string_literal`) hash
differently from quoted strings, unlike Java text blocks.

Invariant: a symbol name and a caller name are **never empty** — every
function-like declaration whose name cannot be recovered contributes nothing.

### Differential audit (Kotlin corpus)

15 Kotlin corpus files added (`basic`, `edge_calls`, `edge_control`,
`edge_enums`, `edge_formatting`, `edge_generics`, `edge_inheritance`,
`edge_interfaces`, `edge_lambdas`, `edge_members`, `edge_negatives`,
`edge_nested`, `edge_objects`, `edge_realworld`, `edge_strings`), each probed
against the regex checker through the real pipeline. Kotlin compares names **and kinds** per file.
`EXPECTED_DIVERGENCES` stays **empty** — the checker bug tail (annotations,
soft keywords, `.kts`, raw strings) was fixed in the checker, not papered over,
and the map-hygiene test keeps it that way.

### Phase 3 verification

| Gate | Result |
|---|---|
| Differential audit | 94 passed (79 + 15 Kotlin corpus files), `EXPECTED_DIVERGENCES` empty |
| Kotlin probe pins | 86 passed (`tests/test_kotlin_probes.py`, K1–K16) |
| Detector matrix | `tests/test_change_detector.py`: 175 passed (incl. D2/D3/D4/D7 rows: stacked-annotation sibling append, destroyed-shape body/annotation edits, bodyless absorption, detached argument annotation with call preservation, local-annotation ownership) |
| Scanner / index / hash / cache / CLI / dependency errors | 39 / 62 / 91 / 46 / 89 / 10 passed |
| Full suite | 1364 passed |
| Sample suites (`test_kotlin_samples/`) | `test_kotlin_types.py`, `test_kotlin_comprehensive.py`, `test_kotlin_multiround.py` all green (the multiround script's rounds 4–6 cover the real-world corpus, line numbers and the cross-language regression) |
| Milestone repo | `pure-kotlin` checkpoint green (11 passed) |
| `ruff check` / `ruff format --check` | All checks passed / 103 files already formatted |
| `basedpyright` | 0 errors, 0 warnings, 0 notes |
| Production code touched | `kotlin_scanner.py` (new), `_tree_sitter_helpers.py` (`METHOD_NODE_TYPES` made public, Kotlin comment/string node types), pipeline wiring (repository_scanner, symbol_index, change_detector, prompt_verifier, model prompts), `pyproject.toml` (dependency) |
| API hygiene | `_METHOD_NODE_TYPES` → public `METHOD_NODE_TYPES` (shared cross-module, matching `class_shell_hash`) |

---

## 12. Phase 4 — PHP remediation — closed (committed as `e8f1201`)

> **Process note:** Phase 4 was verified through all six gates, reported, and
> then committed by explicit instruction as `e8f1201` (`feat(v17): Phase 4 —
> PHP language support + full-repo checkup fixes`). Sections 12 and 13 below
> were written before that commit and are included in it.

### Dependency floor

The scope's `tree-sitter-php>=0.23` resolves on PyPI only up to **0.24.1**, so
the floor was raised to `tree-sitter-php>=0.24` in `pyproject.toml`; installed
0.24.1 verified against `tree-sitter` 0.26.0. The grammar ships **two**
languages; the scanner loads `language_php()` — the HTML-embedded one that
matches the `.php` file format — because the pure-source `language_php_only()`
hard-errors on an HTML template (probe-pinned). `.phtml`/`.php3` stay out of
scope as documented.

### Fixture probes PH1–PH12 — resolved empirically, each pinned as a permanent test

Resolved **before** any collector code and pinned in
`tests/test_php_probes.py` (**74 tests** — PH1–PH12 plus boundaries and the
dependency-floor pin). Facts that changed the scope's assumptions or shaped
the implementation:

- **PH1/PH2**: a plain call's callee lives in the **`function` field** (not
  `name`); member/nullsafe/scoped calls carry the method in `name` — and a
  *dynamic* name puts a `variable_name`/`string` there instead of a `name`
  node, which is exactly how "not a static target" is detected.
- **PH4**: attributes are **children** of their declaration — an attribute
  edit is part of that declaration's own hash; no sibling folding (the
  opposite of the v16 TS decorator shape).
- **PH6**: closure/arrow assignments are FUNCTION symbols named without the
  `$` (the PHP spelling of the JS `const f = ...` rule); a closure inside a
  function body is a caller, not a symbol.
- **PH8/PH9**: traits → CLASS with trait-name `parent_class` on methods; a
  declaration-only method (interface/abstract) carries `body_hash=None` and
  can never fire `CHANGED_FUNCTION`.
- **PH11**: `'x'`/`"x"` hash identically but `'\n'`/`"\n"` stay different —
  PHP is the one language whose quote style selects the escape rules, so it
  got a dedicated `php_string_leaf` normaliser (interpolation marked so a
  literal `"\$x"` can never collide with `"$x"`; heredoc vs nowdoc distinct;
  delimiter lines are formatting, not content).
- **PH12 + empirical corrections**: `isset`/`empty`/`die`/`eval` **do** parse
  as `function_call_expression` while `unset`/`exit`/`print`/`echo`/
  `include`/`require`/`clone`/`list`/`array`/`match` do not — verified during
  checker work and corrected in the notes (the older assumption lumped them).
  First-class callable `strlen(...)` is a call node with a lone
  `variadic_placeholder` (excluded); spread `f(...$args)` is a real call.
- **Loud grammar lag**: asymmetric visibility in a *promoted constructor
  parameter* is an `ERROR` node (`has_error` set, parse warning fires); the
  same modifier on a standalone property parses cleanly.
- **Property hooks (PHP 8.4)**: named bodies inside the property — the
  property stays class-shell content while each hook owns its calls (the
  Kotlin accessor rule), caller named after the property.

### Scanner + pipeline integration

`nowreck/scanner/php_scanner.py` (new): symbols (`class` → CLASS,
`interface` → INTERFACE, `enum` → ENUM, `trait` → CLASS (PH8), top-level
`function` (incl. inside `namespace`/`declare` bodies, both block and
semicolon forms) → FUNCTION, class-body `method_declaration` → METHOD with
`parent_class`, `__construct` an ordinary METHOD named `__construct` (PH12),
closure/arrow assignments → FUNCTION (PH6)); anonymous classes produce no
symbol (PH5); `TYPE_ALIAS` never fires. Callers: named bodies own their
calls — methods, functions, named closures, property hooks (named after the
property); unnamed bodies (bare lambdas, call arguments) own nothing, so
their calls stay with the nearest enclosing named caller (the G1/G2 rule);
an anonymous-class method is a caller with no class attribution. Wired
through `repository_scanner` (`.php` discovery, cache `language="php"`,
`ScanResult.php_files`, failure accounting), `symbol_index` merge,
`change_detector._extract_calls` PHP arm, `prompt_verifier` n_files counts,
and both prompt language lists (prompts.py:31/33 and 111/113 — the stale-text
rule from Section 6 applied).

Hash model: CLASS/ENUM/trait carry the class-shell hash with
`method_declaration` subtrees excluded (disjoint facts); INTERFACE carries no
hash; declaration-only methods carry `body_hash=None` (PH9); PHP semicolons
are required syntax and hashed as content (PH10 — *not* in the ASI
exclusion, unlike Kotlin); trailing commas stay hash-invisible (shared
rule).

### Differential audit (PHP corpus)

18 PHP corpus files added (`basic`, `edge_calls`, `edge_control`,
`edge_enums`, `edge_formatting`, `edge_inheritance`, `edge_interfaces`,
`edge_lambdas`, `edge_members`, `edge_negatives`, `edge_nested`,
`edge_objects`, `edge_realworld`, `edge_strings`, `edge_traits`,
`edge_attributes`, `edge_namespace`, `edge_template`) — 86 parser symbols /
101 calls across the corpus. The checker gained the PHP stripper (single
left-to-right alternation: block comment / `//` + `#[Attr]` + `#` line
comment / heredoc / nowdoc / double / single), the `<?php`/`?>` tag blanking,
the PH11 interpolation handling (calls inside `{$…}` are real calls), the
alt-syntax colon keywords, the caller-scope mask and the symbol extractor;
`LANGS` is now 8 languages. `EXPECTED_DIVERGENCES` stays **empty**.

Checker defects found and fixed during the PHP work (same discipline as
Section 5 — the parser was ground truth throughout):

1. **Left-in `<?php` broke head-anchored matches** — the first declaration
   in a file read `<?php\n\ninterface`, so statement-start-anchored symbol
   regexes missed it. Tag markers are now blanked like comments.
2. **`_php_new_prefix` swallowed the `new` keyword** — `new Foo()` blanked
   the wrong span; fixed to strip only a namespace segment ending in `\`
   (lookbehind prevents consuming `new`).
3. **Anonymous-closure heads blanked preceding real calls** — blanks now
   emit `()` so a preceding call's `(`…`)` pairing survives.
4. **`_php_arrow_body` param-list mis-pairing** — prefers the pre-paren
   `=>` (for `get =>` forms), else skips the parameter list.
5. **`#[Attr]` attribute regex** — the `#` line-comment alternative was
   eating declaration heads after an attribute; narrowed to
   `#\[[^\[\]\n]*\]` so only bracketed attributes are protected.

### Per-suite verification

| Gate | Result |
|---|---|
| Fixture probes | 74 passed (`tests/test_php_probes.py`, PH1–PH12 + boundaries + dependency floor) |
| Differential audit | 112 passed (79 Java-era + 15 Kotlin + 18 PHP corpus files; combined run), `EXPECTED_DIVERGENCES` empty and hygiene-enforced |
| Detector matrix | `tests/test_change_detector.py`: 210 passed (`TestDetectPhpChanges`, 34 PHP tests: add/remove/changed per symbol kind, trait→CLASS rows, PH9 declaration-only → nothing, PH5 anonymous → nothing, closures, attribute/interpolation/quote/semicolon/reformat/heredoc rows, the full PH1/2/3/12 call matrix with exclusions, property-hook caller attribution, CALL_REMOVED) |
| Scanner / index / hash / cache / dependency errors | 49 / 67 / 115 / 51 / 12 passed |
| CLI E2E | `tests/test_cli.py`: 100 passed — `TestE2EPhpPipeline` (json/sarif/junit render, honest-claim CONFIRMED, top-level function spelling, method-call claim, UNVERIFIABLE, CONTRADICTED, `--compare` from git, P3 no-cache) + the `_LANG_CASES` PHP row |
| Full suite | **1545 passed** in 83.63 s (Phase 3 baseline 1364 + PHP additions) |
| Sample suites (`test_php_samples/`) | `test_php_types.py` 216, `test_php_comprehensive.py` 53, `test_php_multiround.py` 46 — all green (multiround covers repeatability, 20×50 stress, path variants, real-world, line numbers, 8-language cross regression, 60 truncations) |
| Milestone repo | `pure-php` checkpoint green (11 passed in the checkpoint module: discovery, kinds, `__construct` naming, trait mapping, PH9 declaration-only, call detection, determinism) |
| Helper self-checks | `/tmp/php_checker_smoke.py` 0 diverged (16 snippets); `/tmp/php_hash_check.py` 20/20 hash semantics OK |
| `ruff check` / `ruff format --check` | All checks passed / 108 files already formatted |
| `basedpyright` | 0 errors, 0 warnings, 0 notes |
| Production code touched | `php_scanner.py` (new), `_tree_sitter_helpers.py` (StringNormaliser hook, `encapsed_string`/`heredoc`/`nowdoc` string node types), pipeline wiring (repository_scanner, symbol_index, change_detector, prompt_verifier, model prompts), `pyproject.toml` (dependency) |

### Call-edge pins — placement decision

`tests/test_call_edges.py` pins the Phase 1 boundaries (JS/TS/Rust/Go/Python
— it predates Java). Java (Phase 2), Kotlin (Phase 3) and PHP (Phase 4) pin
their full call matrices in `tests/test_change_detector.py` instead
(`test_java_calls_captured_and_excluded`, `test_kotlin_calls_captured_and_excluded`,
`test_php_calls_captured_and_excluded`), because those matrices are
detector-level (caller attribution + `parent_class` through the real
pipeline) rather than single-scanner edges. No new file was created for PHP;
the boundary is documented here and pinned where its siblings are.

## 13. Full-repo checkup (post-Phase 4) — three defects found and fixed

A verification sweep across every suite, all 8 languages, lint, typecheck and
the installed CLI binary found three issues. None was introduced by the PHP
diff's call-capture paths; one is a genuine Rust scanner defect that predates
Phase 4, the other two are sample-suite defects.

### 13.1 Rust `impl Trait for Type` attributed methods to the trait (fixed)

`_impl_struct_name` in `nowreck/scanner/rust_scanner.py` returned the first
`type_identifier` before the impl body. For a trait impl that is the *trait*
name, so `impl Summary for Article { fn summarize ... }` produced
`parent_class="Summary"` instead of `"Article"` — contradicting the helper's
own docstring ("Type name an ``impl`` block targets"). Calls inside such
methods were mis-attributed to the trait. Found by the deterministic failure
of `test_rust_samples/test_rust_types.py::summarize parent_class is Article`
(4/4 runs); the main suite never pinned the trait-impl case, so pytest could
not catch it.

Fix: read the grammar's `type` field (the implementing type) first, falling
back to the old scan only for malformed parses; generic targets keep the head
identifier (`Wrapper<T>` → `Wrapper`). Verified: `summarize`→Article,
`to_json`/`from_json`→Article, `fmt`/`debug`→Point; all three Rust sample
suites green (153 + 68 + 36), `SymbolIndex` collision grouping unaffected.

### 13.2 TSX sample test contradicted the member-call contract (fixed)

`test_ts_samples/test_phase1_comprehensive_tsx.py` asserted that
`this.toggle()` inside a JSX-attribute arrow is *not* captured. The production
contract, pinned in `tests/test_change_detector.py::test_js_member_chains_captured`
(`obj.bar()`→`bar`, `this.x()`→`x`), is that member calls are captured by final
property name — so `render→toggle` is correct evidence. The sample test was
wrong, deterministic (4/4). Its assertion now matches the contract
(58/58 green). No production change.

### 13.3 Wall-clock "stress scan is fast" budget (stabilised)

The `< 5.0 s` smoke bound on the ~2,000-line generated stress file in
`test_kotlin_multiround.py` flaked under parallel suite load (5.58 s / 8.13 s
observed, quiet runs ~2–4 s). The check guards against gross regressions, not
benchmarking. Budget raised to `< 30.0 s` with an intent comment, in all three
sibling suites (`test_kotlin/java/php_multiround.py`) for consistency.

### 13.4 Checkup verification table

| Area | Result |
| --- | --- |
| Full pytest | **1545 passed** (67.09 s), 1 pre-existing DeprecationWarning |
| Milestone checkpoint | 116 passed (incl. `TestPurePhpRepo`) |
| Differential audit + PHP probes | 186 passed |
| Rust samples | types 153, comprehensive 68, multiround 36 — green after 13.1 fix |
| TS samples | types, comprehensive, multiround, multiround_tsx green; comprehensive_tsx 58/58 after 13.2 fix |
| Kotlin / Java / PHP samples | all green (multiround budgets per 13.3) |
| CLI binary smoke (`nowreck fix --pre/--post`) | PHP project: JSON (7 unexplained changes enumerated with correct types/parents/lines), SARIF 2.1.0 (7 results, NW001–NW006), JUnit (true `ADD_FUNCTION reset` claim → `tests="1" failures="0"`) |
| `ruff check` / `ruff format --check` | All checks passed / 108 files formatted |
| `basedpyright` | 0 errors, 0 warnings, 0 notes |
| TODO/FIXME/XXX/HACK in `nowreck/` | none |
| Attribution ban | clean (grep over diff + new files) |
| Dependency floors (`pyproject.toml`) | all 8 grammar pins present, incl. `tree-sitter-php>=0.24` (installed 0.24.1) |
| Dead code | one unused `source_bytes` parameter removed from `_closure_assignment` (`php_scanner.py`, Phase 4 new code); `scan_cache.put` unused-by-design `mtime`/`size` documented as API contract, pre-existing |

## 14. Phase 5 — C++ remediation — verified (awaiting commit instruction)

> **Process note:** Phase 5 is finished and verified through all six gates, but
> is **not committed** — the standing instruction is to stop at the verified
> state and report. The work sits in the working tree on `main`: 14 modified
> files (+2282/−20) and 5 new paths on top of `e8f1201`, the Phase 4 commit.

### Dependency floor

`tree-sitter-cpp>=0.23` pinned in `pyproject.toml`; installed **0.23.4**
(ABI 14) verified against `tree-sitter` 0.26.0. The grammar exposes a single
`language()` covering the whole C++ grammar. Discovery list (user decision):
`.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`, `.h++`, `.h`. Two
accepted edges, documented for Phase 7: the grammar **also** parses C, and
`.h` is in the list, so a C header in a mixed repository is parsed as C++
(and `_discover_files`' `rglob("*.c++")` was verified to match literally);
`.c` is never discovered.

### Fixture probes E1–E14 — resolved empirically, each pinned as a permanent test

Resolved **before** any collector code and pinned in
`tests/test_cpp_probes.py` (**59 tests** — E1–E14 plus the extra boundaries
and the dependency-floor pin). Facts that shaped the implementation:

- **E1/E2 — call shapes**: `a.b()` and `a->b()` are one `field_expression`
  shape (member in the `field` field, receiver in `argument`); `ns::func()` /
  `Class::static()` / `::global_fn()` carry a `qualified_identifier` in the
  call's `function` field with a recursive `name` child (`a::b::c()`), and a
  templated target keeps its head identifier in a `template_function`.
- **E3 — operator functions**: `operator+`, `operator<<`, `operator[]`,
  `operator()` are `operator_name` nodes; a reference return type wraps the
  declarator in a `reference_declarator`, so a declarator walk is required.
- **E4 — constructor invocations**: `new Foo()` is a `new_expression` and
  `Foo obj(3)` an `init_declarator` — neither call-shaped, so neither is
  captured; `std::vector<int>(10)` **is** a `call_expression` and is captured.
  Policy: only grammar-exposed call shapes are captured, never guessed.
- **E5 — template prefix**: `template <...>` is a sibling wrapper
  (`template_declaration`); the whole wrapper is hashed, so a template-parameter
  edit is visible (the v16 TS-decorator lesson generalised).
- **E6 — `#ifdef` regions**: `preproc_ifdef` nodes are embedded *inside* the
  enclosing `compound_statement`, so a conditional edit is part of that
  function's span; no conditional-aware hashing.
- **E7/E8/E10 — hash model**: string leaves are `string_literal`,
  `raw_string_literal`, `char_literal` (raw stays a distinct node, so a
  raw↔interpreted swap is a change); C++ `;` is required syntax and is
  **hashed as content** (the shared ASI exclusion set is never forwarded);
  `comment` was already in `COMMENT_NODE_TYPES`. Consequence:
  `_tree_sitter_helpers.py` needed **no change** for C++ — its string/comment
  unions already covered every leaf C++ produces, and C++ uses no string
  normaliser.
- **E9 — declaration-only members**: no `compound_statement` → symbol with
  `body_hash=None`, so a `.cpp` body edit can never falsify a header symbol.
- **E11 — overloads**: every overload is emitted; `Symbol` identity is
  `(name, kind, file, parent_class)`, so same-identity overloads dedupe in the
  ADD/REMOVE set-diff and the body-hash pass is last-wins (deterministic scan
  order). An edit fires `CHANGED_FUNCTION` only when the last-iterated
  overload changed — pinned exactly in the detector matrix, documented as
  coarseness.
- **E12 — lambdas**: a named lambda assignment (`auto f = [](){};`) →
  FUNCTION (the JS `const f = () => {}` rule); a named lambda inside a
  function body is a caller, not a symbol.
- **E13 — `= default` / `= delete`**: a `function_definition` with no body but
  a `default_method_clause`/`delete_method_clause` — a *definition*, hashed
  normally; `override`/`noexcept` live inside the node and hash naturally.
- **E14 — constructors/destructors**: METHOD symbols, names `Calculator` and
  `~Widget`, parent attribution as for any member.

Scope assumption broken: the scope document names the `using X = Y` node
`type_alias_declaration`. The grammar actually calls it **`alias_declaration`**
(`type_alias_declaration` exists in other grammars, not this one); `typedef` is
`type_definition`. Both → TYPE_ALIAS, pinned in `TestE17TypeDeclarations`.

Two more findings that changed collector code:

- **`union_specifier` is class-like** → added to `_CLASS_KINDS` (canonical
  kinds stay `class_specifier`/`struct_specifier`) — a union is a class-like
  type declaration.
- **Reserved call-shaped keywords**: the grammar exposes `static_cast<int>(x)`
  and siblings as a `call_expression` with a `template_function` target, and
  `typeid(x)`/`noexcept(x)` as identifier targets. These are keywords, not
  calls, so `_RESERVED_CALL_KEYWORDS` filters them in `_cpp_called_name`;
  `sizeof`/`alignof`/`decltype` are not call nodes at all.

### Header/impl split (E9) — the new modeling

A method declared in `foo.h` and defined in `foo.cpp` is **two independent
per-file symbols**; there is no `#include` resolution. The three pinned rows:

| Scenario | Result |
|---|---|
| Header *declaration* edited (signature shell content) | `CHANGED_CLASS` on the header's own type; the declaration-only method symbol is hash-less by design and never fires |
| `.cpp` body edited | `CHANGED_FUNCTION` on the `.cpp` symbol |
| `.cpp` body edited, header declaration symbol considered | never fires — `body_hash=None` (defensive rule tested) |

`= default` / `= delete` members are definitions and fire normally. Out-of-line
definitions (`void Widget::draw() {}`) put the qualifier in `parent_class`
(`Widget`); the grammar cannot distinguish a class qualifier from a namespace
qualifier (both `namespace_identifier`), so `void app::run() {}` is attributed
to `app` — accepted coarseness, documented. `Box<T>::put` keeps the head
identifier (`Box`), mirroring the Rust generic-`impl` rule. A templated
specialisation (`template <> class Buffer<char, 0>`) indexes the name as
written (`Buffer<char, 0>`). `namespace_definition` and `linkage_specification`
(`extern "C" { … }`) descend — not symbols, like Python modules. `friend`
declarations declare a non-member and yield no symbol. A bare
`int (*callback)(int);` (no `typedef`) yields no symbol — it is a variable, not
a type; `typedef void (*Cb)(int);`, `typedef int Table[4];` and
`using UAlias = …` are TYPE_ALIAS (the declarator walk needed
`parenthesized_declarator` support: its inner declarator is an *unnamed*
child; `array_declarator` and `type_identifier` names were added to the
resolver).

### Scanner + pipeline integration

`nowreck/scanner/cpp_scanner.py` (new, 927 lines): the symbol model above,
plus the hash rules — CLASS/ENUM carry a class-*shell* hash with
`function_definition` subtrees excluded (method edits fire
`CHANGED_FUNCTION` only), TYPE_ALIAS carries no hash (no
`CHANGED_TYPE_ALIAS` claim type, like every other language), semicolons
hashed, no ASI exclusions, no string normaliser. `INTERFACE` never fires — C++
has no interface keyword (the Phase 7-documented accepted edge, like Go
enums). Wired through: `repository_scanner` (`ScanResult.cpp_files`,
`.cpp`-family discovery, `_parse_cpp_file` with the
`pip install tree-sitter tree-sitter-cpp` install hint, cache
`language="cpp"`, success/failure accounting), `symbol_index` merge,
`change_detector._extract_calls` C++ arm, `prompt_verifier` `n_files` counts
(two places), and `model/prompts.py` language lists (`ADD_INTERFACE` excludes
C++; `ADD_ENUM` and `ADD_TYPE_ALIAS` include it). Scanning a file whose parse
has `has_error` (e.g. a numeric user-defined literal `1"_km"`, which this
grammar treats as an error) logs a warning and still extracts the partial
symbols — loud, not silent.

### Differential audit (C++ corpus)

17 corpus files added (`basic`, `classes`, `header_split.h/.cpp`, `namespaces`,
`templates`, `enums`, `aliases`, `lambdas`, `calls`, `operators`, `control`,
`preprocessor`, `strings_comments`, `attributes_friend`, `realworld`,
`negatives`) — 525 lines, **0 divergences**. The checker gained the C++
stripper, structure/head classifiers, call mask and symbol extractor;
`LANGS` is now 9 languages; `EXPECTED_DIVERGENCES` stays **empty**.

Checker defects found and fixed while wiring the corpus (same discipline as
prior phases — the parser was ground truth throughout):

1. **`f().bar()` receiver exclusion never fired** — `_cpp_name_is_call`
   compared `op in (".", "->")` where `op` is a tuple; fixed to `op[0]`.
2. **Qualified call statement misread as a declaration** —
   `Service::flush();` inside a body was classified as a METHOD symbol; new
   `_cpp_function_kind` counts a qualified name as a declaration only at
   module scope.
3. **Template arguments dropped from type names** — `_CPP_TYPE_DECL` now
   keeps `Box<int>` intact.
4. **Typedef function-pointer form** — `_CPP_TYPEDEF_FN_PTR` mirrors the
   scanner's TYPE_ALIAS for `typedef void (*Cb)(int);`.
5. **`type_identifier` names** — accepted in the symbol extractor.
6. **`template <...>` sibling unwrap** — `_cpp_strip_template_prefix` runs
   before classifying type/function heads (E5).
7. **Keyword/expression heads misclassified as declarations** —
   `_cpp_prefix_is_typeish` rejects `int x = compute();` and keyword-prefixed
   expression statements.
8. **Parameter default values** — `_CPP_PARAM_ITEM` accepts `int x = 3`.
9. **Leading access specifiers** — `_CPP_ACCESS_SPECIFIER` strips
   `public:`/`private:`/`protected:` from member heads.
10. **`friend` declarations** — yield nothing.
11. **Operator/destructor qualifiers** — `_cpp_operator_before` returns a
    tuple and `_CPP_OPERATOR_NAME` takes the `::` qualifier
    (`Widget::~Widget`).
12. **Templated calls** — `f<int>(x)` / `std::vector<int>(10)` reachable only
    via `_cpp_templated_call_names` + `_CPP_TEMPLATED_CALL` because the name
    ends at `>` (the plain scan cannot see it).

Documented checker limitations (docstrings; all kept out of the corpus): a
call-bearing default argument, a call-bearing `friend` *definition*,
template arguments nested deeper than one level, `<`/`>` comparison in call
position, and conversion operators (`operator T()`) not modelled.

### Per-suite verification

| Gate | Result |
|---|---|
| Fixture probes | 59 passed (`tests/test_cpp_probes.py`) |
| Differential audit | 129 passed; 0 divergences over the 17-file C++ corpus; `EXPECTED_DIVERGENCES` empty and hygiene-enforced |
| Detector matrix | `tests/test_change_detector.py -k cpp`: 31 passed (add/remove/change per symbol kind, header/impl three-row pins, template/`#ifdef`/string/semicolon/reformat rows, overload rows, full call matrix with exclusions, destructor/naming rows) |
| Scanner / index / hash / cache / dependency errors / CLI | 56 / 72 / 115 / 57 / 14 / 111 passed |
| Full suite | **1683 passed** in 92.17 s (Phase 4 baseline 1545 + 138 C++ additions); 1 pre-existing deprecation warning |
| Sample suites (`test_cpp_samples/`) | `test_cpp_types.py` 157, `test_cpp_comprehensive.py` 51, `test_cpp_multiround.py` 44 — all green (multiround covers repeatability, the 30.0 s stress smoke bound, 9-language cross regression `success_count == 9`, 60 truncation chaos) |
| Milestone repo | `pure-cpp` in the checkpoint module: 127 passed overall, incl. 11 `TestPureCppRepo` tests (discovery/9 extensions/declaration-only `body_hash=None`/union+enum+alias symbols/`interfaces == []`/constructor parent/header-vs-impl hashing) |
| CLI binary smoke (`nowreck fix`, C++ project) | `--pre/--post` json mixed: 2 claims/2 CONFIRMED, 1 unexplained (`free_function`, line 40) → exit 1; json all-true: 3/3 CONFIRMED, 0 unexplained → exit 0; sarif: 2.1.0 + schema, NW015 note for the unexplained change; junit: `testsuites name="nowreck" tests="2" failures="0"`; `--compare HEAD~1` in a real git repo: `src/app.cpp` + `lib/util.hpp` (.hpp) parsed, exactly 1 change (`CHANGED_FUNCTION run`) → exit 1 |
| `ruff check` / `ruff format --check` | All checks passed / 113 files already formatted |
| `basedpyright` | 0 errors, 0 warnings, 0 notes |
| TODO/FIXME/XXX/HACK in the Phase 5 surface | none |
| Attribution ban | clean (grep over the tracked diff and every new file) |

### Phase 5 DoD checklist

- [x] E1–E14 resolved + pinned before collector code (59 probes)
- [x] Header/impl semantics pinned by the three-row test table; `body_hash=None` defensive rule tested
- [x] `ScanResult.cpp_files` flows through cache/index/detector/verifier-counts
- [x] Differential pass over the C++ corpus clean
- [x] `test_cpp_samples/` + `pure-cpp` milestone green
- [x] Adversarial review passed (sweeps above); commit pending the standing instruction

### Accepted edges carried to Phase 6/7

- `.h` discovers C headers and the C++ grammar parses C — accepted, documented
  for Phase 7 (`.c` never discovered).
- No `#include` resolution: header declaration and `.cpp` definition are two
  independent per-file facts, by design.
- Namespace vs class qualifier collision (`void app::run() {}` → parent `app`).
- Overload coarseness in the detector (E11) — precise, documented, pinned.
- Template-specialisation names are indexed as written (`Buffer<char, 0>`).
- Grammar parse errors are loud: warning logged, partial symbols retained
  (`1"_km"` pinned as the lag example).
- Constructor invocations are captured only in the forms the grammar exposes
  as calls (E4 policy — `new Foo()`/`Foo obj(3)` excluded).

## 15. Phase 5 adversarial review — 19 defects found and fixed (committed as `5ccb289`+review)

A second-pass review swept the C++ surface with a 54-case divergence probe
(scanner output vs. the differential checker, symbol sets **and** called-name
sets) and a CST dump of every ambiguous shape. **21 divergences** surfaced in
the first sweep; all were classified root-cause-first, fixed, and pinned.
Final state: **0 unexpected divergences** over the 54 cases (1 expected — see
§15.4).

### 15.1 Scanner defects (production code — `nowreck/scanner/cpp_scanner.py`)

1. **Tagged declarations dropped the type** — `struct Foo { ... } obj;`,
   `enum Color { RED } c;` and `class W { ... } w;` put the specifier inside
   a `declaration`/`field_declaration`, so the scope walk never reached it
   (losing its members too). New `_collect_nested_type_specifiers` emits
   every **body-carrying** type child of a declaration first; a bare
   `struct Foo x;` (elaborated-type use, no body) correctly stays a non-symbol.
2. **Nested type members dropped** — a nested `struct B { void m(); };` in a
   class body had the same shape problem; it is now a file-level CLASS fact
   (no `parent_class` — the Java nested-class rule) with its members parented
   to `B`. A type declared *inside a function body* stays a local: neither it
   nor its members are symbols (its calls still get that member as caller).
3. **`typedef struct Foo { ... } FooT;` dropped the tag** — `type_definition`
   now goes through the same nested-specifier collector before aliasing.
4. **`extern "C"` single-declaration form dropped the symbol** — `extern "C"
   int f() { ... }` puts the declaration itself in `body` (not a
   `declaration_list`); walking its children visited the declarator and body
   as pseudo-declarations and lost the symbol. Both forms now descend
   correctly.
5. **Reference declarators dropped declaration-only members** —
   `reference_declarator` exposes no `declarator` field, so `A& get();` and
   `A& operator+=(int);` were invisible. The wrapper walk now falls back to
   the first named child.
6. **Conversion operators dropped** — a declaration-only `operator bool
   const;` has no `function_declarator`; the `operator_cast` node *is* the
   declarator (and its text includes the parameter list — sliced off at the
   declarator child). `operator_cast` added to the name-node set; conversion
   operators are now METHODs named `operatorbool`.
7. **Class-field lambda: symbol/caller parity with JS (G3)** —
   `auto on_ready = []() { ... };` in a class body has no `init_declarator`
   wrapper, so the lambda looked unnamed: its calls were misattributed to
   the class. It is now a **caller named after the field** (preceding
   `field_identifier`), never a symbol — the JS class-field arrow rule.
8. **Member-template call targets dropped** — `box.put<int>(v)` has a
   `template_method` head (not `template_function`); `put` was invisible.
9. **Grammar-error recovery invented calls** — `b.operator bool()` is a
   grammar error; the leftover identifier could read as a call. A call
   subtree carrying `has_error` is now skipped rather than guessed.

### 15.2 Checker (oracle) defects — `tests/helpers/differential.py`

The checker is the completeness oracle; every fix was validated against the
tree-sitter parse (parser = ground truth):

1. **Conversion-operator symbol names** — `_CPP_OPERATOR_NAME` gained the
   conversion form (`operator bool`, `operator const char*`) with the
   qualifier rule (`Vec::operator*`), matching the scanner's `operator_cast`
   slicing.
2. **Specialisation template arguments dropped from names** —
   `template <> int identity<int>(...)` read the head as `identity<int>`;
   `_CPP_DECL_TEMPLATE_ARGS` now strips one nesting level (deeper nesting
   stays a documented limitation).
3. **Braced typedef / nested type heads** — `_CPP_TYPEDEF_TYPE_HEAD` marks
   the typedef body as a *type* container so its members classify as
   methods; the symbol extractor accepts `type_identifier` and template
   arguments in type names.
4. **Declaration-head classifier** — parameter default values, leading
   access specifiers, keyword/expression heads (`int x = compute();`) and
   `friend` heads classified correctly.
5. **Destructor-name lookbehind** — the `~`-prefix rule (definition head
   vs. destructor call vs. unary complement) needed a proper operator
   context check; `~A() {`/`= delete` heads are not calls, `this->~A()`
   keeps its `~` name.
6. **Member-initialiser / `noexcept` head calls** — *documented limitation*,
   not a defect: the scanner walks the whole declaration subtree while the
   checker's per-line mask opens at the body brace (opening at the head
   would invent `W(`/`x_(` declarator calls). Kept out of the corpus, in
   the module docstring.

### 15.3 Pins added (tests)

| Surface | What was added |
|---|---|
| `tests/test_cpp_probes.py` | E17 probe classes (type declarations, module wrappers, attributes/friend) + the **E18 review set**: wrapped type declarations, single-declaration `extern "C"`, declarator wrappers (reference / `operator_cast`), class-field lambda shape, grammar-error recovery — **78 probes total** (was 59) |
| `tests/test_scanner.py` | Scanner-level rows: tagged/nested/local types, conversion operators, reference-declarator members, `template_method` calls, error-recovery exclusion |
| `tests/test_change_detector.py` | **11 end-to-end behaviour tests** (42 C++ detector tests, was 31): tagged-declaration ADD/CHANGE/NO-OP rows, nested-type class+method attribution, local-type non-symbol rule, forward-decl + braced typedef, `extern "C"` body edit, E9-mirroring reference member, conversion-op body edit, class-field-lambda call ownership, `box.put<int>`/`this->~A()` calls, specialisation-as-function, grammar-error no-call |
| `tests/differential_corpus/cpp/` | 9 corpus files extended with every fixed shape (tagged/nested types, class-field lambdas, conversion operators, specialisations, `template_method`/destructor calls, `extern "C"` forms) — permanently audited |
| `tests/helpers/differential.py` | Checker fixes above + module docstring's C++ limitation list updated to match |

### 15.4 Expected divergences

Exactly **1** documented checker limitation remains in the 54-case review
probe: a constructor member-initialiser call (`W() : x_(make()) {}`) — the
head-call class (default argument / init-list / `noexcept` operand). It is
recorded as expected in the probe harness and absent from the corpus, per
the oracle's "documented boundaries are mirrored, not measured" rule.
`EXPECTED_DIVERGENCES` for the corpus stays **empty**.

### 15.5 Review verification

| Gate | Result |
|---|---|
| Review probe (54 cases, scanner vs checker) | 0 unexpected divergences, 1 expected/documented |
| Fixture probes | 78 passed (`tests/test_cpp_probes.py`) |
| Change-detector matrix (`-k TestDetectCppChanges`) | 42 passed |
| Differential audit | 0 divergences over the extended C++ corpus; `EXPECTED_DIVERGENCES` empty |
| Attribution ban | clean (no co-author / agent notes in files or commits) |

