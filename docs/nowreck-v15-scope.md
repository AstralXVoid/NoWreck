# NoWreck v0.15.0 — Scope

**Release goal:** Publish NoWreck to PyPI so users can `pip install nowreck`.

---

## Problem

Installation currently requires cloning the repository and building in place:

```bash
git clone https://github.com/AstralXVoid/NoWreck.git
cd NoWreck
pipx install .        # or: pip install -e .
```

The README itself says *"…installs `nowreck` as a globally available command in
your user environment (PyPI publishing is coming later)."* — external users
cannot `pip install nowreck`.

`pyproject.toml` is also missing the metadata a PyPI page needs:

- No `readme` field → the PyPI project page would have no description
- No `license` field → license not surfaced on PyPI (repo is FSL-1.1-MIT)
- No `[project.urls]` → no Homepage/Source links on the project page
- No classifiers or keywords → poor discoverability

Version is duplicated across three sites (`pyproject.toml`, `nowreck/__init__.py`,
`_BANNER` in `main.py`) — a publishing release needs a guard so they can't drift.

## Solution

Publish properly tagged releases to PyPI:

```bash
# New — primary install path after v0.15.0
pipx install nowreck     # or: pip install nowreck
```

Facts verified during planning (no action needed):

- **Name `nowreck` is free on PyPI** (registry returns 404 for it)
- **README images are already absolute** `https://github.com/user-attachments/...`
  URLs → they render on the PyPI project page unchanged
- **`build/`, `dist/`, `*.egg-info/` are already gitignored** and untracked
- **Dependencies are publish-ready**: pydantic, questionary, tree-sitter + the
  four grammar packages all ship platform wheels (Linux/macOS/Windows); nothing
  to vendor
- **One pre-existing defect found**: README header image has a malformed HTML
  attribute `height="="140""` (line 9) — fix while editing that block

---

## Phase 1: Packaging metadata — `pyproject.toml`

**Files:** `pyproject.toml`, `README.md`

| Field | Change |
|-------|--------|
| `readme` | Add `readme = "README.md"` (Markdown auto-detected by extension) |
| `license` | Add `license = "FSL-1.1-MIT"` (SPDX expression, PEP 639) + `license-files = ["LICENSE"]` |
| `build-system` | Bump `setuptools>=75` → `setuptools>=77` (PEP 639 support) |
| `[project.urls]` | Add `Homepage` + `Source` → `https://github.com/AstralXVoid/NoWreck` |
| Classifiers | `Programming Language :: Python :: 3.11/3.12/3.13`, `Environment :: Console`, `Topic :: Software Development :: Quality Assurance` |
| `keywords` | e.g. `ai`, `verification`, `tree-sitter`, `llm`, `code-review` |
| `README.md` | Fix malformed `height="="140""` → `height="140"` (header avatar, line 9) |

**Version stays manually synced across the three existing sites** (pyproject /
`__init__.py` / `_BANNER`), matching the v0.14.0 process — guarded by a
consistency test in Phase 2 rather than a dynamic-version refactor (keeps this
increment narrow).

**Validation steps (local):** — `build` and `twine` are **not installed** on
this machine (verified), and neither should be installed globally — use a
throwaway venv (local Python is 3.13, satisfies `requires-python >=3.11`):

```bash
rm -rf build dist nowreck.egg-info          # clean slate (all gitignored)
python3 -m venv /tmp/nr-build
/tmp/nr-build/bin/pip install -q build twine
/tmp/nr-build/bin/python -m build           # sdist + wheel
/tmp/nr-build/bin/twine check dist/*        # metadata valid, README renders
unzip -l dist/nowreck-*.whl                 # no tests/, samples, docs inside
```

Then install the **wheel** (not `-e`) into a second fresh venv and verify:
`nowreck --version` → `0.15.0`, bare `nowreck` banner, and one real smoke run
(`nowreck fix --compare HEAD~1` inside a checkout).

---

## Phase 2: Tests + publish CI

**Files:** `tests/test_packaging.py` (new), `.github/workflows/publish.yml` (new)

### Packaging tests

New `tests/test_packaging.py` (offline, deterministic — parse `pyproject.toml`
with `tomllib`, read `nowreck/__init__.py` by import).

> **Found during Phase 2 verification (practical dress rehearsal):**
> 1. The `test` extra declared only `jsonschema` (unused by any test) and
>    **no pytest** — the publish gate would fail with `No module named pytest`
>    on a fresh runner. Root-cause fix: `test = ["pytest>=7", "jsonschema>=4.0"]`.
> 2. `TestPickerTerminal` (real-tmux PTY tests, run on GitHub runners) flaked
>    under load with 6s poll deadlines — could randomly block the publish
>    gate. Root-cause fix: generous load-tolerant deadlines (15s pane poll,
>    10s session-death poll) in `tests/test_picker_integration.py`.

- `pyproject.toml` `[project].version` == `nowreck.__version__`
- `readme` field points at an existing file; `license` is `FSL-1.1-MIT` and
  `LICENSE` exists; `[project.urls]` present
- console script `nowreck = nowreck.__main__:main` declared
- `packages.find` includes only `nowreck*`

### Publish workflow `.github/workflows/publish.yml`

Triggers on **tag pushes `v*` only** (never every push):

1. Checkout + set up Python 3.12
2. `pip install build twine`
3. **`python -m pytest` gate** — refuse to publish with failing tests
4. `python -m build` → `twine check dist/*`
5. Publish to PyPI via `pypa/gh-action-pypi-publish` (Trusted Publishing / OIDC,
   no token in repo)
6. Create a GitHub Release (`softprops/action-gh-release`) with the dist
   artifacts attached

The repo's own claims-armed NoWreck gate stays green on the tag push: a
metadata/docs/test-only commit produces no structural code changes → report-only
mode passes.

---

## Phase 3: Docs + version bump

| File | Change |
|------|--------|
| `nowreck/__init__.py` | `__version__` → `"0.15.0"` |
| `nowreck/main.py` | `_BANNER` → `NoWreck v0.15.0` |
| `pyproject.toml` | `version` → `"0.15.0"` |
| `README.md` | Install section → `pipx install nowreck` / `pip install nowreck` primary; source install demoted to "from source" alternative; remove *"(PyPI publishing is coming later)"*; Roadmap: add row `PyPI publishing — pip install nowreck` ✅ v0.15.0 |
| `use.md` | Install/uninstall examples (lines 34–59: `pipx install .` / `pip install -e .` / `pipx uninstall nowreck`) → `pipx install nowreck` etc. |
| `docs/release15.md` | Create release notes |

### README Installation section, before

```bash
# Clone the repository
git clone https://github.com/AstralXVoid/NoWreck.git
cd NoWreck
pipx install .
# ...pipx install . installs nowreck as a globally available command in your
# user environment (PyPI publishing is coming later).
```

### After

```bash
# From PyPI (recommended)
pipx install nowreck
# or: pip install nowreck

# From source (development)
git clone https://github.com/AstralXVoid/NoWreck.git
cd NoWreck
pip install -e .
```

---

## What this does NOT do

- No changes to scanners, detector, verifier, parsers, reporters, or exit codes
- No new CLI flags, claim types, or formats
- No automatic publish on every push — tags (`v*`) only
- Does not refactor to single-source versions (manual 3-site sync, guarded by test)
- Does not change the license — FSL-1.1-MIT stays; only adds SPDX metadata
- Does not vendor tree-sitter grammars (already proper pip deps with wheels)
- Does not create the PyPI account / trusted-publisher binding — that is a
  one-time user action on pypi.org, listed in the DoD below

---

## Definition of Done

- [x] `pyproject.toml` metadata complete (readme / license / urls / classifiers); `twine check` clean
- [x] sdist + wheel build cleanly from a fresh checkout
- [x] Wheel installs in a clean venv on Python 3.11+; `--version` → 0.15.0; smoke run passes
- [x] Wheel contents verified — no `tests/`, samples, or docs inside
- [x] `tests/test_packaging.py` added; version-consistency test passes
- [ ] `.github/workflows/publish.yml` live — tag `v*` → pytest gate → build → `twine check` → publish → GitHub Release *(file complete + locally dress-rehearsed; first execution happens on the `v0.15.0` tag push)*
- [ ] TestPyPI dry-run publish succeeds (user step: token or trusted publisher on test.pypi.org)
- [ ] Live PyPI publish of the `v0.15.0` tag (user step: trusted publisher on pypi.org/project/nowreck)
- [x] README + use.md show `pip install nowreck`; "coming later" text removed; roadmap row flipped to ✅ v0.15.0
- [x] Version bumped to 0.15.0 in all sites + `_BANNER`
- [x] `docs/release15.md` created
- [x] All existing tests pass

**Repo-side DoD: 9/9 complete.** Remaining 3 items are execution steps that require
GitHub/PyPI (tag push, TestPyPI + live publish) — the repo changes for them are all
in place and validated.
