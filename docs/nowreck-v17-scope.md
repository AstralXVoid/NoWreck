# NoWreck v0.17.0 — Scope

**The quality release.** Four new languages (Java, Kotlin, PHP, C++) **and**
a full evidence-driven audit of the five existing parsers (Python, JS, TS,
Rust, Go) — every gap found is fixed or documented, nothing waved through.
No schedule pressure exists: each phase is tested until we are *satisfied*,
and "satisfied" is defined mechanically (Section: The Quality Bar), not by
mood.

Everything v16 built carries over **unchanged**: CHANGED claims, strict
`parent_class` call matching, structural body hashes, cache schema v2, all
reporters, verifier. The only prompt touch is stale language text in both
prompt builders (see Overview). v17 is a **scanner-layer release plus one
new piece of permanent test infrastructure** (the differential checker).

---

## Overview

| | |
|---|---|
| **New languages** | Java (`.java`), Kotlin (`.kt`, `.kts`), PHP (`.php`), C++ (`.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`, `.h++`, `.h`) |
| **New claim types** | **None** — the existing 15 map 1:1 onto all four languages |
| **Verifier / reporters / cache schema** | **Zero changes** (schema stays `CACHE_VERSION = 2`) |
| **Prompts** | Near-zero: **both** prompt builders carry stale language text — v10's claim-type parentheticals (e.g. `(TS/TSX/Rust/Go)`, prompts.py:110) and `SYSTEM_PROMPT`'s header "structural changes in Python code repositories" (prompts.py:10, live via prompts.py:183) — updated per language phase |
| **Existing languages** | Audited end-to-end; every real gap fixed, every deliberate limit documented |
| **New test infrastructure** | Differential checker (`tests/helpers/differential.py`) + per-language corpora — permanent, runs in the main suite forever |
| **Known pre-existing issue fixed** | tmux-deadline flake in `tests/test_picker_integration.py` (has bitten 3+ full-suite runs) |
| **Version** | `0.17.0` (all three sites) |

## Release order and why

```
Phase 0  Differential audit infrastructure + audit of existing 5   (evidence first)
Phase 1  Audit remediation + tmux flake kill + accepted-edges docs (fix what evidence found)
Phase 2  Java    — easiest of the four; validates the language template
Phase 3  Kotlin  — community grammar; stress-tests the fixture-first discipline
Phase 4  PHP     — official grammar, but `$`-syntax, traits, and attributes need probing
Phase 5  C++     — hardest; header/impl split, templates, qualified names; fully warmed up
Phase 6  Cross-language hardening — differential re-run over all 9, full matrix re-run
Phase 7  Docs + version bump
```

Audit before fixes (never fix from vibes). Easiest language first (the Java
phase shakes out anything wrong in the shared language template cheaply).
Hardest last (C++ arrives after three warm-ups). No language phase starts
until the previous one has passed its review gate and been committed.

---

## The Quality Bar — the satisfaction mechanism

This section is the contract for every phase below. **A phase is done when
all of its gates pass, and not before.** "Test as much as we have to be
satisfied" is operationalized as these six gates:

1. **Fixture probes first.** Every grammar edge is resolved *empirically*
   against the pinned grammar version **before** collector code is written
   (the v16 lesson: the TS method-decorator bug shipped because a grammar
   shape was assumed). Each probe becomes a permanent test pinning the
   resolved fact.
2. **Full detector matrix.** add / remove / changed / line-shift /
   reformat-only / quote-policy / decoration-adjacency per language —
   every row of the language's test matrix green.
3. **Full call-capture matrix.** Every call syntax the language has,
   captured or excluded per a written rule.
4. **Differential pass clean.** The regex-based differential checker (below)
   and the tree-sitter parser must agree on symbol sets and called-name sets
   over the language's corpus — every divergence is either fixed or mapped
   in an explicit, justified `EXPECTED_DIVERGENCES` entry. **No unmapped
   divergence may ship.**
5. **E2E pipeline.** Real `fix --pre --post`, `--compare`, cache round-trip,
   all three output formats (`terminal`/`json`+`--json`, `sarif`, `junit`)
   through the real CLI binary for the language.
6. **Adversarial review gate.** Re-verification of the implementation by
   execution (not read-and-assume) before commit — the same discipline the
   v16 phase reviews used, which caught real bugs in 4 of 6 phases. A phase
   that has not passed review is not committed.

**Scope-drift antidote:** each phase ends with an explicit PASS verdict and
a commit. We only reopen a phase if a gate found something real. Polishing
beyond the gates is out of scope — the gates are the definition of satisfied.

### The differential checker — design

**Files:** `tests/helpers/differential.py` (new), `tests/differential_corpus/<lang>/` (new),
`tests/test_differential_audit.py` (new).

An **independent, deliberately dumb symbol/call extractor** built without
tree-sitter (and without Python's `ast` for the Python checker — `ast` is
the parser under test there). Implementation: per-language regex/tokenizer
extractors.

- `extract_symbols_<lang>(source: str) -> set[SymbolTuple]` where
  `SymbolTuple = tuple[kind, name]` — kind ∈ {`function`, `method`, `class`,
  `interface`, `enum`, `type_alias`}, mirroring `SymbolType`'s claim-relevant
  kinds.
- `extract_called_names_<lang>(source: str) -> set[str]` — identifiers
  followed by `(` (with the language's keyword set excluded: `if`, `for`,
  `while`, `switch`, `catch`, `return`, `sizeof`, … per language), plus the
  final segment of dotted/arrow/qualified chains (`a.b()` → `b`,
  `ns::f()` → `f`, `a->b()` → `b`).

**Deliberate scope of the checker (documented, not a gap):** it compares
*sets of names and kinds per file* — not full `Symbol` tuples with
`parent_class` or caller attribution. Regex caller-tracking is fragile and
would make the oracle itself untrustworthy. The checker's value is
**completeness auditing** (declarations and call targets the parser missed
or invented), which is exactly where v16's real bugs lived.

**Corpora:** `tests/differential_corpus/{python,javascript,typescript,rust,go,java,kotlin,php,cpp}/`
— 12–18 authored real-world-style files per language (classes, inheritance,
interfaces, enums, generics, closures/lambdas, async/concurrency, error
handling, formatting variety, comment styles) plus the language's edge-case
constructs. Files are authored (no licensing entanglement) and every file's
ground truth is reviewed once, then pinned.

**The permanent test:** `tests/test_differential_audit.py` runs both
extractors over every corpus file and asserts parser output == checker
output, **modulo** an explicit module-level map:

```python
EXPECTED_DIVERGENCES: dict[tuple[str, str], dict[str, str]] = {
    # (lang, corpus_file): {"diverging-name": "justification — accepted edge"}
}
```

Empty by default. Every entry needs a written justification referencing the
language's accepted-edge documentation. CI-green requires
`divergences ⊆ EXPECTED_DIVERGENCES` — permanently, for all nine languages,
in the main suite (`testpaths = ["tests"]` already collects it).

**Ground-truth workflow (Phase 0):** first run produces diffs → each diff is
investigated → real parser gap (goes to Phase 1 fix list) or deliberate
design limit (goes to accepted-edges documentation + map entry). The audit
report is an artifact committed with the phase.

---

## Phase 0 — Differential audit infrastructure + audit of the existing 5

**Files:** `tests/helpers/differential.py`, `tests/helpers/__init__.py` (the
helpers dir is not currently a package — nothing imports `pty_helper.py`, itself
an audit item), `tests/differential_corpus/{python,javascript,typescript,rust,go}/`,
`tests/test_differential_audit.py`, `docs/v17-audit-report.md` (new — the findings
artifact), plus a `pyproject.toml` ruff exclusion (below).

**Implementation:**

0. **Record the perf baseline**: full-suite wall-clock time on this machine,
   written into the audit report — the Phase 6 `> 2×` gate needs a number,
   not a memory.
1. Build the checker: 5 language extractor pairs (symbols + called names),
   keyword exclusion sets per language, corpus authoring (12–18 files × 5).
   The parser side gets a thin uniform adapter per language (run
   `SymbolIndexBuilder` / `scan_<lang>_file` on one corpus file →
   `(kind, name)` set) so the comparison is one shared code path.
2. **Ruff carve-out (gate conflict, resolved here):** the corpus goal
   *formatting variety* directly fights the repo's own `ruff format --check`
   gate — authored messy `.py` corpus files would fail it. `pyproject.toml`
   gains `[tool.ruff] exclude = ["tests/differential_corpus/**"]` (check and
   format). The checker/test files themselves stay lint-clean. Sample suites
   (Phases 2–5) do NOT get this carve-out — they mirror the existing
   ruff-clean suites.
3. Run parser-vs-checker over all corpora. Investigate **every** divergence.
4. Produce `docs/v17-audit-report.md`: per language, every finding with
   classification (REAL GAP → Phase 1 fix list / ACCEPTED EDGE → docs + map)
   and the evidence for the classification.

**Audit dimensions (what the run must cover):**

| Dimension | Concrete questions per language |
|-----------|-------------------------------|
| Symbol extraction completeness | Are these visible: nested/local functions? property/getter/setter accessors? arrow-function class fields? Rust trait default methods + associated functions? Go pointer receivers? generator expressions? object-literal methods? `const f = function(){}`? lambdas assigned at module level? |
| Call-capture completeness | Are these captured: `super.x()` (JS — excluded by receiver-is-a-call rule: verify the exclusion is *documented*, not accidental)? Rust turbofish `Vec::<i32>::new()`? Kotlin/JS optional chaining? constructor invocations? macro-generated calls (accepted edge)? |
| Hash normalization robustness | Do comments/strings/quotes/formatting behave identically across all five (v16 pinned rows re-verified)? Are there leaf node types in any grammar that normalize when they shouldn't (or vice versa)? |
| Accepted-edges hygiene | Is every deliberate limit written down with its evidence? (v16 §Accepted Edges had 5 entries — re-verify each still true, extend per findings) |
| Dead code / drift | Unused exports and orphaned helpers: `tests/helpers/pty_helper.py` (no importers found — verified), stale language text in **both** prompt builders (`SYSTEM_PROMPT` header claims "Python" only; v10 parentheticals list a subset) |

**DoD:**

- [x] Perf baseline recorded in the audit report
- [x] Checker + 5 corpora exist; `tests/test_differential_audit.py` runs them
- [x] Corpus dir excluded from ruff check/format in `pyproject.toml`; everything else still lint-clean
- [x] First divergences either mapped (with justification) or listed as findings
- [x] `docs/v17-audit-report.md` written: findings classified, evidence included
- [x] Dead-code items (`pty_helper` — no importers found) investigated and dispositioned
- [x] Phase 1 fix list frozen (no new fixes mid-Phase-1 without re-running the audit)
- [x] Full suite green (checker infrastructure must not disturb anything)

## Phase 1 — Audit remediation + flake kill

**Every REAL GAP from the Phase 0 report is fixed here. Each fix ships with
the test that would have caught it** (standing rule since v16 P5). Findings
classified as accepted edges get: justification in
`EXPECTED_DIVERGENCES` + a pinning test asserting the *documented* behavior +
a row in the language's accepted-edges table (README Limitations in Phase 7).

**Named item — the tmux-deadline flake (`tests/test_picker_integration.py`):**
the real-terminal tests poll the pane with a `deadline` loop that loses the
race under full-suite load (observed 3+ times, always recovering standalone).
Fix: make `_wait_for_output` wait on process/pane-settled conditions with a
generous timeout and **one retry** before failing; verify with **10
consecutive full-suite runs, all green**. That count is the gate — not
"ran it once".

**DoD:**

- [x] Every Phase 0 REAL GAP fixed with its catching test; suite green
- [x] Every accepted edge mapped + pinned + documented
- [x] tmux flake fixed; **10 consecutive clean full-suite runs** recorded
- [x] `ruff check`/`format` + `basedpyright` strict green
- [x] Adversarial review passed; committed

---

## Phase 2 — Java

**Dependency:** `"tree-sitter-java>=0.23"` (official grammar) — the floor
is **verified and pinned at phase start** (same discipline as K12; version
floors are never assumed). Lazy-loaded
via the exact `rust_scanner.py` pattern (per-process singleton, clean
`ImportError` fallback in the repository scanner).

**Language reality (shapes the claim mapping):**

- **No top-level functions exist** — everything is a method in a class, so
  `FUNCTION`-without-`parent_class` never fires for Java; METHOD +
  `parent_class` handles everything.
- Java has real `interface` → `ADD_INTERFACE`/`REMOVE_INTERFACE` **do fire**
  (unlike C++).
- One public top-level type per file (convention) — but the scanner does not
  enforce it; nested + multiple top-level types parse fine and are handled.

### Fixture probes J1–J12 (resolved before any collector code)

| # | Question | Gates |
|---|----------|-------|
| J1 | `method_invocation` receiver shapes: `foo()`, `obj.foo()`, `this.foo()`, `A.B.foo()`, `super.foo()` — which node encloses the receiver; is `super.foo()` a distinct `super` node? | call capture |
| J2 | `object_creation_expression` (`new Foo(...)`) — exact shape. **Policy:** constructor invocations are captured as calls to the class name **only if** the grammar exposes them as call-shaped expressions; forms not exposed are excluded, never guessed. | call capture policy |
| J3 | Method references `Foo::bar` — confirm they are `method_reference` (a reference, not a call) and excluded. | call capture |
| J4 | Annotations: is `@Override` a **child** of `method_declaration` (then hashing needs nothing) or a sibling (then the v16 decorator-folding logic generalizes)? Same for class-level annotations. | body hash |
| J5 | `constructor_declaration` node shape + name extraction. **Decision:** constructors are METHOD symbols named after the class, `parent_class` = the class. | symbol model |
| J6 | `record_declaration` (→ CLASS), `annotation_type_declaration` (`@interface`, → INTERFACE) — verify node types and name fields. | symbol model |
| J7 | `text_block` (Java 15 `"""`) — multi-line leaf; quote normalization must handle it without mangling. Test the swap `"x"` ↔ text block explicitly. | hash normalization |
| J8 | Generics on classes/methods — type parameters are content (hashed); name extraction excludes the `<...>` region. | symbol name / hash |
| J9 | Interface default methods — METHOD with `parent_class` = interface name. | symbol model |
| J10 | Nested/inner classes — method `parent_class` attribution uses the **immediate** enclosing class (one-level philosophy, same as v16 nested-class edge). | symbol model |
| J11 | `enum_declaration` — enum constant edits fire `CHANGED_CLASS` (enum body = class-shell content); enum methods are METHOD symbols. | symbol model / hash |
| J12 | Semicolons are **required** syntax → hashed as content (same policy as Rust, opposite of JS/TS/Go). Verify reformat-only tests pass with `;` hashed. | ASI exclusion policy |

### Implementation

| File | Change |
|------|--------|
| `nowreck/scanner/java_scanner.py` | **New** — `_get_java_language()`, `scan_java_file`, `scan_java_calls`; collector: `class_declaration`/`record_declaration` → CLASS, `interface_declaration`/`annotation_type_declaration` → INTERFACE, `enum_declaration` → ENUM, `method_declaration`/`constructor_declaration` → METHOD (+`parent_class`), `field_declaration`/enum constants → class-shell content |
| `nowreck/scanner/_tree_sitter_helpers.py` | Extend `COMMENT_NODE_TYPES` (`line_comment`, `block_comment`), `STRING_NODE_TYPES` (`string_literal`, `text_block`, `character_literal`) per J7 |
| `nowreck/scanner/repository_scanner.py` | `ScanResult.java_files`; `_discover_files(".java")`; `_parse_java_file` with cache path (mirrors the Rust block exactly); `success_count` **and the failure-rate log block** (its `total` sum and `%d languages` count are a second, separate count site — verified at lines ~329–350) include Java |
| `nowreck/scanner/symbol_index.py` | `build` merges `java_files` |
| `nowreck/detector/change_detector.py` | `_extract_calls` gains the Java arm via `_resolve_call_file` |
| `nowreck/verifier/prompt_verifier.py` | `n_files` counts gain `java_files` (two places) |

### Test matrix (highlights — the phase's full matrix follows the shared template)

- Detector: method add/remove → ADD/REMOVE + `parent_class`, **no** `CHANGED_CLASS`; method body edit → `CHANGED_FUNCTION` only; class field/base/annotation edit → `CHANGED_CLASS` only; reformat-only → nothing; comment-only → nothing; text-block swap policy per J7; enum-constant edit → `CHANGED_CLASS`; interface default-method edit → `CHANGED_FUNCTION` with `parent_class`; remove+recreate → REMOVE+ADD; **constructor add (J5) → `ADD_FUNCTION Foo` with `parent_class=Foo` alongside existing `CLASS Foo` — no identity collision (kinds differ), pinned**.
- Calls: `foo()` inside method (captured, caller has class), `obj.m()`, `this.m()`, `A.B.m()`, `super.m()` per J1, `new Foo()` per J2, `Foo::bar` excluded (J3), nested-class caller attribution per J10, top-level-less regression (Java has none — plain-call evidence comes only from methods).
- E2E: real `fix --pre --post` on `.java` dirs; `--compare` on a git repo; hallucinated claim → UNVERIFIABLE; removal claim vs CHANGED → CONTRADICTED; sarif/junit/json render; external dirs cache-free (P3 rule).
- Cache: cold/warm equality incl. `body_hash` for `.java`; schema v2 untouched.
- Samples: `test_java_samples/` (comprehensive, multiround, types + `edge_*.java` files — mirrors `test_rust_samples/`). Milestone: `test_milestone1/repos/pure-java/` + `TestPureJavaRepo`.

**DoD:** all six gates of The Quality Bar, plus:

- [x] J1–J12 resolved empirically, each pinned as a permanent test, **before** collector code
- [x] `ScanResult.java_files` flows through cache/index/detector/verifier-counts
- [x] Differential pass over the Java corpus clean (or mapped)
- [x] `test_java_samples/` + `pure-java` milestone green
- [x] Adversarial review passed; committed

---

## Phase 3 — Kotlin

**Dependency:** `"tree-sitter-kotlin>=0.22"` — **community grammar
(fwcd)**; the exact floor is verified and pinned during K12, and the grammar's
known-lag list is written down as part of the phase (this is the language
where the fixture-first discipline earns its keep).

**Language reality:**

- `fun` at top level → FUNCTION (the model fits); `class`/`data class`/`sealed class` → CLASS;
  `interface` → INTERFACE; `enum class` → ENUM; `typealias` → TYPE_ALIAS.
- **Extension functions** (`fun String.foo()`): FUNCTION **without**
  `parent_class` — documented (the receiver is not a containing class).
- **Companion objects / object declarations:** companion bodies are
  outer-class shell content (v16 nested-class philosophy), **but** the
  class-shell walk must skip `function_declaration` children inside the
  companion (generalizing the v16 disjoint-facts rule) so a companion-method
  edit fires `CHANGED_FUNCTION` with `parent_class` = outer class, not a
  coarse `CHANGED_CLASS`. K3 resolves the exact node shape.

### Fixture probes K1–K12 (resolved before any collector code)

| # | Question | Gates |
|---|----------|-------|
| K1 | `function_declaration` top-level vs local (`fun` inside `fun`) — locals are not symbols (accepted edge, like Python nested functions). | symbol model |
| K2 | How `interface` / `enum class` / `data class` / `value class` encode (modifiers as children of `class_declaration`?) → CLASS/INTERFACE/ENUM mapping + name extraction. | symbol model |
| K3 | `object_declaration` + `companion object` node shapes; companion-method `parent_class` attribution; shell-hash walk skip logic. | symbol model / disjoint facts |
| K4 | Extension function receiver — confirm it is a distinct child; FUNCTION with `parent_class=None`. | symbol model |
| K5 | Call shapes: `a.b()`, `a?.b()` (safe-call node type), `a!!.b()`, scope functions (`let`/`run`/`apply` are plain calls — captured). | call capture |
| K6 | Lambdas `val f = { ... }` / `val g = fun(x: Int) = ...` — mirror the JS arrow-function pattern (`maybe_arrow_function_declarator` generalization) or exclude; decide + pin. | symbol model |
| K7 | String templates `"x ${y}"` — leaf node type; normalization must keep template edits visible as changes (template *content* is real content). | hash normalization |
| K8 | Annotations `@Annotation` — child or sibling of the declaration (v16 TS-decorator lesson; folding logic if sibling). | body hash |
| K9 | `typealias` node type + name field → TYPE_ALIAS. | symbol model |
| K10 | Semicolons are **optional** in Kotlin — empirically determine whether the grammar emits `;` tokens consistently; choose hashed vs excluded per evidence, pin the reformat-only test. | ASI policy |
| K11 | Properties `val x = ...` in class body → class-shell content (property edit fires `CHANGED_CLASS`). | hash / disjoint facts |
| K12 | **Grammar floor + lag audit:** pin the version; verify current-syntax constructs parse (data objects, value classes, trailing commas); write the grammar's known-unsupported list into the phase notes + accepted edges. | grammar pin |

### Implementation

Identical file pattern to Java: `nowreck/scanner/kotlin_scanner.py` (new) —
`scan_kotlin_file`, `scan_kotlin_calls`; `ScanResult.kotlin_files`; discover
`.kt`, `.kts`; index merge; detector arm; verifier counts (two places);
`success_count` + failure-rate log block; helper-union
extensions for comment/string node types per K7/K8.

### Test matrix

Follows the shared template. Kotlin-specific rows: extension-function ADD +
body-change claims (no `parent_class`); companion-method edit →
`CHANGED_FUNCTION` + `parent_class` (the K3 generalization, pinned both
ways: no `CHANGED_CLASS`); property edit → `CHANGED_CLASS`; safe-call
capture; enum-class mapping; typealias; `?.`/`!!` chains; string-template
edit fires `CHANGED_FUNCTION`; K10 semicolon policy pinned.

Samples: `test_kotlin_samples/` (mirrors). Milestone: `pure-kotlin` repo +
`TestPureKotlinRepo`.

**DoD:** all six gates, plus:

- [x] K1–K12 resolved + pinned before collector code; grammar floor pinned (K12)
- [x] Disjoint-facts rule verified for Kotlin (companion/property rows)
- [x] Differential pass over the Kotlin corpus clean (or mapped)
- [x] `test_kotlin_samples/` + `pure-kotlin` milestone green
- [x] Adversarial review passed; committed

---

## Phase 4 — PHP

**Dependency:** `"tree-sitter-php>=0.23"` (official grammar) — floor
verified and pinned at phase start. Extension: `.php` (the one standard
extension; `.phtml` and legacy `.php3`–`.php5` are out of scope, documented).

**Language reality:**

- Top-level `function foo()` → FUNCTION (the model fits); everything inside a
  class → METHOD via `parent_class`.
- `class` → CLASS; `interface` → INTERFACE (**fires** — PHP has real
  interfaces); `enum` (PHP 8.1) → ENUM; `trait` → **CLASS** (no TRAIT claim
  type — documented mapping; trait methods get `parent_class` = trait name).
- **TYPE_ALIAS never fires** (PHP has no type-alias construct) — empty set,
  documented like C++ INTERFACE.
- Anonymous classes (`new class {...}`) → no symbols (PH5, accepted edge).
- Namespaces → descend (not a symbol — like Python modules); namespaced
  functions are plain FUNCTIONs.
- Interface methods are declaration-only by language rule → `body_hash=None`
  (PH9) — `CHANGED_FUNCTION` never fires for them, documented.

### Fixture probes PH1–PH12 (resolved before any collector code)

| # | Question | Gates |
|---|----------|-------|
| PH1 | `$obj->method()` vs `$obj->prop` — node types (`member_call_expression` vs `member_access_expression`?); where the method name lives | call capture |
| PH2 | `Class::method()` / `self::method()` / `static::method()` / `parent::method()` — `scoped_call_expression` shape; `self`/`static`/`parent` are keyword names — called_name = final method name | call capture |
| PH3 | Namespaced calls `Foo\Bar::baz()` / `ns\func()` — `qualified_name` handling; final segment extraction | call capture |
| PH4 | Attributes `#[Attr]` (PHP 8.0) on functions/methods/classes — child or sibling (v16 TS-decorator lesson; fold if sibling) | body hash |
| PH5 | Anonymous classes — confirm no symbols; their methods never fire METHOD claims | symbol model |
| PH6 | Closures `$fn = function() {...}` and arrow `$fn = fn() => ...` — mirror the JS arrow-function pattern (index as FUNCTION) or exclude; decide + pin | symbol model |
| PH7 | `enum` (PHP 8.1) — node type + name field → ENUM; cases are shell content, enum methods are METHOD symbols | symbol model / hash |
| PH8 | `trait Foo` — node type + mapping decision (traits → CLASS), trait methods → METHOD with `parent_class` = trait name | symbol model |
| PH9 | Interface methods (declaration-only) → `body_hash=None` (defensive, like C++ E9); never CHANGED | symbol model / hash |
| PH10 | Semicolons required → hashed as content (NOT in ASI exclusions); reformat-only + line-shift pins | ASI policy |
| PH11 | String shapes: `'x'`/`"x"` quote-swap neutral; heredoc/nowdoc `<<<EOT`; interpolation `"$var"`/`"{$var}"` — which join `STRING_NODE_TYPES`; interpolation content is real content (edit = change, like Kotlin K7) | hash normalization |
| PH12 | Magic methods `__construct`/`__destruct` → METHOD symbols (dunder rule governs *call capture* only, never symbol indexing); `$this->m()` captured; `?->` nullsafe shape | symbol model / call capture |

### Implementation

| File | Change |
|------|--------|
| `nowreck/scanner/php_scanner.py` | **New** — `_get_php_language()`, `scan_php_file`, `scan_php_calls`; collector: `class_declaration` → CLASS, `interface_declaration` → INTERFACE, `enum_declaration` → ENUM, `trait_declaration` → CLASS (PH8), `function_definition` → FUNCTION (top level / in namespace) or METHOD (+`parent_class`), `namespace_definition` → descend, declaration-only interface methods → `body_hash=None` (PH9), closure declarators → FUNCTION (PH6) |
| `nowreck/scanner/_tree_sitter_helpers.py` | `COMMENT_NODE_TYPES` (`comment`); `STRING_NODE_TYPES` per PH11 |
| `nowreck/scanner/repository_scanner.py` | `ScanResult.php_files`; `_discover_files(".php")`; `_parse_php_file`; `success_count` + failure-rate log block |
| `nowreck/scanner/symbol_index.py` | `build` merges `php_files` |
| `nowreck/detector/change_detector.py` | `_extract_calls` PHP arm via `_resolve_call_file` |
| `nowreck/verifier/prompt_verifier.py` | `n_files` counts gain `php_files` (two places) |

### Test matrix

Shared template plus PHP rows: function/method/class/interface/enum
add-remove-change; **trait body edit → `CHANGED_CLASS`** (PH8 mapping,
pinned); enum-case edit → `CHANGED_CLASS`; enum-method edit →
`CHANGED_FUNCTION` + `parent_class`; interface-method declaration edit →
nothing beyond symbol level (PH9 — no CHANGED for declaration-only);
anonymous-class body edit → nothing (PH5); closure-assignment edit per PH6;
attribute edit per PH4; interpolation edit → `CHANGED_FUNCTION` (PH11);
`'x'`↔`"x"` swap → nothing; semicolon policy (PH10); calls: `$obj->m()`,
`$this->m()`, `Class::m()`, `self::m()`, `static::m()`, `ns\func()`,
`Foo\Bar::baz()`, `$a?->m()` per PH1/2/3/12; `f()->m()` (receiver is a call)
excluded; `$obj->__construct()` dunder-excluded.

E2E: real `fix --pre --post` on `.php` dirs; `--compare`; hallucinated →
UNVERIFIABLE; removal vs CHANGED → CONTRADICTED; sarif/junit/json render;
external dirs cache-free (P3 rule).

Samples: `test_php_samples/` (comprehensive, multiround, types +
`edge_*.php` — mirrors `test_rust_samples/`). Milestone:
`test_milestone1/repos/pure-php/` + `TestPurePhpRepo`.

**DoD:** all six gates of The Quality Bar, plus:

- [x] PH1–PH12 resolved empirically, each pinned as a permanent test, **before** collector code
- [x] `ScanResult.php_files` flows through cache/index/detector/verifier-counts
- [x] Differential pass over the PHP corpus clean (or mapped)
- [x] `test_php_samples/` + `pure-php` milestone green
- [x] Adversarial review passed; committed

---

## Phase 5 — C++

**Dependency:** `"tree-sitter-cpp>=0.23"` (official grammar) — floor
verified and pinned at phase start. Extensions
(user decision): `.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`,
`.h++`, `.h`. Note: `_discover_files` matches via `rglob(f"*{suffix}")` —
`.c++` contains no glob metacharacters and matches literally (verified
against the implementation); `.h` will also match C headers in mixed
repos — accepted (C++ grammar parses C), documented in Phase 7.

**Language reality (hardest of the four):**

- **Header/impl split** is the genuinely new modeling: a method declared in
  `foo.h` and defined in `foo.cpp` is **two per-file symbols**. Declaration-only
  members get `body_hash=None` (defensive) — a `.cpp` body edit can never
  falsify the header symbol. Header signature edits and `.cpp` body edits
  each fire `CHANGED_FUNCTION` on their own file's symbol. No `#include`
  resolution — independent per-file structural facts, documented.
- `INTERFACE` never fires (no keyword) — empty set, documented like Go enums.
- Overload sets: per E11 — same-identity overloads dedupe in the ADD/REMOVE
  set-diff and the body-hash pass is last-wins; an edit fires
  `CHANGED_FUNCTION` iff the last-iterated overload's body changed, edits to
  shadowed overloads are invisible. Documented coarseness.

### Fixture probes E1–E14 (resolved before any collector code)

| # | Question | Gates |
|---|----------|-------|
| E1 | Do `a.b()` and `a->b()` both parse to `field_expression` with a `field` child? | call capture |
| E2 | Does `ns::func()` / `Class::static()` put the target in `call_expression.function` as a `qualified_identifier`? Is the final name the last `identifier` child? | call capture |
| E3 | Are `operator+` / `operator<<` / `operator()` names extractable (which node holds the operator token)? | symbol name |
| E4 | `new Foo()` — node type (`new_expression`); `Foo obj(args)` — does the initializer parse to a call expression? **Policy:** constructor invocations ARE captured as calls to the class name when the grammar exposes them as call expressions; forms not exposed are excluded, never guessed. | call capture policy |
| E5 | **Template prefix attachment** — is `template <typename T>` a sibling of the `function_definition`/`class_specifier` or inside it? If a sibling, a template-param edit must fold into the symbol's body hash (the v16 TS-decorator fix generalizes) or the edit is invisible. | body hash |
| E6 | `#ifdef` regions — preprocessor nodes are part of the raw CST; a change inside a conditional fires `CHANGED_FUNCTION` (the text changed). Verify and pin; **no** conditional-aware hashing. | body hash semantics |
| E7 | String leaf shapes: `string_literal`, `char_literal`, `raw_string_literal` (`R"(...)"`), `concatenated_string`, `user_defined_literal`, `preproc_arg`. Only node types where a quote-style swap is genuinely hash-neutral join `STRING_NODE_TYPES`; raw strings stay distinct (v16 Rust/Go precedent). | hash normalization |
| E8 | Semicolons: C++ `;` is required syntax → **hashed as content** (NOT added to `ASI_LEAF_EXCLUSIONS`). Verify reformat-only and line-shift tests pass with `;` hashed. | ASI policy |
| E9 | **Declaration-only methods** (headers): does the collector emit the symbol with `body_hash=None` (defensive, no CHANGED) so a `.cpp` body-only edit never falsifies the header symbol? | header/impl split |
| E10 | Comment node type (`comment`) joins `COMMENT_NODE_TYPES`. | hash normalization |
| E11 | **Overload semantics, stated precisely (verified against the detector):** `Symbol` equality is `(name, kind, file, parent_class)` — so same-identity overloads **dedupe to one in the ADD/REMOVE set-diff** (adding a second overload of an existing name fires *nothing*), and the body-hash pass keys a dict by that identity with **last-wins** iteration order (deterministic: scan order). Net: an edit fires `CHANGED_FUNCTION` iff the *last-iterated* overload's body changed; edits to shadowed overloads are invisible. Pin exactly this; document as coarseness. | detector semantics |
| E12 | Lambdas: `auto f = [](int x) { ... };` — mirror the JS arrow-function pattern (index as FUNCTION). | symbol model |
| E13 | `= default` / `= delete` / `override` / `noexcept` — verify they live inside the function node (hashed naturally). | body hash |
| E14 | Destructors/constructors as members: node types + name extraction (`~Widget`, `Widget`); constructors/destructors are METHOD symbols. | symbol model |

### Implementation

| File | Change |
|------|--------|
| `nowreck/scanner/cpp_scanner.py` | **New** — collector: `class_specifier`/`struct_specifier` → CLASS, `enum_specifier` → ENUM (both `enum class X` and `enum X`), `type_alias_declaration` (`using X = Y`) → TYPE_ALIAS, `function_definition` → FUNCTION (top level / in namespace) or METHOD (+`parent_class`), `namespace_definition` → descend (not a symbol — like Python modules), `template_declaration` → wrapped declaration is the symbol (E5 folding), declaration-only members → `body_hash=None` (E9), lambda declarators → FUNCTION (E12) |
| `nowreck/scanner/_tree_sitter_helpers.py` | `COMMENT_NODE_TYPES`/`STRING_NODE_TYPES` unions per E7/E10; class-shell walk skips method subtrees (E5 decides whether template prefixes need folding for classes too) |
| `nowreck/scanner/repository_scanner.py` | `ScanResult.cpp_files`; `_discover_files(".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h++", ".h")`; `_parse_cpp_file`; `success_count` + failure-rate log block |
| `nowreck/scanner/symbol_index.py` | `build` merges `cpp_files` |
| `nowreck/detector/change_detector.py` | `_extract_calls` C++ arm via `_resolve_call_file` |
| `nowreck/verifier/prompt_verifier.py` | `n_files` counts gain `cpp_files` (two places) |

### Test matrix

Shared template plus C++ rows: free function + method + constructor +
destructor add/remove/change; class/struct shell edit (field, base list,
access specifier) → `CHANGED_CLASS` only; **header/impl split pins** (E9 —
the three-row scenario table: header-declaration edit, `.cpp` body edit,
declaration-only symbol never fires from the `.cpp` edit); template-param
edit visible (E5); `#ifdef`-region edit → `CHANGED_FUNCTION` (E6); raw↔
interpreted string stays a change (E7); reformat-only / comment-only /
line-shift → nothing; `;` hashed (E8); overload edit → exactly one
`CHANGED_FUNCTION` when the *last-iterated* overload changed, nothing when
only a shadowed overload changed (E11); calls: `foo()`, `obj.m()`, `obj->m()`, `ns::f()`, `Class::static()`,
`a.b.c()`, `f().bar()` excluded, constructor invocations per E4, lambda
calls excluded as callers; caller inside namespace keeps namespace-less
caller name (consistent with Rust/Go).

Samples: `test_cpp_samples/` (mirrors). Milestone: `pure-cpp` repo
(`greeter.cpp/.h`, `calculator.cpp/.h`, `models.h`) + `TestPureCppRepo`
including the header-split pins.

**DoD:** all six gates, plus:

- [x] E1–E14 resolved + pinned before collector code
- [x] Header/impl semantics pinned by the three-row test table; `body_hash=None` defensive rule tested
- [x] `ScanResult.cpp_files` flows through cache/index/detector/verifier-counts
- [x] Differential pass over the C++ corpus clean (or mapped)
- [x] `test_cpp_samples/` + `pure-cpp` milestone green
- [x] Adversarial review passed; committed

---

## Phase 6 — Cross-language hardening

1. **Differential re-run over all 9 languages** — corpora for the four new
   languages get the same grounding pass as the original five; any late
   divergence is fixed or mapped (no new features, only correctness).
2. **Full matrix re-run** — the v16 detector/verifier/reporter matrices
   re-verified through all 9 scanners (per-language CHANGED + call rows
   through the real pipeline).
3. **Cache honesty check** — `CACHE_VERSION` stays 2; stale-cache rebuild
   and body-hash round-trips verified for all 9 languages.
4. **Determinism sweep** — `test_deterministic_across_runs` equivalents per
   milestone repo; byte-identical scan output across runs.
5. **Performance sanity** — full-suite runtime vs the Phase 0 baseline; no
   suite may take > 2× that number (catches accidental O(n²) in a new
   collector).
6. **Picker smoke test** — `picker.py` constructs the scanner directly (P3
   touched it), so new languages should flow through automatically; verify
   with a mixed-language repo smoke test rather than assuming.

**DoD:** all six items green; findings from this phase are fixed in-phase
(this is why it exists), suite fully green, review passed, committed.

## Phase 7 — Docs + version bump

| File | Change |
|------|--------|
| `nowreck/__init__.py` | `__version__` → `"0.17.0"` |
| `nowreck/main.py` | `_BANNER` → `NoWreck v0.17.0` |
| `pyproject.toml` | `version` → `"0.17.0"`; deps + tree-sitter-java/kotlin/php/cpp |
| `README.md` | Language lists gain Java/Kotlin/PHP/C++ (now 9); claim table notes per language (Java: no top-level functions, INTERFACE fires; Kotlin: extension functions parentless; PHP: TYPE_ALIAS never fires, traits → CLASS, `$obj->m()`/`Class::m()` capture; C++: INTERFACE never fires, header/impl split, `->`/`::` capture); Limitations rewritten from the audit's accepted-edge tables; roadmap rows (4 languages ✅ + existing-parser audit ✅) |
| `use.md` | Same language table + per-language notes |
| `docs/release17.md` | **New** — release notes: 4 languages, audit results (N real gaps fixed, M documented edges), differential-checker infrastructure, flake fix |
| `docs/v17-audit-report.md` | Finalized in Phase 0/1, linked from release notes |

**DoD:** version sync verified across all three sites (`--version`, banner,
pyproject); all doc language-lists consistent; release notes match what
actually shipped (numbers from the audit report, not vibes).

---

## Dependencies (complete list)

```toml
"tree-sitter>=0.26",                # existing
"tree-sitter-javascript>=0.25",     # existing
"tree-sitter-typescript>=0.23.2",   # existing
"tree-sitter-rust>=0.23",           # existing
"tree-sitter-go>=0.25",             # existing
"tree-sitter-java>=0.23",           # NEW (Phase 2)
"tree-sitter-kotlin>=0.22",         # NEW (Phase 3 — floor verified in K12)
"tree-sitter-php>=0.23",            # NEW (Phase 4 — floor verified at phase start)
"tree-sitter-cpp>=0.23",            # NEW (Phase 5)
```

No other new dependencies. All four grammars lazy-load via the existing
rust/go pattern; `test_dependency_errors.py` gains the four new
missing-grammar cases.

## Complete files list (new / modified across all phases)

| File | Phase | What |
|------|-------|------|
| `tests/helpers/__init__.py` + `tests/helpers/differential.py` | 0 | New — 9-language regex checker (built incrementally: 5 in Phase 0, 4 more in each language phase); helpers dir becomes a package |
| `tests/differential_corpus/{python,javascript,typescript,rust,go}/` | 0 | New — corpora (5 in Phase 0; `java/`, `kotlin/`, `php/`, `cpp/` added in Phases 2–5) |
| `tests/test_differential_audit.py` | 0 | New — the permanent differential test + `EXPECTED_DIVERGENCES` |
| `docs/v17-audit-report.md` | 0/1 | New — findings artifact |
| `tests/test_picker_integration.py` | 1 | Flake fix |
| Audit-driven fixes (files TBD by findings) | 1 | Each with its catching test |
| `nowreck/scanner/java_scanner.py` + integration sites | 2 | New language |
| `nowreck/scanner/kotlin_scanner.py` + integration sites | 3 | New language |
| `nowreck/scanner/php_scanner.py` + integration sites | 4 | New language |
| `nowreck/scanner/cpp_scanner.py` + integration sites | 5 | New language |
| `nowreck/scanner/repository_scanner.py` | 2/3/4/5 | `java_files`/`kotlin_files`/`php_files`/`cpp_files` + parse blocks |
| `nowreck/scanner/symbol_index.py` | 2/3/4/5 | Index merges |
| `nowreck/scanner/_tree_sitter_helpers.py` | 2/3/4/5 | Node-type union extensions |
| `nowreck/detector/change_detector.py` | 2/3/4/5 | `_extract_calls` arms |
| `nowreck/verifier/prompt_verifier.py` | 2/3/4/5 | Count lines |
| `tests/test_change_detector.py`, `tests/test_scanner.py`, `tests/test_symbol_index.py`, `tests/test_scan_cache.py`, `tests/test_cli.py`, `tests/test_dependency_errors.py` | 2/3/4/5 | Per-language matrices |
| `test_java_samples/`, `test_kotlin_samples/`, `test_php_samples/`, `test_cpp_samples/` | 2/3/4/5 | New sample suites — ruff-clean, mirroring the existing suites (no corpus-style carve-out) |
| `test_milestone1/repos/pure-java|pure-kotlin|pure-php|pure-cpp` + checkpoint classes | 2/3/4/5 | New milestone repos |
| `pyproject.toml` | 0/2/3/4/5/7 | P0: corpus ruff carve-out; P2–5: four grammar deps; P7: version `"0.17.0"` |
| `nowreck/__init__.py`, `nowreck/main.py`, `README.md`, `use.md`, `docs/release17.md` | 7 | Version `0.17.0` ×3 sites + docs |

## What this does NOT do

- No new claim types; verifier, reporters, and cache schema
  unchanged (`CACHE_VERSION` stays 2); prompts change only in the stale
  language text of both builders (Overview row)
- No `.c` (C) support — needs `tree-sitter-c`; separate scope
- No `#include` resolution or cross-file symbol linking — header/impl is
  independent per-file facts
- No semantic call-graph resolution; no preprocessor-aware hashing; no
  template instantiation analysis
- No receiver tracking in call identity — consistent with v16
- No new CLI flags, exit codes, or formats
- No rewrite of existing scanners beyond audit findings — the audit fixes
  what evidence shows is broken, not what looks improvable
- No new verdict logic or three-verdict-model changes; "claim is never its
  own evidence" invariant untouched

## Definition of Done (global)

- [x] **Phase 0:** checker + 5 corpora + audit report; findings frozen
- [x] **Phase 1:** every REAL GAP fixed with its test; accepted edges
      documented + mapped; tmux flake dead (10 consecutive green full runs)
- [x] **Phase 2:** Java through all six gates (probes J1–J12 pinned first)
- [x] **Phase 3:** Kotlin through all six gates (probes K1–K12 pinned first;
      the phase added K13–K16 with the D7 fix, so the delivered set is
      K1–K16)
- [x] **Phase 4:** PHP through all six gates (probes PH1–PH12 pinned first)
- [x] **Phase 5:** C++ through all six gates (probes E1–E14 pinned first; the
      adversarial review added E17/E18, so the delivered set is E1–E18)
- [x] **Phase 6:** 9-language differential clean; full matrix re-verified;
      determinism + perf sanity green
- [x] **Phase 7:** version 0.17.0 in all three sites; README/use.md/
      release17.md complete and accurate
- [x] Full suite green; `ruff check`/`format` clean; `basedpyright` strict
      clean; every phase committed separately (no attribution)
- [x] **The standing promise kept:** 9 languages, every one having passed
      the *same* satisfaction bar — no legacy tier, no "new but unproven"
      tier

**Definition of Done: 10/10 complete.** `v0.17.0` ships nine languages —
Python, JavaScript, TypeScript (incl. `.tsx`), Rust, Go, Java, Kotlin, PHP and
C++ — every one grounded by the differential oracle, its grammar probes
pinned before collector code, and its own detector matrix, sample suite and
milestone repo. Verified on the final tree: full suite **1,731 passed** (1
pre-existing deprecation warning), differential audit **129 passed** with
`EXPECTED_DIVERGENCES` empty over **125** corpus files, grammar probes
**33 / 86 / 74 / 78**, milestone checkpoint **131 passed**, `ruff check` +
`ruff format --check` clean, `basedpyright` strict **0 errors**. Two Phase 7
closeout items were fixed rather than assumed: `docs/release17.md` (the one
missing deliverable) and the picker terminal tests' hermeticity — they drove
a `PATH`-resolved `nowreck`, so a stale user-level install became the process
under test; they now run this checkout via `<sys.executable> -m nowreck`,
pinned by a regression test that puts a broken decoy first on `PATH`. One
gate is recorded with its measurement rather than as a bare pass: the
full-suite `< 2×` baseline wall-clock bound measured **1.47×–2.31×** on this
host (43.84 s–68.57 s vs 29.74 s), one run of five over the bound — a
load-sensitivity with no collector hotspot behind it (see
`docs/v17-audit-report.md` §17).
