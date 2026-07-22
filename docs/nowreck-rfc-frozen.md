# Nowreck — Final Implementation Specification (frozen)

**Status:** Architecture frozen. Implementation-ready.

## 1. Identity

Nowreck is a deterministic verifier that checks whether an AI coding
assistant's explanation of a code change matches observable repository
structure — the real files, symbols, and diff.

Nowreck is **not** a code reviewer, bug finder, security scanner,
correctness engine, autonomous agent, or AI replacement. It answers exactly
one question: *does the AI's explanation match what actually changed in the
repository?* Nothing more.

### What it catches
- Hallucinated internal files, functions, or classes
- Fake internal API calls (references to symbols that don't exist)
- Explanation-vs-diff mismatches
- Unexplained changes (real modifications the AI never mentioned)

### What it does not catch
- Logical bugs, incorrect algorithms, runtime failures
- Security issues
- Hallucinated third-party packages (defer to slopcheck/slop-scan)

## 2. Locked MVP Stack

- Python only
- CLI first
- stdlib `ast` only — no LibCST
- No embeddings, no vector database
- No autonomous agents, no code execution, no test execution, no sandbox
- No second AI judging another AI's correctness
- One OpenAI-compatible model provider, no abstraction layer

## 3. Architecture — Unified Detection Model

### 3.1 The inconsistency this fixes

The previous draft treated `DetectedChange` as the single source of truth,
but let `CALLS_FUNCTION` verify directly against the symbol index — a second,
undeclared verification path. This version closes that gap: **all**
structural facts, including function calls, are produced once, during
detection, before any claim is looked at. `ClaimVerifier` does comparison
only. It never parses AST, never queries the symbol index directly, and
never re-derives a fact that detection didn't already produce.

```
Repository (pre-change: git HEAD)
      │
      ▼
  AST Scanner ──► Symbol Index (pre)
      │
Repository (post-change: working tree)
      │
      ▼
  AST Scanner ──► Symbol Index (post)
      │
      ▼
  Change Detector
      │  compares Symbol Index (pre) vs (post)
      │  AND walks call sites in both, resolving each
      │  against the symbol index
      ▼
  list[DetectedChange]      ◄── the one and only source of truth
  (includes ADD_FUNCTION, REMOVE_FUNCTION, ADD_CLASS, REMOVE_CLASS,
   FILE_CREATED, FILE_DELETED, and CALL_DETECTED records)
      │                            │
AI model ──► Claim Parser ──► claims
      │                            │
      └──────────► Claim Verifier ◄┘
        (pure comparison — no AST access, no symbol
         index access, no independent analysis)
                    │
                    ▼
              Terminal Report
```

### 3.2 Rule, stated permanently

`ClaimVerifier` is a comparison function over two already-computed lists
(`claims`, `DetectedChange`). If a verification need ever seems to require
`ClaimVerifier` to look at the AST or symbol index directly, that is a sign
the fact is missing from `DetectedChange` and belongs in the Change Detector
instead — not a sign that `ClaimVerifier` should grow a second analysis
path.

### 3.3 Pipeline build order (each stage complete before the next starts)

1. AST repository scanner
2. Symbol index
3. Repository comparison
4. `DetectedChange` generation (including call detection)
5. Claim schema and parser
6. Claim verification
7. Terminal reporting
8. OpenAI-compatible model connection

Model integration is deliberately last. Everything through stage 7 must work
correctly on hand-constructed inputs before a live model is ever involved —
see Milestone 1, §7.

## 4. Diff Source (MVP definition)

- **Pre-change state:** git `HEAD`, or an explicitly provided baseline
  repository path if no git repository is present.
- **Post-change state:** the current working tree.
- Nowreck requires a git repository for MVP. Non-git support (baseline
  snapshots, arbitrary diff files, comparing two arbitrary commits) is
  future work, not required to validate the core loop.

## 5. Components

### 5.1 Repository Scanner
- **Purpose:** parse Python files into ASTs for both pre- and post-change
  states.
- **Inputs:** repository root path, git ref for pre-change state.
- **Outputs:** `dict[Path, ast.Module]` for each state.
- **MVP approach:** stdlib `ast.parse` per file, full rescan every run.
- **Intentionally excluded:** LibCST, incremental/cached scanning,
  non-Python file parsing.

### 5.2 Symbol Index
- **Purpose:** flat lookup of functions, classes, and methods by name.
- **Inputs:** `ast.Module` per file.
- **Outputs:** `SymbolIndex`.
- **MVP approach:** one level of nesting only (methods inside classes).
- **Intentionally excluded:** nested functions, async, properties,
  decorators as metadata, `__all__` tracking, cross-file resolution beyond
  direct name lookup.

### 5.3 Change Detector
- **Purpose:** produce the complete, single source of truth for everything
  the verifier will ever compare against — including call sites, not just
  add/remove of definitions.
- **Inputs:** `SymbolIndex` (pre), `SymbolIndex` (post), `ast.Module` (post,
  for call-site walking).
- **Outputs:** `list[DetectedChange]`.
- **MVP approach:** set-difference on qualified names for
  `ADD_FUNCTION`/`REMOVE_FUNCTION`/`ADD_CLASS`/`REMOVE_CLASS`, file-list
  diff for `FILE_CREATED`/`FILE_DELETED`, and a walk of every `ast.Call`
  node in the post-change tree, resolving each callee name against the
  post-change symbol index and recording a `CALL_DETECTED` fact for every
  call that resolves to a known symbol.
- **Intentionally excluded:** rename detection, import-chain resolution,
  any condition/branch analysis (see §6 on `ADD_CONDITION`).

### 5.4 Claim Parser
- **Purpose:** turn the model's structured JSON response into validated
  `Claim` objects.
- **Inputs:** raw model output.
- **Outputs:** `list[Claim]`, or a parse failure.
- **MVP approach:** Pydantic model, one repair round-trip on invalid JSON,
  then abort with raw output saved to disk.
- **Intentionally excluded:** schema versioning, multi-format support.

### 5.5 Claim Verifier
- **Purpose:** compare `claims` against `DetectedChange` list, in both
  directions. Pure comparison only — see §3.2.
- **Inputs:** `list[Claim]`, `list[DetectedChange]`.
- **Outputs:** `list[VerificationResult]`, `list[UnexplainedChange]`.
- **MVP approach:** for each claim, look up a matching `DetectedChange` by
  type + target + file. Match → `CONFIRMED`. Contradictory state found (e.g.
  claim says added, detection shows no such addition but the name existed
  already) → `CONTRADICTED`. No matching or contradicting fact at all →
  `UNVERIFIABLE`. Reverse direction: any `DetectedChange` not referenced by
  a claim → `UnexplainedChange`.
- **Intentionally excluded:** confidence formulas beyond §7's rules,
  severity classification of unexplained changes.

### 5.6 Terminal Report
- **Purpose:** render results for a human to read and act on.
- **Inputs:** `list[VerificationResult]`, `list[UnexplainedChange]`.
- **Outputs:** formatted terminal text.
- **MVP approach:** counts + per-claim evidence lines. No JSON mode.
- **Intentionally excluded:** JSON output, CI-mode tuning, pagination.

## 6. Claim Taxonomy — MVP Only

| Type | Verified against | Confidence ceiling |
|---|---|---|
| `ADD_FUNCTION` | `DetectedChange` (structural) | 1.0 |
| `REMOVE_FUNCTION` | `DetectedChange` (structural) | 1.0 |
| `ADD_CLASS` | `DetectedChange` (structural) | 1.0 |
| `REMOVE_CLASS` | `DetectedChange` (structural) | 1.0 |
| `FILE_CREATED` | `DetectedChange` (structural) | 1.0 |
| `FILE_DELETED` | `DetectedChange` (structural) | 1.0 |
| `CALLS_FUNCTION` | `DetectedChange` (`CALL_DETECTED` fact, structural) | 1.0 |

All seven MVP claim types are now verified purely structurally — existence
or non-existence of a fact already produced by the Change Detector. This is
the complete MVP taxonomy.

### 6.1 `ADD_CONDITION` — removed from MVP

`ADD_CONDITION` (claiming a new conditional was added, e.g. "adds an expiry
check") was previously included as a heuristic claim type verified by
keyword overlap between the claim's `subject` and a new `if` node's test
expression. That is not a deterministic structural fact — it's a semantic
judgment about whether a keyword match means the condition does what the
claim says. It does not belong in an MVP whose entire premise is
deterministic verification.

`ADD_CONDITION` moves to **future work**, alongside the other heuristic and
semantic claim types (renames, decorators, parameter/return modification,
exception handling). It should only re-enter scope if a genuinely
deterministic verification method is found for it — not by lowering the
confidence ceiling and shipping it anyway.

## 7. Confidence Rules (permanent)

1. Every MVP claim type verifies against a structural fact and may report
   confidence up to 1.0. There are no heuristic claim types in MVP.
2. If a future claim type requires heuristic or pattern-based matching, it
   must cap confidence at 0.7 and be labeled "heuristic," never "confirmed."
3. When a result could plausibly be `CONTRADICTED` or `UNVERIFIABLE`,
   `UNVERIFIABLE` is always preferred.
4. Every result must state the specific deterministic evidence that
   produced it.

## 8. Report Format

```
NOWRECK REPORT
────────────────────────────────────
Claims: 7   Confirmed: 5   Contradicted: 1   Unverifiable: 1

[001] ADD_FUNCTION — auth/token.py: refresh_token
  Evidence: symbol exists post-diff, did not exist pre-diff
  Result: CONFIRMED (confidence 1.00)

[005] CALLS_FUNCTION — auth/token.py: validate_token → log_event
  Evidence: no CALL_DETECTED fact for validate_token → log_event
  Result: CONTRADICTED (confidence 1.00)

⚠ Unexplained modification: auth/token.py, lines 78-82
  Not described by any claim.
────────────────────────────────────
```

No aggregate "overall confidence %" — `CONTRADICTED` and `UNVERIFIABLE`
results are never averaged into one number that could hide them.

## 9. CLI (MVP scope)

```
nowreck fix "<prompt>"          # first run prompts inline for model endpoint,
                                  # saves to .nowreck/config.yaml, then runs
nowreck config show / set        # manual config editing
```

## 10. Model Interaction

The model's only job: propose a diff and describe it as structured claims
matching §6's schema. It never evaluates its own correctness. Malformed JSON
gets exactly one repair round-trip, then a clear abort with the raw output
saved to `.nowreck/last_failed_response.txt`.

## 11. Project Structure

```
nowreck/
  cli.py
  main.py
  scanner/
    repository_scanner.py
    symbol_index.py
  detector/
    change_detector.py
  claims/
    models.py
    parser.py
  verifier/
    verifier.py
  reporter/
    terminal.py
  providers/
    openai_compatible.py
  storage/
    config.py
```

No additional layers, no plugin system, no interface modules. Each folder
maps directly to one component in §5. `providers/` holds exactly one file —
it is a folder rather than a flat module only because it groups naturally
with `storage/` as "external-facing" code, not because a second provider is
expected soon.

## 12. Do Not Build Yet

- Caching
- CI/CD integration
- JSON output mode
- Multi-language support
- Advanced rename detection
- Deep import resolution
- Semantic analysis of any kind (including `ADD_CONDITION`, see §6.1)
- IDE/editor plugins
- Multiple AI providers or a provider abstraction interface
- Benchmark suite with formal precision/recall measurement
- Non-git diff sources (baseline snapshots, arbitrary diff files)

## 13. Milestone 1 — Detection Without AI

Before any model integration (stage 8 of §3.3), the pipeline through stage 4
must be independently provable:

**Requirement:** given two repository states (a pre-change directory or git
ref, and a post-change working tree), the system must output a correct,
deterministic list of structural changes — with no AI provider, no claim
parser, and no model interaction involved at all.

**Example:**

```
Input:
  old repository state (git HEAD)
  new repository state (working tree)

Output:
  Added function validate_user() in auth/login.py
  Removed class LegacyAuth() in auth/legacy.py
  Detected call: validate_user() -> hash_password()
```

This milestone is the proof that stages 1–4 are correct on their own terms,
independent of anything the model later claims. Do not proceed to claim
parsing or model integration until this milestone passes on at least 3
hand-constructed test repositories.

## 14. Implementation Roadmap

1. AST repository scanner
2. Symbol index
3. Repository comparison
4. `DetectedChange` generation (including call detection) — **Milestone 1
   checkpoint**
5. Claim schema and parser
6. Claim verification
7. Terminal reporting
8. OpenAI-compatible model connection

## 15. Implementation Readiness

**Is the architecture stable enough to code?**
Yes. Every component has a single, non-overlapping responsibility, the
source-of-truth inconsistency from the prior draft is resolved, and the
build order in §14 has an explicit correctness checkpoint (Milestone 1)
before model integration begins.

**What assumptions remain, unverified?**
- stdlib `ast`'s line-range precision is assumed sufficient for MVP's
  existence/absence checks — not yet tested against a real model's output.
- git `HEAD` as the pre-change baseline is assumed to match what users
  actually want to compare against in practice.
- The model's structured-JSON reliability is assumed sufficient for a
  single-retry repair budget.

**What measurements will decide future upgrades?**
- If `ast`'s line-range coarseness causes real false `UNVERIFIABLE` results
  in practice, that's the trigger to evaluate LibCST — not before.
- If users regularly need a non-`HEAD` baseline, that's the trigger to add
  non-git diff sources.
- If the model's structured-JSON failure rate is a regular friction point,
  that's the trigger to invest in schema robustness beyond one retry.

---

**The architecture is frozen after this revision. Further improvements
should come from implementation evidence, user feedback, and measured
failures, not additional speculative planning.**
