# NoWreck v0.16.0 — Scope

**Release goal:** Make *"I modified X"* claims verifiable (the biggest remaining
hole in the claim taxonomy) and extend `CALLS_FUNCTION` to real-world
method/attribute calls (`obj.method()`, `self.foo()`, `this.bar()`,
`pkg.Func()`). Two features, one release, zero new languages — **plus four
pre-existing fixes found in the review sweep** (see Part B): the git-repo
prompt-mode restore bug (P1, must-fix), Python async-function symbol indexing
(P2), scan-cache writes into scanned directories (P3), and a label-map gap
(P4).

---

## Problem

### 1. Structural edits are invisible to the verifier

The verifier's two core structures (`ClaimType`, 13 types; `ChangeType`, 14)
only express **existence** claims — ADD/REMOVE of symbols/files and
`CALLS_FUNCTION`. Symbol identity deliberately excludes `line_number`
(`Symbol`, `symbol_index.py`) so pure line shifts don't produce remove+add
pairs — but **nothing else about a symbol is compared either**.

Concretely, this body edit between pre/post snapshots:

```python
def greet():            # before
    return "hi"
```
```python
def greet():            # after
    return "hello world"
```

produces **zero `DetectedChange`s** — the pre and post symbol sets are equal.
Consequences:

- The most common real-world AI claim — *"I fixed the bug inside
  `validate_email()`"*, *"I changed the implementation of `greet()`"* — is
  **UNVERIFIABLE** today, even against a perfectly captured before/after state.
- Worse, it is **un-contradictable**: if the model claims it modified code it
  never touched, NoWreck sees no change and cannot call the lie. The verifier
  can only catch hallucinated *additions/removals*, not hallucinated *edits*.

### 2. Method/attribute calls are invisible to call detection

`_extract_calls` (Python, `change_detector.py`) and the tree-sitter call
extractors (`_tree_sitter_helpers.py`, `rust_scanner.py`, `go_scanner.py`)
only capture simple identifier calls (`foo()`). Excluded by design since v1:

- `obj.method()` — the overwhelmingly common OOP call form
- `self.validate()` / `this.foo()` / `s.foo()` / `pkg.Func()`
- `a.b.c()` chains

A claim like *"`process()` now calls `validate()` on `self`"* matches nothing.
The verifier's own comment says *"Attribute/method calls … are excluded from
MVP scope"* — v16 retires that exclusion.

Neither change touches how CONFIRMED/CONTRADICTED/UNVERIFIABLE work; both add
new fact kinds into the existing deterministic pipeline.

---

## Solution — overview

### Hash semantics (design decision)

**Structural hash in every language — one consistent rule.**

- **Python:** `sha256` of `ast.dump(node)` for the definition node
  (`include_attributes=False` → line numbers excluded, comments/whitespace
  absent from the AST by construction). Renaming a local, changing a literal,
  adding/removing a statement, changing a decorator **changes** the hash;
  reformatting or reordering lines does **not**.
- **JS/TS/Rust/Go:** a canonical serialization of the tree-sitter CST node:
  emit each node's *type*, recurse into **all** children including unnamed
  tokens (so operators `a+b` vs `a-b` differ), and for leaf tokens emit the
  trimmed source text. `comment` nodes are skipped entirely.

**String-leaf normalization (added in review):** for known string node types
(`string` JS/TS, `string_literal`/`raw_string_literal` Rust,
`interpreted_string_literal`/`raw_string_literal` Go), strip the matching
outer quote pair before whitespace-collapsing. `"x"` and `'x'` therefore hash
identically in every language — quote-style is a formatting change, and the
documented divergence from the first draft is **eliminated**, not tolerated.

Consequences (documented, test-enforced):

| Edit | Python | JS/TS/Rust/Go |
|------|--------|---------------|
| Reformat / whitespace | no change | no change |
| Comment edit | no change | no change |
| String quote-style swap (`"x"` → `'x'`) | no change | no change |
| Identifier / literal / operator / statement edit | change | change |
| Line shift within body | no change | no change |

**Python docstrings count as body changes** (they are AST constants): editing
a docstring → `CHANGED_FUNCTION`. This is consistent with "editing content is
a change" and is intentional — flagged here so it is a decision, not a
surprise.

The `body_hash` is **identity-exempt** (`compare=False`, exactly like
`line_number`): a pure body edit must not masquerade as remove+add.

### New claim types

`CHANGED_FUNCTION` and `CHANGED_CLASS`. Methods collapse into
`CHANGED_FUNCTION` with `parent_class`, matching the existing ADD/REMOVE
convention. A `CHANGED_*` claim is:

- **CONFIRMED** — a `CHANGED_*` change with matching identity fields exists.
- **CONTRADICTED** — the symbol was actually **added** or **removed**
  (claiming "I modified `x`" when `x` was deleted — or never existed — is a
  hallucination).
- **UNVERIFIABLE** — the symbol exists in both states with an identical body.

### Disjoint-facts rule for CHANGED detection (added in review — the core fix)

A method's body is *inside* its class's body, so a naive "class body hash
changed" would fire `CHANGED_CLASS` for every method edit — double-reporting
the same edit and forcing claims to duplicate. v16 therefore defines the
hashes so the facts are **disjoint by construction**:

- **Function/method hash** = the whole definition node (signature + body +
  decorators).
- **Class hash** = the class *shell only*: decorators, base classes,
  keywords, and class-level statements — **excluding every method subtree**
  (Python: `FunctionDef`/`AsyncFunctionDef` children of the class body;
  JS/TS: `method_definition` and accessor members). Rust/Go structs naturally
  contain only fields (methods live in `impl` blocks / `method_declaration`s),
  so no exclusion logic is needed there — the shell hash just works.

Resulting fact decomposition (test-enforced, no overlaps; one grammar caveat in Accepted Edges #1):

| Edit | Facts emitted |
|------|---------------|
| Method body edit | `CHANGED_FUNCTION` only |
| Method signature edit | `CHANGED_FUNCTION` only |
| Method add / remove | `ADD_FUNCTION` / `REMOVE_FUNCTION` only |
| Method decorator edit (Python: decorator lives inside the `FunctionDef` node) | `CHANGED_FUNCTION` only |
| Method decorator edit (JS/TS: decorators may attach as siblings of `method_definition`, grammar-dependent) | see Accepted Edges #1 — fixture-verified during implementation |
| Class decorator / base class / class-level statement edit | `CHANGED_CLASS` only |
| Remove + recreate with different body | `REMOVE_FUNCTION` + `ADD_FUNCTION` (never CHANGED) |

**Strictness decision:** a symbol recreated as remove+add is ADD/REMOVE by
construction — `CHANGED` requires the symbol to exist in *both* snapshots. A
`CHANGED_FUNCTION` claim against a remove+recreate diff is therefore
CONTRADICTED (the identity truly was added). Deliberate; documented here so it
never reads as a surprise bug.

### New call identity

`CallEvidence(file_path, caller_name, caller_parent_class, called_name)`
replaces the `(Path, str, str)` tuples across all five call extractors.
Rule, consistent across languages:

- Capture a call when its target is a plain identifier **or** an
  attribute/member/field/selector chain whose receiver is an identifier or
  member chain: `foo()`, `self.foo()`, `obj.bar()`, `a.b.c()`, `this.foo()`,
  `s.foo()`, `pkg.Func()`.
- Exclude when the receiver is itself a call (`super().foo()`, `f().bar()`).
- Exclude dunder-named attributes (`^__.*__$`, e.g. `__init__`).
- `called_name` = the **final method name** (receiver chain is not part of
  identity: `self.foo()` and `obj.foo()` both yield `called_name="foo"`).
- `caller_parent_class` = enclosing class of the calling function/method
  (`None` for top-level callers).

**Strict matching (added in review):** the verifier's `_fields_match` compares
`parent_class` symmetrically. Therefore a `CALLS_FUNCTION` claim about a
method call **must** carry `parent_class` to match method-call evidence; a
plain claim (`parent_class=None`) will NOT match a call whose evidence has a
class, and vice-versa — such a claim comes back UNVERIFIABLE, not CONTRADICTED.
This is deliberate strictness (a vague claim deserves Unverifiable), and the
prompt already instructs `parent_class` for methods. Users see it documented in
README.

The invariant from v10 holds unchanged: **a claim is never its own evidence** —
all `CHANGED_*` and call facts come from independently captured pre/post
snapshots, never from the model.

---

## Phase 1: Foundation — `body_hash`, structural hash, cache bump, call evidence

**Files:** `nowreck/scanner/symbol_index.py`, `nowreck/scanner/_tree_sitter_helpers.py`,
`nowreck/scanner/rust_scanner.py`, `nowreck/scanner/go_scanner.py`,
`nowreck/scanner/scan_cache.py`, **new** `nowreck/scanner/call_evidence.py`

### `Symbol.body_hash`

| Change | Where |
|--------|-------|
| `body_hash: str \| None = None` with `field(default=None, compare=False)` appended after `parent_class` (defaulted field keeps dataclass ordering valid) | `symbol_index.py` |
| `to_dict()` serialises it; `from_dict` reads via `d.get("body_hash")` (tolerant of old payloads) | `symbol_index.py` |
| Python function/method hash: `sha256(ast.dump(node, include_attributes=False)...)` over the definition node — computed in `SymbolIndexBuilder._process_module` / `_process_class_body` | `symbol_index.py` |
| Python class-shell hash: hash of (`ast.dump` of decorator_list, bases, keywords) + `ast.dump` of each non-`FunctionDef`/`AsyncFunctionDef` class-body statement — **methods excluded** | `symbol_index.py` |
| Tree-sitter: new shared `structural_hash(node, source_bytes) -> str` — see algorithm below | `_tree_sitter_helpers.py` |
| Wire `body_hash=...` at every Symbol construction site: `collect_top_level_symbols`, `collect_class_methods`, `maybe_arrow_function_declarator` (JS/TS, shared helpers); `_collect_rust_symbols`, `_collect_impl_methods` (`rust_scanner.py`); `_collect_go_symbols`, `_collect_type_symbols` (`go_scanner.py`) | helpers + rust + go |
| Class-declaration symbols hash their shell: `collect_top_level_symbols` hashes class children excluding `method_definition`/accessor subtrees | `_tree_sitter_helpers.py` |
| TS shell walk must also skip decorator siblings attached to a member or class declaration (Accepted Edges #1) — fixture-verified during implementation | `_tree_sitter_helpers.py` |

**Note:** `javascript_scanner.py` / `typescript_scanner.py` need **no symbol
changes** — they delegate to `_tree_sitter_helpers.collect_top_level_symbols`,
which gains the hash automatically. Python needs **no scanner change** either —
`SymbolIndexBuilder` computes it from the already-parsed AST, and cache hits
re-parse from cached source, so `body_hash` is always derivable.

`structural_hash` algorithm (shared, language-agnostic):

```
def structural_hash(node, source_bytes) -> str:
    if node.type == "comment":
        return ""                       # comments never affect the hash
    parts = [node.type]
    if node.child_count == 0:           # leaf token: identifier/literal/operator
        text = decode(node)
        if node.type in STRING_NODE_TYPES:
            text = strip_outer_quotes(text)   # quote-style insensitive
        parts.append(" ".join(text.split()))  # collapse whitespace, trim
    else:
        for child in node.children:     # includes unnamed tokens (operators, punctuation)
            parts.append(structural_hash(child, source_bytes))
    return sha256("|".join(parts)).hexdigest()
```

`STRING_NODE_TYPES` = `{"string"} ∪ {"string_literal", "raw_string_literal",
"char_literal", "interpreted_string_literal", "rune_literal", "template_string"}` —
language union; per-grammar availability is irrelevant (a type absent from a
grammar simply never matches).

### Cache invalidation — `scan_cache.py`

Old caches (schema v1) store symbols **without** `body_hash`, so `from_dict`
would produce `body_hash=None` for every symbol → `None == None` on both sides
→ the detector would falsely report *everything unchanged*.

- Bump `CACHE_VERSION = 1` → `2`. The existing version-mismatch path in
  `ScanCache._load` already handles this: old caches are ignored and rebuilt.
- `CacheEntry` needs no structural change — `symbols` are serialised through
  `Symbol.to_dict`, which now includes `body_hash` automatically.

### `CallEvidence` — `scanner/call_evidence.py` (new)

```python
@dataclass(frozen=True)
class CallEvidence:
    file_path: Path
    caller_name: str
    caller_parent_class: str | None = None
    called_name: str   # required — every call has one (Accepted Edge #5)
```

Replaces the `set[tuple[Path, str, str]]` return type of `_extract_calls`
(Python) and `scan_js_calls` / `scan_ts_calls` / `scan_rust_calls` /
`scan_go_calls`. Equality/hash come free from the frozen dataclass, so the
`pre_calls - post_calls` set-diff in `ChangeDetector._detect_calls` keeps
working unchanged.

---

## Phase 2: Detector — `CHANGED_*` changes + extended call capture

**Files:** `nowreck/detector/change_detector.py`, the five call extractors

### `ChangeType` additions

| Value | Notes |
|-------|-------|
| `CHANGED_FUNCTION` | body changed; methods carry `parent_class` |
| `CHANGED_CLASS` | class *shell* changed (see disjoint-facts rule) |

### Body-hash change pass

New step in `ChangeDetector.detect` between symbol set-diff and file set-diff:

1. Build identity keys `(name, symbol-kind, file_path, parent_class)` from
   both pre and post symbol sets, where symbol-kind groups FUNCTION + METHOD
   as one kind and CLASS as another (parent_class disambiguates methods of
   the same name in different classes).
2. Symbols present in **both** with **both hashes non-None and different** →
   emit `CHANGED_FUNCTION` (FUNCTION/METHOD) or `CHANGED_CLASS` (CLASS) with
   the post-snapshot `line_number`.
3. **Defensive None rule (added in review):** if either side's `body_hash` is
   `None` (corrupt or legacy data), emit **nothing** — never fabricate a
   change from an uncomputable comparison.
4. INTERFACE/ENUM/TYPE_ALIAS symbols are skipped (no `CHANGED_*` claim types —
   keeps v16 narrow; hashes may be computed but are not compared).

Existing ADD/REMOVE set-diff is untouched. Because `body_hash` is
identity-exempt, a body edit alone still produces **no** ADD/REMOVE, and
remove+recreate of a symbol with a different body still produces REMOVE + ADD,
**not** CHANGED.

### Extended call capture

**Python (`change_detector._extract_calls` / `_find_call_names`):**

- Caller discovery becomes class-aware: replace the flat `ast.walk` with an
  explicit contextual walk that tracks the enclosing `ClassDef`. Top-level
  functions → `caller_parent_class=None`; methods → enclosing class name. The
  `skip_owner` nested-function rule is preserved exactly — inner functions
  still get their own caller entries, and outer functions never inherit inner
  calls.
- `_find_call_names` additionally accepts `ast.Attribute` when the receiver
  (`value`) is an `ast.Name` or `ast.Attribute` chain (`self.foo()`,
  `a.b.c()`). Excluded when `value` is an `ast.Call` (`super().foo()`) or the
  attribute name matches `^__.*__$`.
- `async def` callers already flow through the existing
  `(ast.FunctionDef, ast.AsyncFunctionDef)` handling in `_extract_calls` —
  preserved.
- **P2:** async defs are now symbols, so async callers participate in the
  same ADD/REMOVE/CHANGED and call machinery as sync functions.

**Tree-sitter (JS/TS via `_tree_sitter_helpers.py`):**

- `collect_tree_sitter_callers` / `find_tree_sitter_calls_in_body`: track the
  enclosing `class_declaration` name during recursion so `method_definition`
  callers carry `caller_parent_class`.
- Accept `member_expression` targets (`this.foo()`, `obj.bar()`, `a.b.c()`);
  `called_name` = final property name; exclude dunder-style names
  (`^__.*__$`).

**Rust (`rust_scanner.py`):** `_collect_rust_callers` tracks the enclosing
`impl_item` type name; `_find_rust_calls_in_body` accepts `field_expression`
targets (`s.foo()`), dunder-excluded.

**Go (`go_scanner.py`):** `_collect_go_callers` derives `caller_parent_class`
from `method_declaration` receivers (reusing `_extract_receiver_type`);
`_find_go_calls_in_body` accepts `selector_expression` targets (`s.foo()`,
`pkg.Func()`), dunder-excluded.

`DetectedChange` for calls now carries `parent_class=caller_parent_class`
(previously always `None`). `change_sort_key` already handles `parent_class` —
no change to the sort key.

---

## Phase 3: Claims + verifier

**Files:** `nowreck/claims/models.py`, `nowreck/verifier/verifier.py`,
`nowreck/model/provider.py`

| File | Change |
|------|--------|
| `claims/models.py` | `ClaimType` gains `CHANGED_FUNCTION`, `CHANGED_CLASS`; `CLAIM_TYPE_NAMES` gains both strings |
| `verifier/verifier.py` | `_SAME_CHANGE`: `CHANGED_FUNCTION → CHANGED_FUNCTION`, `CHANGED_CLASS → CHANGED_CLASS` |
| `verifier/verifier.py` | `_OPPOSITE_CHANGE` value type widens to `ChangeType \| tuple[ChangeType, ...]`: `CHANGED_FUNCTION → (REMOVE_FUNCTION, ADD_FUNCTION)`, `CHANGED_CLASS → (REMOVE_CLASS, ADD_CLASS)`; existing single-value entries unchanged (backward compatible) |
| `verifier/verifier.py` | The opposite-type match loop checks `change.change_type in target` when the target is a tuple; identical `_fields_match` semantics for each member |
| `nowreck/model/provider.py` | `_CLAIM_TYPE_TO_CHANGE` gains both CHANGED entries |

**Verifier rule updates (documented in the class docstring):**

- **CONFIRMED** — same-type `CHANGED_*` change with matching
  file/symbol/parent_class.
- **CONTRADICTED** — the symbol was added or removed instead of changed.
- **UNVERIFIABLE** — symbol exists with an identical body (fallback; identity
  existence is exhausted by CONFIRMED/CONTRADICTED).

**`_fields_match` needs zero changes** for method calls: the symmetric
`parent_class` compare already exists, and call identity already compares
`caller_name`/`called_name`. Consequences (deliberate, documented — see
strict-matching note in the overview):

- A method-call claim (`parent_class="Calculator"`) matches only evidence
  whose caller is in `Calculator`.
- A plain-call claim (`parent_class=None`) matches only plain-call evidence
  (`caller_parent_class=None`).
- Cross-class claims with a mismatched/missing class → UNVERIFIABLE.
- The existing `CALLS_FUNCTION` caller-exists contradiction check (verifier
  step 2) is untouched — it looks up `ADD_FUNCTION` with
  `symbol_name == claim.caller_name and parent_class == claim.parent_class`,
  which already composes with the strict rule.

**`claims/parser.py` needs no change** — `CLAIM_TYPE_NAMES` is the single
source of truth referenced by the parser.

---

## Phase 4: Prompt + reporters

**Files:** `nowreck/model/prompts.py`, `nowreck/reporter/terminal_reporter.py`,
`nowreck/reporter/sarif_reporter.py`; `nowreck/reporter/junit_reporter.py`
(check only)

### Prompts — `model/prompts.py`

- Add to **both** taxonomy lists (system prompt and v10 prompt):
  `CHANGED_FUNCTION — The body of an existing function was changed.` /
  `CHANGED_CLASS — The body of an existing class was changed.`
- Add a `CHANGED_FUNCTION` example to both JSON-format blocks.
- `_CHANGE_LABELS`: `CHANGED_FUNCTION: "Function changed"`,
  `CHANGED_CLASS: "Class changed"`.
- `_change_detail`: CHANGED function/class changes flow through the existing
  symbol-name branch (`Class.method()` already rendered via `parent_class`);
  call details already generic. No schema change.
- Field notes: state explicitly that `CALLS_FUNCTION` claims about a method
  call must include `parent_class` (strict matching).

### Terminal reporter — `terminal_reporter.py`

- `_CLAIM_TYPE_LABELS` and `_CHANGE_TYPE_LABELS`: add both CHANGED entries.
- `_describe_evidence`: add `CHANGED_FUNCTION` and `CHANGED_CLASS` branches —
  *"Function 'greet' in hello.py: body changed"* /
  *"Class 'Calculator' in calc.py: body changed"*; the call branch **gains
  new behavior** — render `Class.method` (e.g. `Calculator.process` calls
  `validate`) when `caller_parent_class` is present on call evidence
  (currently it renders only `'caller' calls 'called'`).
- `_describe_change` (unexplained) picks up the new label automatically.

### SARIF — `sarif_reporter.py`

- `_SARIF_RULES`: **NW016** `HallucinatedFunctionChange` ("AI claimed a
  function was changed but no body change was detected" — level `error`),
  **NW017** `HallucinatedClassChange` (same wording, class).
- `_CLAIM_TYPE_TO_RULE`: `"CHANGED_FUNCTION": "NW016"`,
  `"CHANGED_CLASS": "NW017"`.
- `_get_message` uses the existing default symbol-name branch for CHANGED
  claims — no new message logic.

### JUnit — `junit_reporter.py`

Uses `claim.type.name` generically throughout; the only special case is
`CALLS_FUNCTION` messaging (unchanged). **Expect zero code changes** — verify
with tests in Phase 5.

---

## Phase 5: Tests (the bulk)

**Files (existing suites extended):** `tests/test_symbol_index.py`,
`tests/test_scanner.py`, `tests/test_change_detector.py`,
`tests/test_verifier.py`, `tests/test_claims.py`, `tests/test_validation.py`,
`tests/test_scan_cache.py`, `tests/test_sarif_reporter.py`,
`tests/test_terminal_reporter.py`, `tests/test_junit_reporter.py`,
`tests/test_prompt_verifier.py`. **Part B adds:** `tests/test_snapshot_manager_git.py`
(new, real-git restore coverage for P1) and async fixtures to
`tests/test_symbol_index.py` / `tests/test_change_detector.py` (P2).

**Existing tests that MUST flip (they pin the old exclusion behavior):**

- `tests/test_change_detector.py::test_attribute_calls_are_excluded` (~line
  362) — `logger.info("started")` is now captured (receiver is a `Name`);
  rewrite as a positive assertion (or keep the name and assert `"info" in
  run_calls`).
- `tests/test_change_detector.py::test_js_attribute_calls_are_excluded`
  (~line 731) — same flip for JS.
- `tests/test_symbol_index.py::test_build_async_functions_are_not_indexed`
  — P2 flips it: async functions ARE indexed now.
- Existing `Symbol.to_dict` snapshots / symbol-shape assertions in
  `test_scanner.py` and `test_symbol_index.py` gain a `body_hash` field —
  update rather than chase.
- **Demo scripts are NOT pytest-gating.** `pyproject.toml` sets
  `testpaths = ["tests"]`; `test_js_samples` / `test_milestone1` /
  `test_ts_samples` / `test_rust_samples` / `test_go_samples` are **not
  collected** (verified — the 809 collected tests are all under `tests/`).
  Their `console.log` / `logger.info` assertions that treat attribute calls
  as excluded are updated for **accuracy**, not because CI fails.

**New-test matrix:**

### Detector

| Scenario | Expected |
|----------|----------|
| Python body edit `"hi"` → `"hello world"` | `CHANGED_FUNCTION` for `greet` |
| Python comment-only / whitespace-only edit | no `CHANGED_*` |
| JS/TS/Rust/Go reformat-only edit (e.g. one-line → multi-line call) | no `CHANGED_*` |
| JS/TS/Rust/Go string quote-style swap | no `CHANGED_*` |
| Python docstring edit | `CHANGED_FUNCTION` (intentional) |
| Line shift within a body | no `CHANGED_*`, no remove+add |
| Method body edit | `CHANGED_FUNCTION` with `parent_class` only — **no `CHANGED_CLASS`** |
| Method add / remove | `ADD_FUNCTION` / `REMOVE_FUNCTION` only — **no `CHANGED_CLASS`** |
| Class decorator / base-class edit | `CHANGED_CLASS` only |
| Class-level statement (field/constant) edit | `CHANGED_CLASS` only |
| Remove + recreate with different body | REMOVE + ADD (never CHANGED) |
| Both hashes `None` (defensive) | no `CHANGED_*` |
| Dunder attr call `obj.__x__()` / `super().__init__()` | not captured |
| `super().foo()` / `f().bar()` (receiver is a call) | not captured |
| `self.foo()`, `obj.bar()`, `a.b.c()`, `this.foo()`, `pkg.Func()`, `s.foo()` (Rust/Go) | captured, `called_name` = final name |
| Nested-function call attribution | unchanged (inner calls stay with inner caller) |
| Top-level `foo()` with `caller_parent_class=None` | captured (regression) |
| `console.log()` / `logger.info()` | captured now (was excluded) |
| **P2:** `async def fetch()` added between snapshots | `ADD_FUNCTION` emitted (was invisible) |
| **P2:** async method body edit | `CHANGED_FUNCTION` with `parent_class` |
| **P2:** sync ↔ async conversion of the same name | **`CHANGED_FUNCTION`** — Symbol identity deliberately excludes the node type, so pre/post symbols are **equal**; `ast.dump` differs (`FunctionDef` vs `AsyncFunctionDef`) → body hash changes. NOT REMOVE+ADD (verified against the actual `Symbol` dataclass: equality is name/type/file/parent_class only) |

### Verifier

| Claim | Evidence | Verdict |
|-------|----------|---------|
| `CHANGED_FUNCTION greet` | `CHANGED_FUNCTION greet` same file | CONFIRMED |
| `CHANGED_FUNCTION greet` | `REMOVE_FUNCTION greet` | CONTRADICTED |
| `CHANGED_FUNCTION greet` | `ADD_FUNCTION greet` | CONTRADICTED |
| `CHANGED_FUNCTION greet` | nothing | UNVERIFIABLE |
| `CHANGED_CLASS` variants | same three verdicts | — |
| `CALLS_FUNCTION caller=process called=validate parent_class=Calculator` | `CALL_DETECTED` with `caller_parent_class=Calculator` | CONFIRMED |
| same claim | `CALL_DETECTED` with `caller_parent_class=None` | UNVERIFIABLE (strict class match) |
| plain `CALLS_FUNCTION caller=main called=run` (no class) | plain `CALL_DETECTED` | CONFIRMED (regression) |
| **P2:** `ADD_FUNCTION caller=fetch_data` where `fetch_data` is `async def` | `ADD_FUNCTION fetch_data` | CONFIRMED (was UNVERIFIABLE) |
| `CHANGED_FUNCTION` claim + `CALLS_FUNCTION` claim both present for a method edit | each matches its own change; no cross-talk | both CONFIRMED, nothing unexplained |

### Other suites

- **Cache:** `CACHE_VERSION=2`; a hand-written v1 cache file is ignored and
  rebuilt; cache round-trip preserves `body_hash`.
- **Cache (P3):** scanning an external dir (`--pre A --post B`, git-archive
  temp dir) creates **no** `.nowreck/` inside it; scanning the CWD creates
  `.nowreck/cache/` there; `.nowreck/` never enters symbol output either
  way; P1 prompt-mode restore removes a `.nowreck/cache/` it created and
  leaves a pre-existing one alone.
- **Parser/validation:** both CHANGED types parse; unknown-type error message
  unchanged; existing 13-type tests untouched.
- **Reporters:** terminal label snapshots for CHANGED evidence; SARIF emits
  NW016/NW017 with correct levels and excludes them from CONFIRMED; JUnit
  produces valid XML with new type names.
- **E2E per language (Pre/Post):** modify a body → `nowreck fix --pre --post`
  → claim CONFIRMED; method-call claim CONFIRMED via real pipeline; a
  hallucinated CHANGED claim → CONTRADICTED.

---

## Phase 6: Docs + version bump (project discipline)

| File | Change |
|------|--------|
| `nowreck/__init__.py` | `__version__` → `"0.16.0"` |
| `nowreck/main.py` | `_BANNER` → `NoWreck v0.16.0` |
| `pyproject.toml` | `version` → `"0.16.0"` |
| `README.md` | Claim table (lines ~600): two new rows `CHANGED_FUNCTION` / `CHANGED_CLASS` with mechanism *structural body-diff*; update "All thirteen" → "All fifteen"; `CALLS_FUNCTION` row + field notes: method calls require `parent_class` |
| `README.md` | Limitations (~line 832): replace the *"`CALLS_FUNCTION` checks direct identifier calls only — it does not resolve `obj.sanitize_input()`"* bullet with the v16 rule (member-chain receivers resolved; receiver-is-a-call and dunder excluded; no semantic call-graph resolution); note CHANGED claims verify body edits, and that Python async functions are now indexed (P2) |
| `README.md` | Roadmap: rows `CHANGED claims (verifiable "I modified X") — ✅ v0.16.0` and `Method/attribute call detection (obj.method(), self.foo()) — ✅ v0.16.0` |
| `use.md` | Claim-type table (~line 429) + `CALLS_FUNCTION` notes gain the two CHANGED types and the method-call `parent_class` requirement |
| `docs/release16.md` | **New** release notes |

---

## What this does NOT do

- No new languages (still Python/JS/TS/TSX/Rust/Go)
- No new CLI flags, exit codes, or `--format` values (the P1 fix reuses
  existing flags; no new CLI surface in v16)
- No `CHANGED_*` claim types for INTERFACE/ENUM/TYPE_ALIAS (deferred — their
  bodies remain existence-checked exactly as today)
- No receiver tracking in call identity (`self.foo()` vs `obj.foo()` both
  yield `called_name="foo"`) — call-site receiver is deliberately not part of
  a claim's identity fields
- No change to the verifier's three-verdict model or the "claim is never its
  own evidence" invariant
- No change to prompts mode's repair/retry loop, model adapters, or provider
  auto-detection
- No formatting-sensitive hashing — the structural hash (with string-quote
  normalization) is the single consistent semantics in all five languages

---

## Part B — Pre-existing fixes folded into v16

Requested during review: the sweep of the existing codebase found one
**must-fix data-integrity bug** (P1), one language-coverage gap that v16's
own hot path touches anyway (P2), one hygiene defect (P3), and one cosmetic
inconsistency (P4). All four are in scope. Their fixes are deliberately
**independent of the CHANGED-claims / method-call features** (Phases 1–6) —
each could land or be reverted on its own.

### P1 — MAJOR: Prompt Mode never restores the working tree on git repos

**Reproduced on disk** (real git repos, real `SnapshotManager` calls):

| Scenario | Observed behaviour |
|----------|--------------------|
| Clean tree; model patch modifies `b.py` | `restore()` returns **False** ("No stash entries found"); the patched `b.py` stays in the tree |
| Dirty tree; patch modifies `b.py`, user edited `a.py` | `restore()` returns True and the user's `a.py` edit returns, **but the patch on `b.py` survives** |

**Root cause** — two compounding defects in `snapshot_manager.py` +
`prompt_verifier.py`:

1. On a **clean** tree `_git_stash()` creates the `.git_stash` sentinel
   directory **without pushing any stash**. `_finalize_repo_state` sees the
   sentinel, calls `_git_stash_pop()`, finds nothing to pop, returns False and
   logs a warning — the applied patch remains in the user's working tree.
2. On a **dirty** tree the strategy is wrong even on success: the model's
   patch is applied **on top of HEAD after the stash was created**, so
   `git stash pop` merges the user's changes back over the *patched* tree.
   Only the temp-copy fallback ever reverts files — the git path never does.

**Why it survived:** every restore test in `tests/test_prompt_verifier.py`
runs against a non-git fixture ("repo_dir is not a git repo"), so only the
temp-copy path is exercised. The git path — what real users hit — has **zero
test coverage**.

**Fix (strategy chosen in review — git-native revert, scoped to applied
files, then pop):**

- `save_before()` records which mode it used instead of overloading the
  sentinel's existence: a clean git repo pushes **no** stash and records
  "clean"; a dirty one pushes and records "stashed".
- `restore()` for a git snapshot reverts **only the patch's applied files**
  to HEAD first (`git checkout HEAD -- <file>` for tracked files;
  delete `<file>` when git reports it untracked — a file the patch created).
  Never a blanket `git checkout -- .` / `git clean` — unrelated untracked
  files and ignored dirs (`.venv`, `node_modules`) are untouchable.
- Then, **only if a stash was actually pushed**, `git stash pop`. With the
  revert-first ordering the same-file case **succeeds by construction**: stash
  push (user's `a.py` dirty → HEAD) → patch edits `a.py` → revert `a.py` to
  HEAD → stash pop restores the user's `a.py`. Patch gone, user edit intact,
  no conflict. The genuinely loud-failure case is the **revert step itself**
  failing (checkout error, file vanished mid-run, `applied_files` stale) —
  that must surface loudly (stash preserved, error returned, never a silent
  warning) rather than silently leaving a partially-reverted tree.
- `restore_after=False` skips the revert but **still pops** a pushed stash
  (the stash holds the user's own uncommitted work — it must return home).
- **`.nowreck/cache/` cleanup (closes the P3 hole):** prompt mode scans the
  CWD, so the cache stays ON there and `.nowreck/cache/` gets written into
  the user's repo during the run — and the git revert only touches
  `applied_files`, so the cache dir would otherwise survive every prompt-mode
  run. `save_before()` therefore records whether `.nowreck/cache/`
  pre-existed; the git revert and the temp-copy restore both remove it when
  it did **not** pre-exist. A pre-existing cache is left untouched.
- The non-git temp-copy path is hardened: the snapshot copy excludes only
  `.git` (drop the `.venv`/`node_modules`/`__pycache__` ignore from the
  **restore-relevant** copy — see P3 for the scan-side exclusion), and
  restore removes exactly the captured entries plus patch artifacts so a
  pre-existing `.venv` can never be deleted-and-not-restored.

**Tests (new `tests/test_snapshot_manager_git.py` + additions):** real `git
init` repos — clean-tree restore removes the patch; dirty-tree restore keeps
user edits and removes the patch; patch-creates-new-file is deleted;
patch-deletes-a-file is restored; patch-touches-the-same-file-the-user-stashed → **succeeds** (user edit
restored intact, patch gone — revert-first ordering makes this a success,
not a conflict); revert-step failure (e.g. `applied_files` stale) → loud
error, stash preserved; `restore_after=False` keeps patch and pops stash.
These are the tests that were missing and let P1 ship.

### P2 — MAJOR: Python `async def` functions/methods are invisible to the symbol index

`SymbolIndexBuilder._process_module` / `_process_class_body` handle only
`ast.FunctionDef`; **`AsyncFunctionDef` is skipped** (pinned today by
`tests/test_symbol_index.py::test_build_async_functions_are_not_indexed`).
Consequences:

- An `ADD_FUNCTION` claim about `async def fetch_data()` is **always
  UNVERIFIABLE**, even when true; removing one is never detected.
- Python is the **only** supported language with this hole — JS/TS `async
  function` and Rust `async fn` parse to the same declaration node types as
  their sync forms and *are* captured. Calls inside async functions are
  already detected, so an async-caller `CALLS_FUNCTION` claim could confirm
  while the function itself could never be ADDed — an internal asymmetry.

**Fix:** treat `AsyncFunctionDef` identically to `FunctionDef` in both
`_process_module` (top level) and `_process_class_body` (async methods).
Async symbols are ordinary `FUNCTION`/`METHOD` symbols — no new
`SymbolType`, and ADD/REMOVE/CHANGED detection flows through unchanged. Flip
the pinning test, update the module docstring and the README/Limitations
lines that claim async is out of scope.

**Why in v16:** Phase 1 rewrites these exact two builder methods for
`body_hash`; adding async handling is nearly free there, and it makes the
new CHANGED-claims feature complete for async bodies. Without it, every
async-edit claim would silently stay UNVERIFIABLE while sync claims work.

### P3 — MEDIUM: scans write `.nowreck/cache/` into the directories they scan

`RepositoryScanner` defaults `use_cache=True` and `ScanCache` persists
`.nowreck/cache/scan_cache.json` **inside the scanned root**. So
`nowreck fix --pre A --post B` silently creates `.nowreck/` inside the
user's snapshot directories, and prompt mode leaves `.nowreck/cache/`
untracked in the working tree (masked today only by the temp-copy restore
wiping it — a path P1 breaks — or by the user's `.gitignore`).

**Fix (decision from review):** enable the persistent cache **only when the
scanned root is the current working directory** (the live project — prompt
mode, or `--pre .`). Scanning external snapshot dirs (`--pre A --post B`,
`--compare` git-archive temp dirs, manual prompt snapshots) runs with the
cache disabled — those directories are inputs, not scratch space, and the
git-archive temps are throwaway anyway. No CLI change; a `use_cache`
decision made at the call sites / scanner entry. The scan-side skip of
hidden dirs is unaffected (`.nowreck` still never enters symbol output).

### P4 — LOW: `CALL_REMOVED` missing from the human label maps

`terminal_reporter._CHANGE_TYPE_LABELS` and `prompts._CHANGE_LABELS` stop
at `CALL_DETECTED`, so a removed call renders as the raw enum name
`"CALL_REMOVED"` in unexplained-change lists and is omitted from the
prompt builder's human-readable change list. One-line additions in each map
— folded into the Phase 4 reporter/prompt edits for free.

### P5 — Test coverage gap (root cause of P1)

The git-stash snapshot path has no integration coverage; 809 green tests
gave false confidence. Fixed by P1's new real-git test file. As a standing
rule for v16: every fix in Part B ships with the test that would have
caught it.

---

## Accepted edges and risks (review pass 2)

These are deliberate or low-probability; each is fixture-verified during
implementation rather than silently relied on.

1. **TS decorator attachment is grammar-dependent.** In the TypeScript
tree-sitter grammar, decorators can appear as siblings *before* a
`method_definition` (or class declaration) rather than as children of it. If
so, a method-decorator edit would land in the class-shell hash and fire
`CHANGED_CLASS`, breaking the disjoint-facts row for TS. Implementation must
inspect the actual CST (fixture: `@dec method() {}`), and the class-shell walk
must skip method-attached decorators as one unit. If the grammar attaches them
inside the member node, nothing extra is needed. **Outcome is test-enforced
one way or the other — no silent divergence between languages.**

2. **Cached `body_hash` has no grammar-version guard.** JS/TS/Rust/Go cache
entries store the hash. If a user upgrades a pinned tree-sitter grammar
package between runs, a re-scan can in principle hash the same source
differently across a pre/post pair that straddles the upgrade → spurious
`CHANGED_*` on every symbol in that file. Accepted: grammar upgrades are rare,
and a full re-parse invalidates on `content_hash` change only when content
actually changed. No action; a manual `.nowreck/cache` clear is the documented
recovery. Python is immune (cache stores source, hash is recomputed per run).

3. **Nested classes are not symbols (pre-existing, one level deep only).**
Editing a nested class body fires `CHANGED_CLASS` on the *outer* class (the
nested `ClassDef` is class-level content of its parent, and is not excluded
like methods). Net effect: nested-class edits stay visible as an outer-class
change — better than invisible, but coarser than method granularity.
Consistent with the existing one-level symbol philosophy; noted so it is a
decision.

4. **TS field arrows / class fields (`foo = () => {}`) and abstract method
signatures have no METHOD symbol** (only `method_definition` is collected).
Editing one fires `CHANGED_CLASS` (it is class-shell content). Same
rationale as #3; symmetric with Python where a lambda/attr assigned in a
class body is class-level content.

5. **`CallEvidence.called_name` should be a required field** (no `= ""`
default) — every call has one; the default only hides construction bugs.

---

## Definition of Done

- [ ] `Symbol` carries `body_hash` (identity-exempt); `to_dict`/`from_dict`
      round-trips it; all five languages populate it structurally
- [ ] Function/method and class-shell hashes are disjoint — method edits
      never emit `CHANGED_CLASS`; class-shell edits never emit
      `CHANGED_FUNCTION`
- [ ] String quote-style swaps produce no `CHANGED_*` in any language;
      reformat/comment edits produce no `CHANGED_*`; real edits always do
- [ ] Cache schema v2 — stale v1 caches ignored and rebuilt with hashes;
      None-hash pairs never fabricate a change
- [ ] Detector captures method/attribute/field/selector calls in all five
      languages with `caller_parent_class`; dunder and receiver-is-a-call
      forms excluded; plain `foo()` capture unchanged
- [ ] Existing exclusion tests flipped (`test_attribute_calls_are_excluded`,
      `test_js_attribute_calls_are_excluded`, sample-dir sweeps); existing
      symbol-shape snapshots updated
- [ ] `ClaimType` + `CLAIM_TYPE_NAMES` gain both CHANGED types; parser and
      validation handle them
- [ ] Verifier: CHANGED confirmed / contradicted-via-ADD / contradicted-via-
      REMOVE / unverifiable; method-call claims match strictly on
      `parent_class`; existing 13 claim types pass unchanged (full regression)
- [ ] Prompts (both copies, incl. `parent_class` field note) + terminal labels
      + SARIF NW016/NW017 updated; JUnit verified unchanged
- [ ] Full new-test matrix above green (detector, verifier, parser, reporters,
      cache, per-language e2e)
- [ ] Version bumped to 0.16.0 in all three sites; `--version` reports it
- [ ] **P1:** git-repo prompt-mode restores the working tree in every case
      (clean/dirty/new-file/deleted-file) via real-git tests; stash-push state
      recorded distinctly from the sentinel; pop failures surface loudly
- [ ] **P2:** `AsyncFunctionDef` indexed as FUNCTION/METHOD in Python
      (top-level + class body); async ADD/REMOVE/CHANGED claims verifiable;
      pinning test flipped; docstrings/README de-scoped
- [ ] **P3:** persistent scan cache enabled only when the scanned root is the
      current working directory; external snapshot dirs scanned cache-free
- [ ] **P4:** `CALL_REMOVED` present in `_CHANGE_TYPE_LABELS` and
      `_CHANGE_LABELS`
- [ ] README claim table + Limitations + roadmap updated; `use.md` updated;
      `docs/release16.md` created
- [ ] Full existing pytest suite still green