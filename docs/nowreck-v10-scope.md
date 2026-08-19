# NoWreck — v10 Scope (Independent Verification Architecture)

**Status:** Draft. Local development only — not published, not merged into the
public repo, until proven and deliberately released. Same discipline as v2
through v9.

## Principle

Same rule as every prior increment: one small thing at a time, proven before
expanding. v9 (Rust + Go) is done and its Definition of Done is fulfilled.
v10 is **fixing the Prompt Mode circularity problem** — the single most
important architectural weakness identified by review.

## The Problem

Prompt Mode currently has a circular confirmation loop:

```
User Prompt → Model → Claims → claims_to_changes(claims) → verify(claims, changes)
```

The `changes` are derived FROM the `claims` via `PromptBuilder.claims_to_changes()`.
The verifier then checks `claims` against `changes` — which were created from the
same claims. This is not independent verification. The evidence is contaminated
by the claim it is supposed to verify.

### Concrete example

```python
# ModelProvider.changes_from_prompt() — CURRENT (broken)
def changes_from_prompt(self, prompt: str) -> ModelResult:
    messages = PromptBuilder.for_prompt(prompt)
    result = self._call_with_retry(messages)
    changes = PromptBuilder.claims_to_changes(result.claims)  # ← CIRCULAR
    return ModelResult(claims=result.claims, changes=changes, ...)
```

If the model claims "I added function validate_email to auth.py", the code
converts that claim into a `DetectedChange(ADD_FUNCTION, "validate_email", "auth.py")`,
then the verifier finds the matching change and reports CONFIRMED. The model
just verified its own claim.

## Root Cause

Prompt Mode has two independent data sources but only uses one:

1. **Model claims** — what the model says happened
2. **Actual repository state** — what actually changed

Currently, source #2 is never independently observed in Prompt Mode. The
`claims_to_changes()` bridge fabricates "observed" changes from the model's
own words.

Pre/Post mode already solves this correctly — it scans two directory snapshots,
detects structural changes via `ChangeDetector.detect()`, and verifies claims
against independently observed evidence. v10 unifies Prompt Mode to use the
same independent evidence path.

## Architectural Principles

1. **Claims and evidence must have independent origins.** A model claim must
   never be used as the source of evidence for verifying that same claim.
2. **Model claims must never generate verification evidence.** The
   `claims_to_changes()` bridge is removed from the verification path.
3. **No evidence may be fabricated.** Every evidence object must trace back
   to an actual repository state or actual patch.
4. **Missing evidence must produce UNVERIFIABLE.** Never guess, never assume.
5. **Contradictory evidence must produce CONTRADICTED.**
6. **Verification must be deterministic given identical inputs.**
7. **Language-specific scanners must feed a common evidence abstraction.**
8. **Prompt Mode and Pre/Post Mode must share the verification engine.**
9. **The verifier must not evaluate code quality.**
10. **Every verification result should be traceable to observable evidence.**

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PROMPT MODE (v10)                     │
│                                                         │
│  User Prompt ──► AI Model ──► Claims (what model says)  │
│       │                              │                  │
│       │                              │                  │
│  BEFORE STATE                 CLAIM PIPELINE            │
│  (git stash / snapshot)       (parse + normalize)       │
│       │                              │                  │
│  Model applies changes               │                  │
│       │                              │                  │
│  AFTER STATE                         │                  │
│  (current working tree)              │                  │
│       │                              │                  │
│  INDEPENDENT SCANNER                 │                  │
│  (scan before + after)               │                  │
│       │                              │                  │
│  OBSERVED CHANGES                    │                  │
│  (from real diff)                    │                  │
│       │                              │                  │
│       └──────────┬───────────────────┘                  │
│                  ↓                                      │
│            VERIFIER                                    │
│     (claims vs. independent evidence)                  │
│                  ↓                                      │
│    CONFIRMED / CONTRADICTED / UNVERIFIABLE              │
└─────────────────────────────────────────────────────────┘
```

The fundamental invariant:

> **A model claim must never be used as the source of evidence for verifying
> that same claim.**

## Repository State Capture

### How Before/After states are obtained

v10 introduces a **snapshot protocol** for Prompt Mode:

```
1. BEFORE SNAPSHOT
   - git stash (save uncommitted changes)
   - OR: copy working tree to temp directory
   - Scan before state → ScanResult + SymbolIndex

2. MODEL EXECUTES
   - Model applies changes to the working tree
   - (or model returns a patch that is applied)

3. AFTER SNAPSHOT
   - Scan current working tree → ScanResult + SymbolIndex
   - Compare before vs. after → ObservedChanges

4. VERIFY
   - Claims (from model) vs. ObservedChanges (from scanner)
```

### State representation options

| Approach | Pros | Cons |
|----------|------|------|
| **Git stash** | Native, atomic, clean | Requires git repo; stashing can fail |
| **Temp directory copy** | Works without git; deterministic | Slow for large repos; disk usage |
| **Filesystem snapshot** | Fast (copy-on-write) | Platform-dependent |
| **AST/symbol snapshots only** | Lightweight | Misses file-level changes |

**Recommended:** Git stash as primary, temp directory copy as fallback.

The scanner already produces `ScanResult` (file lists + parsed ASTs/symbols)
and `SymbolIndex` (all symbols by name/type). These are the right abstractions
for state representation — not raw text diffs.

### What the independent scanner detects

From `ScanResult` + `SymbolIndex` before vs. after:

- **Files added** — present in after, not in before
- **Files deleted** — present in before, not in after
- **Symbols added** — present in after's SymbolIndex, not in before's
- **Symbols deleted** — present in before's SymbolIndex, not in after's
- **Calls added** — new call relationships in after

These map directly to the existing `ChangeType` enum and `DetectedChange` dataclass.
No new evidence model is needed — the existing model IS the evidence model.

## Claim Pipeline (Independent)

```
Model Output (JSON)
    ↓
ClaimParser.parse()          ← existing, unchanged
    ↓
list[Claim]                  ← structured claims
    ↓
Claim Normalization          ← validate, deduplicate, assign IDs
    ↓
list[NormalizedClaim]        ← ready for verification
```

The claim parser does NOT create "observed changes." It only interprets what
the model claims happened.

### Existing Claim model (unchanged)

The current `Claim` dataclass already has all needed fields:
- `type` (ClaimType) — what kind of change
- `symbol_name` — which symbol
- `file_path` — which file
- `parent_class` — method owner
- `caller_name` / `called_name` — for CALLS_FUNCTION
- `confidence` — model's certainty
- `line_number` — optional location

No new claim types or fields are needed for v10.

## Observed Change Pipeline (Independent)

```
BEFORE ScanResult + SymbolIndex
  +
AFTER ScanResult + SymbolIndex
  ↓
ChangeDetector.detect()      ← existing, unchanged
  ↓
list[DetectedChange]         ← independent evidence
```

This is exactly what Pre/Post mode already does. v10 reuses it unchanged
for Prompt Mode.

### Evidence model (existing DetectedChange)

Each `DetectedChange` already contains:
- `change_type` (ChangeType) — what changed
- `file_path` — which file
- `symbol_name` — which symbol
- `parent_class` — method owner
- `line_number` — location
- `caller_name` / `called_name` — for CALL_DETECTED

These fields are sufficient for the verifier to match claims. No new
evidence model is needed.

## Verification Engine (Unchanged)

The existing `ClaimVerifier.verify(claims, detected_changes)` is already
correct — it compares claims against independent `DetectedChange` objects.
The problem was never in the verifier; it was in how `detected_changes`
were sourced.

v10 only changes WHERE `detected_changes` come from in Prompt Mode:

| Mode | v0.8.0 source | v10 source |
|------|--------------|------------|
| Pre/Post | `ChangeDetector.detect(pre, post)` | Same (unchanged) |
| Prompt | `claims_to_changes(claims)` ← **CIRCULAR** | `ChangeDetector.detect(before, after)` ← **INDEPENDENT** |

## Prompt Mode Scenarios

### Scenario A: Model directly modifies the repository

**Most common case.** The coding agent edits files in the working tree.

```
1. Snapshot before state
2. Model edits files
3. Snapshot after state
4. Detect changes
5. Verify claims against detected changes
```

**Result:** Full independent verification.

### Scenario B: Model returns a patch/diff

The model returns a unified diff or patch string instead of editing files.

```
1. Snapshot before state
2. Apply patch to working tree
3. Snapshot after state
4. Detect changes
5. Verify claims against detected changes
```

**Result:** Full independent verification (after patch application).

### Scenario C: Model returns both claims and a patch

```
1. Snapshot before state
2. Apply patch
3. Snapshot after state
4. Detect changes
5. Verify claims against detected changes
```

**Result:** Full independent verification. The patch is the evidence source,
not the claims.

### Scenario D: Model only returns claims, no actual changes

```
1. No before/after transition available
2. Claims cannot be independently verified
```

**Result:** All claims → UNVERIFIABLE. NoWreck must NOT fabricate evidence.
The CLI should clearly communicate: "No independent repository transition
detected. All claims are UNVERIFIABLE."

### Scenario E: No working directory available (e.g., stdin mode)

```
1. No repository to scan
2. No before/after state possible
```

**Result:** All claims → UNVERIFIABLE. Same as Scenario D.

## What Changes in v10

### Removed

| What | Why |
|------|-----|
| `PromptBuilder.claims_to_changes()` | Circular — generates "evidence" from claims |
| `ModelResult.changes` field in Prompt Mode | Changes must come from scanner, not claims |
| `PromptBuilder.for_prompt()` system prompt | Replaced with new prompt that returns patch |
| `PROMPT_SYSTEM_PROMPT` | Replaced with independent-verification prompt |

### Added

| What | Why |
|------|-----|
| `SnapshotManager` | Captures before/after repository state |
| `PromptModeVerifier` | Orchestrates snapshot → model → patch → scan → verify |
| New model prompt | Asks model to return claims + patch (not just claims) |
| `--before` / `--after` CLI flags | Allow manual before/after for Prompt Mode |
| `evidence_source` field in JSON | Shows where evidence came from |
| Security hardening | API key masking in all output paths |

### Refactored

| What | Why |
|------|-----|
| `_handle_prompt_mode()` | Use SnapshotManager instead of claims_to_changes |
| `ModelResult` | `changes` field sourced from scanner, not claims |
| `VerificationReport` | Add evidence source metadata |

### Unchanged

| What | Why |
|------|-----|
| `ClaimParser` | Already correct — parses claims only |
| `ClaimVerifier.verify()` | Already correct — matches claims vs. changes |
| `ChangeDetector.detect()` | Already correct — independent detection |
| `TerminalReporter` | Already correct — renders results |
| `RepositoryScanner` | Already correct — scans files |
| `SymbolIndex` | Already correct — indexes symbols |
| All claim types | No new types needed |
| Pre/Post mode | Already correct — fully independent |
| JSON schema (structure) | Same fields, new optional metadata |
| All existing tests | Must pass unchanged |

## CLI / UX

### v10 Prompt Mode

```bash
# Standard prompt mode — now with independent verification
nowreck fix "Add email validation to auth.py"

# The CLI will:
# 1. Snapshot the current working tree (before state)
# 2. Send the prompt to the model
# 3. Model returns claims + patch
# 4. Apply the patch to the working tree
# 5. Scan the after state
# 6. Detect independent changes
# 7. Verify claims against detected changes
# 8. Report results
# 9. Restore the working tree (git stash pop or temp dir cleanup)
```

### Manual before/after for Prompt Mode

```bash
# User provides explicit before/after directories
nowreck fix "Add email validation" --before ./before --after ./after
```

### Pre/Post mode (unchanged)

```bash
nowreck fix --pre ./before --post ./after
nowreck fix --pre ./before --post ./after --claims '{"claims": [...]}'
```

### New flags

| Flag | Description |
|------|-------------|
| `--before PATH` | Before-state directory (for Prompt Mode with manual snapshots) |
| `--after PATH` | After-state directory (for Prompt Mode with manual snapshots) |

### Removed flags

None. All existing flags remain.

## Reporting Changes

### Evidence source in output

The verification report now includes where evidence came from:

```json
{
  "version": "0.9.0",
  "evidence_source": "independent_scan",
  "success": true,
  "summary": {
    "total_claims": 3,
    "confirmed": 2,
    "contradicted": 1,
    "unverifiable": 0,
    "unexplained_count": 0
  },
  "results": [...],
  "unexplained_changes": [...]
}
```

Evidence source values:
- `"independent_scan"` — before/after scanned independently
- `"manual_pre_post"` — user provided explicit directories
- `"none"` — no independent evidence available

### Terminal output

```
  ═══════════════════════════════════════════════════
    Nowreck Verification Report
  ═══════════════════════════════════════════════════

    Evidence: Independent scan (before → after)
    ──────────────────────────────────────────────

    Summary
    ────────────────────
    ● 3 claims total
    ● 2 confirmed
    ● 1 contradicted
    ...
```

## Security (v10)

### API key handling

| Area | Current | v10 |
|------|---------|-----|
| Config storage | Plaintext in `.nowreck/config.json` | Same (acceptable for local tool) |
| Env var | `NOWRECK_API_KEY` | Same |
| Terminal display | Not masked | Mask in verbose output |
| JSON output | Not included | Never include |
| Error messages | May include key fragments | Mask all key fragments |
| Verbose mode | Shows full HTTP messages | Mask Authorization header |
| Failed response saves | Includes full messages | Mask Authorization header |
| Shell history | Key visible in command line | Recommend env var over CLI arg |

### Implementation

- Add `_mask_key(key: str) -> str` helper: shows first 4 + last 4 chars
- Apply masking in: error messages, verbose output, failed response saves
- Never include API key in JSON output
- Update prompt to warn models about not echoing keys

## Test Strategy

### Circularity tests (CRITICAL)

```python
def test_prompt_mode_cannot_self_verify():
    """Prove that the verifier cannot obtain evidence from claims."""
    # 1. Create a repo with function A
    # 2. Model claims "I added function B" (which doesn't exist)
    # 3. In v0.8.0 this would be CONFIRMED (circular)
    # 4. In v10 this must be CONTRADICTED or UNVERIFIABLE
    #    (depending on whether before/after is available)

def test_prompt_mode_detects_unmentioned_changes():
    """Model omits a real change — must appear as unexplained."""
    # 1. Create a repo with function A
    # 2. Model adds function B AND function C, but only claims B
    # 3. Function C must appear as unexplained change

def test_independent_evidence_not_from_claims():
    """Verify evidence comes from scanner, not from claim conversion."""
    # 1. Mock the model to return claims
    # 2. Verify that PromptBuilder.claims_to_changes() is NOT called
    # 3. Verify that ChangeDetector.detect() IS called
```

### Unit tests

- `SnapshotManager`: snapshot creation, restoration, cleanup
- `PromptModeVerifier`: full orchestration flow
- Claim parsing (unchanged)
- Evidence generation from scanner (unchanged)
- Verification rules (unchanged)
- Result classification (unchanged)

### Integration tests

- Real repository changes with model claims
- Multiple files, multiple symbols
- Mixed verified/contradicted/unverifiable claims
- Patch application + scan + verify

### Regression tests

- All existing Python/JS/TS/TSX/Rust/Go verification must pass unchanged
- Pre/Post mode must be byte-identical to v0.8.0
- All 453+ existing tests must pass

### Security tests

- API keys must not appear in logs, verbose output, JSON, exceptions, reports
- Masking must work correctly for short and long keys

### Negative tests

- Model claims a function that doesn't exist → CONTRADICTED
- Model claims a file that doesn't exist → CONTRADICTED
- Model returns no patch → UNVERIFIABLE
- Model returns invalid patch → UNVERIFIABLE + error message
- No working directory → UNVERIFIABLE

## Migration Strategy

### What stays

- `ClaimParser` — unchanged
- `ClaimVerifier.verify()` — unchanged
- `ChangeDetector.detect()` — unchanged
- `RepositoryScanner` — unchanged
- `SymbolIndex` — unchanged
- `TerminalReporter` — mostly unchanged (add evidence source)
- `ModelConfig` — unchanged
- Pre/Post mode — completely unchanged
- All claim types — unchanged
- All existing tests — must pass

### What gets refactored

- `ModelProvider.changes_from_prompt()` — rewrite to not use claims_to_changes
- `_handle_prompt_mode()` — use SnapshotManager
- `PromptBuilder.for_prompt()` — new prompt requesting patch
- `ModelResult` — `changes` sourced from scanner

### What gets deprecated

- `PromptBuilder.claims_to_changes()` — keep for backward compat but
  mark as deprecated; remove in v11

### Incremental approach

1. **Phase 1:** Add SnapshotManager (additive, no existing code changed)
2. **Phase 2:** Add new model prompt (additive)
3. **Phase 3:** Rewrite `_handle_prompt_mode()` (replaces circular path)
4. **Phase 4:** Add evidence source to reporting (additive)
5. **Phase 5:** Security hardening (additive)
6. **Phase 6:** Deprecate old path, run full test suite

## Implementation Phases

### Phase 1: SnapshotManager

**Objective:** Capture before/after repository state independently.

**Files affected:**
- `nowreck/scanner/snapshot_manager.py` (new)
- `tests/test_snapshot_manager.py` (new)

**Implementation:**
- `SnapshotManager.snapshot(path: Path) -> ScanResult` — scan a directory
- `SnapshotManager.save_snapshot(path: Path, dest: Path)` — copy directory to temp
- `SnapshotManager.restore_snapshot(src: Path, dest: Path)` — restore from temp
- `SnapshotManager.cleanup(snapshot_dir: Path)` — remove temp directory
- Git-aware variant: `git_stash()` / `git_stash_pop()` for repos

**Tests:**
- Snapshot creation captures all files
- Snapshot restoration recovers exact state
- Cleanup removes temp files
- Git stash/pop round-trips correctly
- Error handling for non-git repos (fallback to copy)

**Completion criteria:** SnapshotManager can capture and restore a directory's state.

### Phase 2: New Model Prompt

**Objective:** Ask the model to return both claims AND a patch.

**Files affected:**
- `nowreck/model/prompts.py` (modify)
- `tests/test_model.py` (extend)

**Implementation:**
- New `PROMPT_SYSTEM_PROMPT_V10` that asks model to return:
  ```json
  {
    "claims": [...],
    "patch": "<unified diff or file changes>"
  }
  ```
- Keep old `PROMPT_SYSTEM_PROMPT` as fallback for backward compat
- `PromptBuilder.for_prompt_v10(prompt: str, repo_context: str) -> list[dict]`

**Tests:**
- Model response parsing with patch field
- Fallback to old format when patch missing
- Patch validation (valid unified diff)

**Completion criteria:** Model can return claims + patch in expected format.

### Phase 3: PromptModeVerifier

**Objective:** Orchestrate the full independent verification flow.

**Files affected:**
- `nowreck/verifier/prompt_mode_verifier.py` (new)
- `tests/test_prompt_mode_verifier.py` (new)

**Implementation:**
```python
class PromptModeVerifier:
    @staticmethod
    def verify(
        prompt: str,
        repo_path: Path,
        model_config: ModelConfig,
    ) -> VerificationReport:
        # 1. Snapshot before state
        before_scan, before_index = scan_directory(repo_path)

        # 2. Call model (get claims + patch)
        result = provider.changes_from_prompt_v10(prompt, repo_context)

        # 3. Apply patch to working tree
        apply_patch(result.patch, repo_path)

        # 4. Snapshot after state
        after_scan, after_index = scan_directory(repo_path)

        # 5. Detect independent changes
        changes = ChangeDetector.detect(before_scan, after_scan, before_index, after_index)

        # 6. Verify claims against independent evidence
        report = ClaimVerifier.verify(result.claims, changes)

        # 7. Restore working tree
        restore_snapshot(before_state, repo_path)

        return report
```

**Tests:**
- Full flow: snapshot → model → patch → scan → verify
- Model claims match real patch → CONFIRMED
- Model claims don't match patch → CONTRADICTED
- Patch fails to apply → UNVERIFIABLE
- No repo available → UNVERIFIABLE
- Working tree restored after verification

**Completion criteria:** PromptModeVerifier produces independent verification results.

### Phase 4: CLI Integration

**Objective:** Wire PromptModeVerifier into the CLI.

**Files affected:**
- `nowreck/main.py` (modify `_handle_prompt_mode`)
- `nowreck/cli.py` (add --before/--after flags)

**Implementation:**
- `_handle_prompt_mode()` uses `PromptModeVerifier.verify()` instead of
  the old claims_to_changes path
- Add `--before` / `--after` flags for manual snapshots
- Add evidence source to log output

**Tests:**
- CLI integration test with mock model
- --before/--after flags work correctly
- Evidence source shown in output

**Completion criteria:** `nowreck fix "prompt"` uses independent verification.

### Phase 5: Reporting + Security

**Objective:** Update reporting and harden security.

**Files affected:**
- `nowreck/reporter/terminal_reporter.py` (add evidence source)
- `nowreck/model/provider.py` (mask API keys)
- `nowreck/model/prompts.py` (mask in messages)

**Implementation:**
- Add `evidence_source` to `VerificationReport` and JSON output
- Add `_mask_key()` helper
- Apply masking in error messages, verbose output, failed saves
- Update terminal report to show evidence source

**Tests:**
- Evidence source appears in JSON output
- API keys masked in all output paths
- Masking works for short/long keys
- No key fragments in exceptions

**Completion criteria:** Reporting shows evidence source; security hardened.

### Phase 6: Cleanup + Release

**Objective:** Deprecate old path, run full suite, release.

**Files affected:**
- `nowreck/model/prompts.py` (deprecate old prompt)
- `nowreck/model/provider.py` (deprecate old method)
- `docs/release10.md` (new)
- `README.md` (update)

**Implementation:**
- Mark `claims_to_changes()` as deprecated
- Mark old `PROMPT_SYSTEM_PROMPT` as deprecated
- Run full test suite (must pass)
- Run ruff + basedpyright (must pass)
- Write release notes
- Update README

**Completion criteria:** Full suite green, release ready.

## Acceptance Criteria

### Test 1: Model claims a change that did not occur
- **Setup:** Repo has function A. Model claims "I added function B"
- **Expected:** CONTRADICTED (B doesn't exist in after state)
- **Proof:** Verify result.verdict is CONTRADICTED

### Test 2: Model claims a real change
- **Setup:** Model adds function B to repo. Model claims "I added function B"
- **Expected:** CONFIRMED
- **Proof:** Verify result.verdict is CONFIRMED

### Test 3: Real change occurs but model fails to mention it
- **Setup:** Model adds functions B and C, but only claims B
- **Expected:** B → CONFIRMED, C → unexplained change
- **Proof:** Verify unexplained_changes contains C

### Test 4: No independent before/after evidence exists
- **Setup:** No working directory, no git repo, no snapshots
- **Expected:** All claims → UNVERIFIABLE
- **Proof:** Verify all results are UNVERIFIABLE

### Test 5: Model claims are used to construct fake evidence
- **Setup:** Attempt to call claims_to_changes() in verification path
- **Expected:** Architecture/tests prevent this from producing verification
- **Proof:** Code review + circularity test

### Test 6: Real patch contradicts the model's explanation
- **Setup:** Model says "I added function B" but actually removed function A
- **Expected:** B → UNVERIFIABLE (not in after), A removal → unexplained
- **Proof:** Verify both outcomes

### Test 7: Multiple claims partially match a real patch
- **Setup:** Model makes 3 claims, 2 are real, 1 is fabricated
- **Expected:** 2 CONFIRMED, 1 CONTRADICTED or UNVERIFIABLE
- **Proof:** Verify each claim independently

### Test 8: Evidence source is documented
- **Setup:** Any successful verification
- **Expected:** JSON output includes "evidence_source": "independent_scan"
- **Proof:** Parse JSON output, check field exists

### Test 9: API key never appears in output
- **Setup:** Run with --verbose and --json
- **Expected:** No API key fragments in any output
- **Proof:** Grep output for key patterns

### Test 10: Pre/Post mode unchanged
- **Setup:** Run Pre/Post mode on any repo
- **Expected:** Byte-identical output to v0.8.0
- **Proof:** Regression test

## Definition of Done

1. Prompt Mode uses independent verification — claims are verified against
   scanner-detected changes, not against claims-derived changes.
2. The circularity test proves the verifier cannot obtain evidence from claims.
3. All 10 acceptance criteria pass.
4. Pre/Post mode produces byte-identical output to v0.8.0.
5. All existing tests pass (regression gate).
6. New tests for SnapshotManager, PromptModeVerifier, and security pass.
7. ruff: 0 issues, basedpyright: 0 errors.
8. JSON output includes evidence_source field.
9. API keys are masked in all output paths.
10. Documentation updated (README, release notes, limitations).

## Claim Type Compatibility Matrix

| Claim Type | Evidence Required | Observable From Before/After? | Possible Results |
|------------|-------------------|-------------------------------|------------------|
| ADD_FUNCTION | Symbol exists in after, not in before | ✅ Yes | CONFIRMED / UNVERIFIABLE |
| REMOVE_FUNCTION | Symbol exists in before, not in after | ✅ Yes | CONFIRMED / UNVERIFIABLE |
| ADD_CLASS | Symbol exists in after, not in before | ✅ Yes | CONFIRMED / UNVERIFIABLE |
| REMOVE_CLASS | Symbol exists in before, not in after | ✅ Yes | CONFIRMED / UNVERIFIABLE |
| ADD_INTERFACE | Symbol exists in after, not in before | ✅ Yes (TS/TSX) | CONFIRMED / UNVERIFIABLE |
| REMOVE_INTERFACE | Symbol exists in before, not in after | ✅ Yes (TS/TSX) | CONFIRMED / UNVERIFIABLE |
| ADD_ENUM | Symbol exists in after, not in before | ✅ Yes (TS/TSX) | CONFIRMED / UNVERIFIABLE |
| REMOVE_ENUM | Symbol exists in before, not in after | ✅ Yes (TS/TSX) | CONFIRMED / UNVERIFIABLE |
| ADD_TYPE_ALIAS | Symbol exists in after, not in before | ✅ Yes (TS/TSX) | CONFIRMED / UNVERIFIABLE |
| REMOVE_TYPE_ALIAS | Symbol exists in before, not in after | ✅ Yes (TS/TSX) | CONFIRMED / UNVERIFIABLE |
| FILE_CREATED | File exists in after, not in before | ✅ Yes | CONFIRMED / UNVERIFIABLE |
| FILE_DELETED | File exists in before, not in after | ✅ Yes | CONFIRMED / UNVERIFIABLE |
| CALLS_FUNCTION | Call relationship in after, not in before | ✅ Yes | CONFIRMED / CONTRADICTED / UNVERIFIABLE |

Note: CONTRADICTED is possible for ADD_* claims when the symbol was actually
removed (opposite change detected), and for REMOVE_* claims when the symbol
was actually added.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Model doesn't return valid patch | High | Fallback to UNVERIFIABLE; retry with repair prompt |
| Git stash fails (dirty state) | Medium | Fallback to temp directory copy |
| Patch application fails | Medium | Report UNVERIFIABLE + error message |
| Large repos slow to snapshot | Medium | Use git stash (fast) over copy (slow) |
| Model modifies files outside repo | Low | Scanner only sees repo-root files |
| Breaking backward compatibility | High | Deprecate old path, don't remove; keep Pre/Post mode identical |
| Existing tests break | High | Run full suite at every phase; regression gate |

## Explicitly not a roadmap

This covers exactly one thing — fixing the Prompt Mode circularity problem,
same phase-by-phase discipline, human-checked at every step. When it's done
and proven, the next increment gets its own equally narrow scoping conversation.
