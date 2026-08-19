# NoWreck v0.10.0 — Independent Verification Architecture

**Release date:** August 2026
**Previous release:** v0.9.0 (Rust + Go Language Support)
**Focus:** Fix the Prompt Mode circular confirmation loop. The single most important architectural weakness identified by review — the model was verifying its own claims.

---

## What's new in v0.10.0

### Independent verification for Prompt Mode ✅

Prompt Mode no longer derives "observed changes" from the model's own claims. The circular confirmation loop is eliminated.

**Before (v0.9.0 — circular):**
```
Model claims → claims_to_changes(claims) → verify(claims, fake_changes) → MATCH
```

**After (v0.10.0 — independent):**
```
Before state → Model applies patch → After state → ChangeDetector.detect(before, after) → verify(claims, real_changes) → verdict
```

The fundamental invariant:

> A model claim must never be used as the source of evidence for verifying that same claim.

### SnapshotManager ✅

New `SnapshotManager` captures repository state before and after the model makes changes. Supports:
- Direct scan (no copy needed)
- Git stash (preferred for git repos)
- Temp directory copy (fallback)

### PromptModeVerifier ✅

New `PromptModeVerifier` orchestrates the full independent verification flow:
1. Capture BEFORE state
2. Get claims + patch from model
3. Apply patch to working tree
4. Capture AFTER state
5. Run `ChangeDetector.detect(before, after)` — independent evidence
6. Verify claims against observed changes
7. Restore working tree

### Model prompt v10 ✅

New system prompt asks the model to return both structured claims AND a unified diff patch:
```json
{
  "claims": [...],
  "patch": "--- a/src/app.py\n+++ b/src/app.py\n..."
}
```

### Security hardening ✅

API keys are now masked in all output paths:
- Error messages: `_mask_key()` applied
- Failed response saves: messages sanitized
- JSON output: never includes key material

### CLI changes ✅

```bash
# Independent verification (automatic):
nowreck fix "Add email validation to auth.py"

# Manual snapshots (reuse --pre/--post):
nowreck fix "Add email validation" --pre ./before --post ./after

# Pre/Post mode (unchanged):
nowreck fix --pre ./before --post ./after
```

No new flags — reuses existing `--pre`/`--post` for manual snapshots.

---

## What's deprecated in v0.10.0

| What | Why | Removal |
|------|-----|---------|
| `PromptBuilder.claims_to_changes()` | Creates circular confirmation loop | v11 |
| `PromptBuilder.for_prompt()` | Uses old prompt without patch request | v11 |
| `PROMPT_SYSTEM_PROMPT` | Replaced by `PROMPT_SYSTEM_PROMPT_V10` | v11 |

All deprecated code still works — warnings added. Will be removed in v11.

---

## What's unchanged

| What | Why |
|------|-----|
| Pre/Post mode | Already independent — untouched |
| `ClaimVerifier.verify()` | Already correct |
| `ChangeDetector.detect()` | Already correct |
| `RepositoryScanner` | Already correct |
| `SymbolIndex` | Already correct |
| All 13 claim types | No new types needed |
| JSON schema (structure) | Same fields, new optional metadata |
| All existing tests | Must pass unchanged |

---

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Existing pytest | 532 | ✅ all pass |
| New security tests | 12 | ✅ all pass |
| New prompt verifier tests | 19 | ✅ all pass |
| New CLI tests | 2 | ✅ all pass |
| Snapshot manager tests | 19 | ✅ all pass |
| ruff | 0 issues | ✅ clean |

---

## Circularity tests (critical)

| Test | What it proves |
|------|----------------|
| `test_claim_not_used_as_evidence` | False claim → UNVERIFIABLE, not CONFIRMED |
| `test_false_claim_contradicted` | False ADD when REMOVED → CONTRADICTED |
| `test_honest_claim_confirmed` | True ADD when added → CONFIRMED |
| `test_multiple_claims_partial_match` | Each claim evaluated independently |
| `test_no_evidence_produces_unverifiable` | No state change → all UNVERIFIABLE |

---

## Files modified

| File | Change |
|------|--------|
| `nowreck/scanner/snapshot_manager.py` | **New** — SnapshotManager |
| `nowreck/verifier/prompt_verifier.py` | **New** — PromptModeVerifier, PatchApplier |
| `nowreck/model/prompts.py` | Added `PROMPT_SYSTEM_PROMPT_V10`, deprecated old prompt |
| `nowreck/model/provider.py` | Added `changes_from_prompt_v10()`, `_mask_key()` |
| `nowreck/claims/models.py` | Added `patch` field to `ParseResult` |
| `nowreck/claims/parser.py` | Extract `patch` from model JSON |
| `nowreck/main.py` | `_handle_prompt_mode()` uses PromptModeVerifier |
| `nowreck/cli.py` | Reuses `--pre`/`--post` for manual snapshots |
| `nowreck/reporter/terminal_reporter.py` | Added `report_v10()`, `report_json_v10()` |
| `tests/test_snapshot_manager.py` | **New** — 19 tests |
| `tests/test_prompt_verifier.py` | **New** — 19 tests |
| `tests/test_security.py` | **New** — 12 tests |
| `tests/test_model.py` | Extended with v10 prompt tests |
| `tests/test_cli.py` | Extended with prompt + pre/post tests |

---

## Definition of Done

| Criterion | Status |
|-----------|--------|
| Prompt Mode uses independent verification | ✅ |
| Circularity test proves verifier cannot self-verify | ✅ |
| All acceptance criteria pass | ✅ |
| Pre/Post mode unchanged | ✅ |
| All existing tests pass | ✅ |
| ruff: 0 issues | ✅ |
| JSON output includes evidence source | ✅ |
| API keys masked in all output paths | ✅ |
| Documentation updated | ✅ |

---

## Upgrade notes

No breaking changes. All existing commands work identically.

To use independent verification:
```bash
# Just run as usual — v10 is automatic
nowreck fix "Add email validation to auth.py"
```

To provide manual before/after:
```bash
nowreck fix "Add email validation" --pre ./before --post ./after
```
