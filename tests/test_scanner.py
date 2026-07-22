from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from nowreck.scanner.repository_scanner import RepositoryScanner, ScanResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    """A temporary directory with no Python files."""
    return tmp_path


@pytest.fixture
def simple_repo(tmp_path: Path) -> Path:
    """A temporary directory containing a valid Python module."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text(
        textwrap.dedent("""\
            def greet(name: str) -> str:
                return f"Hello, {name}!"
        """),
    )
    return tmp_path


@pytest.fixture
def repo_with_invalid_file(tmp_path: Path) -> Path:
    """A repo containing one valid and one syntactically invalid file."""
    (tmp_path / "valid.py").write_text("x = 1\n")
    (tmp_path / "invalid.py").write_text(
        "def broken(\n"
    )  # SyntaxError: incomplete function
    return tmp_path


@pytest.fixture
def nested_repo(tmp_path: Path) -> Path:
    """A repo with nested package structure."""
    pkg = tmp_path / "mypackage" / "sub"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text("class MyClass:\n    pass\n")
    (tmp_path / "top_level.py").write_text("y = 2\n")
    return tmp_path


@pytest.fixture
def repo_with_hidden_dirs(tmp_path: Path) -> Path:
    """A repo that has hidden directories (like .git, .venv) with .py files
    inside them — those should *not* be discovered."""
    # Non-hidden file
    (tmp_path / "visible.py").write_text("a = 1\n")
    # Hidden directory with a .py file — should be skipped
    hidden = tmp_path / ".hidden" / "sub"
    hidden.mkdir(parents=True)
    (hidden / "should_be_ignored.py").write_text("b = 2\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScanResult:
    """ScanResult is a simple frozen dataclass."""

    def test_empty_result(self) -> None:
        result = ScanResult()
        assert result.modules == {}
        assert result.failed_files == {}
        assert result.success_count == 0
        assert result.failure_count == 0

    def test_with_data(self) -> None:
        tree = ast.parse("x = 1")
        result = ScanResult(
            modules={Path("f.py"): tree},
            failed_files={Path("bad.py"): "SyntaxError"},
        )
        assert result.success_count == 1
        assert result.failure_count == 1


class TestRepositoryScannerInit:
    """RepositoryScanner initialisation."""

    def test_resolves_to_absolute_path(self) -> None:
        scanner = RepositoryScanner(".")
        assert scanner.repo_path.is_absolute()

    def test_accepts_pathlib_path(self, empty_repo: Path) -> None:
        scanner = RepositoryScanner(empty_repo)
        assert scanner.repo_path == empty_repo.resolve()


class TestRepositoryScannerScan:
    """Core scan behaviour."""

    def test_scan_empty_directory_returns_empty_result(self, empty_repo: Path) -> None:
        scanner = RepositoryScanner(empty_repo)
        result = scanner.scan()
        assert result.success_count == 0
        assert result.failure_count == 0

    def test_scan_finds_and_parses_python_files(self, simple_repo: Path) -> None:
        scanner = RepositoryScanner(simple_repo)
        result = scanner.scan()
        assert result.success_count == 1
        assert result.failure_count == 0

        relative_path = Path("src/hello.py")
        module = result.modules.get(relative_path)
        assert module is not None
        assert isinstance(module, ast.Module)
        # The module has one function definition
        assert len(module.body) == 1
        func_def = module.body[0]
        assert isinstance(func_def, ast.FunctionDef)
        assert func_def.name == "greet"

    def test_scan_returns_deterministic_results(self, simple_repo: Path) -> None:
        """Two scans of the same repository must return identical results."""
        scanner = RepositoryScanner(simple_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        assert list(result1.modules.keys()) == list(result2.modules.keys())
        for path, tree1 in result1.modules.items():
            tree2 = result2.modules[path]
            assert ast.dump(tree1) == ast.dump(tree2)

    def test_scan_handles_invalid_syntax(self, repo_with_invalid_file: Path) -> None:
        scanner = RepositoryScanner(repo_with_invalid_file)
        result = scanner.scan()

        # Valid file should be parsed successfully
        assert result.success_count == 1
        assert Path("valid.py") in result.modules

        # Invalid file should appear in failed_files, not modules
        assert result.failure_count == 1
        assert Path("invalid.py") in result.failed_files

    def test_scan_discovers_nested_files(self, nested_repo: Path) -> None:
        scanner = RepositoryScanner(nested_repo)
        result = scanner.scan()

        assert result.success_count == 2
        # Both files discovered regardless of nesting depth
        paths = {str(p) for p in result.modules}
        assert "top_level.py" in paths
        assert "mypackage/sub/mod.py" in paths

    def test_scan_skips_hidden_directories(self, repo_with_hidden_dirs: Path) -> None:
        scanner = RepositoryScanner(repo_with_hidden_dirs)
        result = scanner.scan()

        assert result.success_count == 1  # only visible.py
        assert result.failure_count == 0
        assert Path("visible.py") in result.modules

    def test_scan_non_existent_directory(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "does_not_exist"
        scanner = RepositoryScanner(fake_path)
        result = scanner.scan()

        assert result.success_count == 0
        assert result.failure_count == 0

    @pytest.mark.parametrize("filename", ["__init__.py", "main.py", "utils.py"])
    def test_scan_various_valid_filenames(self, tmp_path: Path, filename: str) -> None:
        (tmp_path / filename).write_text("x = 1\n")
        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()
        assert result.success_count == 1
        assert Path(filename) in result.modules

    def test_scan_non_utf8_file_is_handled(self, tmp_path: Path) -> None:
        """Binary-looking content that isn't valid UTF-8."""
        py_file = tmp_path / "bad_encoding.py"
        py_file.write_bytes(b"x = 1\n# \xff\xfe\n")
        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()
        # The file exists as a .py but fails to decode — filed as failure
        assert result.failure_count == 1
        assert Path("bad_encoding.py") in result.failed_files

    def test_scan_only_parses_py_files(self, tmp_path: Path) -> None:
        """Non-.py files should be ignored."""
        (tmp_path / "readme.md").write_text("# Not Python\n")
        (tmp_path / "data.json").write_text('{"key": "value"}\n')
        (tmp_path / "script.py").write_text("z = 3\n")
        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()
        assert result.success_count == 1
        assert Path("script.py") in result.modules

    def test_scan_handles_null_bytes_gracefully(self, tmp_path: Path) -> None:
        """A .py file containing null bytes should not crash the scanner.

        ``ast.parse()`` raises ``ValueError`` (or ``SyntaxError`` on
        Python ≥ 3.12) when source contains null bytes. The scanner
        catches both and records the file as a failure.
        """
        null_file = tmp_path / "null_bytes.py"
        # Valid Python followed by a null byte
        null_file.write_text("x = 1\n\x00\n", encoding="utf-8")
        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()
        assert result.success_count == 0
        assert result.failure_count == 1
        assert Path("null_bytes.py") in result.failed_files
