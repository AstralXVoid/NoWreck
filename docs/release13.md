# NoWreck v0.13.0 — CI/CD Integration

**Release date:** August 2026
**Previous release:** v0.12.0 (Provider Consolidation + Scan Caching)
**Focus:** CI/CD integration with machine-readable output formats (SARIF, JUnit)
and automated git comparison for pull request verification.

---

## What's new in v0.13.0

### SARIF output ✅

SARIF v2.1.0 output for GitHub Code Scanning, SonarQube, and CodeQL.

```bash
nowreck fix --compare HEAD~1 --format sarif > nowreck.sarif
```

**15 rules defined:**
- NW001-NW013: One per CONTRADICTED claim type (error level)
- NW014: UNVERIFIABLE claims (warning level)
- NW015: UNEXPLAINED changes (note level)

**Design decisions:**
- CONFIRMED results excluded by default (SARIF is for problems)
- Uses `ruleId` (string) for GitHub UI readability
- Each claim type gets its own rule for granular filtering

### JUnit XML output ✅

Standard JUnit XML format for Jenkins, GitLab CI, and Azure Pipelines.

```bash
nowreck fix --compare HEAD~1 --format junit > nowreck-junit.xml
```

**Verdict mapping:**
- CONFIRMED → pass (no element)
- CONTRADICTED → `<failure>`
- UNVERIFIABLE → `<failure type="UNVERIFIABLE">`
- UNEXPLAINED → excluded (not a claim)

### --format flag ✅

New `--format` flag for output format selection:

```bash
nowreck fix --compare HEAD~1 --format json    # JSON
nowreck fix --compare HEAD~1 --format sarif   # SARIF
nowreck fix --compare HEAD~1 --format junit   # JUnit
```

**Backward compatibility:** `--json` deprecated with warning, still works.

### --output flag ✅

Write output to file instead of stdout:

```bash
nowreck fix --compare HEAD~1 --format sarif --output nowreck.sarif
```

### --compare flag ✅

Automated git comparison:

```bash
nowreck fix --compare HEAD~1           # Compare against previous commit
nowreck fix --compare main             # Compare against main branch
nowreck fix --compare abc1234          # Compare against specific commit
```

**Supported ref types:** commit hash, branch name, tag, HEAD~N syntax.

**Implementation:** Uses `git archive` for clean extraction to temp directories.
Automatic cleanup via `tempfile.TemporaryDirectory`.

---

## What's unchanged

| What | Why |
|------|-----|
| All 13 claim types | No new types needed |
| `ClaimVerifier.verify()` | Already correct |
| `ChangeDetector.detect()` | Already correct |
| `PromptModeVerifier` | Format routing is transparent |
| `SnapshotManager` | Already correct |
| `PatchApplier` | Already correct |
| Pre/Post mode | Already correct |
| Prompt mode | Already correct |
| Scan cache | Already correct |

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Full pytest suite | 781 | ✅ all pass |
| New SARIF reporter tests | 23 | ✅ all pass |
| New JUnit reporter tests | 15 | ✅ all pass |
| New CLI flag tests | 16 | ✅ all pass |
| New git integration tests | 8 | ✅ all pass |
| ruff check + format | 0 issues | ✅ clean |
| basedpyright (strict) | 0 errors | ✅ clean |

## Files modified

| File | Change |
|------|--------|
| `nowreck/reporter/sarif_reporter.py` | **New** — SARIF v2.1.0 output formatter |
| `nowreck/reporter/junit_reporter.py` | **New** — JUnit XML output formatter |
| `nowreck/git_integration.py` | **New** — Git snapshot extraction |
| `nowreck/cli.py` | Added `--format`, `--output`, `--compare` flags |
| `nowreck/main.py` | Flag conflict detection, format routing, --compare handler |
| `pyproject.toml` | Added `jsonschema` to test dependencies |
| `tests/test_sarif_reporter.py` | **New** — 23 SARIF tests |
| `tests/test_junit_reporter.py` | **New** — 15 JUnit tests |
| `tests/test_cli.py` | 16 new flag tests |
| `tests/test_git_integration.py` | **New** — 8 git integration tests |
| `README.md` | Added CI/CD section, version bump |
| `docs/nowreck-v13-scope.md` | Marked done |

---

## Definition of Done

| Criterion | Status |
|-----------|--------|
| `--format sarif` produces valid SARIF v2.1.0 | ✅ |
| `--format junit` produces valid JUnit XML | ✅ |
| `--compare <ref>` extracts and scans git snapshots | ✅ |
| `--json` deprecated with warning | ✅ |
| `--json` + `--format` conflict detected | ✅ |
| `--compare` + `--post` conflict detected | ✅ |
| Exit code convention preserved | ✅ |
| All existing tests pass (781/781) | ✅ |
| New tests pass (23 + 15 + 16 + 8) | ✅ |
| ruff: 0 issues, basedpyright: 0 errors | ✅ |
| README updated with CI/CD examples | ✅ |
| Release notes created | ✅ |
| Version bumped to 0.13.0 | ✅ |

---

## Upgrade notes

No breaking changes. Every existing command and configuration works
identically.

**New flags:**
- `--format json|sarif|junit` — output format selection
- `--output <path>` — write output to file
- `--compare <ref>` — git comparison mode

**Deprecated:**
- `--json` — use `--format json` instead (warning shown, still works)

**New dependencies (test only):**
- `jsonschema>=4.0` — for SARIF schema validation in tests

---

*NoWreck v0.13.0 — August 2026*
