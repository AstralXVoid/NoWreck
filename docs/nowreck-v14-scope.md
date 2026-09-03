# NoWreck v0.14.0 — Scope

**Release goal:** `--claims @file.json` — read claims from a file instead of inline JSON only.

---

## Problem

`--claims` currently only accepts inline JSON strings:

```bash
nowreck fix --pre ./before --post ./after \
  --claims '{"claims": [{"type": "ADD_FUNCTION", "symbol_name": "greet"}]}'
```

This is painful for:
- Large claim sets (shell quoting hell)
- CI pipelines that generate claims files
- Piping output from other tools
- The README itself suggests `cat claims.json | xargs -I{} ...` as a workaround

## Solution

`@` prefix reads from a file (like `curl -d @file`):

```bash
# New — read from file
nowreck fix --pre ./before --post ./after --claims @claims.json

# Old — still works (inline JSON)
nowreck fix --pre ./before --post ./after --claims '{"claims": [...]}'
```

---

## Phase 1: Core — `resolve_claims_input()` helper

**Files:** `nowreck/main.py`

Add a helper function that resolves the `--claims` value. Follows the same pattern as `_resolve_path()` — raises `ValueError` on bad input, caller prints the error and returns 1.

```python
def resolve_claims_input(value: str) -> str:
    """Resolve --claims value. If it starts with '@', read from file."""
    value = value.strip()
    if not value.startswith("@"):
        return value

    raw_path = value[1:]
    if not raw_path:
        raise ValueError("--claims @ requires a file path")

    path = Path(raw_path).expanduser().resolve()
    cwd = Path.cwd().resolve()

    # Reject path traversal above CWD
    try:
        path.relative_to(cwd)
    except ValueError:
        raise ValueError(
            f"--claims path must be inside the current directory: {raw_path}"
        )

    if not path.exists():
        raise ValueError(f"claims file not found: {raw_path}")

    # Read errors are wrapped like ``_resolve_path()`` does — callers only
    # catch ValueError, so a raw OSError from read_text() (e.g. permission
    # denied) would traceback.
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read claims file: {raw_path}") from exc

    if not content.strip():
        # Raise instead of returning "" so the existing ``if args.claims:``
        # guards keep working — an empty string is falsy and would silently
        # skip parsing, producing no warning. Raising gives a clear error.
        raise ValueError(f"claims file is empty: {raw_path}")

    return content
```

**Integration points** — resolve at the two *int-returning entry points*
(both already wrap `ValueError` → `print` → `return 1`):

1. `handle_fix()` pre/post path — alongside the existing `_resolve_path()`
   try block at **line 154** in `main.py`. This feeds `_detect_and_verify()`
   (claims read at **line 457**).
2. `_handle_compare_mode()` — just after `ref = args.compare` at **line 524**
   (claims read at **line 567**).

> ⚠️ **Do NOT put `return 1` inside `_detect_and_verify()` itself** — it
> returns `VerificationReport`, not an int; the caller would crash on
> `report.unverifiable`. Resolve in the entry points below instead and
> reassign `args.claims` to the resolved text (it is only read after this
> point), so the parse sites stay untouched:

```python
# --- handle_fix() pre/post path (extend the existing try block) ---
try:
    pre_path = _resolve_path(args.pre)
    post_path = _resolve_path(args.post)
    if args.claims:
        args.claims = resolve_claims_input(args.claims)
except ValueError as exc:
    print(f"Error: {exc}", file=sys.stderr)
    return 1

# --- _handle_compare_mode(), before ``with GitSnapshot(ref)`` ---
if args.claims:
    try:
        args.claims = resolve_claims_input(args.claims)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
```

Both sites currently guard with `if args.claims:` and call
`ClaimParser.parse(args.claims)` — with the resolution above, `args.claims`
already holds file contents (or the original inline JSON) by then, so the
parse sites need **no change**. Prompt mode never resolves `--claims`
(claims are unused there).

---

## Phase 2: Tests

**File:** `tests/test_cli.py`

### Test cases

| Test | Input | Expected |
|------|-------|----------|
| `test_claims_from_file` | `@valid.json` where file contains valid JSON | Reads file content, parses successfully |
| `test_claims_from_file_missing` | `@nonexistent.json` | Exits with "claims file not found" error |
| `test_claims_from_file_traversal` | `@/etc/passwd` | Exits with "must be inside the current directory" error |
| `test_claims_inline_still_works` | `{"claims": [...]}` | Inline JSON works unchanged (regression — covered by existing `test_fix_with_claims_confirmed`) |
| `test_claims_at_with_no_path` | `@` | Exits with "requires a file path" error |
| `test_claims_from_file_empty` | `@empty.json` (empty file) | Exits with `"claims file is empty"` error (exit code 1) |
| `test_claims_at_with_whitespace` | `" @claims.json "` (spaces around) | Trimmed before `@` check, reads file successfully |

### Unit tests (resolve_claims_input in isolation)

> Placement: add a `class TestResolveClaimsInput` right after
> `class TestResolvePath` (test_cli.py:109) — same style, `self` + fixtures.
> The integration test below is a method of `class TestHandleFix`
> (test_cli.py:213). Add `resolve_claims_input` to the existing
> `from nowreck.main import (...)` block (test_cli.py:10-17).

> ⚠️ Every test that reads a file under `tmp_path` must `chdir` into it
> first: the traversal guard rejects anything outside CWD, and pytest's
> `tmp_path` lives under `/tmp`, outside the project directory. Tests that
> only exercise rejection (`@/etc/passwd`, `@` alone) need no chdir.

```python
def test_claims_from_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # tmp_path is now inside CWD
    claims_file = tmp_path / "claims.json"
    claims_file.write_text('{"claims": []}')
    result = resolve_claims_input(f"@{claims_file}")
    assert '"claims"' in result

def test_claims_from_file_traversal(self) -> None:
    with pytest.raises(ValueError, match="must be inside"):
        resolve_claims_input("@/etc/passwd")

def test_claims_from_file_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="file not found"):
        resolve_claims_input(f"@{tmp_path / 'nonexistent.json'}")

def test_claims_at_with_no_path(self) -> None:
    with pytest.raises(ValueError, match="requires a file path"):
        resolve_claims_input("@")

def test_claims_from_file_tilde_expansion(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # expanduser + CWD guard both exercised: HOME and CWD both point at
    # tmp_path, so @~/claims.json expands inside CWD and is accepted.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    claims_file = tmp_path / "claims.json"
    claims_file.write_text('{"claims": []}')
    result = resolve_claims_input("@~/claims.json")
    assert '"claims"' in result

def test_claims_at_with_whitespace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Leading/trailing whitespace is trimmed before @ check
    monkeypatch.chdir(tmp_path)
    claims_file = tmp_path / "claims.json"
    claims_file.write_text('{"claims": []}')
    result = resolve_claims_input(f"  @{claims_file}  ")
    assert '"claims"' in result

def test_claims_from_file_symlink(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Symlink to a file inside CWD is read through the link."""
    monkeypatch.chdir(tmp_path)
    real = tmp_path / "real.json"
    real.write_text('{"claims": []}')
    link = tmp_path / "link.json"
    link.symlink_to(real)
    result = resolve_claims_input(f"@{link}")
    assert '"claims"' in result

def test_claims_from_file_symlink_outside(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Symlink pointing OUTSIDE CWD is rejected — resolve() runs before
    the guard, so the target path fails the CWD-relative check."""
    monkeypatch.chdir(tmp_path)
    outside = Path("/etc/passwd")
    if not outside.exists():
        pytest.skip("no /etc/passwd to symlink to")
    link = tmp_path / "claims.json"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="must be inside"):
        resolve_claims_input(f"@{link}")

def test_claims_from_file_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty file raises a clear error instead of silently parsing ""."""
    monkeypatch.chdir(tmp_path)
    empty = tmp_path / "empty.json"
    empty.write_text("")
    with pytest.raises(ValueError, match="claims file is empty"):
        resolve_claims_input(f"@{empty}")
```

### Integration test (handle_fix with @file)

```python
def test_fix_with_claims_from_file(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: --claims @file triggers resolve + parse + verify."""
    # Set CWD to tmp_path so the @file path passes the CWD-relative check
    monkeypatch.chdir(tmp_path)

    pre = tmp_path / "pre"
    post = tmp_path / "post"
    pre.mkdir()
    post.mkdir()

    (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
    (post / "app.py").write_text(
        "def old(): pass\n\ndef new_fn(): pass\n", encoding="utf-8"
    )

    claims = json.dumps({
        "claims": [{
            "type": "ADD_FUNCTION",
            "symbol_name": "new_fn",
            "file_path": "app.py",
        }]
    })
    claims_file = tmp_path / "claims.json"
    claims_file.write_text(claims, encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args([
        "fix",
        "--pre", str(pre),
        "--post", str(post),
        "--claims", f"@{claims_file}",
    ])

    rc = handle_fix(args)
    assert rc == 0  # claim confirmed
```

---

## Phase 3: Docs + version bump

### Files to update

| File | Change |
|------|--------|
| `nowreck/cli.py` | Update `--claims` help text to mention `@file` syntax |
| `README.md` | Replace the "must be passed inline" paragraph (line 432) with `@file` docs + add example |
| `use.md` | Replace the `cat claims.json \| xargs` workaround (line 329) with the `@file` one-liner |
| `nowreck/__init__.py` | Bump `__version__` to `"0.14.0"` |
| `nowreck/main.py` | Update `_BANNER` from `v0.13.0` to `v0.14.0` |
| `pyproject.toml` | Bump `version` to `"0.14.0"` |
| `docs/release14.md` | Create release notes |

### CLI help text change

```
# Before
help="AI claims as a JSON string (advanced — skip to detect only)"

# After
help="AI claims as JSON string, or @file to read from file (advanced)"
```

### README addition (Claims Mode section)

Add after the existing inline JSON example:

```bash
# Read claims from a file (@ prefix)
nowreck fix --pre ./repo-before --post ./repo-after --claims @claims.json
```

**Must also replace** the paragraph that currently contradicts the feature
(README.md:432–433):

```markdown
Claims must be passed inline via `--claims`; the CLI does not currently
read claims from stdin. If you keep claims in a file, pass its JSON content
directly as the `--claims` argument.
```

…with:

```markdown
Claims can be passed inline via `--claims`, or read from a file using the
`@` prefix — useful for large claim sets and CI pipelines that generate
claims files.
```

`use.md` (line 329) has the same problem — it shows the shell workaround
`cat claims.json | xargs -I{} nowreck fix ... --claims '{}'` that this
feature eliminates. Replace that snippet with the `@claims.json` one-liner.

### Release notes template

```markdown
# NoWreck v0.14.0

## New: `--claims @file.json`

Claims can now be read from a file using the `@` prefix:

    nowreck fix --pre ./before --post ./after --claims @claims.json

Inline JSON still works unchanged.

Security: path traversal outside the current directory is rejected.
```

---

## What this does NOT do

- Does not touch the scanner, detector, verifier, or reporter
- Does not change any existing behavior
- Does not add new claim types or exit codes
- Pure additive — `@file` is opt-in, inline JSON unchanged
- **Symlinks:** the path is fully resolved *before* the CWD check, so a symlink pointing outside CWD (e.g. `./claims.json` → `/etc/passwd`) is **rejected** by the traversal guard. Symlinks to files *inside* CWD are read through the link. Verified behavior, covered by `test_claims_from_file_symlink` (inside) and `test_claims_from_file_symlink_outside` (rejected).

---

## Definition of Done

- [x] `nowreck fix --pre A --post B --claims @file.json` works
- [x] `@` paths are `expanduser`-expanded, then still subject to the CWD-relative check (`@~/file` works when HOME is under CWD; rejected otherwise)
- [x] `nowreck fix --pre A --post B --claims '{...}'` still works (regression)
- [x] Path traversal (`@/etc/passwd`) is rejected with clear error
- [x] Missing file gives clear error
- [x] Empty file gives clear `"claims file is empty"` error + exit code 1
- [x] `@` alone gives clear error
- [x] `" @file.json"` (leading whitespace) works correctly — trimmed before `@` check
- [x] All existing tests pass
- [x] Unit tests for `resolve_claims_input()` added
- [x] End-to-end integration test via `handle_fix` + `@file` added (uses `monkeypatch.chdir()` so claims file is CWD-relative)
- [x] `--claims` help text updated
- [x] README.md and use.md updated with @file examples
- [x] Version bumped to 0.14.0
- [x] `_BANNER` updated to v0.14.0
- [x] Release notes created
