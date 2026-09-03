"""Packaging metadata tests (v0.15.0 — PyPI publishing).

Offline and deterministic: parse ``pyproject.toml`` with ``tomllib`` and
inspect the ``nowreck`` package directly. No network, no build step.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import nowreck

ROOT = Path(__file__).resolve().parent.parent


def _load_pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# [project] metadata
# ---------------------------------------------------------------------------


class TestPyprojectMetadata:
    def test_version_matches_package_version(self) -> None:
        """The two version sites must not drift (bump both together)."""
        pyproject = _load_pyproject()
        assert pyproject["project"]["version"] == nowreck.__version__

    def test_readme_field_points_to_existing_file(self) -> None:
        """PyPI page description source must exist at build time."""
        pyproject = _load_pyproject()
        readme = pyproject["project"]["readme"]
        assert (ROOT / readme).is_file()

    def test_license_is_spdx_and_file_exists(self) -> None:
        """PEP 639: license as SPDX expression + license file shipped."""
        pyproject = _load_pyproject()
        assert pyproject["project"]["license"] == "FSL-1.1-MIT"
        license_files = pyproject["project"]["license-files"]
        assert license_files, "license-files must list at least one file"
        for rel in license_files:
            assert (ROOT / rel).is_file(), f"license file missing: {rel}"

    def test_project_urls_present(self) -> None:
        pyproject = _load_pyproject()
        urls = pyproject["project"]["urls"]
        assert urls.get("Homepage") == "https://github.com/AstralXVoid/NoWreck"
        assert urls.get("Source") == "https://github.com/AstralXVoid/NoWreck"

    def test_build_requires_setuptools_for_pep639(self) -> None:
        """License-as-SPDX-string needs setuptools >= 77 (PEP 639 support)."""
        pyproject = _load_pyproject()
        requires = pyproject["build-system"]["requires"]
        pins = [r for r in requires if r.startswith("setuptools")]
        assert pins, "no setuptools pin in build-system.requires"
        match = re.search(r">=?(\d+)", pins[0])
        assert match, f"cannot parse setuptools pin: {pins[0]}"
        assert int(match.group(1)) >= 77


# ---------------------------------------------------------------------------
# Entry points and package discovery
# ---------------------------------------------------------------------------


class TestEntryPointsAndPackaging:
    def test_console_script_entry_point(self) -> None:
        pyproject = _load_pyproject()
        scripts = pyproject["project"]["scripts"]
        assert scripts["nowreck"] == "nowreck.__main__:main"

    def test_console_script_target_importable(self) -> None:
        """The entry-point target must exist and be callable."""
        import nowreck.__main__ as main_module

        assert callable(main_module.main)

    def test_packages_find_includes_only_nowreck(self) -> None:
        """Wheel must contain only the nowreck package, nothing else."""
        pyproject = _load_pyproject()
        find = pyproject["tool"]["setuptools"]["packages"]["find"]
        assert find["where"] == ["."]
        assert find["include"] == ["nowreck*"]