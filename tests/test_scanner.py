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
        "const helper = () => {};\nclass Widget { render() {} }\n",
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
        'fn greet() -> &\'static str { "hello" }\n',
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
def java_only_repo(tmp_path: Path) -> Path:
    """A repo with Java files only."""
    (tmp_path / "Main.java").write_text(
        'public class Main {\n  static String greet() { return "hello"; }\n}\n',
    )
    (tmp_path / "Utils.java").write_text(
        "public class Utils {\n  static int helper() { return 42; }\n}\n",
    )
    return tmp_path


@pytest.fixture
def kotlin_only_repo(tmp_path: Path) -> Path:
    """A repo with Kotlin files only.

    Unlike Java, Kotlin has top-level functions, so one file exercises the
    FUNCTION path and the other the CLASS/METHOD path.
    """
    (tmp_path / "Main.kt").write_text(
        'class Main {\n    fun greet(): String = "hello"\n}\n',
    )
    (tmp_path / "Utils.kt").write_text(
        "fun helper(): Int {\n    return 42\n}\n",
    )
    return tmp_path


@pytest.fixture
def php_only_repo(tmp_path: Path) -> Path:
    """A repo with PHP files only.

    PHP has top-level functions (like Kotlin), so one file exercises the
    FUNCTION path and the other the CLASS/METHOD path.
    """
    (tmp_path / "Main.php").write_text(
        "<?php\n\nclass Main\n{\n    public function greet(): string\n"
        "    {\n        return 'hello';\n    }\n}\n",
    )
    (tmp_path / "Utils.php").write_text(
        "<?php\n\nfunction helper(): int\n{\n    return 42;\n}\n",
    )
    return tmp_path


@pytest.fixture
def cpp_only_repo(tmp_path: Path) -> Path:
    """A repo with C++ files only.

    C++ has namespace-scope functions (like Rust/Go), so one file
    exercises the FUNCTION path and the other the CLASS/METHOD path.
    """
    (tmp_path / "Main.cpp").write_text(
        "class Main\n"
        "{\n"
        "public:\n"
        "    int greet() const\n"
        "    {\n"
        "        return 1;\n"
        "    }\n"
        "};\n",
    )
    (tmp_path / "Utils.cpp").write_text(
        "int helper()\n{\n    return 42;\n}\n",
    )
    return tmp_path


@pytest.fixture
def multi_lang_repo(tmp_path: Path) -> Path:
    """A repo with Python, JS, TS, Rust, Go, Java, Kotlin, PHP, C++ files."""
    (tmp_path / "app.py").write_text("def run(): ...\n")
    (tmp_path / "util.js").write_text("function greet() {}\n")
    (tmp_path / "mod.ts").write_text("function hello(): void {}\n")
    (tmp_path / "lib.rs").write_text("fn compute() -> i32 { 0 }\n")
    (tmp_path / "srv.go").write_text(
        "package main\n\nfunc serve() {}\n",
    )
    (tmp_path / "App.java").write_text(
        "public class App {\n  void boot() {}\n}\n",
    )
    (tmp_path / "App.kt").write_text(
        "class App {\n  fun boot() {}\n}\n",
    )
    (tmp_path / "Index.php").write_text(
        "<?php\n\nfunction index(): void\n{\n}\n",
    )
    (tmp_path / "app.cpp").write_text(
        "int entry()\n{\n    return 1;\n}\n",
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


class TestRepositoryScannerJava:
    """Java file discovery and parsing."""

    def test_scan_finds_java_files(self, java_only_repo: Path) -> None:
        scanner = RepositoryScanner(java_only_repo)
        result = scanner.scan()

        assert result.success_count == 2
        assert result.failure_count == 0

        assert Path("Main.java") in result.java_files
        assert Path("Utils.java") in result.java_files

        main_syms = result.java_files[Path("Main.java")]
        # Java has no top-level functions: the class plus its method.
        assert [(s.name, s.symbol_type.name) for s in main_syms] == [
            ("Main", "CLASS"),
            ("greet", "METHOD"),
        ]
        assert main_syms[1].parent_class == "Main"

    def test_scan_java_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "Visible.java").write_text("public class Visible {}\n")
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "Ignored.java").write_text("public class Ignored {}\n")

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()

        assert result.success_count == 1
        assert Path("Visible.java") in result.java_files
        assert Path("Ignored.java") not in result.java_files

    def test_scan_java_deterministic(self, java_only_repo: Path) -> None:
        scanner = RepositoryScanner(java_only_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        assert result1.success_count == result2.success_count
        for path in result1.java_files:
            syms1 = [(s.name, s.symbol_type) for s in result1.java_files[path]]
            syms2 = [(s.name, s.symbol_type) for s in result2.java_files[path]]
            assert syms1 == syms2

    def test_scan_java_counts_in_success_total(self, java_only_repo: Path) -> None:
        result = RepositoryScanner(java_only_repo).scan()
        assert result.success_count == len(result.java_files)


class TestRepositoryScannerKotlin:
    """Kotlin file discovery and parsing (v0.17.0 Phase 3)."""

    def test_scan_finds_kotlin_files(self, kotlin_only_repo: Path) -> None:
        scanner = RepositoryScanner(kotlin_only_repo)
        result = scanner.scan()

        assert result.success_count == 2
        assert result.failure_count == 0

        assert Path("Main.kt") in result.kotlin_files
        assert Path("Utils.kt") in result.kotlin_files

        main_syms = result.kotlin_files[Path("Main.kt")]
        assert [(s.name, s.symbol_type.name) for s in main_syms] == [
            ("Main", "CLASS"),
            ("greet", "METHOD"),
        ]
        assert main_syms[1].parent_class == "Main"

        # Kotlin *does* have top-level functions (Java does not).
        util_syms = result.kotlin_files[Path("Utils.kt")]
        assert [(s.name, s.symbol_type.name) for s in util_syms] == [
            ("helper", "FUNCTION"),
        ]
        assert util_syms[0].parent_class is None

    def test_scan_kotlin_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "Visible.kt").write_text("class Visible\n")
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "Ignored.kt").write_text("class Ignored\n")

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()

        assert result.success_count == 1
        assert Path("Visible.kt") in result.kotlin_files
        assert Path("Ignored.kt") not in result.kotlin_files

    def test_scan_kotlin_deterministic(self, kotlin_only_repo: Path) -> None:
        scanner = RepositoryScanner(kotlin_only_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        assert result1.success_count == result2.success_count
        for path in result1.kotlin_files:
            syms1 = [(s.name, s.symbol_type) for s in result1.kotlin_files[path]]
            syms2 = [(s.name, s.symbol_type) for s in result2.kotlin_files[path]]
            assert syms1 == syms2

    def test_scan_kotlin_counts_in_success_total(self, kotlin_only_repo: Path) -> None:
        result = RepositoryScanner(kotlin_only_repo).scan()
        assert result.success_count == len(result.kotlin_files)

    def test_scan_kotlin_preceding_annotations_report_their_line(
        self, tmp_path: Path
    ) -> None:
        """D7: the attached and detached spellings report the same line.

        The grammar begins a declaration at its annotation when it attaches
        it and excludes it when it detaches it, so the scanner folds a
        *preceding* annotation into the declaration's reported start.
        """
        (tmp_path / "Detached.kt").write_text(
            "fun plain(): Int {\n"
            "    return 1\n"
            "}\n"
            "@Deprecated\n"
            '@Suppress("x")\n'
            "class B {\n"
            "    val x: Int = 1\n"
            "}\n"
        )
        (tmp_path / "Attached.kt").write_text(
            "class Z {}\n"
            "@Deprecated\n"
            '@Suppress("x")\n'
            "class A {\n"
            "    val x: Int = 1\n"
            "}\n"
        )

        result = RepositoryScanner(tmp_path).scan()

        assert [
            (s.name, s.line_number) for s in result.kotlin_files[Path("Detached.kt")]
        ] == [("plain", 1), ("B", 4)]
        assert [
            (s.name, s.line_number) for s in result.kotlin_files[Path("Attached.kt")]
        ] == [("Z", 1), ("A", 2)]

    def test_scan_kotlin_contained_annotation_keeps_the_declaration_line(
        self, tmp_path: Path
    ) -> None:
        """D7: an annotation *inside* a declaration is content, not a prefix.

        A property annotation in a class body and a local annotation in a
        function body are folded into the enclosing declaration's hash, but
        they must not move its reported line — the declaration still names
        itself on its own line (the sample suite's line-number round).
        """
        (tmp_path / "Outer.kt").write_text(
            "class Outer {\n"
            '    @Suppress("UNUSED")\n'
            "    val x = 1\n"
            "\n"
            "    fun tagged(name: String) {\n"
            '        @Suppress("UNUSED")\n'
            "        val value = name.length\n"
            "    }\n"
            "}\n"
        )

        result = RepositoryScanner(tmp_path).scan()

        assert [
            (s.name, s.symbol_type.name, s.line_number)
            for s in result.kotlin_files[Path("Outer.kt")]
        ] == [("Outer", "CLASS", 1), ("tagged", "METHOD", 5)]

    def test_scan_kotlin_script_extension(self, tmp_path: Path) -> None:
        """``.kts`` files are discovered alongside ``.kt``."""
        (tmp_path / "build.kts").write_text("fun build(): Int {\n    return 1\n}\n")

        result = RepositoryScanner(tmp_path).scan()

        assert Path("build.kts") in result.kotlin_files
        assert [s.name for s in result.kotlin_files[Path("build.kts")]] == ["build"]


class TestRepositoryScannerPhp:
    """PHP file discovery and parsing (v0.17.0 Phase 4)."""

    def test_scan_finds_php_files(self, php_only_repo: Path) -> None:
        scanner = RepositoryScanner(php_only_repo)
        result = scanner.scan()

        assert result.success_count == 2
        assert result.failure_count == 0

        assert Path("Main.php") in result.php_files
        assert Path("Utils.php") in result.php_files

        main_syms = result.php_files[Path("Main.php")]
        assert [(s.name, s.symbol_type.name) for s in main_syms] == [
            ("Main", "CLASS"),
            ("greet", "METHOD"),
        ]
        assert main_syms[1].parent_class == "Main"

        # PHP has top-level functions (like Kotlin, unlike Java).
        util_syms = result.php_files[Path("Utils.php")]
        assert [(s.name, s.symbol_type.name) for s in util_syms] == [
            ("helper", "FUNCTION"),
        ]
        assert util_syms[0].parent_class is None

    def test_scan_php_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "Visible.php").write_text("<?php\nclass Visible {}\n")
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "Ignored.php").write_text("<?php\nclass Ignored {}\n")

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()

        assert result.success_count == 1
        assert Path("Visible.php") in result.php_files
        assert Path("Ignored.php") not in result.php_files

    def test_scan_php_deterministic(self, php_only_repo: Path) -> None:
        scanner = RepositoryScanner(php_only_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        assert result1.success_count == result2.success_count
        for path in result1.php_files:
            syms1 = [(s.name, s.symbol_type) for s in result1.php_files[path]]
            syms2 = [(s.name, s.symbol_type) for s in result2.php_files[path]]
            assert syms1 == syms2

    def test_scan_php_counts_in_success_total(self, php_only_repo: Path) -> None:
        result = RepositoryScanner(php_only_repo).scan()
        assert result.success_count == len(result.php_files)

    def test_scan_php_only_extension(self, tmp_path: Path) -> None:
        """``.php`` is the one supported extension — ``.phtml`` and the
        legacy ``.php3`` are out of scope (documented)."""
        (tmp_path / "Page.phtml").write_text("<?php echo 1;\n")
        (tmp_path / "Legacy.php3").write_text("<?php echo 1;\n")
        (tmp_path / "Real.php").write_text("<?php\nfunction real() {}\n")

        result = RepositoryScanner(tmp_path).scan()

        assert set(result.php_files) == {Path("Real.php")}

    def test_scan_php_file_without_open_tag_has_no_symbols(
        self, tmp_path: Path
    ) -> None:
        """A ``.php`` template that never opens ``<?php`` parses as one
        ``text`` node: PHP would emit those bytes, so "no symbols" is the
        correct answer rather than a silent gap."""
        (tmp_path / "Template.php").write_text("<html><body>hi</body></html>\n")

        result = RepositoryScanner(tmp_path).scan()

        assert result.failure_count == 0
        assert result.php_files[Path("Template.php")] == []

    def test_scan_php_declaration_only_method_has_no_body_hash(
        self, tmp_path: Path
    ) -> None:
        """PH9: an interface method ends with ``;`` instead of a body, so
        it carries ``body_hash=None`` and can never fire CHANGED_FUNCTION."""
        (tmp_path / "I.php").write_text(
            "<?php\n\ninterface I\n{\n    public function m(string $name);\n}\n",
        )

        result = RepositoryScanner(tmp_path).scan()

        methods = [
            s for s in result.php_files[Path("I.php")] if s.symbol_type.name == "METHOD"
        ]
        assert [s.name for s in methods] == ["m"]
        assert methods[0].body_hash is None

    def test_scan_php_trait_and_enum_symbols(self, tmp_path: Path) -> None:
        """PH7/PH8: ``trait`` maps to CLASS (no TRAIT claim type) and
        ``enum`` maps to ENUM, both with their own shell hash."""
        (tmp_path / "Types.php").write_text(
            "<?php\n\n"
            "trait Loggable\n"
            "{\n"
            "    public function log(): void\n"
            "    {\n"
            "    }\n"
            "}\n\n"
            "enum Status: string\n"
            "{\n"
            "    case On = 'on';\n"
            "}\n",
        )

        result = RepositoryScanner(tmp_path).scan()

        symbols = result.php_files[Path("Types.php")]
        assert [(s.name, s.symbol_type.name) for s in symbols] == [
            ("Loggable", "CLASS"),
            ("log", "METHOD"),
            ("Status", "ENUM"),
        ]
        by_name = {s.name: s for s in symbols}
        assert by_name["Loggable"].body_hash is not None
        assert by_name["Status"].body_hash is not None
        assert by_name["log"].parent_class == "Loggable"


class TestRepositoryScannerCpp:
    """C++ file discovery and parsing (v0.17.0 Phase 5)."""

    def test_scan_finds_cpp_files(self, cpp_only_repo: Path) -> None:
        scanner = RepositoryScanner(cpp_only_repo)
        result = scanner.scan()

        assert result.success_count == 2
        assert result.failure_count == 0

        assert Path("Main.cpp") in result.cpp_files
        assert Path("Utils.cpp") in result.cpp_files

        main_syms = result.cpp_files[Path("Main.cpp")]
        assert [(s.name, s.symbol_type.name) for s in main_syms] == [
            ("Main", "CLASS"),
            ("greet", "METHOD"),
        ]
        assert main_syms[1].parent_class == "Main"

        # C++ has namespace-scope functions (like Kotlin, unlike Java).
        util_syms = result.cpp_files[Path("Utils.cpp")]
        assert [(s.name, s.symbol_type.name) for s in util_syms] == [
            ("helper", "FUNCTION"),
        ]
        assert util_syms[0].parent_class is None

    def test_scan_cpp_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "Visible.cpp").write_text("int visible() { return 1; }\n")
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "Ignored.cpp").write_text("int ignored() { return 1; }\n")

        scanner = RepositoryScanner(tmp_path)
        result = scanner.scan()

        assert result.success_count == 1
        assert Path("Visible.cpp") in result.cpp_files
        assert Path("Ignored.cpp") not in result.cpp_files

    def test_scan_cpp_deterministic(self, cpp_only_repo: Path) -> None:
        scanner = RepositoryScanner(cpp_only_repo)
        result1 = scanner.scan()
        result2 = scanner.scan()

        assert result1.success_count == result2.success_count
        for path in result1.cpp_files:
            syms1 = [(s.name, s.symbol_type) for s in result1.cpp_files[path]]
            syms2 = [(s.name, s.symbol_type) for s in result2.cpp_files[path]]
            assert syms1 == syms2

    def test_scan_cpp_counts_in_success_total(self, cpp_only_repo: Path) -> None:
        result = RepositoryScanner(cpp_only_repo).scan()
        assert result.success_count == len(result.cpp_files)

    def test_scan_cpp_extensions(self, tmp_path: Path) -> None:
        """Every documented C++ extension is discovered; ``.c`` is not."""
        supported = [
            "a.cpp",
            "b.cc",
            "c.cxx",
            "d.c++",
            "e.hpp",
            "f.hh",
            "g.hxx",
            "h.h++",
            "i.h",
        ]
        for name in supported:
            (tmp_path / name).write_text("int marker() { return 1; }\n")
        (tmp_path / "Legacy.c").write_text("int legacy(void) { return 1; }\n")

        result = RepositoryScanner(tmp_path).scan()

        assert set(result.cpp_files) == {Path(n) for n in supported}
        assert Path("Legacy.c") not in result.cpp_files

    def test_scan_cpp_declaration_only_member_has_no_body_hash(
        self, tmp_path: Path
    ) -> None:
        """E9: a header-side member ends with ``;`` instead of a body, so
        it carries ``body_hash=None`` and can never fire CHANGED_FUNCTION."""
        (tmp_path / "widget.h").write_text(
            "class Widget\n{\npublic:\n    void draw();\n};\n",
        )

        result = RepositoryScanner(tmp_path).scan()

        methods = [
            s
            for s in result.cpp_files[Path("widget.h")]
            if s.symbol_type.name == "METHOD"
        ]
        assert [s.name for s in methods] == ["draw"]
        assert methods[0].body_hash is None

    def test_scan_cpp_union_enum_and_alias_symbols(self, tmp_path: Path) -> None:
        """A union maps to CLASS (a class-like type), ``enum class`` to ENUM
        and ``using`` to TYPE_ALIAS, each with its own shell hash."""
        (tmp_path / "types.cpp").write_text(
            "union Value\n"
            "{\n"
            "    int as_int;\n"
            "    double as_double;\n"
            "};\n\n"
            "enum class Mode\n"
            "{\n"
            "    Fast\n"
            "};\n\n"
            "using Count = unsigned long;\n",
        )

        result = RepositoryScanner(tmp_path).scan()

        symbols = result.cpp_files[Path("types.cpp")]
        assert [(s.name, s.symbol_type.name) for s in symbols] == [
            ("Value", "CLASS"),
            ("Mode", "ENUM"),
            ("Count", "TYPE_ALIAS"),
        ]
        by_name = {s.name: s for s in symbols}
        assert by_name["Value"].body_hash is not None
        assert by_name["Mode"].body_hash is not None
        # A type alias has no CHANGED_TYPE_ALIAS claim, so no hash.
        assert by_name["Count"].body_hash is None

    def test_scan_cpp_tagged_nested_and_forward_types(self, tmp_path: Path) -> None:
        """E18: a tagged declaration, a nested type member and a forward
        declaration all declare CLASS/ENUM facts, and a nested type's
        members belong to the nested type."""
        (tmp_path / "types.cpp").write_text(
            "struct Tagged\n"
            "{\n"
            "    void touch() { return; }\n"
            "} instance;\n"
            "\n"
            "struct Outer\n"
            "{\n"
            "    struct Inner\n"
            "    {\n"
            "        void visit() { return; }\n"
            "    };\n"
            "\n"
            "    enum Kind { First, Second };\n"
            "};\n"
            "\n"
            "struct Forwarded;\n",
        )

        result = RepositoryScanner(tmp_path).scan()

        symbols = result.cpp_files[Path("types.cpp")]
        assert [(s.name, s.symbol_type.name) for s in symbols] == [
            ("Tagged", "CLASS"),
            ("touch", "METHOD"),
            ("Outer", "CLASS"),
            ("Inner", "CLASS"),
            ("visit", "METHOD"),
            ("Kind", "ENUM"),
            ("Forwarded", "CLASS"),
        ]
        by_name = {s.name: s for s in symbols}
        assert by_name["touch"].parent_class == "Tagged"
        assert by_name["visit"].parent_class == "Inner"
        assert by_name["Forwarded"].body_hash is not None

    def test_scan_cpp_wrapped_declarator_shapes(self, tmp_path: Path) -> None:
        """E18: the single-declaration ``extern "C"`` form, a reference-
        return declaration-only member and a declaration-only conversion
        operator are all indexed (no body → no hash)."""
        (tmp_path / "api.h").write_text(
            'extern "C" int legacy_total();\n'
            "\n"
            "struct Widget\n"
            "{\n"
            "    Widget& merge(const Widget& other);\n"
            "    explicit operator bool() const;\n"
            "};\n",
        )

        result = RepositoryScanner(tmp_path).scan()

        symbols = result.cpp_files[Path("api.h")]
        assert [(s.name, s.symbol_type.name) for s in symbols] == [
            ("legacy_total", "FUNCTION"),
            ("Widget", "CLASS"),
            ("merge", "METHOD"),
            ("operatorbool", "METHOD"),
        ]
        by_name = {s.name: s for s in symbols}
        assert by_name["merge"].parent_class == "Widget"
        assert by_name["merge"].body_hash is None
        assert by_name["operatorbool"].parent_class == "Widget"
        assert by_name["operatorbool"].body_hash is None


class TestRepositoryScannerMultiLang:
    """Multi-language repo with all 9 families."""

    def test_scan_discovers_all_languages(self, multi_lang_repo: Path) -> None:
        scanner = RepositoryScanner(multi_lang_repo)
        result = scanner.scan()

        assert result.success_count == 9
        assert Path("app.py") in result.modules
        assert Path("util.js") in result.js_files
        assert Path("mod.ts") in result.ts_files
        assert Path("lib.rs") in result.rust_files
        assert Path("srv.go") in result.go_files
        assert Path("App.java") in result.java_files
        assert Path("App.kt") in result.kotlin_files
        assert Path("Index.php") in result.php_files
        assert Path("app.cpp") in result.cpp_files

    def test_scan_success_count_includes_all(
        self,
        multi_lang_repo: Path,
    ) -> None:
        scanner = RepositoryScanner(multi_lang_repo)
        result = scanner.scan()
        expected = (
            len(result.modules)
            + len(result.js_files)
            + len(result.ts_files)
            + len(result.rust_files)
            + len(result.go_files)
            + len(result.java_files)
            + len(result.kotlin_files)
            + len(result.php_files)
            + len(result.cpp_files)
        )
        assert result.success_count == expected
