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
MIXED_REPO = REPOS / "mixed"

EXPECTED_PY_FILES = 3     # greeter.py, calculator.py, models.py
EXPECTED_JS_FILES = 3     # greeter.js, calculator.js, models.js
EXPECTED_TS_FILES = 3     # greeter.ts, calculator.ts, models.ts
EXPECTED_TSX_FILES = 3    # greeter.tsx, calculator.tsx, models.tsx
EXPECTED_MIXED_PY = 2     # utils.py, main.py
EXPECTED_MIXED_JS = 2     # utils.js, ui_handler.js


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
def mixed_scan() -> tuple[ScanResult, SymbolIndex]:
    return _scan_and_index(MIXED_REPO)


# ---------------------------------------------------------------------------
# 1. Pure Python repo
# ---------------------------------------------------------------------------


class TestPurePythonRepo:
    """3 Python files with functions, classes, methods, calls."""

    def test_discovers_all_files(self, pure_python_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_python_scan
        assert scan.success_count == EXPECTED_PY_FILES
        assert scan.failure_count == 0
        assert len(scan.modules) == EXPECTED_PY_FILES
        assert set(scan.modules) == {
            Path("greeter.py"),
            Path("calculator.py"),
            Path("models.py"),
        }

    def test_greeter_has_functions(self, pure_python_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_python_scan
        greeter = scan.modules[Path("greeter.py")]
        names = {
            n.name
            for n in ast.walk(greeter)
            if isinstance(n, ast.FunctionDef)
        }
        assert "greet" in names
        assert "format_greeting" in names
        assert "farewell" in names

    def test_calculator_has_class_and_methods(self, pure_python_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_python_scan
        calc = scan.modules[Path("calculator.py")]
        calc_class = next(
            n for n in ast.walk(calc)
            if isinstance(n, ast.ClassDef) and n.name == "Calculator"
        )
        method_names = {
            n.name
            for n in calc_class.body
            if isinstance(n, ast.FunctionDef)
        }
        assert "add" in method_names
        assert "subtract" in method_names
        assert "multiply" in method_names
        assert "divide" in method_names
        # compute_average is a top-level function, not a method
        assert "compute_average" not in method_names

    def test_models_has_class_hierarchy(self, pure_python_scan: tuple[ScanResult, Any]) -> None:
        scan, _ = pure_python_scan
        models = scan.modules[Path("models.py")]
        class_names = {
            n.name
            for n in ast.walk(models)
            if isinstance(n, ast.ClassDef)
        }
        assert "User" in class_names
        assert "AdminUser" in class_names

    def test_symbol_index_has_py_symbols(self, pure_python_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_python_scan
        # greeter.py: greet, format_greeting, farewell (3 functions)
        # calculator.py: Calculator (class), compute_average (function), add/sub/multiply/divide (methods)
        # models.py: User (class), AdminUser (class), __init__/display/to_dict/__init__/display (methods)
        assert len(idx.functions) >= 4  # greet, format_greeting, farewell, compute_average
        assert len(idx.classes) >= 3  # Calculator, User, AdminUser
        assert len(idx.methods) >= 5  # add, subtract, multiply, divide, __init__, display, to_dict, display

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

    def test_no_changes_when_identical(self, pure_python_scan: tuple[ScanResult, Any]) -> None:
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

    def test_calculator_has_class_and_methods(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
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

    def test_models_has_class_hierarchy(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_js_scan
        assert len(idx.by_name("User")) == 1
        assert len(idx.by_name("AdminUser")) == 1
        # Methods on User: display, toDict, constructor -> but constructor is 'constructor' keyword
        user_methods = {s.name for s in idx.methods if s.parent_class == "User"}
        assert "display" in user_methods
        assert "toDict" in user_methods

    def test_symbol_index_has_js_symbols(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_js_scan
        assert len(idx.functions) >= 3  # greet, formatGreeting, farewell, computeAverage
        assert len(idx.classes) >= 3  # Calculator, User, AdminUser
        assert len(idx.methods) >= 6  # add, subtract, multiply, divide, display, toDict, display

    def test_call_detection(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = pure_js_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # greet calls formatGreeting and console.log (but console.log is attribute call — excluded!)
        # formatGreeting makes no calls
        # farewell calls console.log (excluded — attribute call)
        # multiply calls console.log (excluded)
        # computeAverage calls sum and len
        # display calls console.log (excluded)
        assert len(calls) >= 1  # at minimum, computeAverage calls sum, len

        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        assert ("computeAverage", "len") in call_pairs

    def test_console_log_is_excluded(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
        """console.log() is an attribute call — should not appear as CALL_DETECTED."""
        scan, idx = pure_js_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        # These are all attribute calls and should be excluded
        assert ("greet", "log") not in call_pairs
        assert ("farewell", "log") not in call_pairs

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_JS_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_JS_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(self, pure_js_scan: tuple[ScanResult, Any]) -> None:
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

    def test_calculator_has_class_and_methods(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
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

    def test_models_has_class_hierarchy(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_ts_scan
        assert len(idx.by_name("User")) == 1
        assert len(idx.by_name("AdminUser")) == 1
        # Methods on User: display, toDict
        user_methods = {s.name for s in idx.methods if s.parent_class == "User"}
        assert "display" in user_methods
        assert "toDict" in user_methods

    def test_symbol_index_has_ts_symbols(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_ts_scan
        assert len(idx.functions) >= 3  # greet, formatGreeting, farewell, computeAverage
        assert len(idx.classes) >= 3  # Calculator, User, AdminUser
        assert len(idx.methods) >= 6  # add, subtract, multiply, divide, display, toDict, display

    def test_call_detection(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = pure_ts_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # greet calls formatGreeting and console.log (but console.log is attribute call — excluded!)
        # formatGreeting makes no calls
        # farewell calls console.log (excluded)
        # multiply calls console.log (excluded)
        # computeAverage calls sum and len
        # display calls console.log (excluded)
        assert len(calls) >= 1  # at minimum, computeAverage calls sum, len

        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        assert ("computeAverage", "len") in call_pairs

    def test_console_log_is_excluded(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
        """console.log() is an attribute call — should not appear as CALL_DETECTED."""
        scan, idx = pure_ts_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        # These are all attribute calls and should be excluded
        assert ("greet", "log") not in call_pairs
        assert ("farewell", "log") not in call_pairs

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, PURE_TS_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_TS_FILES
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(self, pure_ts_scan: tuple[ScanResult, Any]) -> None:
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

    def test_calculator_has_class_and_methods(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
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

    def test_symbol_index_has_tsx_symbols(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
        _, idx = pure_tsx_scan
        assert len(idx.functions) >= 6  # Greeting, formatGreeting, Farewell, computeAverage, UserCard, AdminCard
        assert len(idx.classes) >= 2  # Calculator, UserList
        assert len(idx.methods) >= 6  # add, subtract, multiply, divide, render (Calculator), render (UserList)

    def test_call_detection(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
        scan, idx = pure_tsx_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)

        # Greeting calls formatGreeting
        # computeAverage calls sum and len
        # multiply calls console.log (excluded — attribute)
        assert len(calls) >= 3

        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        assert ("Greeting", "formatGreeting") in call_pairs
        assert ("computeAverage", "len") in call_pairs

    def test_console_log_is_excluded(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
        """console.log() is an attribute call — should not appear as CALL_DETECTED."""
        scan, idx = pure_tsx_scan
        changes = detect_changes(ScanResult(), scan, SymbolIndex(), idx)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        call_pairs = {(c.caller_name, c.called_name) for c in calls}
        # These are all attribute calls and should be excluded
        assert ("Calculator", "log") not in call_pairs

    def test_jsx_element_usage_is_not_a_call(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
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

    def test_no_changes_when_identical(self, pure_tsx_scan: tuple[ScanResult, Any]) -> None:
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
# 4. Mixed Python + JavaScript repo
# ---------------------------------------------------------------------------


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
        # JS calls: validateEmail calls console.log (excluded — attribute)
        #           UiHandler.renderUser calls validateEmail and Logger.log (excluded)
        #           UiHandler.renderDate calls formatDate and console.log (excluded)

        # We should have at least several Python calls
        py_calls = {(c.caller_name, c.called_name) for c in calls if str(c.file_path).endswith(".py")}
        assert ("validate_all", "validate_email") in py_calls
        assert ("load_config", "print") in py_calls
        assert ("validate_all", "len") in py_calls

    def test_file_changes_detected(self) -> None:
        changes = _changes_between(None, MIXED_REPO)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == EXPECTED_MIXED_PY + EXPECTED_MIXED_JS
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_no_changes_when_identical(self, mixed_scan: tuple[ScanResult, Any]) -> None:
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
    """All 3 repos, scanned 3x each — every field must be identical."""

    REPOS = [
        ("pure-python", PURE_PY_REPO),
        ("pure-js", PURE_JS_REPO),
        ("pure-ts", PURE_TS_REPO),
        ("pure-tsx", PURE_TSX_REPO),
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
            assert results[i][0].failed_files == results[0][0].failed_files
            assert results[i][1].symbols == results[0][1].symbols, (
                f"{name}: symbol index differs on run {i + 1}"
            )


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
