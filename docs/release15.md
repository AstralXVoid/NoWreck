# NoWreck v0.15.0 — PyPI Publishing

**Release date:** September 2026
**Previous release:** v0.14.0 (@file Claims Input)
**Focus:** Publish NoWreck to PyPI so users can `pip install nowreck`.

---

## What's new in v0.15.0

### `pip install nowreck` ✅

NoWreck is now published on PyPI. Installing is a single command:

```bash
# From PyPI (recommended)
pipx install nowreck
# or: pip install nowreck

# From source (development)
git clone https://github.com/AstralXVoid/NoWreck.git
cd NoWreck
pip install -e .
```

**Why:** previously every user had to clone the repository and build in
place (`pipx install .`). PyPI removes that barrier and enables standard
dependency management.

### Complete PyPI metadata ✅

`pyproject.toml` now ships everything a PyPI page needs:

- `readme` — the full README renders on the project page (verified with
  `twine check` and PyPI's own renderer; all images use absolute URLs)
- `license` — SPDX expression `FSL-1.1-MIT` (PEP 639) with the license file
  bundled in the wheel
- `[project.urls]` — Homepage + Source links
- Classifiers (Python 3.11–3.13, Console, Quality Assurance) and keywords

**Build hardening:** `setuptools>=77` (PEP 639 support); `twine check`
passes on both the sdist and wheel; the wheel contains only the `nowreck`
package and its license — no tests, samples, or docs.

### Automated publish workflow ✅

New `.github/workflows/publish.yml`, triggered on `v*` tags only:

1. Run the full test suite (gate — never publish with failing tests)
2. Build sdist + wheel
3. `twine check`
4. Publish to PyPI via trusted publishing (OIDC — no token in the repo)
5. Create a GitHub Release with the artifacts attached

### Reliability fixes (discovered during release verification)

- The `test` extra now declares `pytest` — the CI test gate was missing it
  entirely (`No module named pytest` on a fresh runner)
- `TestPickerTerminal` (real-tmux PTY tests) poll deadlines increased from
  6s to 15s — the old deadlines flaked under load and could randomly block
  the publish gate

---

## What's unchanged

| What | Why |
|------|-----|
| CLI, flags, exit codes | Untouched — publishing is distribution, not features |
| Scanners, detector, verifier, parsers, reporters | Untouched |
| All 13 claim types | No new types |
| License | Still FSL-1.1-MIT (auto-converts to MIT in July 2028) |
| Install from source | Still supported (`pip install -e .`) |

## Test results

| Suite | Count | Status |
|-------|-------|--------|
| Full pytest suite | 809 | ✅ all pass (verified under pytest 7.x and 9.x) |
| New packaging metadata tests (`tests/test_packaging.py`) | 8 | ✅ all pass |

## Files modified

| File | Change |
|------|--------|
| `pyproject.toml` | Version → `"0.15.0"`; `readme`, SPDX `license` + `license-files`, `[project.urls]`, classifiers, keywords; `setuptools>=77`; `test` extra gains `pytest>=7` |
| `nowreck/__init__.py` | `__version__` → `"0.15.0"` |
| `nowreck/main.py` | `_BANNER` → v0.15.0 |
| `README.md` | Install section → PyPI-first; version surfaces → v0.15.0; roadmap row `PyPI publishing — pip install nowreck` ✅ v0.15.0 |
| `use.md` | Install/uninstall examples → `pip install nowreck`; version example → v0.15.0 |
| `.github/workflows/publish.yml` | **New** — tag-triggered build → gate → `twine check` → PyPI (trusted publishing) → GitHub Release |
| `tests/test_packaging.py` | **New** — 8 offline packaging metadata tests (version sync, license, entry points, package discovery) |
| `tests/test_picker_integration.py` | Flake fix: load-tolerant tmux poll deadlines (15s / 10s) |
| `docs/nowreck-v15-scope.md` | **New** — v0.15.0 scope document |
| `docs/release15.md` | **New** — these release notes |