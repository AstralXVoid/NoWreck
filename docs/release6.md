# NoWreck v0.6.0 — Verbose Mode Release

**Release date:** August 2026  \
**Previous release:** v0.5.0 (TypeScript Support)  \
**Focus:** `--verbose` mode showing full deterministic evidence per claim — the oldest item on the roadmap. A reporter + CLI feature only: zero changes to scanners, the symbol index, the change detector, the claim parser, the verifier, the 7 claim types, or the JSON schema.

---

## What's new in v0.6.0

### `--verbose` mode ✅

The terminal report already showed, per claim, a one-line verdict and a
one-line `Evidence:` / `Reason:`. Verbose mode adds **full deterministic
detail** for every claim — the exact structural facts the verifier matched:

```bash
nowreck fix --pre <pre-snapshot> --post <post-snapshot> --claims '<json>' --verbose
```

For each CONFIRMED / CONTRADICTED claim, verbose mode shows:

- **`Claim:`** — all eight claim identity fields exactly as `report_json`
  serializes them: `type`, `symbol_name`, `file_path`, `parent_class`,
  `line_number`, `caller_name`, `called_name`, `confidence` (the model's
  original value)
- **`Matched:`** — the complete `DetectedChange` field dump that confirmed
  or contradicted the claim, including the exact `line_number` of the
  matched symbol — a structural fact the one-line view hides
- **`Confidence:`** — the display confidence with the same 100%-for-
  structural-match rule as the claim line

For UNVERIFIABLE claims it shows the full claim dump plus the existing
`Reason:`. Unexplained changes get a full `DetectedChange` field dump
instead of the one-line summary.

Every field shown is **already computed** by the pipeline — verbose mode is
a presentation-layer change only. It proves *why* a verdict was reached by
printing the exact structural fact the verifier matched. Determinism is
unchanged: verbose mode shows more of the same deterministic facts, never
new judgment.

### Scope boundary: JSON unchanged

`nowreck fix --json` already serializes the full `matched_change` for every
result — it was already "verbose" in machine-readable form. `--verbose`
**does not change JSON output**; the CI schema stays frozen. `--verbose`
and `--json` together simply behave like `--json`.

### Non-verbose output: byte-identical

The default (non-verbose) rendering is pinned byte-for-byte to the v0.5.0
output. A golden regression test captures the v0.5.0 rendering and asserts
the current default matches it exactly — the hard gate that proves verbose
mode only *adds* detail.

---

## Test suite growth

| Suite | v0.5.0 | v0.6.0 | Growth |
|-------|--------|--------|--------|
| pytest (project unit tests) | 433 | **449** | **+16** |
| JS comprehensive | 101 tests | 101 tests | — |
| JS multi-round | 80 tests | 80 tests | — |
| TS comprehensive | 42 tests | 42 tests | — |
| TS multi-round | 29 tests | 29 tests | — |
| Milestone 1 checkpoint (4 repos) | Clean | Clean | — |
| Phase 4a demo (17 TS claims) | Clean | Clean | — |
| Live hallucination-catch tests (JS + TS) | PASS | PASS | — |
| ruff | 0 issues | **0 issues** | — |
| basedpyright | 0 errors | **0 errors** | — |

**+16 new pytest tests**, broken down as:

- **Phase 1 (plumbing):** `tests/test_cli.py` — `--verbose` parses, defaults
  to `False`, accepted in both prompt-mode and pre/post-mode paths;
  `tests/test_picker.py` — both picker flows ask the verbose question,
  answer Yes → fresh verbose reporter for that run only (shared reporter
  never mutated), answer No → v0.5.0 rendering path; `tests/test_picker_integration.py`
  — happy-path asserts the question is asked once with the right prompt
- **Phase 3 (rendering):** `tests/test_terminal_reporter.py` — `TestReporterVerbose`
  class (10 tests): full claim field dump, full matched-change dump,
  UNVERIFIABLE claim + reason, unexplained full change dump, `None`-field
  omission, claim-line byte-identity across modes, Evidence-line
  replacement (not duplication), **non-verbose byte-identity to v0.5.0**
  (golden gate), determinism across runs, CONTRADICTED matched-change dump

---

## File changes

### Modified files

| File | What changed |
|------|-------------|
| `nowreck/cli.py` | `--verbose` flag on `fix` (`store_true`, default `False`, help notes no-op with `--json`) |
| `nowreck/reporter/terminal_reporter.py` | `__init__(colour=True, verbose=False)`; claim/unverifiable/unexplained sections branch on verbose; new `_append_verbose_claim_detail` + `_append_verbose_change_detail` helpers |
| `nowreck/main.py` | Reporter constructed once as `TerminalReporter(colour=colour, verbose=args.verbose)` |
| `nowreck/picker.py` | `_ask_verbose()` helper; both flows (`_run_verification`, `_run_pre_post`) ask before rendering; Yes → fresh `TerminalReporter(colour=True, verbose=True)` per run |
| `tests/test_cli.py` | 3 new flag tests |
| `tests/test_picker.py` | 2 new verbose-choice test classes (3 tests) + confirm-mock on 8 existing tests |
| `tests/test_picker_integration.py` | Happy-path asserts verbose question; confirm-mock on 3 pre_post tests |
| `tests/test_terminal_reporter.py` | `TestReporterVerbose` class (10 tests) |
| `README.md` | Roadmap: `--verbose` marked done in v0.6.0; TSX marked v0.7.0 |
| `docs/nowreck-v6-scope.md` | Full scope document tracing the increment |
| `docs/release6.md` | This release notes file |

### New files

| File | What it covers |
|------|---------------|
| `docs/nowreck-v6-scope.md` | Full scope document (Phase 4 output) |
| `docs/release6.md` | This release notes file |

### Unchanged

- Python / JavaScript / TypeScript scanners — **0 changes**
- Symbol index, change detector, claim parser, claim verifier — **0 changes**
- JSON output schema — **0 changes**
- Claim types — exactly the same 7
- Non-verbose terminal output — **byte-identical** (golden-tested)
- All milestone repos — **0 changes**
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
# → nowreck 0.6.0
```

---

## Definition of Done ✅

1. `nowreck fix --pre <empty> --post <pure-ts repo> --verbose` shows, for a
   hand-written claim set, the full claim identity and the exact
   `DetectedChange` fields that confirmed/contradicted it — matching
   reality.
2. `nowreck fix ...` (without `--verbose`) output is byte-identical to
   v0.5.0 for the same inputs.
3. The full existing test battery passes, plus the new verbose tests.
4. ruff: 0 issues, basedpyright: 0 errors.

**Result (verified live):** ran the real CLI against the pure-ts milestone
repo (empty pre → full post, 17 hand-written claims covering all 7 claim
types). Verbose output showed every `Matched:` block with `line_number`
values cross-checked against the actual source — all 12 definitions
matched exactly (e.g. `formatGreeting` at line 9 of `greeter.ts`,
`Calculator` at line 3 of `calculator.ts`, `AdminUser` at line 20 of
`models.ts`). All 75 non-verbose output lines are preserved verbatim in
verbose mode (only the one-line `Evidence:` / unexplained summaries are
replaced by detail blocks, per design). Milestone demos pass on all 4
repos; 45/45 milestone checkpoint; full battery green.

---

## What's next

The roadmap remains focused on narrow, testable increments, each with its
own scope document and phase-by-phase build discipline. **v0.7.0 is TSX
(`.tsx` files)** — decided during the v6 planning conversation; it gets its
own scope document when work begins.

- TSX (`.tsx` files) — separate TSX grammar + JSX handling — **v0.7.0 (decided)**
- `explanation` field on claims — model + prompt change (README documents
  it, the `Claim` model doesn't have it yet) — deferred from v6
- Scan-summary expansion in verbose mode (per-language file counts) —
  deferred from v6; verbose is about claim evidence, not scan statistics
- Additional model providers (Anthropic, Gemini)
- Caching for large repositories
- CI/CD integration
