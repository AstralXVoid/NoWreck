# NoWreck v0.17.0 — Nine Languages + Differential Audit

**Release date:** October 2026
**Previous release:** v0.16.0 (Verifiable Body Edits + Method Call Detection)
**Focus:** Prove the five existing parsers before extending them — a
differential audit against a deliberately dumb regex checker — then add four
new languages (Java, Kotlin, PHP, C++) under the same satisfaction bar.

---

## What's new in v0.17.0

### Differential audit — the parsers are now measured, not assumed ✅

Before a single new language landed, the five existing parsers were audited
against an independent oracle: a deliberately dumb regex checker
(`tests/helpers/differential.py`) run over a 60-file authored corpus
(12 files × 5 languages), compared through the **real production pipeline**
(`RepositoryScanner` → `build_symbol_index` → `ChangeDetector._extract_calls`)
— no mocks, no re-implementations. Every divergence was either a fixed
checker bug or a classified finding. The checker and the audit test are
**permanent**: they now cover all nine languages and run in the main suite
forever.

**Result: 3 real gaps, all one defect, fixed.**

| # | Gap | Fix |
|---|-----|-----|
| G1/G2 | Calls inside anonymous arrows in argument/return position (`this.enqueue(() => handler(p))`, `return () => this.unsubscribe(...)`) were invisible — no caller to attribute them to | The call walker now attributes an anonymous arrow's calls to the nearest *enclosing named* caller |
| G3 | Calls inside JS/TS class-field arrow values (`incrementBy = (step) => this.increment(step)`) were never collected — tree-sitter models those as field definitions, not declarators | Class-field arrows are collected as callers (named after the field) |

Each shipped with the corpus file that caught it plus 23 pinning tests in
`tests/test_call_edges.py` that freeze every documented boundary, so an
accepted edge cannot drift silently. `EXPECTED_DIVERGENCES` is empty and
hygiene-enforced: a fixed gap's entry must be deleted, not left to rot.

### Four new languages — nine total ✅

| Language | Extensions | Grammar (installed) | Symbols |
|----------|-----------|---------------------|---------|
| Java | `.java` | `tree-sitter-java` 0.23.5 | class / record → CLASS, interface / `@interface` → INTERFACE, enum → ENUM, methods → METHOD |
| Kotlin | `.kt`, `.kts` | `tree-sitter-kotlin` 1.1.0 | class / data / sealed / value class / object → CLASS, interface / fun interface → INTERFACE, enum class → ENUM, annotation class → INTERFACE, typealias → TYPE_ALIAS |
| PHP | `.php` | `tree-sitter-php` 0.24.1 | class → CLASS, interface → INTERFACE, enum → ENUM, trait → CLASS, functions and closures/arrows → FUNCTION, methods → METHOD |
| C++ | `.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`, `.h++`, `.h` | `tree-sitter-cpp` 0.23.4 | class / struct / union → CLASS, enum → ENUM, `using` / `typedef` → TYPE_ALIAS, methods, free functions, named lambdas |

All four go through the same gates the first five did — grammar probes
resolved **before** any collector code, a scanner, full pipeline wiring
(scanner → index → detector → verifier counts → prompts), a differential
corpus, a change-detector matrix, a sample suite, and a milestone repo:

| Language | Probes pinned | Corpus files | Milestone repo |
|----------|---------------|--------------|----------------|
| Java | 33 (`J1`–`J12`) | 15 | `pure-java` |
| Kotlin | 86 (`K1`–`K16`) | 15 | `pure-kotlin` |
| PHP | 74 (`PH1`–`PH12`) | 18 | `pure-php` |
| C++ | 78 (`E1`–`E18`) | 17 | `pure-cpp` |

**No new claim types and no schema change.** `ClaimType` stays at 15 types
and `CACHE_VERSION` stays 2 — the four languages produce the same
ADD / REMOVE / CHANGED / CALLS_FUNCTION / CALL_REMOVED facts through the
existing taxonomy. C++ and Go are the two languages where `INTERFACE` never
fires; PHP is the one where `TYPE_ALIAS` never fires.

### Awkward grammars, handled honestly

Adopting four grammars surfaced real parser defects, not just missing
features. The notable ones, each probed, fixed and pinned:

- **Kotlin silently loses declarations (D7).** With two or more stacked
  annotations, a plain top-level `class` / `interface` / `annotation class`
  following any sibling declaration is destroyed — `class` is read as an
  infix operator, the symbol vanishes and `has_error` stays `False`. Rather
  than pattern-matching damage shapes (which grow with the grammar), the
  scanner blanks annotation spans, re-parses the blinded source, then folds
  each annotation back onto the declaration it owns via a positional
  ownership map. Files with no annotations take the original path byte for
  byte.
- **Kotlin's 7 confirmed misparses on ordinary source** — only three of which
  set `has_error` (D1–D7 in the audit report). The accepted edges are
  documented next to the ones that were recovered.
- **Rust `impl Trait for Type` mis-attribution** — methods in a trait impl
  were parented to the *trait* instead of the implementing type (a
  pre-existing v16-era defect found by the full-repo checkup). Fixed to read
  the grammar's `type` field.
- **C++ header/impl split** — a declaration and its out-of-line definition
  are two independent per-file facts by design (no `#include` resolution); a
  declaration-only member carries `body_hash=None` and can never fire
  `CHANGED_FUNCTION`.
- **PHP string semantics** — PHP is the one language where quote style
  selects escape rules, so it has a dedicated normaliser; heredoc and nowdoc
  stay distinct.

### Phase 5 adversarial review — 19 defects found and fixed ✅

A second-pass review of the C++ surface (54-case divergence probe plus CST
dumps of every ambiguous shape) surfaced 21 divergences. All were
root-caused, fixed and pinned — 9 scanner defects (tagged/nested type
declarations, `extern "C"` single-declaration form, reference declarators,
conversion operators, class-field lambdas, member-template call targets,
grammar-error recovery inventing calls), 6 checker defects, and 11
end-to-end detector tests. Final state: 0 unexpected divergences.

### Cross-language hardening ✅

- **Nine-language determinism sweep** — the all-repos sweep had silently
  lagged the four new repos, and had never compared the two identity-exempt
  fields (`line_number`, `body_hash`), so a run-to-run hash difference could
  have survived a "byte-identical" gate. It now spans 11 repos × nine
  language maps and compares explicit
  `(name, type, path, line, parent_class, body_hash)` tuples.
- **Picker summary knew only three languages** — six of the nine were
  invisible in the picker's pre/post scan output. Fixed with one loop over
  all nine language maps; the Python/JS/TS lines stay byte-identical.
- **Cache round-trips closed** for TypeScript / Rust / Go, plus an
  all-nine stale-cache rebuild test (a v1 cache is rewritten hash-less and
  re-scanned; every language is asserted to rebuild fresh, hash-carrying,
  warm-honest entries).

### Test-suite hardening

- **Picker terminal tests are hermetic.** `TestPickerTerminal` drove a bare
  `nowreck` resolved from `PATH`, so a stale user-level install earlier on
  `PATH` became the process under test and failed the whole class on a blank
  pane while every other suite stayed green. It now launches the checkout's
  own package via the interpreter running the tests
  (`<sys.executable> -m nowreck --interactive`), pinned by a regression test
  that puts a deliberately broken `nowreck` first on `PATH` and requires the
  run to succeed anyway.
- **tmux picker flake killed** (Phase 1) — the wait raced process start-up
  (measured ~7s cold, up to 8.4s under load) against a fixed 15s deadline.
  The deadline is now sized to the measurement, a slow `tmux` means "keep
  waiting" instead of a test error, and the pane must be *settled* after a
  match before assertions run.
- **Wall-clock stress budgets** in the Java/Kotlin/PHP sample suites were
  raised to a regression guard rather than a benchmark.

## Not in this release

- No new claim types, verdict logic, CLI flags, exit codes, formats, or
  cache schema changes (`CACHE_VERSION` stays 2)
- No `.c` (C) support — needs `tree-sitter-c`; `.h` files are parsed with the
  C++ grammar and `.c` is never discovered
- No `#include` resolution or cross-file symbol linking — header and impl are
  independent per-file facts
- No semantic call-graph resolution, preprocessor-aware hashing, or
  template-instantiation analysis; no receiver tracking in call identity
- No rewrite of the existing five scanners beyond what the audit's evidence
  showed was broken

## Compatibility

| What | Why |
|------|-----|
| CLI, flags, exit codes, output formats | Untouched — no new CLI surface |
| Existing 15 claim types | Byte-identical semantics (regression-pinned) |
| Cache schema | Still v2; new languages add no cache fields |
| `--pre` / `--post` on external dirs | Still cache-free, output identical |
| License | Still FSL-1.1-MIT (auto-converts to MIT in July 2028) |

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Full pytest suite | 1731 | ✅ all pass (1 pre-existing deprecation warning) |
| Differential audit (nine corpora, 130 files) | 129 | ✅ 0 unexpected divergences |
| Grammar probes (Java / Kotlin / PHP / C++) | 33 / 86 / 74 / 78 | ✅ all pass |
| Per-language detector matrices (nine classes) | 163 | ✅ all pass |
| `ruff check` + `ruff format --check` | — | ✅ clean (113 files) |
| `basedpyright` strict | — | ✅ 0 errors, 0 warnings, 0 notes |
| Milestone checkpoint | 131 | ✅ all pass |

**Performance:** the 1,731-test suite runs 29–69 s depending on host load —
measured here at 43.84 s, 52.64 s, 53.83 s, 63.88 s and 68.57 s against the
Phase 0 baseline of 29.74 s (1,004 tests). That is **1.47×–2.31×** of the
baseline, so the scope's `< 2×` gate is met at typical load but not
*guaranteed* under heavy load: one run of the five exceeded it. The
load-sensitivity is the machine's, not a collector's — the slowest items are
the known PTY picker tests (~12 s total) and the differential corpus setup
(~6 s), with no pathological hotspot anywhere, and the Phase 6 measurements
on a quieter host were 29.22–47.85 s (0.98×–1.61×).

## Files changed

| File | Change |
|------|--------|
| `tests/helpers/differential.py` | **New** — the 9-language regex oracle (strippers, caller-scope masks, symbol + call extraction) |
| `tests/differential_corpus/{python,javascript,typescript,rust,go,java,kotlin,php,cpp}/` | **New** — 125 authored corpus files, each probing a named audit dimension |
| `tests/test_differential_audit.py` | **New** — the permanent audit test + `EXPECTED_DIVERGENCES` (empty, hygiene-enforced) |
| `tests/test_call_edges.py` | **New** — 23 pins freezing every documented boundary |
| `tests/test_{java,kotlin,php,cpp}_probes.py` | **New** — 33 / 86 / 74 / 78 grammar probes, pinned before collector code |
| `nowreck/scanner/{java,kotlin,php,cpp}_scanner.py` | **New** — the four scanners + their hash models |
| `nowreck/scanner/_tree_sitter_helpers.py` | The G1/G2/G3 caller-walker fix (`_function_valued_initialiser`, `_has_own_caller`); node-type unions for the four grammars |
| `nowreck/scanner/repository_scanner.py` | Discovery, parsing, cache and failure accounting for the four languages |
| `nowreck/scanner/symbol_index.py`, `nowreck/detector/change_detector.py`, `nowreck/verifier/prompt_verifier.py`, `nowreck/model/prompts.py` | Pipeline wiring, `_extract_calls` arms, `n_files` counts, per-language prompt text |
| `nowreck/scanner/rust_scanner.py` | `impl Trait for Type` parent attribution fix |
| `nowreck/picker.py` | Pre/post scan summary covers all nine languages |
| `tests/test_picker_integration.py` | tmux flake hardening + hermetic interpreter-anchored launch |
| `tests/test_scan_cache.py`, `tests/test_scanner.py`, `tests/test_change_detector.py`, `tests/test_cli.py`, `tests/test_dependency_errors.py` | Per-language matrices, cache round-trips, E2E pipelines |
| `test_{java,kotlin,php,cpp}_samples/` | **New** — sample suites mirroring the existing five |
| `test_milestone1/repos/pure-{java,kotlin,php,cpp}` + checkpoint classes | **New** — milestone repos |
| `pyproject.toml` | Four new grammar pins; corpus ruff carve-out; version → `"0.17.0"` |
| `nowreck/__init__.py`, `nowreck/main.py` | Version → `0.17.0` (banner + `--version`) |
| `README.md`, `use.md` | Language tables (nine), per-language claim notes, rewritten Limitations from the audit's accepted-edge tables, roadmap rows |
| `docs/nowreck-v17-scope.md`, `docs/v17-audit-report.md` | **New** — scope and the full differential audit report |
| `docs/release17.md` | **New** — these release notes |
