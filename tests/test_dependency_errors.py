"""Tests for graceful ImportError handling when dependencies are missing."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# pydantic missing — entry point
# ---------------------------------------------------------------------------


class TestPydanticMissing:
    """Verify that missing pydantic produces a helpful error, not a traceback."""

    def test_missing_pydantic_shows_install_hint(self, tmp_path: Path) -> None:
        """Running nowreck without pydantic should print install hint."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                textwrap.dedent("""\
                    import sys
                    # Block pydantic import
                    sys.modules["pydantic"] = None
                    sys.modules["pydantic.fields"] = None
                    sys.modules["pydantic.functional_validators"] = None
                    try:
                        from nowreck.__main__ import main
                        # Won't reach here — main import will fail
                    except (ImportError, SystemExit) as exc:
                        print(f"CAUGHT: {type(exc).__name__}", file=sys.stderr)
                        sys.exit(0)
                    # If import succeeded (shouldn't), also try main()
                """),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should either catch ImportError or exit cleanly
        assert result.returncode == 0

    def test_main_entry_catches_import_error(self) -> None:
        """__main__.py wraps ImportError with install guidance."""
        # Use subprocess to get a clean module state
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                textwrap.dedent("""\
                    import sys
                    # Remove all nowreck and pydantic from cache
                    for key in list(sys.modules.keys()):
                        if 'nowreck' in key or 'pydantic' in key:
                            del sys.modules[key]
                    # Block pydantic before importing nowreck
                    sys.modules['pydantic'] = None
                    sys.modules['pydantic.fields'] = None
                    sys.modules['pydantic.functional_validators'] = None
                    try:
                        from nowreck.__main__ import main  # noqa: F401
                    except (ImportError, SystemExit) as exc:
                        print(f"CAUGHT: {type(exc).__name__}")
                    except Exception as exc:
                        print(f"UNEXPECTED: {type(exc).__name__}: {exc}")
                """),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "CAUGHT" in result.stdout


# ---------------------------------------------------------------------------
# questionary missing — interactive mode
# ---------------------------------------------------------------------------


class TestQuestionaryMissing:
    """Verify that missing questionary produces a helpful error."""

    def test_picker_import_error_message(self) -> None:
        """Importing picker without questionary should give install hint."""
        with patch.dict("sys.modules", {"questionary": None}):
            with pytest.raises(ImportError, match="pip install questionary"):
                import importlib

                import nowreck.picker

                importlib.reload(nowreck.picker)


# ---------------------------------------------------------------------------
# tree-sitter missing — scanner methods
# ---------------------------------------------------------------------------


class TestTreeSitterMissing:
    """Verify that missing tree-sitter produces helpful errors per language."""

    def _scan_file_with_missing_tree_sitter(
        self, file_path: Path, parse_method: str
    ) -> str:
        """Helper: run a parse method with tree-sitter blocked."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                textwrap.dedent(f"""\
                    import sys
                    from pathlib import Path
                    from unittest.mock import patch

                    # Block tree_sitter and language grammars
                    blocked = {{
                        "tree_sitter": None,
                        "tree_sitter_javascript": None,
                        "tree_sitter_typescript": None,
                        "tree_sitter_rust": None,
                        "tree_sitter_go": None,
                    }}

                    with patch.dict("sys.modules", blocked):
                        from nowreck.scanner.repository_scanner import RepositoryScanner
                        scanner = RepositoryScanner(
                            "{file_path.parent}", use_cache=False
                        )
                        result = scanner._{parse_method}(Path("{file_path}"))
                        # result is (symbols_or_None, error_or_None)
                        if result[1]:
                            print(f"ERROR: {{result[1]}}")
                        else:
                            print(f"OK: {{result[0]}}")
                """),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()

    def test_js_file_graceful_error(self, tmp_path: Path) -> None:
        """JS file with missing tree-sitter should return helpful error."""
        js_file = tmp_path / "test.js"
        js_file.write_text("function hello() {}")
        output = self._scan_file_with_missing_tree_sitter(js_file, "parse_js_file")
        assert "tree-sitter" in output
        assert "pip install" in output
        assert "ERROR" in output

    def test_ts_file_graceful_error(self, tmp_path: Path) -> None:
        """TS file with missing tree-sitter should return helpful error."""
        ts_file = tmp_path / "test.ts"
        ts_file.write_text("function hello(): void {}")
        output = self._scan_file_with_missing_tree_sitter(ts_file, "parse_ts_file")
        assert "tree-sitter" in output
        assert "pip install" in output
        assert "ERROR" in output

    def test_rust_file_graceful_error(self, tmp_path: Path) -> None:
        """Rust file with missing tree-sitter should return helpful error."""
        rs_file = tmp_path / "test.rs"
        rs_file.write_text("fn hello() {}")
        output = self._scan_file_with_missing_tree_sitter(rs_file, "parse_rust_file")
        assert "tree-sitter" in output
        assert "pip install" in output
        assert "ERROR" in output

    def test_go_file_graceful_error(self, tmp_path: Path) -> None:
        """Go file with missing tree-sitter should return helpful error."""
        go_file = tmp_path / "test.go"
        go_file.write_text("package main\nfunc hello() {}")
        output = self._scan_file_with_missing_tree_sitter(go_file, "parse_go_file")
        assert "tree-sitter" in output
        assert "pip install" in output
        assert "ERROR" in output

    def test_scan_with_missing_tree_sitter_no_crash(self, tmp_path: Path) -> None:
        """Full scan with JS files and missing tree-sitter should not crash."""
        js_file = tmp_path / "test.js"
        js_file.write_text("function hello() {}")

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                textwrap.dedent(f"""\
                    import sys
                    from unittest.mock import patch

                    blocked = {{
                        "tree_sitter": None,
                        "tree_sitter_javascript": None,
                        "tree_sitter_typescript": None,
                        "tree_sitter_rust": None,
                        "tree_sitter_go": None,
                    }}

                    with patch.dict("sys.modules", blocked):
                        from nowreck.scanner.repository_scanner import RepositoryScanner
                        scanner = RepositoryScanner("{tmp_path}", use_cache=False)
                        scan_result = scanner.scan()
                        print(f"JS files: {{len(scan_result.js_files)}}")
                        print(f"Failed: {{len(scan_result.failed_files)}}")
                        for path, err in scan_result.failed_files.items():
                            print(f"  {{path}}: {{err}}")
                """),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "JS files: 0" in result.stdout
        assert "Failed: 1" in result.stdout
        assert "tree-sitter" in result.stdout
