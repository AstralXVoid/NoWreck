# NoWreck v13 Scope — CI/CD Integration

**Version:** 0.13.0
**Date:** 2026-08-28
**Status:** Done. Released as v0.13.0.

---

## Objective

Make NoWreck first-class in CI/CD pipelines by adding machine-readable output formats (SARIF, JUnit XML) and git integration for automated pre/post snapshot detection.

---

## Part 1: Output Formats

### Current State

NoWreck supports two output modes:
- **Terminal** (default): Coloured human-readable text
- **JSON** (`--json`): Structured JSON for CI tools

### Proposed: Three Output Formats

| Format | Flag | Use Case |
|--------|------|----------|
| `json` | `--format json` (alias: `--json`) | Existing CI integration, scripting |
| `sarif` | `--format sarif` | GitHub Code Scanning, SonarQube, CodeQL |
| `junit` | `--format junit` | Jenkins, GitLab CI, Azure Pipelines test reports |

**Backward compatibility:** `--json` remains as a deprecated alias. Users will see a deprecation warning. Removal targeted for v0.14.0.

**Flag conflict:** Using both `--json` and `--format` is an error:
```bash
$ nowreck fix --format sarif --json
Error: cannot use both --json and --format
```

### SARIF Output

Static Analysis Results Interchange Format (SARIF) v2.1.0 — the standard for GitHub Code Scanning.

**CONFIRMED results are excluded from SARIF output by default.** SARIF is designed for reporting problems, not successes. Adding `--sarif-verbose` in a future version if needed.

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "nowreck",
          "version": "0.13.0",
          "informationUri": "https://github.com/AstralXVoid/NoWreck",
          "rules": [
            {
              "id": "NW001",
              "name": "HallucinatedFunction",
              "shortDescription": { "text": "AI claimed a function was added but it doesn't exist" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW002",
              "name": "HallucinatedRemoveFunction",
              "shortDescription": { "text": "AI claimed a function was removed but it still exists" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW003",
              "name": "HallucinatedClass",
              "shortDescription": { "text": "AI claimed a class was added but it doesn't exist" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW004",
              "name": "HallucinatedRemoveClass",
              "shortDescription": { "text": "AI claimed a class was removed but it still exists" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW005",
              "name": "HallucinatedInterface",
              "shortDescription": { "text": "AI claimed an interface was added but it doesn't exist" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW006",
              "name": "HallucinatedRemoveInterface",
              "shortDescription": { "text": "AI claimed an interface was removed but it still exists" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW007",
              "name": "HallucinatedEnum",
              "shortDescription": { "text": "AI claimed an enum was added but it doesn't exist" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW008",
              "name": "HallucinatedRemoveEnum",
              "shortDescription": { "text": "AI claimed an enum was removed but it still exists" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW009",
              "name": "HallucinatedTypeAlias",
              "shortDescription": { "text": "AI claimed a type alias was added but it doesn't exist" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW010",
              "name": "HallucinatedRemoveTypeAlias",
              "shortDescription": { "text": "AI claimed a type alias was removed but it still exists" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW011",
              "name": "HallucinatedFileCreated",
              "shortDescription": { "text": "AI claimed a file was created but it doesn't exist" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW012",
              "name": "HallucinatedFileDeleted",
              "shortDescription": { "text": "AI claimed a file was deleted but it still exists" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW013",
              "name": "FakeApiCall",
              "shortDescription": { "text": "AI claimed a function calls another but no call exists" },
              "defaultConfiguration": { "level": "error" }
            },
            {
              "id": "NW014",
              "name": "UnverifiedClaim",
              "shortDescription": { "text": "AI claim could not be verified against structural evidence" },
              "defaultConfiguration": { "level": "warning" }
            },
            {
              "id": "NW015",
              "name": "UnexplainedChange",
              "shortDescription": { "text": "Structural change detected with no matching claim" },
              "defaultConfiguration": { "level": "note" }
            }
          ]
        }
      },
      "results": [...]
    }
  ]
}
```

**Rule ID mapping (15 rules):**

| Rule ID | Claim Type | Verdict | SARIF Level | In Output? |
|---------|------------|---------|-------------|------------|
| NW001 | ADD_FUNCTION | CONTRADICTED | error | ✅ yes |
| NW002 | REMOVE_FUNCTION | CONTRADICTED | error | ✅ yes |
| NW003 | ADD_CLASS | CONTRADICTED | error | ✅ yes |
| NW004 | REMOVE_CLASS | CONTRADICTED | error | ✅ yes |
| NW005 | ADD_INTERFACE | CONTRADICTED | error | ✅ yes |
| NW006 | REMOVE_INTERFACE | CONTRADICTED | error | ✅ yes |
| NW007 | ADD_ENUM | CONTRADICTED | error | ✅ yes |
| NW008 | REMOVE_ENUM | CONTRADICTED | error | ✅ yes |
| NW009 | ADD_TYPE_ALIAS | CONTRADICTED | error | ✅ yes |
| NW010 | REMOVE_TYPE_ALIAS | CONTRADICTED | error | ✅ yes |
| NW011 | FILE_CREATED | CONTRADICTED | error | ✅ yes |
| NW012 | FILE_DELETED | CONTRADICTED | error | ✅ yes |
| NW013 | CALLS_FUNCTION | CONTRADICTED | error | ✅ yes |
| NW014 | (any) | UNVERIFIABLE | warning | ✅ yes |
| NW015 | (unexplained) | (no claim) | note | ✅ yes |
| — | (any) | CONFIRMED | — | ❌ no (excluded) |

**Result format:**
```json
{
  "ruleId": "NW001",
  "ruleIndex": 0,
  "level": "error",
  "message": { "text": "AI claimed function 'validate_email' was added but it doesn't exist" },
  "locations": [{
    "physicalLocation": {
      "artifactLocation": { "uri": "src/auth.py" },
      "region": { "startLine": 1 }
    }
  }]
}
```

**Design decisions:**
- Uses `ruleId` (string) not `ruleIndex` (integer) — more readable in GitHub UI, doesn't break if rules are reordered
- CONFIRMED results are excluded — SARIF is for problems, not successes
- Each CONTRADICTED claim type gets its own rule for granular filtering

### JUnit XML Output

Standard JUnit XML format for test report integration.

**Verdict → JUnit status mapping:**

| Verdict | JUnit Element | Meaning |
|---------|---------------|---------|
| CONFIRMED | (none) | Test passed — no element needed |
| CONTRADICTED | `<failure>` | Claim is wrong — assertion failed |
| UNVERIFIABLE | `<failure type="UNVERIFIABLE">` | Claim couldn't be verified — treated as failure |
| UNEXPLAINED | N/A | Not a claim — reported separately, not as test case |

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="nowreck" tests="2" failures="1" errors="0">
  <testsuite name="verification" tests="2" failures="1">
    <testcase name="ADD_FUNCTION validate_email" classname="src/auth.py">
    </testcase>
    <testcase name="CALLS_FUNCTION validate_email" classname="src/auth.py">
      <failure type="CONTRADICTED" message="Contradicted: No matching call detected">
        Evidence: Function 'validate_email' was added in src/auth.py
      </failure>
    </testcase>
  </testsuite>
</testsuites>
```

**Note:** UNEXPLAINED changes (structural changes with no matching claim) are reported in a separate section, not as test cases. The example above shows 2 claims (1 passed, 1 failed), not 3.

**Design decisions:**
- `classname` uses full relative path (not just filename) — Jenkins/GitLab use this for grouping
- `failure/@type` attribute matches NoWreck verdict name
- `failure/message` is human-readable summary
- `failure/text` contains full evidence
- UNVERIFIABLE claims are treated as failures (couldn't verify = test didn't pass)
- UNEXPLAINED changes are excluded from test count (they're not claims)

---

## Part 2: Git Integration

### Current State

Pre/Post mode requires explicit directory paths:
```bash
nowreck fix --pre ./before --post ./after
```

### Proposed: Auto-Detect from Git

New flags for automatic snapshot detection:

| Flag | Description |
|------|-------------|
| `--pre <ref>` | Use git ref as pre snapshot (default post: HEAD) |
| `--post <ref>` | Use git ref as post snapshot (default pre: HEAD) |
| `--compare <ref>` | Shorthand for `--pre <ref> --post HEAD` |

**Defaults:**
- `--pre <ref>` alone → uses HEAD as post snapshot
- `--post <ref>` alone → uses HEAD as pre snapshot
- `--compare <ref>` → sets both pre and post
- All three can be combined with `--claims`

**Supported ref types:**
- Commit hash: `abc1234`
- Branch name: `main`, `feature/foo`
- Tag: `v0.12.0`
- HEAD syntax: `HEAD~1`, `HEAD~3`, `HEAD^`
- Any valid git ref

**Semantics:**
- `--compare <ref>` means "compare `<ref>` against HEAD"
- `--compare HEAD~1` means "compare previous commit against current"
- `--compare main` means "compare main branch against current HEAD"
- `--pre abc123 --post def456` means "compare two specific commits"

**Flag conflict:** Using `--compare` with `--pre` or `--post` is an error:
```bash
$ nowreck fix --compare HEAD~1 --post HEAD~2
Error: cannot use --compare with --post
```

**Implementation:**
1. Use `git archive <ref> | tar -x` to extract commit state to temp directory
2. Use `tempfile.TemporaryDirectory` for automatic cleanup (handles SIGKILL better than atexit)
3. Scan both directories
4. Temp directories cleaned up automatically on exit

**Example:**
```bash
# Compare current state against previous commit
nowreck fix --compare HEAD~1

# Compare against a specific commit
nowreck fix --pre abc123 --post HEAD

# Verify claims against a PR
nowreck fix --compare main --claims '{...}'
```

**Dirty working tree behavior:**
- `--post HEAD` uses the committed state, not the working tree
- Uncommitted changes are ignored by default
- Add `--include-dirty` flag to include working tree changes (future enhancement, not in v13)

**Submodules:**
- Submodules are NOT included in extracted snapshots
- `git archive` doesn't export submodules by default
- Support planned for v14 with `--recurse-submodules` flag

**Error handling:**
- If git is not installed: error "git is required for --compare mode"
- If ref doesn't exist: error "ref <ref> not found"
- If not a git repository: error "not a git repository"
- All git errors return exit code 1

---

## Part 3: GitHub Actions Integration

### Example Workflow

```yaml
name: NoWreck Verification
on: [pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # For --compare HEAD~1, need at least 2 commits
          # For --compare HEAD~N, need N+1 commits
          # For --compare <branch>, fetch that branch explicitly
          fetch-depth: 2

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install nowreck

      - name: Run NoWreck verification
        run: nowreck fix --compare HEAD~1 --format sarif > nowreck.sarif

      - name: Upload SARIF to GitHub Code Scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: nowreck.sarif
```

### Exit Code Convention

| Exit Code | Meaning |
|-----------|---------|
| 0 | All claims confirmed, no unexplained changes |
| 1 | Contradicted, unverifiable, or unexplained changes |

### Output File Convention

| Format | Default Output | Flag to Override |
|--------|----------------|------------------|
| terminal | stdout | N/A |
| json | stdout | `--output <path>` |
| sarif | stdout | `--output <path>` |
| junit | stdout | `--output <path>` |

**Recommended file naming:**
- `nowreck.json` for JSON
- `nowreck.sarif` for SARIF
- `nowreck-junit.xml` for JUnit

**`--output` behavior:**
- Creates parent directories if they don't exist
- Overwrites existing files without warning
- Fails with error if path is not writable

---

## Part 4: Files Affected

| File | Change | Status |
|------|--------|--------|
| `nowreck/reporter/sarif_reporter.py` | **New** — SARIF output formatter | To create |
| `nowreck/reporter/junit_reporter.py` | **New** — JUnit XML output formatter | To create |
| `nowreck/main.py` | Add `--format`, `--output`, `--compare` flags | To modify |
| `nowreck/cli.py` | Add new CLI arguments | To modify |
| `nowreck/git_integration.py` | **New** — Git snapshot extraction | To create |
| `tests/test_sarif_reporter.py` | **New** — SARIF output tests | To create |
| `tests/test_junit_reporter.py` | **New** — JUnit XML tests | To create |
| `tests/test_git_integration.py` | **New** — Git integration tests | To create |
| `tests/test_cli.py` | Update for new flags | To modify |
| `README.md` | Add CI/CD section | To modify |
| `docs/release13.md` | **New** — v0.13.0 release notes | To create |
| `docs/nowreck-v13-scope.md` | This document | To update |

---

## Part 5: Implementation Phases

### Phase 1: Output Formats (SARIF + JUnit)

**Files affected:**
- `nowreck/reporter/sarif_reporter.py` (new)
- `nowreck/reporter/junit_reporter.py` (new)
- `tests/test_sarif_reporter.py` (new)
- `tests/test_junit_reporter.py` (new)

**Tasks:**
1. Create `SarifReporter` class
2. Create `JUnitReporter` class
3. Map all 13 claim types to SARIF rule IDs (NW001-NW013)
4. Map verdicts to SARIF severity levels (error/warning/note/none)
5. Write comprehensive tests
6. SARIF validation: use `jsonschema` library (add as test dependency in pyproject.toml)
7. JUnit validation: use `xml.etree.ElementTree` (built-in, no external dependency)

**Dependencies:**
- Add `jsonschema` to `[project.optional-dependencies] test`

**Estimated effort:** 2-3 hours

### Phase 2: CLI Integration

**Files affected:**
- `nowreck/main.py`
- `nowreck/cli.py`
- `tests/test_cli.py`

**Tasks:**
1. Add `--format json|sarif|junit` flag
2. Add `--output <path>` flag for file output
3. Keep `--json` as deprecated alias (warning on use)
4. Add flag conflict detection (`--json` + `--format` = error)
5. Route output to appropriate reporter
6. Write CLI tests

**Estimated effort:** 1-2 hours

### Phase 3: Git Integration

**Files affected:**
- `nowreck/git_integration.py` (new)
- `nowreck/main.py`
- `tests/test_git_integration.py` (new)

**Tasks:**
1. Create `GitSnapshot` class for extracting commit states
2. Implement `--compare` flag
3. Use `tempfile.TemporaryDirectory` for automatic cleanup
4. Handle error cases (no git, invalid ref, not a repo)
5. Handle flag conflicts (`--compare` + `--post` = error)
6. Write git integration tests

**Estimated effort:** 2-3 hours

### Phase 4: Documentation + Release

**Files affected:**
- `README.md`
- `docs/release13.md`
- `docs/nowreck-v13-scope.md`

**Tasks:**
1. Add CI/CD section to README with GitHub Actions example
2. Create release notes
3. Update version to 0.13.0
4. Update roadmap (mark CI/CD as done)

**Estimated effort:** 1 hour

---

## Part 6: Definition of Done

1. ✅ `--format sarif` produces valid SARIF v2.1.0 output (validated against schema with `jsonschema`)
2. ✅ `--format junit` produces valid JUnit XML output (validated with `xml.etree.ElementTree`)
3. ✅ `--compare <ref>` extracts and scans git snapshots
4. ✅ `--json` still works (with deprecation warning)
5. ✅ `--json` + `--format` together produces clear error
6. ✅ `--compare` + `--post` together produces clear error
7. ✅ Exit code convention preserved (0 = success, 1 = issues)
8. ✅ All existing tests pass (no regressions from v0.12.0 baseline)
9. ✅ New tests for SARIF, JUnit, and git integration
10. ✅ ruff: 0 issues
11. ✅ basedpyright: 0 errors
12. ✅ README updated with CI/CD examples
13. ✅ Release notes created
14. ✅ Version bumped to 0.13.0

---

## Part 7: Risk Assessment

| Risk | Mitigation |
|------|------------|
| SARIF schema complexity | Validate output against official JSON schema using `jsonschema` in tests |
| Git archive performance on large repos | `git archive` is fast (reads from packfile); no caching needed |
| JUnit XML format variations | Stick to JUnit 4 schema; validate with `xml.etree.ElementTree` in tests |
| Backward compatibility | `--json` remains as deprecated alias; removal in v0.14.0 |
| Git not installed | Clear error message: "git is required for --compare mode" |
| Invalid ref | Clear error message: "ref <ref> not found" |
| Submodules | Not supported in v13; documented limitation, support in v14 |
| `atexit` limitations | Use `tempfile.TemporaryDirectory` instead — handles cleanup more robustly |

---

## Part 8: Explicitly Not in Scope

- **CI server integration** (Jenkins plugin, GitLab integration) — out of scope
- **Web dashboard** — future work
- **`--include-dirty` flag** — deferred to v14
- **`--recurse-submodules` flag** — deferred to v14
- **New claim types** — unrelated to CI/CD, tracked separately

---

*Document created: 2026-08-28*
*Review 1 fixes applied: 2026-08-28*
*Review 2 fixes applied: 2026-08-28*
