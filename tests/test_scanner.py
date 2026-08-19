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


@pytest.fixture
def js_only_repo(tmp_path: Path) -> Path:
    """A repo with JavaScript files only (no Python)."""
    (tmp_path / "app.js").write_text("function greet() { return 'hello'; }\n")
    (tmp_path / "utils.js").write_text(
        "const double = (n) => n * 2;\n",
    )
    return tmp_path


@pytest.fixture
def mixed_repo(tmp_path: Path) -> Path:
    """A repo with both Python and JavaScript files."""
    (tmp_path / "main.py").write_text("def run(): ...\n")
    (tmp_path / "models.py").write_text("class User: pass\n")
    (tmp_path / "app.js").write_text("function greet() {}\n")
    (tmp_path / "utils.js").write_text(
        "const helper = () => {};\n"
        "class Widget { render() {} }\n",
    )
    return tmp_path


@pytest.fixture
def repo_with_js_hidden_dirs(tmp_path: Path) -> Path:
    """A repo with .js files inside hidden directories that should be ignored."""
    (tmp_path / "visible.js").write_text("function visible() {}\n")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "ignored.js").write_text("function ignored() {}\n")
    return tmp_path


@pytest.fixture
def repo_with_empty_js(tmp_path: Path) -> Path:
    """A repo with an empty .js file (valid, but produces no symbols)."""
    (tmp_path / "empty.js").write_text("")
    (tmp_path / "code.py").write_text("x = 1\n")
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

    # ------------------------------------------------------------------
    # JavaScript discovery and parsing
    # ------------------------------------------------------------------

    def test_scan_finds_js_files(self, js_only_repo: Path) -> None:
        """JS-only repository: all .js files are discovered and parsed."""
        scanner = RepositoryScanner(js_only_repo)
        result = scanner.scan()

        assert result.success_count == 2  # app.js + utils.js
        assert result.failure_count == 0

        assert Path("app.js") in result.js_files
        assert Path("utils.js") in result.js_files

        # app.js has one function declaration
        app_symbols = result.js_files[Path("app.js")]
        assert len(app_symbols) == 1
        assert app_symbols[0].name == "greet"

        # utils.js has one arrow function
        utils_symbols = result.js_files[Path("utils.js")]
        assert len(utils_symbols) == 1
        assert utils_symbols[0].name == "double"

    def test_scan_mixed_python_and_js(self, mixed_repo: Path) -> None:
        """Mixed repo: both .py and .js files are discovered and parsed."""
        scanner = RepositoryScanner(mixed_repo)
        result = scanner.scan()

        # 2 Python + 2 JavaScript = 4 successfully parsed files
        assert result.success_count == 4
        assert result.failure_count == 0

        # Python files in modules
        assert Path("main.py") in result.modules
        assert Path("models.py") in result.modules

        # JS files in js_files
        assert Path("app.js") in result.js_files
        assert Path("utils.js") in result.js_files

        # Verify JS symbol content
        assert len(result.js_files[Path("app.js")]) == 1  # function greet
        # utils.js has const helper + class Widget { render() } = 3 symbols
        assert len(result.js_files[Path("utils.js")]) == 3

    def test_scan_js_hidden_dirs_skipped(self, repo_with_js_hidden_dirs: Path) -> None:
        """.js files inside hidden directories are not discovered."""
        scanner = RepositoryScanner(repo_with_js_hidden_dirs)
        result = scanner.scan()

        assert result.success_count == 1  # only visible.js
        assert result.failure_count == 0
        assert Path("visible.js") in result.js_files

    def test_scan_js_empty_file(self, repo_with_empty_js: Path) -> None:
        """Empty .js files are parsed successfully (zero symbols)."""
        scanner = RepositoryScanner(repo_with_empty_js)
        result = scanner.scan()

        # Python file + empty JS file = 2 successes
        assert result.success_count == 2
        assert result.failure_count == 0

        assert Path("empty.js") in result.js_files
        assert result.js_files[Path("empty.js")] == []

    def test_scan_js_deterministic(self, mixed_repo: Path) -> None:
        """Two scans of the same mixed repo produce identical results."""
        scanner = RepositoryScanner(mixed_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        # Same number of files discovered
        assert result1.success_count == result2.success_count
        assert result1.failure_count == result2.failure_count

        # Same keys in all dicts
        assert list(result1.modules) == list(result2.modules)
        assert list(result1.js_files) == list(result2.js_files)
        assert list(result1.failed_files) == list(result2.failed_files)

        # Same symbols per JS file (use name+type as a proxy for equality)
        for rel_path in result1.js_files:
            syms1 = [(s.name, s.symbol_type) for s in result1.js_files[rel_path]]
            syms2 = [(s.name, s.symbol_type) for s in result2.js_files[rel_path]]
            assert syms1 == syms2


# ------------------------------------------------------------------
# Rust discovery and parsing
# ------------------------------------------------------------------


@pytest.fixture
def rust_only_repo(tmp_path: Path) -> Path:
    """A repo with Rust files only."""
    (tmp_path / "main.rs").write_text(
        "fn greet() -> &'static str { \"hello\" }\n",
    )
    (tmp_path / "utils.rs").write_text(
        "fn helper() -> i32 { 42 }\n",
    )
    return tmp_path


@pytest.fixture
def go_only_repo(tmp_path: Path) -> Path:
    """A repo with Go files only."""
    (tmp_path / "main.go").write_text(
        'package main\n\nfunc greet() string { return "hello" }\n',
    )
    (tmp_path / "utils.go").write_text(
        "package main\n\nfunc helper() int { return 42 }\n",
    )
    return tmp_path


@pytest.fixture
def multi_lang_repo(tmp_path: Path) -> Path:
    """A repo with Python, JS, TS, Rust, and Go files."""
    (tmp_path / "app.py").write_text("def run(): ...\n")
    (tmp_path / "util.js").write_text("function greet() {}\n")
    (tmp_path / "mod.ts").write_text("function hello(): void {}\n")
    (tmp_path / "lib.rs").write_text("fn compute() -> i32 { 0 }\n")
    (tmp_path / "srv.go").write_text(
        "package main\n\nfunc serve() {}\n",
    )
    return tmp_path


class TestRepositoryScannerRust:
    """Rust file discovery and parsing."""

    def test_scan_finds_rust_files(self, rust_only_repo: Path) -> None:
        scanner = RepositoryScanner(rust_only_repo)
        result = scanner.scan()

        assert result.success_count == 2
        assert result.failure_count == 0

        assert Path("main.rs") in result.rust_files
        assert Path("utils.rs") in result.rust_files

        main_syms = result.rust_files[Path("main.rs")]
        assert len(main_syms) == 1
        assert main_syms[0].name == "greet"

    def test_scan_rust_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "visible.rs").write_text("fn visible() {}\n")
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "ignored.rs").write_text("fn ignored() {}\n")

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()

        assert result.success_count == 1
        assert Path("visible.rs") in result.rust_files
        assert Path("ignored.rs") not in result.rust_files

    def test_scan_rust_deterministic(self, rust_only_repo: Path) -> None:
        scanner = RepositoryScanner(rust_only_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        assert result1.success_count == result2.success_count
        for path in result1.rust_files:
            syms1 = [(s.name, s.symbol_type) for s in result1.rust_files[path]]
            syms2 = [(s.name, s.symbol_type) for s in result2.rust_files[path]]
            assert syms1 == syms2


class TestRepositoryScannerGo:
    """Go file discovery and parsing."""

    def test_scan_finds_go_files(self, go_only_repo: Path) -> None:
        scanner = RepositoryScanner(go_only_repo)
        result = scanner.scan()

        assert result.success_count == 2
        assert result.failure_count == 0

        assert Path("main.go") in result.go_files
        assert Path("utils.go") in result.go_files

        main_syms = result.go_files[Path("main.go")]
        assert len(main_syms) == 1
        assert main_syms[0].name == "greet"

    def test_scan_go_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "visible.go").write_text(
            "package main\n\nfunc visible() {}\n",
        )
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "ignored.go").write_text(
            "package main\n\nfunc ignored() {}\n",
        )

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()

        assert result.success_count == 1
        assert Path("visible.go") in result.go_files
        assert Path("ignored.go") not in result.go_files

    def test_scan_go_deterministic(self, go_only_repo: Path) -> None:
        scanner = RepositoryScanner(go_only_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        assert result1.success_count == result2.success_count
        for path in result1.go_files:
            syms1 = [(s.name, s.symbol_type) for s in result1.go_files[path]]
            syms2 = [(s.name, s.symbol_type) for s in result2.go_files[path]]
            assert syms1 == syms2


class TestRepositoryScannerMultiLang:
    """Multi-language repo with all 5 families."""

    def test_scan_discovers_all_languages(self, multi_lang_repo: Path) -> None:
        scanner = RepositoryScanner(multi_lang_repo)
        result = scanner.scan()

        assert result.success_count == 5
        assert Path("app.py") in result.modules
        assert Path("util.js") in result.js_files
        assert Path("mod.ts") in result.ts_files
        assert Path("lib.rs") in result.rust_files
        assert Path("srv.go") in result.go_files

    def test_scan_success_count_includes_all(
        self, multi_lang_repo: Path,
    ) -> None:
        scanner = RepositoryScanner(multi_lang_repo)
        result = scanner.scan()
        expected = (
            len(result.modules)
            + len(result.js_files)
            + len(result.ts_files)
            + len(result.rust_files)
            + len(result.go_files)
        )
        assert result.success_count == expected
