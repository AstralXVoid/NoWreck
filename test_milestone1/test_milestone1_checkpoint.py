#!/usr/bin/env python3
"""
Milestone 1 checkpoint — end-to-end pipeline test on 3 hand-constructed repos.

Tests
-----
- ``test_pure_python``: 3 .py files → scan → symbol index → change detection →
  deterministic across 3 runs
- ``test_pure_js``: 3 .js files → scan → symbol index → change detection →
  deterministic across 3 runs
- ``test_mixed_py_js``: 2 .py + 2 .js files → scan → symbol index →
  change detection → deterministic across 3 runs
- ``test_all_repos_deterministic``: all 3 repos scanned 3x each, every
  field of ScanResult and SymbolIndex must be identical across runs
- ``test_call_detection_python``: verify calls are detected in Python repo
- ``test_call_detection_js``: verify calls are detected in JS repo
- ``test_call_detection_mixed``: verify calls are detected across both languages
- ``test_file_created_deleted``: make a temp modification, verify changes
- ``test_same_inputs_no_changes``: pre == post → no detected changes
- ``test_pre_post_pipeline``: full pre/post detection on a real repo
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from nowreck.detector.change_detector import (
    ChangeType,
    DetectedChange,
    detect_changes,
)
from nowreck.scanner.repository_scanner import RepositoryScanner, ScanResult
from nowreck.scanner.symbol_index import (
    Symbol,
    SymbolIndex,
    SymbolType,
    build_symbol_index,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPOS = Path(__file__).resolve().parent / "repos"

PURE_PY_REPO = REPOS / "pure-python" / "src"
PURE_JS_REPO = REPOS / "pure-js" / "src"
PURE_TS_REPO = REPOS / "pure-ts" / "src"
PURE_TSX_REPO = REPOS / "pure-tsx" / "src"
PURE_RUST_REPO = REPOS / "pure-rust" / "src"
PURE_GO_REPO = REPOS / "pure-go" / "src"
PURE_JAVA_REPO = REPOS / "pure-java" / "src"
PURE_KOTLIN_REPO = REPOS / "pure-kotlin" / "src"
PURE_PHP_REPO = REPOS / "pure-php" / "src"
PURE_CPP_REPO = REPOS / "pure-cpp" / "src"
MIXED_REPO = REPOS / "mixed"

EXPECTED_PY_FILES = 3  # greeter.py, calculator.py, models.py
EXPECTED_JS_FILES = 3  # greeter.js, calculator.js, models.js
EXPECTED_TS_FILES = 3  # greeter.ts, calculator.ts, models.ts
EXPECTED_TSX_FILES = 3  # greeter.tsx, calculator.tsx, models.tsx
EXPECTED_RUST_FILES = 3  # greeter.rs, calculator.rs, models.rs
EXPECTED_GO_FILES = 3  # greeter.go, calculator.go, models.go
EXPECTED_JAVA_FILES = 3  # Greeter.java, Calculator.java, Models.java
EXPECTED_KOTLIN_FILES = 3  # Greeter.kt, Calculator.kt, Models.kt
EXPECTED_PHP_FILES = 3  # Greeter.php, Calculator.php, Models.php
EXPECTED_CPP_FILES = 5  # greeter.h/.cpp, calculator.h/.cpp, models.h
EXPECTED_MIXED_PY = 2  # utils.py, main.py
EXPECTED_MIXED_JS = 2  # utils.js, ui_handler.js


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_and_index(
    repo_path: Path,
) -> tuple[ScanResult, SymbolIndex]:
    scanner = RepositoryScanner(repo_path)
    scan_result = scanner.scan()
    sym_index = build_symbol_index(scan_result)
    return scan_result, sym_index


def _changes_between(
    pre_path: Path | None,
    post_path: Path | None,
) -> list[DetectedChange]:
    """Detect changes from *pre_path* → *post_path*.

    If a path is ``None``, use an empty ``ScanResult`` and ``SymbolIndex``.
    """
    if pre_path is not None:
        pre_scan, pre_sym = _scan_and_index(pre_path)
    else:
        pre_scan, pre_sym = ScanResult(), SymbolIndex()

    if post_path is not None:
        post_scan, post_sym = _scan_and_index(post_path)
    else:
        post_scan, post_sym = ScanResult(), SymbolIndex()

    return detect_changes(pre_scan, post_scan, pre_sym, post_sym)


def _changes_of_type(
    changes: list[DetectedChange],
    change_type: ChangeType,
) -> list[DetectedChange]:
    return [c for c in changes if c.change_type is change_type]


def _full_symbol_tuples(
    symbols: Iterable[Symbol],
) -> list[tuple[str, str, str, int, str | None, str | None]]:
    """Explicit symbol projection including the ``__eq__``-exempt fields.

    ``Symbol.__eq__`` deliberately excludes ``line_number`` and ``body_hash``
    (identity-exempt, so a line shift or body edit is not a remove+add pair).
    A determinism sweep must still compare them, so symbols are projected to
    explicit tuples in a canonical order.
    """
    tuples = [
        (
            s.name,
            s.symbol_type.name,
            str(s.file_path),
            s.line_number,
            s.parent_class,
            s.body_hash,
        )
        for s in symbols
    ]
    return sorted(
        tuples,
        key=lambda t: (t[0], t[1], t[2], t[3], t[4] or "", t[5] or ""),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pure_python_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_PY_REPO)


@pytest.fixture(scope="module")
def pure_js_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_JS_REPO)


@pytest.fixture(scope="module")
def pure_ts_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_TS_REPO)


@pytest.fixture(scope="module")
def pure_tsx_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_TSX_REPO)


@pytest.fixture(scope="module")
def pure_rust_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_RUST_REPO)


@pytest.fixture(scope="module")
def pure_go_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_GO_REPO)


@pytest.fixture(scope="module")
def pure_java_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_JAVA_REPO)


@pytest.fixture(scope="module")
def pure_kotlin_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_KOTLIN_REPO)


@pytest.fixture(scope="module")
def pure_php_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_PHP_REPO)


@pytest.fixture(scope="module")
def pure_cpp_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(PURE_CPP_REPO)


@pytest.fixture(scope="module")
def mixed_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(MIXED_REPO)


# ---------------------------------------------------------------------------
# 1. Pure Python repo
# ---------------------------------------------------------------------------


class TestPurePythonRepo:
    """3 Python files with functions, classes, methods, calls."""

    def test_discovers_all_files(
        self, pure_python_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, _ = pure_python_scan
        assert scan.success_count == EXPECTED_PY_FILES
        assert scan.failure_count == 0
        assert len(scan.modules) == EXPECTED_PY_FILES
        assert set(scan.modules) == {
            Path("greeter.py"),
            Path("calculator.py"),
            Path("models.py"),
        }

    def test_greeter_has_functions(
        self, pure_python_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, _ = pure_python_scan
        greeter = scan.modules[Path("greeter.py")]
        names = {n.name for n in ast.walk(greeter) if isinstance(n, ast.FunctionDef)}
        assert "greet" in names
        assert "format_greeting" in names
        assert "farewell" in names

    def test_calculator_has_class_and_methods(
        self, pure_python_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, _ = pure_python_scan
        calc = scan.modules[Path("calculator.py")]
        calc_class = next(
            n
            for n in ast.walk(calc)
            if isinstance(n, ast.ClassDef) and n.name == "Calculator"
        )
        method_names = {
            n.name for n in calc_class.body if isinstance(n, ast.FunctionDef)
        }
        assert "add" in method_names
        assert "subtract" in method_names
        assert "multiply" in method_names
        assert "divide" in method_names
        # compute_average is a top-level function, not a method
        assert "compute_average" not in method_names

    def test_models_has_class_hierarchy(
        self, pure_python_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, _ = pure_python_scan
        models = scan.modules[Path("models.py")]
        class_names = {n.name for n in ast.walk(models) if isinstance(n, ast.ClassDef)}
        assert "User" in class_names
        assert "AdminUser" in class_names

    def test_symbol_index_has_py_symbols(
        self, pure_python_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_python_scan
        # greeter.py: greet, format_greeting, farewell (3 functions)
        # calculator.py: Calculator (class), compute_average (function), add/sub/multiply/divide (methods)
        # models.py: User (class), AdminUser (class), __init__/display/to_dict/__init__/display (methods)
        assert (
            len(idx.functions) >= 4
        )  # greet, format_greeting, farewell, compute_average
        assert len(idx.classes) >= 3  # Calculator, User, AdminUser
        assert (
            len(idx.methods) >= 5
        )  # add, subtract, multiply, divide, __init__, display, to_dict, display

    def test_call_detection(self, pure_python_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = pure_python_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # greeter.py: greet calls format_greeting and print; farewell calls print
        # calculator.py: multiply calls print; compute_average calls sum and len
        # models.py: display calls print; AdminUser.display calls print; Logger.log calls print

        # Should have multiple calls
        assert len(calls) >= 5

        # Verify specific calls
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        assert ("greet", "print") in call_pairs
        assert ("compute_average", "len") in call_pairs

    def test_file_changes_detected(self) -> None:
        """Modifying a file shows up as changes."""
        # Scan the repo as the 'post' state, empty as 'pre'
        changes = _changes_between(None, PURE_PY_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_PY_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(
        self, pure_python_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_python_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert changes == []

    def test_deterministic_across_runs(self) -> None:
        """Same inputs → identical structural output across 3 runs.

        ``ast.Module`` objects do not implement structural ``==``, so
        we compare via ``ast.dump()`` and compare file-path sets.
        """
        scans = [_scan_and_index(PURE_PY_REPO) for _ in range(3)]
        for i in range(1, 3):
            for path in scans[0][0].modules:
                assert ast.dump(scans[i][0].modules[path]) == ast.dump(
                    scans[0][0].modules[path],
                ), f"Mismatch in {path} on run {i + 1}"
            assert list(scans[i][0].modules) == list(scans[0][0].modules)
            assert scans[i][0].js_files == scans[0][0].js_files
            assert scans[i][0].failed_files == scans[0][0].failed_files
            assert scans[i][1].symbols == scans[0][1].symbols


# ---------------------------------------------------------------------------
# 2. Pure JavaScript repo
# ---------------------------------------------------------------------------


class TestPureJsRepo:
    """3 JavaScript files with functions, arrow functions, classes, methods, calls."""

    def test_discovers_all_files(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_js_scan
        assert scan.success_count == EXPECTED_JS_FILES
        assert scan.failure_count == 0
        assert len(scan.js_files) == EXPECTED_JS_FILES
        assert set(scan.js_files) == {
            Path("greeter.js"),
            Path("calculator.js"),
            Path("models.js"),
        }

    def test_greeter_has_symbols(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_js_scan
        assert len(idx.by_name("greet")) == 1  # function greet
        assert len(idx.by_name("formatGreeting")) == 1  # var formatGreeting = function
        assert len(idx.by_name("farewell")) == 1  # const farewell = () => {}

    def test_calculator_has_class_and_methods(
        self, pure_js_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_js_scan
        assert len(idx.by_name("Calculator")) == 1
        calc = idx.by_name("Calculator")[0]
        assert calc.symbol_type is SymbolType.CLASS
        # Methods: add, subtract, multiply, divide
        methods = {s.name for s in idx.methods}
        assert "add" in methods
        assert "subtract" in methods
        assert "multiply" in methods
        assert "divide" in methods

    def test_models_has_class_hierarchy(
        self, pure_js_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_js_scan
        assert len(idx.by_name("User")) == 1
        assert len(idx.by_name("AdminUser")) == 1
        # Methods on User: display, toDict, constructor -> but constructor is 'constructor' keyword
        user_methods = {s.name for s in idx.methods if s.parent_class == "User"}
        assert "display" in user_methods
        assert "toDict" in user_methods

    def test_symbol_index_has_js_symbols(
        self, pure_js_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_js_scan
        assert (
            len(idx.functions) >= 3
        )  # greet, formatGreeting, farewell, computeAverage
        assert len(idx.classes) >= 3  # Calculator, User, AdminUser
        assert (
            len(idx.methods) >= 6
        )  # add, subtract, multiply, divide, display, toDict, display

    def test_call_detection(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = pure_js_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # greet calls formatGreeting and console.log (member call — captured)
        # formatGreeting makes no calls
        # farewell calls console.log (member call — captured)
        # multiply calls console.log (member call — captured)
        # computeAverage calls sum and len
        # display calls console.log (member call — captured)
        assert len(calls) >= 1  # at minimum, computeAverage calls sum, len

        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        assert ("computeAverage", "len") in call_pairs

    def test_console_log_is_captured(
        self, pure_js_scan: tuple[ScanResult, Any]
    ) -> None:
        """console.log() is a member call — captured as CALL_DETECTED since v16."""
        scan, idx = pure_js_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        # console.log has a Name receiver — captured with called_name "log"
        assert ("greet", "log") in call_pairs
        assert ("farewell", "log") in call_pairs

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_JS_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_JS_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(
        self, pure_js_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_js_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert changes == []

    def test_deterministic_across_runs(self) -> None:
        scans = [_scan_and_index(PURE_JS_REPO) for _ in range(3)]
        for i in range(1, 3):
            for path in scans[0][0].modules:
                assert ast.dump(scans[i][0].modules[path]) == ast.dump(
                    scans[0][0].modules[path],
                ), f"Mismatch in {path} on run {i + 1}"
            assert list(scans[i][0].modules) == list(scans[0][0].modules)
            assert scans[i][0].js_files == scans[0][0].js_files
            assert scans[i][0].failed_files == scans[0][0].failed_files
            assert scans[i][1].symbols == scans[0][1].symbols


# ---------------------------------------------------------------------------
# 3. Pure TypeScript repo
# ---------------------------------------------------------------------------


class TestPureTsRepo:
    """3 TypeScript files with functions, arrow functions, classes, methods, calls."""

    def test_discovers_all_files(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_ts_scan
        assert scan.success_count == EXPECTED_TS_FILES
        assert scan.failure_count == 0
        assert len(scan.ts_files) == EXPECTED_TS_FILES
        assert set(scan.ts_files) == {
            Path("greeter.ts"),
            Path("calculator.ts"),
            Path("models.ts"),
        }

    def test_greeter_has_symbols(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_ts_scan
        assert len(idx.by_name("greet")) == 1  # function greet
        assert len(idx.by_name("formatGreeting")) == 1  # const arrow
        assert len(idx.by_name("farewell")) == 1  # const farewell = () => {}

    def test_calculator_has_class_and_methods(
        self, pure_ts_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_ts_scan
        assert len(idx.by_name("Calculator")) == 1
        calc = idx.by_name("Calculator")[0]
        assert calc.symbol_type is SymbolType.CLASS
        # Methods: add, subtract, multiply, divide
        methods = {s.name for s in idx.methods}
        assert "add" in methods
        assert "subtract" in methods
        assert "multiply" in methods
        assert "divide" in methods

    def test_models_has_class_hierarchy(
        self, pure_ts_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_ts_scan
        assert len(idx.by_name("User")) == 1
        assert len(idx.by_name("AdminUser")) == 1
        # Methods on User: display, toDict
        user_methods = {s.name for s in idx.methods if s.parent_class == "User"}
        assert "display" in user_methods
        assert "toDict" in user_methods

    def test_symbol_index_has_ts_symbols(
        self, pure_ts_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_ts_scan
        assert (
            len(idx.functions) >= 3
        )  # greet, formatGreeting, farewell, computeAverage
        assert len(idx.classes) >= 3  # Calculator, User, AdminUser
        assert (
            len(idx.methods) >= 6
        )  # add, subtract, multiply, divide, display, toDict, display

    def test_type_level_symbols_captured(
        self, pure_ts_scan: tuple[ScanResult, Any]
    ) -> None:
        """models.ts type-level contracts land as INTERFACE/ENUM/TYPE_ALIAS
        (v0.8.0 material) without touching the older counts."""
        _, idx = pure_ts_scan
        profile = idx.by_name("UserProfile")
        assert len(profile) == 1
        assert profile[0].symbol_type is SymbolType.INTERFACE
        role = idx.by_name("Role")
        assert len(role) == 1
        assert role[0].symbol_type is SymbolType.ENUM
        status = idx.by_name("UserStatus")
        assert len(status) == 1
        assert status[0].symbol_type is SymbolType.TYPE_ALIAS
        # Index properties expose the new kinds
        assert "UserProfile" in {s.name for s in idx.interfaces}
        assert "Role" in {s.name for s in idx.enums}
        assert "UserStatus" in {s.name for s in idx.type_aliases}

    def test_call_detection(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = pure_ts_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # greet calls formatGreeting and console.log (member call — captured)
        # formatGreeting makes no calls
        # farewell calls console.log (member call — captured)
        # multiply calls console.log (member call — captured)
        # computeAverage calls sum and len
        # display calls console.log (member call — captured)
        assert len(calls) >= 1  # at minimum, computeAverage calls sum, len

        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        assert ("computeAverage", "len") in call_pairs

    def test_console_log_is_captured(
        self, pure_ts_scan: tuple[ScanResult, Any]
    ) -> None:
        """console.log() is a member call — captured as CALL_DETECTED since v16."""
        scan, idx = pure_ts_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        # console.log has a Name receiver — captured with called_name "log"
        assert ("greet", "log") in call_pairs
        assert ("farewell", "log") in call_pairs

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_TS_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_TS_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_type_level_change_detection(self) -> None:
        """Empty → repo emits the six type-level kinds with the right
        names (no mislabeling as functions)."""
        changes = _changes_between(None, PURE_TS_REPO)
        added_interfaces = _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        added_enums = _changes_of_type(changes, ChangeType.ADD_ENUM)
        added_aliases = _changes_of_type(changes, ChangeType.ADD_TYPE_ALIAS)
        assert [c.symbol_name for c in added_interfaces] == ["UserProfile"]
        assert [c.symbol_name for c in added_enums] == ["Role"]
        assert [c.symbol_name for c in added_aliases] == ["UserStatus"]

    def test_no_changes_when_identical(
        self, pure_ts_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_ts_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert changes == []

    def test_deterministic_across_runs(self) -> None:
        scans = [_scan_and_index(PURE_TS_REPO) for _ in range(3)]
        for i in range(1, 3):
            assert list(scans[i][0].modules) == list(scans[0][0].modules)
            assert scans[i][0].js_files == scans[0][0].js_files
            assert scans[i][0].ts_files == scans[0][0].ts_files
            assert scans[i][0].failed_files == scans[0][0].failed_files
            assert scans[i][1].symbols == scans[0][1].symbols


# ---------------------------------------------------------------------------
# 3b. Pure TSX repo (v0.7.0)
# ---------------------------------------------------------------------------


class TestPureTsxRepo:
    """3 TSX files with function/arrow/class components, methods, and calls.

    ``.tsx`` files fold into the ``ts_files`` field (same language family),
    so all assertions here go through ``scan.ts_files``.
    """

    def test_discovers_all_files(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_tsx_scan
        assert scan.success_count == EXPECTED_TSX_FILES
        assert scan.failure_count == 0
        assert len(scan.ts_files) == EXPECTED_TSX_FILES
        assert set(scan.ts_files) == {
            Path("greeter.tsx"),
            Path("calculator.tsx"),
            Path("models.tsx"),
        }

    def test_greeter_has_symbols(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_tsx_scan
        assert len(idx.by_name("Greeting")) == 1  # function component
        assert len(idx.by_name("formatGreeting")) == 1  # const arrow
        assert len(idx.by_name("Farewell")) == 1  # const Farewell = () => {}

    def test_calculator_has_class_and_methods(
        self, pure_tsx_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_tsx_scan
        assert len(idx.by_name("Calculator")) == 1
        calc = idx.by_name("Calculator")[0]
        assert calc.symbol_type is SymbolType.CLASS
        # Methods: add, subtract, multiply, divide, render
        methods = {s.name for s in idx.methods}
        assert "add" in methods
        assert "subtract" in methods
        assert "multiply" in methods
        assert "divide" in methods
        assert "render" in methods

    def test_models_has_components(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_tsx_scan
        assert len(idx.by_name("UserCard")) == 1  # function component
        assert len(idx.by_name("AdminCard")) == 1  # arrow component
        assert len(idx.by_name("UserList")) == 1  # class component
        assert len(idx.by_name("UserList")) == 1
        user_list = idx.by_name("UserList")[0]
        assert user_list.symbol_type is SymbolType.CLASS
        # UserList.render is a method with parent_class=UserList
        render_methods = [s for s in idx.methods if s.name == "render"]
        assert any(s.parent_class == "UserList" for s in render_methods)

    def test_symbol_index_has_tsx_symbols(
        self, pure_tsx_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_tsx_scan
        assert (
            len(idx.functions) >= 6
        )  # Greeting, formatGreeting, Farewell, computeAverage, UserCard, AdminCard
        assert len(idx.classes) >= 2  # Calculator, UserList
        assert (
            len(idx.methods) >= 6
        )  # add, subtract, multiply, divide, render (Calculator), render (UserList)

    def test_type_level_symbols_captured(
        self, pure_tsx_scan: tuple[ScanResult, Any]
    ) -> None:
        """models.tsx type-level contracts land as INTERFACE/ENUM/TYPE_ALIAS
        (v0.8.0 material) without touching the older counts."""
        _, idx = pure_tsx_scan
        props = idx.by_name("UserProps")
        assert len(props) == 1
        assert props[0].symbol_type is SymbolType.INTERFACE
        view_mode = idx.by_name("ViewMode")
        assert len(view_mode) == 1
        assert view_mode[0].symbol_type is SymbolType.ENUM
        sort_order = idx.by_name("SortOrder")
        assert len(sort_order) == 1
        assert sort_order[0].symbol_type is SymbolType.TYPE_ALIAS
        assert "UserProps" in {s.name for s in idx.interfaces}
        assert "ViewMode" in {s.name for s in idx.enums}
        assert "SortOrder" in {s.name for s in idx.type_aliases}

    def test_call_detection(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = pure_tsx_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # Greeting calls formatGreeting
        # computeAverage calls sum and len
        # multiply calls console.log (member call — captured)
        assert len(calls) >= 3

        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        assert ("Greeting", "formatGreeting") in call_pairs
        assert ("computeAverage", "len") in call_pairs

    def test_console_log_is_captured(
        self, pure_tsx_scan: tuple[ScanResult, Any]
    ) -> None:
        """console.log() is a member call — captured as CALL_DETECTED since v16."""
        scan, idx = pure_tsx_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        # console.log has a Name receiver — captured with called_name "log"
        assert ("multiply", "log") in call_pairs

    def test_jsx_element_usage_is_not_a_call(
        self, pure_tsx_scan: tuple[ScanResult, Any]
    ) -> None:
        """<UserCard /> and <AdminCard /> in JSX are elements, not calls."""
        scan, idx = pure_tsx_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        # JSX usage inside UserList.render must not surface as calls
        assert ("render", "UserCard") not in call_pairs
        assert ("render", "AdminCard") not in call_pairs

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_TSX_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_TSX_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}
        assert ChangeType.ADD_CLASS in {c.change_type for c in changes}

    def test_no_changes_when_identical(
        self, pure_tsx_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_tsx_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert changes == []

    def test_deterministic_across_runs(self) -> None:
        scans = [_scan_and_index(PURE_TSX_REPO) for _ in range(3)]
        for i in range(1, 3):
            assert list(scans[i][0].modules) == list(scans[0][0].modules)
            assert scans[i][0].js_files == scans[0][0].js_files
            assert scans[i][0].ts_files == scans[0][0].ts_files
            assert scans[i][0].failed_files == scans[0][0].failed_files
            assert scans[i][1].symbols == scans[0][1].symbols


# ---------------------------------------------------------------------------
# 4. Pure Rust repo
# ---------------------------------------------------------------------------


class TestPureRustRepo:
    """3 Rust files with functions, structs, impl methods, traits, enums, type aliases."""

    def test_discovers_all_files(self, pure_rust_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_rust_scan
        assert scan.success_count == EXPECTED_RUST_FILES
        assert scan.failure_count == 0
        assert len(scan.rust_files) == EXPECTED_RUST_FILES
        assert set(scan.rust_files) == {
            Path("greeter.rs"),
            Path("calculator.rs"),
            Path("models.rs"),
        }

    def test_greeter_has_symbols(self, pure_rust_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_rust_scan
        greet = idx.by_name("greet")
        assert len(greet) == 1
        assert greet[0].symbol_type is SymbolType.FUNCTION
        fmt = idx.by_name("format_greeting")
        assert len(fmt) == 1
        assert fmt[0].symbol_type is SymbolType.FUNCTION
        farewell = idx.by_name("farewell")
        assert len(farewell) == 1
        assert farewell[0].symbol_type is SymbolType.FUNCTION

    def test_calculator_has_class_and_methods(
        self, pure_rust_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_rust_scan
        calc = idx.by_name("Calculator")
        assert len(calc) == 1
        assert calc[0].symbol_type is SymbolType.CLASS
        # Methods: new, add, subtract, multiply, divide, display
        add_methods = [s for s in idx.by_name("add") if s.parent_class == "Calculator"]
        assert len(add_methods) == 1
        assert add_methods[0].symbol_type is SymbolType.METHOD

    def test_models_has_types(self, pure_rust_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_rust_scan
        user = idx.by_name("User")
        assert len(user) == 1
        assert user[0].symbol_type is SymbolType.CLASS
        admin = idx.by_name("AdminUser")
        assert len(admin) == 1
        assert admin[0].symbol_type is SymbolType.CLASS
        display_trait = idx.by_name("Display")
        assert len(display_trait) == 1
        assert display_trait[0].symbol_type is SymbolType.INTERFACE
        role = idx.by_name("Role")
        assert len(role) == 1
        assert role[0].symbol_type is SymbolType.ENUM
        status = idx.by_name("UserStatus")
        assert len(status) == 1
        assert status[0].symbol_type is SymbolType.TYPE_ALIAS

    def test_symbol_index_has_rust_symbols(
        self, pure_rust_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_rust_scan
        assert (
            len(idx.functions) >= 4
        )  # greet, format_greeting, farewell, compute_average
        assert len(idx.classes) >= 3  # Calculator, User, AdminUser
        assert (
            len(idx.methods) >= 7
        )  # Calculator methods + User methods + AdminUser methods

    def test_call_detection(self) -> None:
        changes = _changes_between(None, PURE_RUST_REPO)
        call_changes = [c for c in changes if c.change_type is ChangeType.CALL_DETECTED]
        # greeter.rs: greet -> format_greeting
        callers = {(c.caller_name, c.called_name) for c in call_changes}
        assert ("greet", "format_greeting") in callers

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_RUST_REPO)
        created = [c for c in changes if c.change_type is ChangeType.FILE_CREATED]
        assert len(created) == EXPECTED_RUST_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(
        self, pure_rust_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_rust_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert len(changes) == 0

    def test_deterministic_across_runs(
        self, pure_rust_scan: tuple[ScanResult, Any]
    ) -> None:
        scan1, idx1 = pure_rust_scan
        scan2, idx2 = _scan_and_index(PURE_RUST_REPO)
        changes1 = detect_changes(ScanResult(), scan1, SymbolIndex(), idx1)
        changes2 = detect_changes(ScanResult(), scan2, SymbolIndex(), idx2)
        assert changes1 == changes2


# 5. Pure Go repo
# ---------------------------------------------------------------------------


class TestPureGoRepo:
    """3 Go files with functions, methods, structs, interfaces, type aliases."""

    def test_discovers_all_files(self, pure_go_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_go_scan
        assert scan.success_count == EXPECTED_GO_FILES
        assert scan.failure_count == 0
        assert len(scan.go_files) == EXPECTED_GO_FILES
        assert set(scan.go_files) == {
            Path("greeter.go"),
            Path("calculator.go"),
            Path("models.go"),
        }

    def test_greeter_has_symbols(self, pure_go_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_go_scan
        greet = idx.by_name("Greet")
        assert len(greet) == 1
        assert greet[0].symbol_type is SymbolType.FUNCTION
        fmt = idx.by_name("FormatGreeting")
        assert len(fmt) == 1
        assert fmt[0].symbol_type is SymbolType.FUNCTION
        farewell = idx.by_name("Farewell")
        assert len(farewell) == 1
        assert farewell[0].symbol_type is SymbolType.FUNCTION

    def test_calculator_has_class_and_methods(
        self, pure_go_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_go_scan
        calc = idx.by_name("Calculator")
        assert len(calc) == 1
        assert calc[0].symbol_type is SymbolType.CLASS
        # Methods: Add, Subtract, Multiply, Divide, Display
        add_methods = [s for s in idx.by_name("Add") if s.parent_class == "Calculator"]
        assert len(add_methods) == 1
        assert add_methods[0].symbol_type is SymbolType.METHOD

    def test_models_has_types(self, pure_go_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_go_scan
        user = idx.by_name("User")
        assert len(user) == 1
        assert user[0].symbol_type is SymbolType.CLASS
        admin = idx.by_name("AdminUser")
        assert len(admin) == 1
        assert admin[0].symbol_type is SymbolType.CLASS
        reader = idx.by_name("Reader")
        assert len(reader) == 1
        assert reader[0].symbol_type is SymbolType.INTERFACE
        status = idx.by_name("Status")
        assert len(status) == 1
        assert status[0].symbol_type is SymbolType.TYPE_ALIAS

    def test_symbol_index_has_go_symbols(
        self, pure_go_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_go_scan
        assert (
            len(idx.functions) >= 4
        )  # Greet, FormatGreeting, Farewell, ComputeAverage
        assert len(idx.classes) >= 2  # Calculator, User, AdminUser
        assert (
            len(idx.methods) >= 7
        )  # Calculator methods + User methods + AdminUser methods

    def test_call_detection(self) -> None:
        changes = _changes_between(None, PURE_GO_REPO)
        call_changes = [c for c in changes if c.change_type is ChangeType.CALL_DETECTED]
        # greeter.go: Greet -> FormatGreeting
        callers = {(c.caller_name, c.called_name) for c in call_changes}
        assert ("Greet", "FormatGreeting") in callers

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_GO_REPO)
        created = [c for c in changes if c.change_type is ChangeType.FILE_CREATED]
        assert len(created) == EXPECTED_GO_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(
        self, pure_go_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_go_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert len(changes) == 0

    def test_deterministic_across_runs(
        self, pure_go_scan: tuple[ScanResult, Any]
    ) -> None:
        scan1, idx1 = pure_go_scan
        scan2, idx2 = _scan_and_index(PURE_GO_REPO)
        changes1 = detect_changes(ScanResult(), scan1, SymbolIndex(), idx1)
        changes2 = detect_changes(ScanResult(), scan2, SymbolIndex(), idx2)
        assert changes1 == changes2


# 6. Pure Java repo
# ---------------------------------------------------------------------------

_JAVA_GREETER = """\
package p;

public class Greeter {
    public static String greet(String name) {
        return formatGreeting(name);
    }
}
"""

_JAVA_GREETER_WITH_CTOR = """\
package p;

public class Greeter {
    private final String prefix;

    public Greeter(String prefix) {
        this.prefix = prefix;
    }

    public static String greet(String name) {
        return formatGreeting(name);
    }
}
"""

_JAVA_ENUM_A = """\
package p;

enum Status {
    ACTIVE, INACTIVE
}
"""

_JAVA_ENUM_B = """\
package p;

enum Status {
    ACTIVE, INACTIVE, ARCHIVED
}
"""


def _java_changes(
    tmp_path: Path,
    pre: dict[str, str],
    post: dict[str, str],
) -> list[DetectedChange]:
    """Scan two in-memory Java trees and detect changes between them."""
    pre_dir = tmp_path / "pre"
    post_dir = tmp_path / "post"
    pre_dir.mkdir()
    post_dir.mkdir()
    for name, source in pre.items():
        (pre_dir / name).write_text(source, encoding="utf-8")
    for name, source in post.items():
        (post_dir / name).write_text(source, encoding="utf-8")
    return _changes_between(pre_dir, post_dir)


class TestPureJavaRepo:
    """3 Java files with classes, methods, interfaces, enums, calls."""

    def test_discovers_all_files(self, pure_java_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_java_scan
        assert scan.success_count == EXPECTED_JAVA_FILES
        assert scan.failure_count == 0
        assert len(scan.java_files) == EXPECTED_JAVA_FILES
        assert set(scan.java_files) == {
            Path("Greeter.java"),
            Path("Calculator.java"),
            Path("Models.java"),
        }

    def test_greeter_has_symbols(self, pure_java_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_java_scan
        # Java has no top-level functions: methods carry parent_class.
        greet = idx.by_name("greet")
        assert len(greet) == 1
        assert greet[0].symbol_type is SymbolType.METHOD
        assert greet[0].parent_class == "Greeter"
        assert len(idx.by_name("formatGreeting")) == 1
        assert len(idx.by_name("farewell")) == 1

    def test_calculator_has_class_and_methods(
        self, pure_java_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_java_scan
        # The constructor shares the class name — filter by type.
        calc = [
            s for s in idx.by_name("Calculator") if s.symbol_type is SymbolType.CLASS
        ]
        assert len(calc) == 1
        add_methods = [s for s in idx.by_name("add") if s.parent_class == "Calculator"]
        assert len(add_methods) == 1
        assert add_methods[0].symbol_type is SymbolType.METHOD
        for name in ("subtract", "multiply", "divide", "display", "computeAverage"):
            assert any(s.parent_class == "Calculator" for s in idx.by_name(name)), name

    def test_constructor_is_a_method_named_after_the_class(
        self, pure_java_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_java_scan
        ctor = [
            s for s in idx.by_name("Calculator") if s.symbol_type is SymbolType.METHOD
        ]
        assert len(ctor) == 1
        assert ctor[0].parent_class == "Calculator"

    def test_models_has_types(self, pure_java_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_java_scan

        def only(name: str, kind: SymbolType) -> list:
            return [s for s in idx.by_name(name) if s.symbol_type is kind]

        assert len(only("User", SymbolType.CLASS)) == 1
        assert len(only("AdminUser", SymbolType.CLASS)) == 1
        assert len(only("Reader", SymbolType.INTERFACE)) == 1
        assert len(only("Status", SymbolType.ENUM)) == 1

    def test_symbol_index_has_java_symbols(
        self, pure_java_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_java_scan
        assert len(idx.functions) == 0  # Java has no top-level functions
        assert len(idx.classes) >= 4  # Greeter, Calculator, User, AdminUser
        assert len(idx.interfaces) >= 1  # Reader
        assert len(idx.enums) >= 1  # Status
        assert len(idx.methods) >= 12

    def test_call_detection(self) -> None:
        changes = _changes_between(None, PURE_JAVA_REPO)
        call_changes = [c for c in changes if c.change_type is ChangeType.CALL_DETECTED]
        callers = {(c.caller_name, c.called_name) for c in call_changes}
        # Greeter.greet -> formatGreeting
        assert ("greet", "formatGreeting") in callers
        # AdminUser.display -> super.display()
        assert ("display", "display") in callers

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_JAVA_REPO)
        created = [c for c in changes if c.change_type is ChangeType.FILE_CREATED]
        assert len(created) == EXPECTED_JAVA_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}
        assert ChangeType.ADD_CLASS in {c.change_type for c in changes}
        assert ChangeType.ADD_INTERFACE in {c.change_type for c in changes}
        assert ChangeType.ADD_ENUM in {c.change_type for c in changes}

    def test_no_changes_when_identical(
        self, pure_java_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_java_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert len(changes) == 0

    def test_deterministic_across_runs(
        self, pure_java_scan: tuple[ScanResult, Any]
    ) -> None:
        scan1, idx1 = pure_java_scan
        scan2, idx2 = _scan_and_index(PURE_JAVA_REPO)
        changes1 = detect_changes(ScanResult(), scan1, SymbolIndex(), idx1)
        changes2 = detect_changes(ScanResult(), scan2, SymbolIndex(), idx2)
        assert changes1 == changes2

    def test_adding_a_constructor_is_add_function_not_add_class(
        self, tmp_path: Path
    ) -> None:
        """J5 pin: a constructor is a METHOD Symbol named after its class,
        so adding one fires ``ADD_FUNCTION Foo`` with ``parent_class=Foo``
        next to the existing ``CLASS Foo`` — the two coexist because kinds
        differ in the symbol identity."""
        changes = _java_changes(
            tmp_path,
            {"Greeter.java": _JAVA_GREETER},
            {"Greeter.java": _JAVA_GREETER_WITH_CTOR},
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [
            ("Greeter", "Greeter")
        ]
        # The class itself still exists — no identity collision.
        assert not _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert not _changes_of_type(changes, ChangeType.REMOVE_CLASS)

    def test_enum_constant_edit_fires_changed_class(self, tmp_path: Path) -> None:
        """J11 pin: enum constants are class-shell content, so adding one
        surfaces as ``CHANGED_CLASS`` (there is no ``CHANGED_ENUM`` claim
        type — ENUM collapses into CLASS for hash comparison)."""
        changes = _java_changes(
            tmp_path,
            {"Status.java": _JAVA_ENUM_A},
            {"Status.java": _JAVA_ENUM_B},
        )
        assert [
            (c.symbol_name, c.change_type)
            for c in changes
            if c.change_type is ChangeType.CHANGED_CLASS
        ] == [("Status", ChangeType.CHANGED_CLASS)]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.ADD_ENUM)

    def test_method_edit_is_changed_function_only(self, tmp_path: Path) -> None:
        """Disjoint facts: a method body edit never fires CHANGED_CLASS."""
        body = (
            "package p;\n\n"
            "public class A {\n"
            "    private int f = 1;\n\n"
            "    int m() {\n"
            "        return @V@;\n"
            "    }\n"
            "}\n"
        )
        changes = _java_changes(
            tmp_path,
            {"A.java": body.replace("@V@", "1")},
            {"A.java": body.replace("@V@", "2")},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert changes[0].symbol_name == "m"
        assert changes[0].parent_class == "A"

    def test_field_edit_is_changed_class_only(self, tmp_path: Path) -> None:
        """Disjoint facts, the other direction."""
        body = (
            "package p;\n\n"
            "public class A {\n"
            "    private int f = @V@;\n\n"
            "    int m() {\n"
            "        return 1;\n"
            "    }\n"
            "}\n"
        )
        changes = _java_changes(
            tmp_path,
            {"A.java": body.replace("@V@", "1")},
            {"A.java": body.replace("@V@", "2")},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"


# 7. Mixed Python + JavaScript repo
# ---------------------------------------------------------------------------


class TestPureKotlinRepo:
    """3 Kotlin files with classes, objects, interfaces, enums, calls."""

    def test_discovers_all_files(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, _ = pure_kotlin_scan
        assert scan.success_count == EXPECTED_KOTLIN_FILES
        assert scan.failure_count == 0
        assert len(scan.kotlin_files) == EXPECTED_KOTLIN_FILES
        assert set(scan.kotlin_files) == {
            Path("Greeter.kt"),
            Path("Calculator.kt"),
            Path("Models.kt"),
        }

    def test_top_level_functions_are_functions(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        """Kotlin differs from Java here: a top-level ``fun`` is a FUNCTION
        symbol with **no** ``parent_class``, not a METHOD on a synthetic type."""
        _, idx = pure_kotlin_scan
        for name in ("greet", "formatGreeting", "farewell"):
            found = idx.by_name(name)
            assert len(found) == 1, name
            assert found[0].symbol_type is SymbolType.FUNCTION, name
            assert found[0].parent_class is None, name

    def test_calculator_has_class_and_methods(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_kotlin_scan
        # The secondary constructor shares the class name — filter by type.
        calc = [
            s for s in idx.by_name("Calculator") if s.symbol_type is SymbolType.CLASS
        ]
        assert len(calc) == 1
        for name in ("add", "subtract", "multiply", "divide", "display"):
            methods = [
                s
                for s in idx.by_name(name)
                if s.parent_class == "Calculator" and s.symbol_type is SymbolType.METHOD
            ]
            assert len(methods) == 1, name

    def test_secondary_constructor_is_a_method_named_after_the_class(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_kotlin_scan
        ctor = [
            s for s in idx.by_name("Calculator") if s.symbol_type is SymbolType.METHOD
        ]
        assert len(ctor) == 1
        assert ctor[0].parent_class == "Calculator"

    def test_companion_method_attributes_to_the_outer_class(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        """Probe K3: a companion is not a symbol of its own, and its members
        belong to the class that owns the companion."""
        _, idx = pure_kotlin_scan
        average = idx.by_name("computeAverage")
        assert len(average) == 1
        assert average[0].symbol_type is SymbolType.METHOD
        assert average[0].parent_class == "Calculator"
        assert len(idx.by_name("Companion")) == 0

    def test_models_has_types(self, pure_kotlin_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_kotlin_scan

        def only(name: str, kind: SymbolType) -> list:
            return [s for s in idx.by_name(name) if s.symbol_type is kind]

        assert len(only("User", SymbolType.CLASS)) == 1  # data class → CLASS
        assert len(only("AdminUser", SymbolType.CLASS)) == 1
        assert len(only("Reader", SymbolType.INTERFACE)) == 1
        assert len(only("Status", SymbolType.ENUM)) == 1
        assert len(only("Registry", SymbolType.CLASS)) == 1  # object → CLASS
        assert len(only("label", SymbolType.METHOD)) == 1
        assert only("label", SymbolType.METHOD)[0].parent_class == "Status"

    def test_symbol_index_has_kotlin_symbols(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_kotlin_scan
        assert len(idx.functions) == 3  # greet, formatGreeting, farewell
        assert len(idx.classes) >= 4  # Calculator, User, AdminUser, Registry
        assert len(idx.interfaces) >= 1  # Reader
        assert len(idx.enums) >= 1  # Status
        assert len(idx.methods) >= 14

    def test_call_detection(self) -> None:
        changes = _changes_between(None, PURE_KOTLIN_REPO)
        call_changes = [c for c in changes if c.change_type is ChangeType.CALL_DETECTED]
        callers = {(c.caller_name, c.called_name) for c in call_changes}
        # Greeter.greet -> formatGreeting, and formatGreeting -> trim
        assert ("greet", "formatGreeting") in callers
        assert ("formatGreeting", "trim") in callers
        # AdminUser.display -> super.display()
        assert ("display", "display") in callers
        # Calculator.add -> history.add(result) — a member call on a property
        assert ("add", "add") in callers
        # Companion method -> stdlib extension on a list
        assert ("computeAverage", "forEach") in callers

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_KOTLIN_REPO)
        created = [c for c in changes if c.change_type is ChangeType.FILE_CREATED]
        assert len(created) == EXPECTED_KOTLIN_FILES
        types = {c.change_type for c in changes}
        assert ChangeType.ADD_FUNCTION in types
        assert ChangeType.ADD_CLASS in types
        assert ChangeType.ADD_INTERFACE in types
        assert ChangeType.ADD_ENUM in types

    def test_no_changes_when_identical(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_kotlin_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert len(changes) == 0

    def test_deterministic_across_runs(
        self, pure_kotlin_scan: tuple[ScanResult, Any]
    ) -> None:
        scan1, idx1 = pure_kotlin_scan
        scan2, idx2 = _scan_and_index(PURE_KOTLIN_REPO)
        changes1 = detect_changes(ScanResult(), scan1, SymbolIndex(), idx1)
        changes2 = detect_changes(ScanResult(), scan2, SymbolIndex(), idx2)
        assert changes1 == changes2


class TestPurePhpRepo:
    """3 PHP files with top-level functions, a class, hierarchy, calls.

    Every assertion below was verified against the real scanner first
    (the scan dump is the empirical basis, not an assumption).
    """

    def test_discovers_all_files(self, pure_php_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_php_scan
        assert scan.success_count == EXPECTED_PHP_FILES
        assert scan.failure_count == 0
        assert len(scan.php_files) == EXPECTED_PHP_FILES
        assert set(scan.php_files) == {
            Path("Greeter.php"),
            Path("Calculator.php"),
            Path("Models.php"),
        }

    def test_top_level_functions_are_functions(
        self, pure_php_scan: tuple[ScanResult, Any]
    ) -> None:
        """A namespaced top-level ``function`` is a FUNCTION with no
        ``parent_class`` — the PHP spelling of the Kotlin rule."""
        _, idx = pure_php_scan
        for name in ("greet", "formatGreeting", "farewell"):
            found = idx.by_name(name)
            assert len(found) == 1, name
            assert found[0].symbol_type is SymbolType.FUNCTION, name
            assert found[0].parent_class is None, name

    def test_calculator_has_class_and_methods(
        self, pure_php_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_php_scan
        calc = [
            s for s in idx.by_name("Calculator") if s.symbol_type is SymbolType.CLASS
        ]
        assert len(calc) == 1
        for name in ("add", "subtract", "multiply", "divide", "display"):
            methods = [
                s
                for s in idx.by_name(name)
                if s.parent_class == "Calculator" and s.symbol_type is SymbolType.METHOD
            ]
            assert len(methods) == 1, name

    def test_constructor_is_a_method_named_dunder_construct(
        self, pure_php_scan: tuple[ScanResult, Any]
    ) -> None:
        """PH12: PHP spells its constructor ``__construct``, so the METHOD
        is named ``__construct`` (unlike Java/Kotlin, where it takes the
        class name) and its ``parent_class`` is the class."""
        _, idx = pure_php_scan
        ctors = [
            s for s in idx.by_name("__construct") if s.symbol_type is SymbolType.METHOD
        ]
        assert {s.parent_class for s in ctors} == {
            "Calculator",
            "User",
            "AdminUser",
        }

    def test_models_has_types(self, pure_php_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_php_scan

        def only(name: str, kind: SymbolType) -> list:
            return [s for s in idx.by_name(name) if s.symbol_type is kind]

        assert len(only("User", SymbolType.CLASS)) == 1
        assert len(only("AdminUser", SymbolType.CLASS)) == 1
        assert len(only("Reader", SymbolType.INTERFACE)) == 1
        assert len(only("Status", SymbolType.ENUM)) == 1
        # PH8: a trait maps to CLASS (the claim taxonomy has no trait type).
        assert len(only("Registry", SymbolType.CLASS)) == 1
        # The trait's methods carry the trait name as parent_class.
        assert only("register", SymbolType.METHOD)[0].parent_class == "Registry"

    def test_interface_method_is_declaration_only(
        self, pure_php_scan: tuple[ScanResult, Any]
    ) -> None:
        """PH9: an interface method has no body, so its ``body_hash`` is
        ``None`` and it can never fire ``CHANGED_FUNCTION``."""
        _, idx = pure_php_scan
        reads = [s for s in idx.by_name("read") if s.symbol_type is SymbolType.METHOD]
        assert len(reads) == 1
        assert reads[0].parent_class == "Reader"
        assert reads[0].body_hash is None

    def test_symbol_index_has_php_symbols(
        self, pure_php_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_php_scan
        assert len(idx.functions) == 3  # greet, formatGreeting, farewell
        assert len(idx.classes) >= 4  # Calculator, User, AdminUser, Registry(trait)
        assert len(idx.interfaces) >= 1  # Reader
        assert len(idx.enums) >= 1  # Status
        assert len(idx.methods) >= 14

    def test_call_detection(self) -> None:
        changes = _changes_between(None, PURE_PHP_REPO)
        call_changes = [c for c in changes if c.change_type is ChangeType.CALL_DETECTED]
        callers = {(c.caller_name, c.called_name) for c in call_changes}
        # Greeter.greet -> formatGreeting, and formatGreeting -> trim
        assert ("greet", "formatGreeting") in callers
        assert ("formatGreeting", "trim") in callers
        # AdminUser.display -> parent::display()
        assert ("display", "display") in callers
        # Calculator.computeAverage -> array_sum()/count()
        assert ("computeAverage", "array_sum") in callers
        assert ("computeAverage", "count") in callers
        # User.toDict -> json_encode()
        assert ("toDict", "json_encode") in callers

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_PHP_REPO)
        created = [c for c in changes if c.change_type is ChangeType.FILE_CREATED]
        assert len(created) == EXPECTED_PHP_FILES
        types = {c.change_type for c in changes}
        assert ChangeType.ADD_FUNCTION in types
        assert ChangeType.ADD_CLASS in types
        assert ChangeType.ADD_INTERFACE in types
        assert ChangeType.ADD_ENUM in types

    def test_no_changes_when_identical(
        self, pure_php_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_php_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert len(changes) == 0

    def test_deterministic_across_runs(
        self, pure_php_scan: tuple[ScanResult, Any]
    ) -> None:
        scan1, idx1 = pure_php_scan
        scan2, idx2 = _scan_and_index(PURE_PHP_REPO)
        changes1 = detect_changes(ScanResult(), scan1, SymbolIndex(), idx1)
        changes2 = detect_changes(ScanResult(), scan2, SymbolIndex(), idx2)
        assert changes1 == changes2


class TestPureCppRepo:
    """5 C++ files: free functions, a class, hierarchy, a split, calls.

    Every assertion below was verified against the real scanner first
    (the scan dump is the empirical basis, not an assumption).
    """

    def test_discovers_all_files(self, pure_cpp_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_cpp_scan
        assert scan.success_count == EXPECTED_CPP_FILES
        assert scan.failure_count == 0
        assert len(scan.cpp_files) == EXPECTED_CPP_FILES
        assert set(scan.cpp_files) == {
            Path("greeter.h"),
            Path("greeter.cpp"),
            Path("calculator.h"),
            Path("calculator.cpp"),
            Path("models.h"),
        }

    def test_free_functions_are_functions(
        self, pure_cpp_scan: tuple[ScanResult, Any]
    ) -> None:
        """A namespace-scope function is a FUNCTION with no ``parent_class``
        — the C++ spelling of the Kotlin/PHP rule."""
        _, idx = pure_cpp_scan
        for name in ("greet", "formatGreeting", "farewell", "trimCopy"):
            found = [
                s for s in idx.by_name(name) if s.symbol_type is SymbolType.FUNCTION
            ]
            # The header declaration and the .cpp definition are two symbols.
            assert len(found) == 2, name
            assert all(s.parent_class is None for s in found), name

    def test_calculator_has_class_and_methods(
        self, pure_cpp_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_cpp_scan
        calc = [
            s for s in idx.by_name("Calculator") if s.symbol_type is SymbolType.CLASS
        ]
        assert len(calc) == 1
        for name in (
            "add",
            "subtract",
            "multiply",
            "divide",
            "display",
            "computeAverage",
        ):
            methods = [
                s
                for s in idx.by_name(name)
                if s.parent_class == "Calculator" and s.symbol_type is SymbolType.METHOD
            ]
            # Declaration (calculator.h) + definition (calculator.cpp).
            assert len(methods) == 2, name

    def test_constructor_is_named_after_its_class(
        self, pure_cpp_scan: tuple[ScanResult, Any]
    ) -> None:
        """C++ spells its constructor with the class name, so the METHOD is
        named ``Calculator`` with the class as ``parent_class``."""
        _, idx = pure_cpp_scan
        ctors = [
            s for s in idx.by_name("Calculator") if s.symbol_type is SymbolType.METHOD
        ]
        assert len(ctors) == 2
        assert {s.parent_class for s in ctors} == {"Calculator"}

    def test_models_has_types(self, pure_cpp_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_cpp_scan

        def only(name: str, kind: SymbolType) -> list:
            return [s for s in idx.by_name(name) if s.symbol_type is kind]

        assert len(only("User", SymbolType.CLASS)) == 1
        assert len(only("AdminUser", SymbolType.CLASS)) == 1
        assert len(only("Status", SymbolType.ENUM)) == 1
        assert len(only("Id", SymbolType.TYPE_ALIAS)) == 1
        # C++ has no interface keyword: INTERFACE never fires (a documented
        # accepted edge, like a Go enum).
        assert idx.interfaces == []

    def test_declaration_only_members_carry_no_hash(
        self, pure_cpp_scan: tuple[ScanResult, Any]
    ) -> None:
        """E9: a header-side member has ``body_hash=None`` so the ``.cpp``
        body edit can never falsify it, while the definition is hashed."""
        _, idx = pure_cpp_scan
        for name in ("add", "display"):
            methods = [s for s in idx.by_name(name) if s.parent_class == "Calculator"]
            header = [s for s in methods if str(s.file_path) == "calculator.h"]
            impl = [s for s in methods if str(s.file_path) == "calculator.cpp"]
            assert len(header) == 1 and len(impl) == 1, name
            assert header[0].body_hash is None, name
            assert impl[0].body_hash is not None, name

    def test_symbol_index_has_cpp_symbols(
        self, pure_cpp_scan: tuple[ScanResult, Any]
    ) -> None:
        _, idx = pure_cpp_scan
        # 4 declarations in greeter.h + 4 definitions in greeter.cpp + escape.
        assert len(idx.functions) == 9
        assert len(idx.classes) == 3  # Calculator, User, AdminUser
        assert len(idx.enums) >= 1  # Status
        assert len(idx.type_aliases) >= 1  # Id
        assert len(idx.methods) >= 20

    def test_call_detection(self) -> None:
        changes = _changes_between(None, PURE_CPP_REPO)
        call_changes = [c for c in changes if c.change_type is ChangeType.CALL_DETECTED]
        callers = {(c.caller_name, c.called_name) for c in call_changes}
        # greet.cpp: greet -> formatGreeting, formatGreeting -> trimCopy
        assert ("greet", "formatGreeting") in callers
        assert ("formatGreeting", "trimCopy") in callers
        # AdminUser::display -> User::display() (the qualified-call row)
        assert ("display", "display") in callers
        # Calculator::computeAverage -> totalOf() / values.size()
        assert ("computeAverage", "totalOf") in callers
        assert ("computeAverage", "size") in callers
        # User::toJson -> escape()
        assert ("toJson", "escape") in callers

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_CPP_REPO)
        created = [c for c in changes if c.change_type is ChangeType.FILE_CREATED]
        assert len(created) == EXPECTED_CPP_FILES
        types = {c.change_type for c in changes}
        assert ChangeType.ADD_FUNCTION in types
        assert ChangeType.ADD_CLASS in types
        assert ChangeType.ADD_ENUM in types
        assert ChangeType.ADD_TYPE_ALIAS in types

    def test_no_changes_when_identical(
        self, pure_cpp_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = pure_cpp_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert len(changes) == 0

    def test_deterministic_across_runs(
        self, pure_cpp_scan: tuple[ScanResult, Any]
    ) -> None:
        scan1, idx1 = pure_cpp_scan
        scan2, idx2 = _scan_and_index(PURE_CPP_REPO)
        changes1 = detect_changes(ScanResult(), scan1, SymbolIndex(), idx1)
        changes2 = detect_changes(ScanResult(), scan2, SymbolIndex(), idx2)
        assert changes1 == changes2


class TestMixedRepo:
    """2 Python + 2 JavaScript files in one repo."""

    def test_discovers_all_files(self, mixed_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = mixed_scan
        assert scan.success_count == EXPECTED_MIXED_PY + EXPECTED_MIXED_JS
        assert scan.failure_count == 0
        assert len(scan.modules) == EXPECTED_MIXED_PY
        assert len(scan.js_files) == EXPECTED_MIXED_JS
        assert Path("main.py") in scan.modules
        assert Path("utils.py") in scan.modules
        assert Path("utils.js") in scan.js_files
        assert Path("ui_handler.js") in scan.js_files

    def test_python_symbols_indexed(self, mixed_scan: tuple[ScanResult, Any]) -> None:
        _, idx = mixed_scan
        # validate_email exists in both main.py (dummy) and utils.py (real)
        assert len(idx.by_name("validate_email")) == 2
        assert len(idx.by_name("format_date")) == 1
        # Logger exists in both utils.py (Python class) and ui_handler.js (JS function)
        assert len(idx.by_name("Logger")) == 2
        assert len(idx.by_name("run_app")) == 1
        assert len(idx.by_name("load_config")) == 1

    def test_js_symbols_indexed(self, mixed_scan: tuple[ScanResult, Any]) -> None:
        _, idx = mixed_scan
        assert len(idx.by_name("validateEmail")) == 1
        assert len(idx.by_name("formatDate")) == 1
        assert len(idx.by_name("pad")) == 1
        assert len(idx.by_name("UiHandler")) == 1
        # Logger appears in both utils.py (Python class) and ui_handler.js (JS function)
        assert len(idx.by_name("Logger")) == 2

    def test_mixed_symbol_count(self, mixed_scan: tuple[ScanResult, Any]) -> None:
        _, idx = mixed_scan
        # Python: validate_email, format_date, Logger, run_app, load_config, get_emails,
        #         validate_all, Logger.__init__, Logger.log = 9
        # JS: validateEmail, formatDate, pad, UiHandler, Logger, UiHandler.renderUser,
        #     UiHandler.renderDate, Logger.log = 8
        # Total: ~17
        assert len(idx.all_symbols) >= 15

    def test_call_detection_mixed(self, mixed_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = mixed_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # Python calls: validate_all calls validate_email and print and len
        #               load_config calls print; run_app calls load_config, get_emails, validate_all
        #               Logger.log calls print
        # JS calls: validateEmail calls console.log (member call — captured)
        #           UiHandler.renderUser calls validateEmail and Logger.log (member call — captured)
        #           UiHandler.renderDate calls formatDate and console.log (member call — captured)

        # We should have at least several Python calls
        py_calls = {
            (c.caller_name, c.called_name)
            for c in calls
            if str(c.file_path).endswith(".py")
        }
        assert ("validate_all", "validate_email") in py_calls
        assert ("load_config", "print") in py_calls
        assert ("validate_all", "len") in py_calls

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, MIXED_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_MIXED_PY + EXPECTED_MIXED_JS
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(
        self, mixed_scan: tuple[ScanResult, Any]
    ) -> None:
        scan, idx = mixed_scan
        changes = detect_changes(scan, scan, idx, idx)
        assert changes == []

    def test_deterministic_across_runs(self) -> None:
        scans = [_scan_and_index(MIXED_REPO) for _ in range(3)]
        for i in range(1, 3):
            for path in scans[0][0].modules:
                assert ast.dump(scans[i][0].modules[path]) == ast.dump(
                    scans[0][0].modules[path],
                ), f"Mismatch in {path} on run {i + 1}"
            assert list(scans[i][0].modules) == list(scans[0][0].modules)
            assert scans[i][0].js_files == scans[0][0].js_files
            assert scans[i][0].failed_files == scans[0][0].failed_files
            assert scans[i][1].symbols == scans[0][1].symbols


# ---------------------------------------------------------------------------
# 5. Cross-repo determinism
# ---------------------------------------------------------------------------


class TestAllReposDeterministic:
    """All 11 milestone repos, scanned 3x each — every field must be identical.

    Besides the ``ScanResult`` fields, every symbol is compared as an explicit
    ``(name, type, path, line, parent, body_hash)`` tuple across all eight
    language maps and the symbol index — ``Symbol.__eq__`` exempts
    ``line_number`` and ``body_hash``, so dataclass equality alone would not
    catch a run-to-run hash difference.
    """

    REPOS = [
        ("pure-python", PURE_PY_REPO),
        ("pure-js", PURE_JS_REPO),
        ("pure-ts", PURE_TS_REPO),
        ("pure-tsx", PURE_TSX_REPO),
        ("pure-rust", PURE_RUST_REPO),
        ("pure-go", PURE_GO_REPO),
        ("pure-java", PURE_JAVA_REPO),
        ("pure-kotlin", PURE_KOTLIN_REPO),
        ("pure-php", PURE_PHP_REPO),
        ("pure-cpp", PURE_CPP_REPO),
        ("mixed", MIXED_REPO),
    ]

    @pytest.mark.parametrize("name,path", REPOS)
    def test_three_runs_identical(self, name: str, path: Path) -> None:
        results = [_scan_and_index(path) for _ in range(3)]
        for i in range(1, 3):
            for p in results[0][0].modules:
                assert ast.dump(results[i][0].modules[p]) == ast.dump(
                    results[0][0].modules[p],
                ), f"{name}: AST dump differs on run {i + 1}"
            assert list(results[i][0].modules) == list(results[0][0].modules)
            assert results[i][0].js_files == results[0][0].js_files
            assert results[i][0].ts_files == results[0][0].ts_files
            assert results[i][0].rust_files == results[0][0].rust_files
            assert results[i][0].go_files == results[0][0].go_files
            assert results[i][0].java_files == results[0][0].java_files
            assert results[i][0].kotlin_files == results[0][0].kotlin_files
            assert results[i][0].php_files == results[0][0].php_files
            assert results[i][0].cpp_files == results[0][0].cpp_files
            assert results[i][0].failed_files == results[0][0].failed_files
            assert results[i][1].symbols == results[0][1].symbols, (
                f"{name}: symbol index differs on run {i + 1}"
            )

            # ``Symbol.__eq__`` exempts ``line_number`` and ``body_hash``, so
            # the field asserts above cannot see those two; compare explicit
            # projections for every language map and the whole index.
            map_names = (
                "js_files",
                "ts_files",
                "rust_files",
                "go_files",
                "java_files",
                "kotlin_files",
                "php_files",
                "cpp_files",
            )
            run_maps = (
                results[i][0].js_files,
                results[i][0].ts_files,
                results[i][0].rust_files,
                results[i][0].go_files,
                results[i][0].java_files,
                results[i][0].kotlin_files,
                results[i][0].php_files,
                results[i][0].cpp_files,
            )
            base_maps = (
                results[0][0].js_files,
                results[0][0].ts_files,
                results[0][0].rust_files,
                results[0][0].go_files,
                results[0][0].java_files,
                results[0][0].kotlin_files,
                results[0][0].php_files,
                results[0][0].cpp_files,
            )
            for map_name, run_map, base_map in zip(
                map_names, run_maps, base_maps, strict=True
            ):
                assert {
                    str(p): _full_symbol_tuples(syms) for p, syms in run_map.items()
                } == {
                    str(p): _full_symbol_tuples(syms) for p, syms in base_map.items()
                }, f"{name}: {map_name} symbols differ on run {i + 1}"
            assert _full_symbol_tuples(
                sym for syms in results[i][1].symbols.values() for sym in syms
            ) == _full_symbol_tuples(
                sym for syms in results[0][1].symbols.values() for sym in syms
            ), f"{name}: symbol index contains a differing symbol on run {i + 1}"


# ---------------------------------------------------------------------------
# 6. Pre → Post pipeline
# ---------------------------------------------------------------------------


class TestPrePostPipeline:
    """Full pre/post change detection on a real repo."""

    def test_adding_file_vs_nothing(self) -> None:
        """Going from empty to a repo detects FILE_CREATED + ADD_FUNCTION."""
        changes = _changes_between(None, PURE_PY_REPO)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_CREATED in types
        assert ChangeType.ADD_FUNCTION in types
        assert ChangeType.ADD_CLASS in types

    def test_going_to_empty_detects_removals(self) -> None:
        """Going from a repo to empty detects FILE_DELETED + REMOVE_FUNCTION."""
        changes = _changes_between(PURE_PY_REPO, None)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_DELETED in types
        assert ChangeType.REMOVE_FUNCTION in types
        assert ChangeType.REMOVE_CLASS in types

    def test_no_changes_identical_scans(self) -> None:
        for repo_path in [
            PURE_PY_REPO,
            PURE_JS_REPO,
            PURE_TS_REPO,
            PURE_TSX_REPO,
            MIXED_REPO,
        ]:
            pre_scan, pre_sym = _scan_and_index(repo_path)
            post_scan, post_sym = _scan_and_index(repo_path)
            changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
            assert changes == [], f"Expected no changes for {repo_path}"


# ---------------------------------------------------------------------------
# 7. Integration: full pipeline determinism
# ---------------------------------------------------------------------------


class TestFullPipelineDeterminism:
    """Run the entire pipeline 5 times on mixed repo — every output identical."""

    def test_five_runs_identical(self) -> None:
        outputs: list[tuple[ScanResult, SymbolIndex, list[DetectedChange]]] = []
        for _ in range(5):
            pre_scan, pre_sym = _scan_and_index(MIXED_REPO)
            post_scan, post_sym = _scan_and_index(MIXED_REPO)
            changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
            outputs.append((pre_scan, pre_sym, changes))

        for i in range(1, 5):
            for p in outputs[0][0].modules:
                assert ast.dump(outputs[i][0].modules[p]) == ast.dump(
                    outputs[0][0].modules[p],
                ), f"AST dump differs on run {i + 1}"
            assert list(outputs[i][0].modules) == list(outputs[0][0].modules)
            assert outputs[i][0].js_files == outputs[0][0].js_files
            assert outputs[i][0].ts_files == outputs[0][0].ts_files
            assert outputs[i][0].failed_files == outputs[0][0].failed_files
            assert outputs[i][1].symbols == outputs[0][1].symbols  # SymbolIndex
            assert outputs[i][2] == outputs[0][2]  # changes list
