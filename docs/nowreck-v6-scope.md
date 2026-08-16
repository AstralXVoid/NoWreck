# NoWreck — v6 Scope (--verbose Mode Only)

**Status:** Draft. Local development only — not published, not merged into the
public repo, until proven and deliberately released. Same discipline as v2,
v3, v4, and v5.

## Principle

Same rule as every prior increment: one small thing at a time, proven before
expanding. v5 (TypeScript) is done and its Definition of Done is fulfilled.
v6 is **`--verbose` mode only. Nothing else.**

TSX (`.tsx` files) was decided during the v6 planning conversation as the
**v7 increment** — it gets its own scope document, later, only after verbose
mode is proven working. The same applies to caching, new claim types, and
additional model providers.

## What this increment actually is

`--verbose` is the oldest item on the roadmap ("`--verbose` mode showing full
deterministic evidence per claim"). It is a **reporter + CLI feature** — it
touches no scanner, no symbol index, no change detector, no claim parser, no
verifier, and no claim types. The determinism contract is unchanged: verbose
mode shows *more of the same deterministic facts*, never new judgment.

### What verbose mode shows

The current terminal report already renders, per claim:

- `✓/✗/? CLAIM_TYPE symbol → file  (conf: 100%)`
- `    Evidence: <one-line description of the matched change>`
- `    Reason: <why nothing matched>` (UNVERIFIABLE only)

Verbose mode adds **full deterministic detail** for every claim:

- **Claim identity** — all eight fields exactly as `report_json` already
  serializes them today (`_claim_to_dict`): `type`, `symbol_name`,
  `file_path`, `parent_class`, `line_number`, `caller_name`,
  `called_name`, `confidence`. The `confidence` here is the **model's**
  original value — a different number from the display confidence on
  the claim line (see Phase 2).
- **Matched change** (CONFIRMED / CONTRADICTED) — the complete
  `DetectedChange` field dump: `change_type`, `file_path`, `symbol_name`,
  `parent_class`, `line_number`, `caller_name`, `called_name`
- **UNVERIFIABLE detail** — the full claim dump plus the existing reason
- **Unexplained changes** — full `DetectedChange` field dump instead of the
  one-line summary

Every field shown is already computed by the pipeline — verbose mode is a
**presentation layer** change only. It proves *why* a verdict was reached by
printing the exact structural fact the verifier matched.

### Scope boundary: JSON output

`nowreck fix --json` already serializes the full `matched_change` for every
result — it is already "verbose" in machine-readable form. Therefore
`--verbose` **does not change JSON output**. This keeps the change minimal
and the CI schema frozen. `--verbose` and `--json` together simply behave
like `--json` (verbose detail is the JSON default). This boundary is
deliberate and documented here so it is not re-litigated mid-build.

### Scope boundary: interactive picker

The picker renders reports through the same `TerminalReporter`. Verbose mode
is available there as a picker option (a yes/no prompt in the verification
flow), not as a new top-level menu item. This keeps the picker's menu
structure unchanged (v3–v5 principle: CLI/picker structure is stable).

One structural constraint drives the design: `run_picker()` constructs a
single reporter and shares it across menu iterations, so verbose cannot be
set at construction time there. Phase 1 resolves this by asking the
question per run and building a fresh verbose reporter only when the user
answers Yes — the shared reporter is never mutated and the default (No)
path stays byte-identical to v0.5.0.

## Mandatory build discipline for this increment

Same rules as v2–v5, without exception:

1. **Build in phases, one component at a time**: CLI flag → reporter
   rendering → tests. Do not write code for a later phase before the current
   phase is complete, tested, and reviewed.
2. **No phase is "done" until it's been shown to work on a hand-built test
   file** — with actual output demonstrating the verbose detail is captured
   correctly, AND demonstrating that the existing test battery (433 pytest +
   42 TS comprehensive + 29 TS multi-round + 101 JS comprehensive + 80 JS
   multi-round + milestone checkpoint) still passes.
3. **Stop and report after each phase** — a human checkpoint between phases
   is required, not optional.
4. **If asked to build multiple phases in one response, refuse and ask which
   single phase to focus on first.**

## What's in scope for v6

**`--verbose` mode in the terminal report, wired through the CLI and picker.**

### Phase 1: CLI flag plumbing

- `nowreck fix --verbose` — new boolean flag in `nowreck/cli.py`
  (`action="store_true"`, `default=False`), documented in help text
- Thread the flag through `nowreck/main.py`. There is exactly **one**
  reporter construction point — `handle_fix` — which becomes
  `TerminalReporter(colour=colour, verbose=args.verbose)`.
  `_handle_prompt_mode` already receives that reporter as a parameter
  and needs no change; `_detect_and_verify` is untouched (verbose is
  presentation-only).
- Thread through `nowreck/picker.py` (see the picker boundary above):
  - Both flows (`_run_verification`, `_run_pre_post`) ask the yes/no
    question "Show full evidence per claim?" (default: No) right before
    rendering the report
  - Answer No → render with the existing shared reporter (byte-identical
    to v0.5.0)
  - Answer Yes → build a fresh `TerminalReporter(colour=True,
    verbose=True)` for that run only and render with it; the shared
    reporter is never mutated
  - `_view_last_report` needs no change — it re-reads whatever text was
    saved, verbose or not
- `TerminalReporter.__init__` gains `verbose: bool = False`. Every
  existing call site uses keyword args (`colour=...`), so this is
  non-breaking.

### Phase 2: Reporter verbose rendering

In `nowreck/reporter/terminal_reporter.py`:

- The claim line itself is unchanged. In verbose mode, the one-line
  `Evidence:` / `Reason:` line under it is **replaced** by a multi-line
  detail block — exactly one rendering path per mode, never both:
  - `Claim:` followed by every non-`None` claim field (this includes the
    model's original `confidence` — distinct from the display confidence
    below)
  - `Matched:` followed by every non-`None` matched-change field
  - `Confidence: <verifier confidence>` — the display rule already used
    today: 100% for CONFIRMED/CONTRADICTED, model confidence for
    UNVERIFIABLE
- `_append_claim_section` and `_append_unverifiable_section` branch on
  `self._verbose` to choose the path. New private helpers
  (`_append_verbose_claim_detail`, `_append_verbose_change_detail`) build
  the detail block; the existing non-verbose helpers are **not modified**.
- `_append_unverifiable_section` — verbose: full claim dump + the existing
  `Reason:` line
- `_append_unexplained_section` — verbose: full `DetectedChange` field
  dump per change instead of the one-line summary
- The non-verbose path must render **byte-identical** output to v0.5.0 —
  this is a hard regression gate
- All new lines use existing `_colourise` / `_ANSI_DIM` helpers — no new
  colour semantics

### Phase 3: Tests

New test coverage, following the existing `tests/` structure:

- `tests/test_terminal_reporter.py`:
  - Verbose output contains all claim identity fields for CONFIRMED
  - Verbose output contains the full matched-change dump
  - Verbose output for UNVERIFIABLE shows full claim + reason
  - Verbose output for unexplained changes shows full change dump
  - **Non-verbose output (`verbose=False`) is byte-identical to the
    v0.5.0 rendering for the same report** (regression gate)
  - Verbose output is deterministic across runs
- `tests/test_cli.py`:
  - `--verbose` flag parses and defaults to `False`
  - `--verbose` is accepted in both prompt-mode and pre/post-mode paths
- `tests/test_picker.py` / `test_picker_integration.py`:
  - Picker flows ask the verbose question and, when Yes, render with a
    fresh verbose reporter; when No, output is byte-identical to v0.5.0
  - Detection-only `_run_pre_post` (no claims) also asks and honours the
    answer (verbose unexplained-change dumps)

### Phase 4: Milestone checkpoint

Run the full pipeline with `--verbose` on the existing milestone repos
(`test_milestone1/`), verify the printed evidence matches the real detected
changes, and confirm the non-verbose output is unchanged. Re-run the full
test battery.

### Deferred (documented, not built)

- **TSX (`.tsx` files)** — decided as the **v7 increment** in the v6 planning
  conversation. Separate scope doc.
- **JSON schema changes** — verbose does not touch `report_json`.
- **New claim types** — unchanged (the same 7).
- **`explanation` field on claims** — the README documents `explanation` as
  an accepted claim field, but the `Claim` model has no such field today.
  Adding it (and surfacing it in verbose mode) is a **model + prompt change**
  — out of scope for v6, noted here for a future increment.
- **Scan-summary expansion** — showing per-language file counts in verbose
  mode is tempting but out of scope; verbose is about *claim evidence*, not
  scan statistics. Deferred.

## Claim types: unchanged

Exactly the same 7 claim types as v3/v4/v5. `--verbose` renders the evidence
for them; it does not add or alter any.

## Dependencies

**None.** No new packages. `--verbose` uses only the existing
`TerminalReporter`, `Claim`, and `DetectedChange` data shapes.

## Files (new / modified)

| File | What it covers |
|------|---------------|
| `tests/test_terminal_reporter.py` | Verbose rendering, field dumps, non-verbose byte-identity regression gate |
| `tests/test_cli.py` | `--verbose` flag parse/default/acceptance |
| `tests/test_picker.py`, `tests/test_picker_integration.py` | Picker verbose option plumbing |
| `test_milestone1/test_milestone1_checkpoint.py` | Unchanged (regression only) |
| `docs/release6.md` | Release notes (Phase 4) |

## Unchanged

- Python / JavaScript / TypeScript scanners — **0 changes**
- Symbol index, change detector, claim parser, claim verifier — **0 changes**
- JSON output schema — **0 changes**
- Claim types — **0 changes**
- Non-verbose terminal output — **byte-identical** (hard gate)
- All milestone repos — **0 changes**

## Definition of done

1. `nowreck fix --pre <empty> --post <pure-ts repo> --verbose` shows, for a
   hand-written claim set, the full claim identity and the exact
   `DetectedChange` fields that confirmed/contradicted it — matching reality.
2. `nowreck fix ...` (without `--verbose`) output is byte-identical to
   v0.5.0 for the same inputs.
3. The full existing test battery passes, plus the new verbose tests.
4. ruff: 0 issues, basedpyright: 0 errors.

## Explicitly not a roadmap

This covers exactly one thing — `--verbose` mode, same claim types,
phase-by-phase, human-checked at every step. When it's done and proven, the
next increment (**TSX, decided as v7**) gets its own equally narrow scoping
conversation.
