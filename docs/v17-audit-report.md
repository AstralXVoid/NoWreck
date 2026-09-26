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
