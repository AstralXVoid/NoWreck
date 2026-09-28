from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from nowreck.detector.change_detector import (
    ChangeDetector,
    ChangeType,
    DetectedChange,
    detect_changes,
)
from nowreck.scanner.repository_scanner import ScanResult
from nowreck.scanner.symbol_index import (
    Symbol,
    SymbolIndex,
    SymbolType,
    build_symbol_index,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scan_result(sources: dict[str, str]) -> ScanResult:
    """Build a ``ScanResult`` from a dict of relative-path to source code."""
    import ast

    parsed: dict[Path, ast.Module] = {}
    failed: dict[Path, str] = {}
    for rel_path, source in sources.items():
        try:
            parsed[Path(rel_path)] = ast.parse(source)
        except SyntaxError as exc:
            failed[Path(rel_path)] = f"SyntaxError: {exc}"
    return ScanResult(modules=parsed, failed_files=failed)


def _pre_post(
    pre_sources: dict[str, str],
    post_sources: dict[str, str],
) -> tuple[ScanResult, ScanResult, SymbolIndex, SymbolIndex]:
    """Build the four inputs needed by ``ChangeDetector.detect()``."""
    pre_scan = _make_scan_result(pre_sources)
    post_scan = _make_scan_result(post_sources)
    pre_sym = build_symbol_index(pre_scan)
    post_sym = build_symbol_index(post_scan)
    return pre_scan, post_scan, pre_sym, post_sym


def _changes_of_type(
    changes: list[DetectedChange],
    change_type: ChangeType,
) -> list[DetectedChange]:
    return [c for c in changes if c.change_type is change_type]


# ---------------------------------------------------------------------------
# ChangeType & DetectedChange basics
# ---------------------------------------------------------------------------


class TestChangeType:
    def test_has_all_mvp_types(self) -> None:
        assert ChangeType.ADD_FUNCTION
        assert ChangeType.REMOVE_FUNCTION
        assert ChangeType.ADD_CLASS
        assert ChangeType.REMOVE_CLASS
        # Type-level kinds added in v0.8.0
        assert ChangeType.ADD_INTERFACE
        assert ChangeType.REMOVE_INTERFACE
        assert ChangeType.ADD_ENUM
        assert ChangeType.REMOVE_ENUM
        assert ChangeType.ADD_TYPE_ALIAS
        assert ChangeType.REMOVE_TYPE_ALIAS
        assert ChangeType.FILE_CREATED
        assert ChangeType.FILE_DELETED
        assert ChangeType.CALL_DETECTED

    def test_values_are_distinct(self) -> None:
        values = {m.value for m in ChangeType}
        assert len(values) == len(ChangeType)


class TestDetectedChange:
    def test_minimal_creation(self) -> None:
        c = DetectedChange(
            change_type=ChangeType.ADD_FUNCTION,
            file_path=Path("main.py"),
            symbol_name="greet",
            line_number=1,
        )
        assert c.symbol_name == "greet"
        assert c.parent_class is None
        assert c.caller_name is None

    def test_call_change_has_caller_and_called(self) -> None:
        c = DetectedChange(
            change_type=ChangeType.CALL_DETECTED,
            file_path=Path("app.py"),
            caller_name="greet",
            called_name="print",
        )
        assert c.caller_name == "greet"
        assert c.called_name == "print"

    def test_frozen_cannot_be_mutated(self) -> None:
        c = DetectedChange(
            change_type=ChangeType.FILE_CREATED,
            file_path=Path("new.py"),
        )
        with pytest.raises(AttributeError):
            c.symbol_name = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Empty / no-change cases
# ---------------------------------------------------------------------------


class TestDetectNoChanges:
    def test_both_empty(self) -> None:
        empty = ScanResult()
        idx = SymbolIndex()
        changes = ChangeDetector.detect(empty, empty, idx, idx)
        assert changes == []

    def test_identical_repos(self) -> None:
        """No changes when both snapshots are identical — including calls."""
        src = {"app.py": "def greet(): pass\n"}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(src, src)
        changes = ChangeDetector.detect(pre_scan, post_scan, pre_sym, post_sym)
        assert changes == []


# ---------------------------------------------------------------------------
# Function addition / removal
# ---------------------------------------------------------------------------


class TestDetectFunctionChanges:
    def test_function_added(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"app.py": "x = 1\n"},
            {"app.py": "x = 1\n\ndef greet() -> str:\n    return 'hi'\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert len(added) == 1
        assert added[0].symbol_name == "greet"
        assert added[0].file_path == Path("app.py")
        assert added[0].line_number == 3

    def test_function_removed(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"app.py": "def greet(): pass\n"},
            {"app.py": "x = 1\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert len(removed) == 1
        assert removed[0].symbol_name == "greet"

    def test_multiple_functions_added(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"app.py": "x = 1\n"},
            {
                "app.py": textwrap.dedent("""\
                    x = 1
                    def foo(): pass
                    def bar(): pass
                """),
            },
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert len(added) == 2
        names = {c.symbol_name for c in added}
        assert names == {"foo", "bar"}

    def test_function_unchanged(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"app.py": "def greet(): pass\n"},
            {"app.py": "def greet(): pass\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        func_changes = [
            c
            for c in changes
            if c.change_type in (ChangeType.ADD_FUNCTION, ChangeType.REMOVE_FUNCTION)
        ]
        assert func_changes == []


# ---------------------------------------------------------------------------
# Class addition / removal
# ---------------------------------------------------------------------------


class TestDetectClassChanges:
    def test_class_added(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"models.py": "x = 1\n"},
            {"models.py": "x = 1\n\nclass User:\n    pass\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert len(added) == 1
        assert added[0].symbol_name == "User"

    def test_class_removed(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"models.py": "class User:\n    pass\n"},
            {"models.py": "x = 1\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_CLASS)
        assert len(removed) == 1
        assert removed[0].symbol_name == "User"

    def test_class_methods_are_detected(self) -> None:
        """Adding a class with methods should add class + methods."""
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"widget.py": "x = 1\n"},
            {
                "widget.py": textwrap.dedent("""\
                    x = 1

                    class Widget:
                        def render(self) -> str:
                            return "hello"
                """),
            },
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added_classes = _changes_of_type(changes, ChangeType.ADD_CLASS)
        added_funcs = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert len(added_classes) == 1
        assert added_classes[0].symbol_name == "Widget"
        # The method 'render' appears as ADD_FUNCTION with parent_class
        render_adds = [c for c in added_funcs if c.symbol_name == "render"]
        assert len(render_adds) == 1
        assert render_adds[0].parent_class == "Widget"
        assert render_adds[0].line_number == 4


# ---------------------------------------------------------------------------
# File creation / deletion
# ---------------------------------------------------------------------------


class TestDetectFileChanges:
    def test_file_created(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {},
            {"new_module.py": "def hello(): pass\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == 1
        assert created[0].file_path == Path("new_module.py")

    def test_file_deleted(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"old.py": "x = 1\n"},
            {},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        deleted = _changes_of_type(changes, ChangeType.FILE_DELETED)
        assert len(deleted) == 1
        assert deleted[0].file_path == Path("old.py")

    def test_multiple_files_created(self) -> None:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {},
            {"a.py": "x = 1\n", "b.py": "y = 2\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert len(created) == 2

    def test_failed_files_count_as_file_presence(self) -> None:
        """A file with syntax errors still exists — should not appear as
        FILE_CREATED if present in both states."""
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"broken.py": "def broken(\n"},
            {"broken.py": "def broken(\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        file_changes = _changes_of_type(changes, ChangeType.FILE_CREATED)
        file_changes += _changes_of_type(changes, ChangeType.FILE_DELETED)
        assert file_changes == []


# ---------------------------------------------------------------------------
# Call detection
# ---------------------------------------------------------------------------


class TestDetectCallChanges:
    def test_simple_call_detected(self) -> None:
        source = "def greet(name: str) -> str:\n    return print(f'Hello {name}')\n"
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {},
            {"app.py": source},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert len(calls) >= 1
        greet_calls = [c for c in calls if c.caller_name == "greet"]
        assert any(c.called_name == "print" for c in greet_calls)

    def test_multiple_calls_in_one_function(self) -> None:
        post_src = {
            "utils.py": textwrap.dedent("""\
                def process(items):
                    result = sorted(items)
                    print(result)
                    return len(result)
            """),
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post({}, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        process_calls = {c.called_name for c in calls if c.caller_name == "process"}
        assert "sorted" in process_calls
        assert "print" in process_calls
        assert "len" in process_calls

    def test_calls_across_multiple_functions(self) -> None:
        post_src = {
            "app.py": textwrap.dedent("""\
                def helper():
                    return 42

                def main():
                    return helper()
            """),
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post({}, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        main_calls = {c.called_name for c in calls if c.caller_name == "main"}
        assert "helper" in main_calls
        helper_calls = {c.called_name for c in calls if c.caller_name == "helper"}
        assert helper_calls == set()  # helper makes no calls

    def test_method_calls_detected(self) -> None:
        post_src = {
            "shapes.py": textwrap.dedent("""\
                class Circle:
                    def draw(self):
                        return print("circle")
            """),
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post({}, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        draw_calls = {c.called_name for c in calls if c.caller_name == "draw"}
        assert "print" in draw_calls

    def test_attribute_calls_are_captured(self) -> None:
        """Method-style calls like obj.method() are captured since v16."""
        post_src = {
            "app.py": textwrap.dedent("""\
                def run():
                    return logger.info("started")
            """),
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post({}, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = [c for c in calls if c.caller_name == "run"]
        # "info" is an attribute call (logger.info()) — captured, receiver is a Name
        assert any(c.called_name == "info" for c in run_calls)
        # Top-level caller carries no parent class
        assert all(c.parent_class is None for c in run_calls)

    def test_nested_function_calls_not_attributed_to_outer(self) -> None:
        post_src = {
            "app.py": textwrap.dedent("""\
                def outer():
                    def inner():
                        return print("hi")
                    return inner()
            """),
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post({}, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        outer_calls = {c.called_name for c in calls if c.caller_name == "outer"}
        inner_calls = {c.called_name for c in calls if c.caller_name == "inner"}
        # outer() does not directly call print — inner() does
        assert "print" not in outer_calls
        assert "print" in inner_calls
        # outer() does call inner()
        assert "inner" in outer_calls


# ---------------------------------------------------------------------------
# Mixed / combined changes
# ---------------------------------------------------------------------------


class TestDetectMixedChanges:
    def test_add_and_remove_in_single_file(self) -> None:
        """Replace one function with another."""
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"app.py": "def old(): pass\n"},
            {"app.py": "def new(): pass\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert len(added) == 1
        assert added[0].symbol_name == "new"
        assert len(removed) == 1
        assert removed[0].symbol_name == "old"

    def test_file_created_with_symbols(self) -> None:
        """Creating a file with functions produces FILE_CREATED + ADD_FUNCTION."""
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {},
            {"utils.py": "def util(): pass\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_CREATED in types
        assert ChangeType.ADD_FUNCTION in types

    def test_file_deleted_with_symbols(self) -> None:
        """Deleting a file with functions produces FILE_DELETED + REMOVE_FUNCTION."""
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {"old.py": "def helper(): pass\n"},
            {},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_DELETED in types
        assert ChangeType.REMOVE_FUNCTION in types


# ---------------------------------------------------------------------------
# Type-level changes (interface / enum / type alias) — v0.8.0
# ---------------------------------------------------------------------------


class TestDetectTypeLevelChanges:
    """Add/remove/replace of ``interface`` / ``enum`` / ``type`` alias
    declarations in ``.ts`` files.

    Uses ``RepositoryScanner`` on temp directories so that ``.ts`` files
    are discovered, parsed with the TS grammar, and recorded in
    ``ScanResult.ts_files``.
    """

    def _write_and_scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        """Write files to *tmp_path* and scan them."""
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scanner = RepositoryScanner(tmp_path)
        scan_result = scanner.scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def test_interface_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"models.ts": "interface User {\n    name: string;\n}\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        assert [c.symbol_name for c in added] == ["User"]

    def test_interface_removed(self, tmp_path: Path) -> None:
        source = {"models.ts": "interface User {\n    name: string;\n}\n"}
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_INTERFACE)
        assert [c.symbol_name for c in removed] == ["User"]

    def test_enum_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"models.ts": "enum Color {\n    Red,\n    Green,\n}\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_ENUM)
        assert [c.symbol_name for c in added] == ["Color"]

    def test_enum_removed(self, tmp_path: Path) -> None:
        source = {"models.ts": "enum Color {\n    Red,\n    Green,\n}\n"}
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_ENUM)
        assert [c.symbol_name for c in removed] == ["Color"]

    def test_type_alias_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"models.ts": 'type Status = "active" | "inactive";\n'},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_TYPE_ALIAS)
        assert [c.symbol_name for c in added] == ["Status"]

    def test_type_alias_removed(self, tmp_path: Path) -> None:
        source = {"models.ts": 'type Status = "active" | "inactive";\n'}
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_TYPE_ALIAS)
        assert [c.symbol_name for c in removed] == ["Status"]

    def test_type_replaced_in_single_file(self, tmp_path: Path) -> None:
        """Replacing an interface with an enum produces add + remove of
        the correct kinds (and never mislabels either as a function)."""
        pre_scan, pre_sym = self._write_and_scan(
            tmp_path,
            {"models.ts": "interface Mode {\n    dark: boolean;\n}\n"},
        )
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"models.ts": "enum Mode {\n    Dark,\n    Light,\n}\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_ENUM)
        removed = _changes_of_type(changes, ChangeType.REMOVE_INTERFACE)
        assert [c.symbol_name for c in added] == ["Mode"]
        assert [c.symbol_name for c in removed] == ["Mode"]
        # The old Phase-1 mislabeling window is closed: no bogus functions
        assert _changes_of_type(changes, ChangeType.ADD_FUNCTION) == []
        assert _changes_of_type(changes, ChangeType.REMOVE_FUNCTION) == []

    def test_multiple_type_level_changes(self, tmp_path: Path) -> None:
        """All three kinds added together surface as three change types."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "models.ts": (
                    "interface User {\n    name: string;\n}\n\n"
                    "enum Role {\n    Admin,\n    Member,\n}\n\n"
                    'type UserStatus = "active" | "deleted";\n'
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        types = {c.change_type for c in changes}
        assert ChangeType.ADD_INTERFACE in types
        assert ChangeType.ADD_ENUM in types
        assert ChangeType.ADD_TYPE_ALIAS in types
        assert ChangeType.FILE_CREATED in types

    def test_no_changes_when_identical(self, tmp_path: Path) -> None:
        source = {"models.ts": "interface User {\n    name: string;\n}\n"}
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan, post_sym = self._write_and_scan(tmp_path, source)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        assert changes == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDetectDeterminism:
    def test_deterministic_order(self) -> None:
        """Same inputs always produce same ordered output."""
        pre_src = {
            "a.py": "def foo(): pass\n",
            "b.py": "class Bar:\n    pass\n",
        }
        post_src = {
            "a.py": "def foo(): pass\ndef baz(): pass\n",
            "b.py": "class Bar:\n    pass\n",
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre_src, post_src)
        changes1 = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        changes2 = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        assert changes1 == changes2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestDetectEdgeCases:
    def test_symbol_and_file_together(self) -> None:
        """Adding a function and its file should detect both."""
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(
            {},
            {"new.py": "def f(): pass\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        # FILE_CREATED and ADD_FUNCTION should both appear
        assert any(c.change_type is ChangeType.FILE_CREATED for c in changes)
        assert any(c.change_type is ChangeType.ADD_FUNCTION for c in changes)

    def test_no_false_positives_from_unchanged_file(self) -> None:
        src = {"stable.py": "x = 1\n"}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(src, src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        assert changes == []


# ---------------------------------------------------------------------------
# JavaScript call detection + file changes
# ---------------------------------------------------------------------------


class TestDetectJsCallChanges:
    """JS call detection works through the same ChangeDetector pipeline.

    Uses ``RepositoryScanner`` on temp directories so that JS files are
    properly scanned and their paths recorded in ``ScanResult.js_files``.
    """

    def _write_and_scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        """Write JS files to *tmp_path* and scan them."""
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scanner = RepositoryScanner(tmp_path)
        scan_result = scanner.scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def test_js_simple_call_detected(self, tmp_path: Path) -> None:
        """A JS function calling ``print()`` surfaces as CALL_DETECTED."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"app.js": "function greet(name) { return print('Hello ' + name); }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        greet_calls = [c for c in calls if c.caller_name == "greet"]
        assert any(c.called_name == "print" for c in greet_calls)

    def test_js_multiple_calls_in_one_function(self, tmp_path: Path) -> None:
        """Multiple calls in one JS function are all captured."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "utils.js": (
                    "function process(items) {\n"
                    "  var result = sort(items);\n"
                    "  console.log(result);\n"
                    "  return len(result);\n"
                    "}\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        process_calls = {c.called_name for c in calls if c.caller_name == "process"}
        assert "sort" in process_calls
        assert "len" in process_calls

    def test_js_class_method_call_detected(self, tmp_path: Path) -> None:
        """Calls inside a class method are attributed to the method."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "shapes.js": (
                    "class Circle {\n  draw() {\n    return print('circle');\n  }\n}\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        draw_calls = {c.called_name for c in calls if c.caller_name == "draw"}
        assert "print" in draw_calls

    def test_js_arrow_function_calls_detected(self, tmp_path: Path) -> None:
        """Calls inside const foo = () => {} are attributed to foo."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "utils.js": (
                    "const greet = (name) => {\n  return print('Hello ' + name);\n};\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        greet_calls = [c for c in calls if c.caller_name == "greet"]
        assert any(c.called_name == "print" for c in greet_calls)

    def test_js_attribute_calls_are_captured(self, tmp_path: Path) -> None:
        """Method-style calls like logger.info() are captured since v16."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "app.js": ("function run() {\n  return logger.info('started');\n}\n"),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = {c.called_name for c in calls if c.caller_name == "run"}
        assert "info" in run_calls

    def test_js_calls_not_reported_when_present_in_both(self, tmp_path: Path) -> None:
        """No CALL_DETECTED when pre and post both have the same call."""
        source = {"app.js": "function greet() { return print('hi'); }\n"}
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan, post_sym = self._write_and_scan(tmp_path, source)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert calls == []

    def test_js_file_created_with_calls(self, tmp_path: Path) -> None:
        """Creating a JS file produces FILE_CREATED + CALL_DETECTED."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"app.js": "function greet() { return print('hi'); }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_CREATED in types
        assert ChangeType.CALL_DETECTED in types

    def test_js_file_deleted(self, tmp_path: Path) -> None:
        """Removing a JS file produces FILE_DELETED + REMOVE_FUNCTION."""
        source = {"old.js": "function helper() { return 42; }\n"}
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_DELETED in types
        assert ChangeType.REMOVE_FUNCTION in types


# ---------------------------------------------------------------------------
# Mixed Python + JavaScript integration
# ---------------------------------------------------------------------------


class TestDetectMixedPyJsChanges:
    """Python and JavaScript files in the same repo are handled together."""

    def _write_and_scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scanner = RepositoryScanner(tmp_path)
        scan_result = scanner.scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def test_both_languages_in_one_repo(self, tmp_path: Path) -> None:
        """A mixed repo detects symbols from both languages."""
        src = {
            "greeter.py": "def greet(): return 'hello'\n",
            "utils.js": "function helper() { return 42; }\n",
        }
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        post_scan, post_sym = self._write_and_scan(tmp_path, src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added_functions = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        added_names = {c.symbol_name for c in added_functions}
        assert "greet" in added_names
        assert "helper" in added_names
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_CREATED in types


# ---------------------------------------------------------------------------
# TSX (`.tsx`) change detection — v0.7.0
# ---------------------------------------------------------------------------


class TestDetectTsxChanges:
    """Add/remove/replace of React components in ``.tsx`` files.

    Uses ``RepositoryScanner`` on temp directories so that ``.tsx`` files
    are discovered, parsed with the TSX grammar, and recorded in
    ``ScanResult.ts_files`` (the TS family fold).
    """

    def _write_and_scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        """Write files to *tmp_path* and scan them."""
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scanner = RepositoryScanner(tmp_path)
        scan_result = scanner.scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def test_function_component_added(self, tmp_path: Path) -> None:
        """Adding a function component produces ADD_FUNCTION."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"App.tsx": "function Greeting(): JSX.Element { return <div>hi</div>; }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [c.symbol_name for c in added] == ["Greeting"]

    def test_function_component_removed(self, tmp_path: Path) -> None:
        """Removing a function component produces REMOVE_FUNCTION."""
        source = {
            "App.tsx": "function Greeting(): JSX.Element { return <div>hi</div>; }\n",
        }
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [c.symbol_name for c in removed] == ["Greeting"]

    def test_component_replaced_in_single_file(self, tmp_path: Path) -> None:
        """Replacing one component with another produces add + remove."""
        pre_scan, pre_sym = self._write_and_scan(
            tmp_path,
            {"App.tsx": "function Old(): JSX.Element { return <div/>; }\n"},
        )
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"App.tsx": "function New(): JSX.Element { return <div/>; }\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [c.symbol_name for c in added] == ["New"]
        assert [c.symbol_name for c in removed] == ["Old"]

    def test_class_component_added(self, tmp_path: Path) -> None:
        """Adding a class component produces ADD_CLASS + method adds."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "App.tsx": (
                    "class Panel extends React.Component {\n"
                    "    render(): JSX.Element { return <div/>; }\n"
                    "}\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        assert any(
            c.change_type is ChangeType.ADD_CLASS and c.symbol_name == "Panel"
            for c in changes
        )
        # Methods fold into ADD_FUNCTION with parent_class (same as .ts/.js)
        added_methods = [
            c
            for c in changes
            if c.change_type is ChangeType.ADD_FUNCTION and c.symbol_name == "render"
        ]
        assert len(added_methods) == 1
        assert added_methods[0].parent_class == "Panel"

    def test_tsx_call_detected(self, tmp_path: Path) -> None:
        """A component calling a helper surfaces as CALL_DETECTED."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "App.tsx": (
                    "function Greeting(): JSX.Element {\n"
                    "    const msg = formatGreeting('hi');\n"
                    "    return <div>{msg}</div>;\n"
                    "}\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        greeting_calls = {c.called_name for c in calls if c.caller_name == "Greeting"}
        assert "formatGreeting" in greeting_calls

    def test_jsx_element_usage_not_a_call(self, tmp_path: Path) -> None:
        """<Child /> usage is an element, not a call — no CALL_DETECTED."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "App.tsx": (
                    "function Parent(): JSX.Element {\n"
                    '    return <Child name="x" />;\n'
                    "}\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        parent_calls = {c.called_name for c in calls if c.caller_name == "Parent"}
        assert "Child" not in parent_calls

    def test_tsx_no_changes_when_identical(self, tmp_path: Path) -> None:
        """Same .tsx file in pre and post → no changes."""
        source = {"App.tsx": "function A(): JSX.Element { return <div/>; }\n"}
        pre_scan, pre_sym = self._write_and_scan(tmp_path, source)
        post_scan, post_sym = self._write_and_scan(tmp_path, source)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        assert changes == []

    def test_tsx_file_created_and_deleted(self, tmp_path: Path) -> None:
        """Creating then deleting a .tsx file surfaces the file events."""
        source = {"App.tsx": "function A(): JSX.Element { return <div/>; }\n"}
        # create
        post_scan, post_sym = self._write_and_scan(tmp_path, source)
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_CREATED in types
        assert ChangeType.ADD_FUNCTION in types
        # delete
        pre_scan, pre_sym = post_scan, post_sym
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        types = {c.change_type for c in changes}
        assert ChangeType.FILE_DELETED in types
        assert ChangeType.REMOVE_FUNCTION in types


# ------------------------------------------------------------------
# Rust / Go change detection — v0.9.0
# ------------------------------------------------------------------


class TestDetectRustChanges:
    """Add/remove/replace of Rust declarations via RepositoryScanner."""

    def _write_and_scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scanner = RepositoryScanner(tmp_path)
        scan_result = scanner.scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def test_rust_function_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"main.rs": "fn greet() -> i32 { 0 }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [c.symbol_name for c in added] == ["greet"]

    def test_rust_function_removed(self, tmp_path: Path) -> None:
        pre_scan, pre_sym = self._write_and_scan(
            tmp_path,
            {"main.rs": "fn greet() -> i32 { 0 }\n"},
        )
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [c.symbol_name for c in removed] == ["greet"]

    def test_rust_struct_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"models.rs": "struct User { name: String }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert [c.symbol_name for c in added] == ["User"]

    def test_rust_trait_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"traits.rs": "trait Drawable { fn draw(&self); }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        assert [c.symbol_name for c in added] == ["Drawable"]

    def test_rust_enum_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"enums.rs": "enum Color { Red, Green, Blue }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_ENUM)
        assert [c.symbol_name for c in added] == ["Color"]

    def test_rust_file_created(self, tmp_path: Path) -> None:
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"new.rs": "fn hello() {}\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert any(c.file_path == Path("new.rs") for c in created)

    def test_rust_file_deleted(self, tmp_path: Path) -> None:
        pre_scan, pre_sym = self._write_and_scan(
            tmp_path,
            {"old.rs": "fn old_fn() {}\n"},
        )
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        deleted = _changes_of_type(changes, ChangeType.FILE_DELETED)
        assert any(c.file_path == Path("old.rs") for c in deleted)

    def test_rust_call_detected(self, tmp_path: Path) -> None:
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"calls.rs": "fn helper() {}\nfn main() { helper(); }\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        main_calls = {c.called_name for c in calls if c.caller_name == "main"}
        assert "helper" in main_calls


class TestDetectGoChanges:
    """Add/remove/replace of Go declarations via RepositoryScanner."""

    def _write_and_scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scanner = RepositoryScanner(tmp_path)
        scan_result = scanner.scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def test_go_function_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"main.go": 'package main\n\nfunc greet() string { return "hi" }\n'},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [c.symbol_name for c in added] == ["greet"]

    def test_go_function_removed(self, tmp_path: Path) -> None:
        pre_scan, pre_sym = self._write_and_scan(
            tmp_path,
            {"main.go": 'package main\n\nfunc greet() string { return "hi" }\n'},
        )
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [c.symbol_name for c in removed] == ["greet"]

    def test_go_struct_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"models.go": "package main\n\ntype User struct { Name string }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert [c.symbol_name for c in added] == ["User"]

    def test_go_interface_added(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"iface.go": "package main\n\ntype Shape interface { Area() float64 }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        assert [c.symbol_name for c in added] == ["Shape"]

    def test_go_file_created(self, tmp_path: Path) -> None:
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {"new.go": "package main\n\nfunc hello() {}\n"},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        created = _changes_of_type(changes, ChangeType.FILE_CREATED)
        assert any(c.file_path == Path("new.go") for c in created)

    def test_go_file_deleted(self, tmp_path: Path) -> None:
        pre_scan, pre_sym = self._write_and_scan(
            tmp_path,
            {"old.go": "package main\n\nfunc old_fn() {}\n"},
        )
        post_scan = ScanResult()
        post_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        deleted = _changes_of_type(changes, ChangeType.FILE_DELETED)
        assert any(c.file_path == Path("old.go") for c in deleted)

    def test_go_call_detected(self, tmp_path: Path) -> None:
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "calls.go": (
                    "package main\n\n"
                    "func helper() int { return 42 }\n\n"
                    "func main() { helper() }\n"
                )
            },
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        main_calls = {c.called_name for c in calls if c.caller_name == "main"}
        assert "helper" in main_calls


class TestDetectJavaChanges:
    """Java detector matrix: symbols, shells, calls, disjount facts.

    Uses the real ``RepositoryScanner`` (not ``ast``) because Java is a
    tree-sitter language.  Every row of the Phase 2 matrix is pinned here.
    """

    def _scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scan_result = RepositoryScanner(tmp_path).scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def _changes(
        self,
        tmp_path: Path,
        pre: dict[str, str],
        post: dict[str, str],
    ) -> list[DetectedChange]:
        pre_scan, pre_sym = self._scan(tmp_path / "pre", pre)
        post_scan, post_sym = self._scan(tmp_path / "post", post)
        return detect_changes(pre_scan, post_scan, pre_sym, post_sym)

    # -- symbol add / remove -------------------------------------------

    def test_java_method_added(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int f = 1; }\n"},
            {"A.java": "class A { int f = 1; int m() { return 1; } }\n"},
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("m", "A")]
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_java_method_removed(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int f = 1; int m() { return 1; } }\n"},
            {"A.java": "class A { int f = 1; }\n"},
        )
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in removed] == [("m", "A")]
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_java_class_interface_enum_record_added(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {},
            {
                "Types.java": (
                    "class A {}\ninterface B {}\nenum C { X }\nrecord D(int x) {}\n"
                )
            },
        )
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_CLASS)
        ] == [
            "A",
            "D",
        ]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        ] == ["B"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_ENUM)
        ] == ["C"]

    def test_java_constructor_added_is_add_function_with_parent(
        self, tmp_path: Path
    ) -> None:
        """J5: a constructor is a METHOD named after its class, so adding
        one fires ADD_FUNCTION with parent_class=Foo — no collision with
        the existing CLASS Foo (identity kinds differ)."""
        changes = self._changes(
            tmp_path,
            {"Foo.java": "class Foo { }\n"},
            {"Foo.java": "class Foo { Foo(int x) { this.x = x; } int x; }\n"},
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("Foo", "Foo")]
        assert not _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert not _changes_of_type(changes, ChangeType.REMOVE_CLASS)

    def test_java_remove_and_recreate_is_remove_plus_add(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { void old() {} }\n"},
            {"A.java": "class A { void fresh() {} }\n"},
        )
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        ] == ["old"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        ] == ["fresh"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    # -- disjoint facts ------------------------------------------------

    def test_java_method_body_edit_is_changed_function_only(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int f = 1; int m() { return 1; } }\n"},
            {"A.java": "class A { int f = 1; int m() { return 2; } }\n"},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("m", "A")

    def test_java_class_field_edit_is_changed_class_only(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int f = 1; int m() { return 1; } }\n"},
            {"A.java": "class A { int f = 2; int m() { return 1; } }\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_java_class_base_edit_is_changed_class_only(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class Base {}\nclass A { int m() { return 1; } }\n"},
            {
                "A.java": (
                    "class Base {}\nclass A extends Base { int m() { return 1; } }\n"
                )
            },
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_java_class_annotation_edit_is_changed_class_only(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int m() { return 1; } }\n"},
            {"A.java": "@Deprecated\nclass A { int m() { return 1; } }\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]

    def test_java_annotation_edit_is_changed_function_on_the_method(
        self, tmp_path: Path
    ) -> None:
        """J4: annotations are children of the declaration, so a method
        annotation edit fires CHANGED_FUNCTION on the method, never
        CHANGED_CLASS on the class."""
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int f = 1; void m() {} }\n"},
            {"A.java": "class A { int f = 1; @Deprecated void m() {} }\n"},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("m", "A")

    def test_java_enum_constant_edit_is_changed_class(self, tmp_path: Path) -> None:
        """J11: enum bodies are class-shell content → CHANGED_CLASS."""
        changes = self._changes(
            tmp_path,
            {"Status.java": "enum Status { ACTIVE, INACTIVE; }\n"},
            {"Status.java": "enum Status { ACTIVE, INACTIVE, ARCHIVED; }\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "Status"

    def test_java_interface_default_method_edit_is_changed_function(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {
                "G.java": (
                    "interface G {\n"
                    "    String name();\n"
                    '    default String greet() { return "hi"; }\n'
                    "}\n"
                )
            },
            {
                "G.java": (
                    "interface G {\n"
                    "    String name();\n"
                    '    default String greet() { return "hello"; }\n'
                    "}\n"
                )
            },
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("greet", "G")

    def test_java_record_component_edit_is_changed_class(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"R.java": "record R(int x) {}\n"},
            {"R.java": "record R(long x) {}\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]

    # -- normalisation -------------------------------------------------

    def test_java_reformat_only_is_no_change(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int m() { return 1; } }\n"},
            {
                "A.java": (
                    "class A\n{\n    int m()\n    {\n        return 1;\n    }\n}\n"
                )
            },
        )
        assert changes == []

    def test_java_comment_only_is_no_change(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": "class A { int m() { return 1; } }\n"},
            {
                "A.java": (
                    "// leading comment\n"
                    "/** doc */\n"
                    "class A {\n"
                    "    /* inline */ int m() { return 1; } // trailing\n"
                    "}\n"
                )
            },
        )
        assert changes == []

    def test_java_text_block_swap_is_no_change(self, tmp_path: Path) -> None:
        """J7: ``"x"`` and a text block holding ``x`` normalise to the
        same hash — quote style is not content."""
        changes = self._changes(
            tmp_path,
            {"A.java": 'class A { String m() { return "x"; } }\n'},
            {"A.java": 'class A { String m() { return """x"""; } }\n'},
        )
        assert changes == []

    def test_java_string_content_edit_is_changed_function(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.java": 'class A { String m() { return "x"; } }\n'},
            {"A.java": 'class A { String m() { return "y"; } }\n'},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_FUNCTION]

    # -- files ---------------------------------------------------------

    def test_java_file_created_and_deleted(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"Old.java": "class Old {}\n"},
            {"New.java": "class New {}\n"},
        )
        assert [
            str(c.file_path) for c in _changes_of_type(changes, ChangeType.FILE_CREATED)
        ] == ["New.java"]
        assert [
            str(c.file_path) for c in _changes_of_type(changes, ChangeType.FILE_DELETED)
        ] == ["Old.java"]

    # -- calls ---------------------------------------------------------

    def test_java_calls_captured_and_excluded(self, tmp_path: Path) -> None:
        source = (
            "class Base { void helper() {} }\n"
            "class A extends Base {\n"
            "    void run() {\n"
            "        helper();\n"
            "        this.helper();\n"
            "        super.helper();\n"
            "        Base.helper();\n"
            "        A an = new A();\n"
            "        Runnable r = A::helper;\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(tmp_path, {}, {"A.java": source})
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        called = {c.called_name for c in calls if c.caller_name == "run"}
        assert called == {"helper"}
        assert all(c.parent_class == "A" for c in calls if c.caller_name == "run")
        # ``new A()`` and ``A::helper`` are not calls.
        assert "A" not in called

    def test_java_nested_class_caller_attribution(self, tmp_path: Path) -> None:
        source = (
            "class Outer {\n"
            "    void om() {}\n"
            "    static class Nested {\n"
            "        void nm() { helper(); }\n"
            "        void helper() {}\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(tmp_path, {}, {"Outer.java": source})
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert any(
            c.caller_name == "nm"
            and c.called_name == "helper"
            and c.parent_class == "Nested"
            for c in calls
        )


class TestDetectKotlinChanges:
    """Kotlin detector matrix: symbols, shells, calls, disjoint facts.

    Uses the real ``RepositoryScanner`` (not ``ast``) because Kotlin is a
    tree-sitter language.  Every row of the Phase 3 matrix is pinned here.
    """

    _CLASS = (
        "class A {\n    val f = 1\n\n    fun m(): Int {\n        return 1\n    }\n}\n"
    )

    def _scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scan_result = RepositoryScanner(tmp_path).scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def _changes(
        self,
        tmp_path: Path,
        pre: dict[str, str],
        post: dict[str, str],
    ) -> list[DetectedChange]:
        pre_scan, pre_sym = self._scan(tmp_path / "pre", pre)
        post_scan, post_sym = self._scan(tmp_path / "post", post)
        return detect_changes(pre_scan, post_scan, pre_sym, post_sym)

    # -- symbol add / remove -------------------------------------------

    def test_kotlin_method_added(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": self._CLASS},
            {
                "A.kt": (
                    "class A {\n"
                    "    val f = 1\n\n"
                    "    fun m(): Int {\n"
                    "        return 1\n"
                    "    }\n\n"
                    "    fun n(): Int {\n"
                    "        return 2\n"
                    "    }\n"
                    "}\n"
                )
            },
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("n", "A")]
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_kotlin_method_removed(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": self._CLASS},
            {"A.kt": "class A {\n    val f = 1\n}\n"},
        )
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in removed] == [("m", "A")]

    def test_kotlin_top_level_function_added_has_no_parent(
        self, tmp_path: Path
    ) -> None:
        """Kotlin has top-level functions (unlike Java), so the claim
        carries no parent_class."""
        changes = self._changes(
            tmp_path,
            {"app.kt": "val x = 1\n"},
            {"app.kt": ("val x = 1\n\nfun hello(): Int {\n    return 1\n}\n")},
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("hello", None)]

    def test_kotlin_type_added(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {},
            {"Types.kt": ("class A\ninterface B\nenum class C { X }\nobject D\n")},
        )
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_CLASS)
        ] == ["A", "D"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        ] == ["B"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_ENUM)
        ] == ["C"]

    def test_kotlin_annotation_class_added_is_add_interface(
        self, tmp_path: Path
    ) -> None:
        """Grammar defect D3: ``annotation class`` destroys the type
        declaration node; the scanner recovers it as an INTERFACE (the
        same kind Java's ``@interface`` maps to)."""
        changes = self._changes(
            tmp_path,
            {},
            {"Ann.kt": "annotation class Ann(val x: Int)\n"},
        )
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        ] == ["Ann"]
        assert not _changes_of_type(changes, ChangeType.ADD_CLASS)

    def test_kotlin_constructor_added_is_add_function_with_parent(
        self, tmp_path: Path
    ) -> None:
        """A secondary constructor is a METHOD named after its class, so
        adding one fires ADD_FUNCTION with parent_class=Foo — no
        collision with the existing CLASS Foo (identity kinds differ)."""
        changes = self._changes(
            tmp_path,
            {"Foo.kt": "class Foo\n"},
            {
                "Foo.kt": (
                    "class Foo {\n"
                    "    constructor(x: Int) {\n"
                    "        this.x = x\n"
                    "    }\n\n"
                    "    val x: Int\n"
                    "}\n"
                )
            },
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("Foo", "Foo")]
        assert not _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert not _changes_of_type(changes, ChangeType.REMOVE_CLASS)

    def test_kotlin_remove_and_recreate_is_remove_plus_add(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": "class A {\n    fun old() {}\n}\n"},
            {"A.kt": "class A {\n    fun fresh() {}\n}\n"},
        )
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        ] == ["old"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        ] == ["fresh"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_kotlin_soft_keyword_function_is_recovered(self, tmp_path: Path) -> None:
        """Grammar defect D5: a declaration named after a soft keyword
        (``dynamic``) parses with a MISSING identifier plus an unnamed
        token; the real name is recovered, so the change is still an
        honest ADD_FUNCTION."""
        changes = self._changes(
            tmp_path,
            {"app.kt": "val x = 1\n"},
            {"app.kt": ("val x = 1\n\nfun dynamic(): Int {\n    return 1\n}\n")},
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("dynamic", None)]

    # -- disjoint facts ------------------------------------------------

    def test_kotlin_method_body_edit_is_changed_function_only(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": self._CLASS},
            {"A.kt": self._CLASS.replace("return 1", "return 2")},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("m", "A")

    def test_kotlin_property_initializer_edit_is_changed_class_only(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": self._CLASS},
            {"A.kt": self._CLASS.replace("val f = 1", "val f = 2")},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_kotlin_supertype_edit_is_changed_class_only(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": "class Base\nclass A {}\n"},
            {"A.kt": "class Base\nclass A : Base() {}\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_kotlin_class_annotation_edit_is_changed_class_only(
        self, tmp_path: Path
    ) -> None:
        """The annotated class is the file's only declaration, so the
        annotation stays attached."""
        changes = self._changes(
            tmp_path,
            {"A.kt": "class A {}\n"},
            {"A.kt": "@Deprecated\nclass A {}\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_kotlin_detached_annotation_edit_is_changed_class_only(
        self, tmp_path: Path
    ) -> None:
        """Grammar defect D4: with any sibling after it the annotation
        detaches into an ``annotated_expression``, yet the annotation is
        canonicalised into the class hash — so the change still lands on
        the class, never on the sibling."""
        changes = self._changes(
            tmp_path,
            {"A.kt": "class A {}\nclass B {}\n"},
            {"A.kt": "@Deprecated\nclass A {}\nclass B {}\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_kotlin_stacked_annotation_class_survives_a_new_sibling(
        self, tmp_path: Path
    ) -> None:
        """Grammar defect D7: a second declaration dissolves the annotated
        class *silently* when two annotations are stacked.  The scanner
        recovers it, so appending the sibling is ADD_CLASS on the sibling
        and nothing else — no REMOVE_CLASS on B, no CHANGED_CLASS."""
        body = '@Deprecated\n@Suppress("x")\nclass B {\n    val x: Int = 1\n}\n'
        changes = self._changes(
            tmp_path,
            {"B.kt": body},
            {"B.kt": body + "class Z {}\n"},
        )
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.ADD_CLASS, "Z")
        ]

    def test_kotlin_stacked_annotation_class_body_edit_is_changed_class(
        self, tmp_path: Path
    ) -> None:
        """D7: the blinded re-parse keeps hashing the class, not the sibling
        the damaged chain used to absorb it into."""
        pre = (
            "@Deprecated\n"
            '@Suppress("x")\n'
            "class B {\n"
            "    val x: Int = 1\n"
            "}\n"
            "class Z {}\n"
        )
        changes = self._changes(
            tmp_path,
            {"B.kt": pre},
            {"B.kt": pre.replace("val x: Int = 1", "val x: Int = 2")},
        )
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.CHANGED_CLASS, "B")
        ]

    def test_kotlin_stacked_annotation_edit_is_changed_class_only(
        self, tmp_path: Path
    ) -> None:
        """D7: editing the *second* annotation of a stack is still an edit of
        the annotated class, never of the following declaration."""
        pre = "@Tag(1)\n@Tag(2)\nclass B {\n    val x: Int = 1\n}\nclass Z {}\n"
        changes = self._changes(
            tmp_path,
            {"B.kt": pre},
            {"B.kt": pre.replace("@Tag(2)", "@Tag(3)")},
        )
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.CHANGED_CLASS, "B")
        ]

    def test_kotlin_bodyless_stacked_annotation_keeps_the_absorbed_class(
        self, tmp_path: Path
    ) -> None:
        """D7: a bodyless destroyed class absorbs the next class into its
        infix chain.  With blinding, both are emitted — so editing the
        absorbed class is CHANGED_CLASS on it alone."""
        pre = "@A\n@B\nclass B\nclass C {\n    val x: Int = 1\n}\nclass Z {}\n"
        changes = self._changes(
            tmp_path,
            {"B.kt": pre},
            {"B.kt": pre.replace("val x: Int = 1", "val x: Int = 2")},
        )
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.CHANGED_CLASS, "C")
        ]

    def test_kotlin_stacked_annotation_class_declaration_survives_a_sibling(
        self, tmp_path: Path
    ) -> None:
        """D3 × D7: an annotated ``annotation class`` is destroyed even with
        *one* annotation; with two and a following sibling it is still
        recovered as the interface it declares."""
        body = "@Target(1)\n@Retention(2)\nannotation class Ann {\n    val v: Int\n}\n"
        changes = self._changes(
            tmp_path,
            {"Ann.kt": body},
            {"Ann.kt": body + "class Z {}\n"},
        )
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.ADD_CLASS, "Z")
        ]

    def test_kotlin_detached_argument_annotation_keeps_the_callers_calls(
        self, tmp_path: Path
    ) -> None:
        """D4/D7: ``@Ann(1)`` detaches into a sibling when a declaration
        follows.  The annotation still folds into the function's hash and
        the function keeps its calls — so this is CHANGED_FUNCTION on ``a``
        with no call churn."""
        pre = "fun a() {\n    work()\n}\nfun b() {}\n"
        post = '@Deprecated("x")\n' + pre
        changes = self._changes(tmp_path, {"A.kt": pre}, {"A.kt": post})
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.CHANGED_FUNCTION, "a")
        ]

    def test_kotlin_local_annotation_edit_is_changed_function(
        self, tmp_path: Path
    ) -> None:
        """D7: a run inside a declaration but before no symbol (a local
        annotation, a property annotation) belongs to the enclosing symbol —
        it folds into that function's hash, never into the class shell."""
        pre = (
            "class A {\n"
            "    fun m() {\n"
            '        @Suppress("UNUSED")\n'
            "        val x = 1\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"A.kt": pre},
            {"A.kt": pre.replace('@Suppress("UNUSED")', '@Suppress("UNCHECKED")')},
        )
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.CHANGED_FUNCTION, "m")
        ]

    def test_kotlin_method_annotation_edit_is_changed_function_on_the_method(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": "class A {\n    fun m() {}\n}\n"},
            {"A.kt": "class A {\n    @Deprecated\n    fun m() {}\n}\n"},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("m", "A")

    def test_kotlin_enum_constant_edit_is_changed_class(self, tmp_path: Path) -> None:
        """Enum entry lists are class-shell content → CHANGED_CLASS."""
        changes = self._changes(
            tmp_path,
            {"Status.kt": "enum class Status { ACTIVE, INACTIVE }\n"},
            {"Status.kt": "enum class Status { ACTIVE, INACTIVE, ARCHIVED }\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "Status"

    def test_kotlin_annotated_single_entry_enum_constant_edit_is_changed_class(
        self, tmp_path: Path
    ) -> None:
        """Grammar defect D2: an annotated single-entry enum without a
        trailing comma is mis-parsed as an infix expression; the scanner
        recovers the type, so a second entry is CHANGED_CLASS on E."""
        changes = self._changes(
            tmp_path,
            {"E.kt": "@Deprecated\nenum class E { A }\nclass Z\n"},
            {"E.kt": "@Deprecated\nenum class E { A, B }\nclass Z\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "E"

    def test_kotlin_companion_method_edit_is_changed_function_on_member(
        self, tmp_path: Path
    ) -> None:
        """A companion object has no symbol of its own — its methods
        belong to the outer class."""
        pre = (
            "class A {\n"
            "    companion object {\n"
            "        fun defaults(): Int {\n"
            "            return 1\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"A.kt": pre},
            {"A.kt": pre.replace("return 1", "return 2")},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("defaults", "A")

    def test_kotlin_interface_default_method_edit_is_changed_function(
        self, tmp_path: Path
    ) -> None:
        pre = (
            "interface G {\n"
            "    fun name(): String\n\n"
            "    fun greet(): String {\n"
            '        return "hi"\n'
            "    }\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"G.kt": pre},
            {"G.kt": pre.replace('"hi"', '"hello"')},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("greet", "G")

    # -- normalisation -------------------------------------------------

    def test_kotlin_reformat_only_is_no_change(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": self._CLASS},
            {
                "A.kt": (
                    "class A\n"
                    "{\n"
                    "    val f = 1\n\n"
                    "    fun m(): Int\n"
                    "    {\n"
                    "        return 1\n"
                    "    }\n"
                    "}\n"
                )
            },
        )
        assert changes == []

    def test_kotlin_comment_only_is_no_change(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.kt": self._CLASS},
            {"A.kt": "// leading\n/* doc */\n" + self._CLASS},
        )
        assert changes == []

    def test_kotlin_semicolon_only_is_no_change(self, tmp_path: Path) -> None:
        """Kotlin semicolons are optional syntax (the ASI exclusion)."""
        changes = self._changes(
            tmp_path,
            {"A.kt": "class A {\n    fun m() {\n        work()\n    }\n}\n"},
            {"A.kt": "class A {\n    fun m() {\n        work();\n    }\n}\n"},
        )
        assert changes == []

    def test_kotlin_raw_string_swap_is_changed_function(self, tmp_path: Path) -> None:
        """Kotlin diverges from Java's text blocks here: a raw string and
        a quoted string are semantically different, so swapping the
        delimiter is a real body change."""
        changes = self._changes(
            tmp_path,
            {
                "A.kt": (
                    'class A {\n    fun m(): String {\n        return "x"\n    }\n}\n'
                )
            },
            {
                "A.kt": (
                    "class A {\n"
                    "    fun m(): String {\n"
                    '        return """x"""\n'
                    "    }\n"
                    "}\n"
                )
            },
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_FUNCTION]

    # -- files ---------------------------------------------------------

    def test_kotlin_file_created_and_deleted(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"Old.kt": "class Old\n"},
            {"New.kt": "class New\n"},
        )
        assert [
            str(c.file_path) for c in _changes_of_type(changes, ChangeType.FILE_CREATED)
        ] == ["New.kt"]
        assert [
            str(c.file_path) for c in _changes_of_type(changes, ChangeType.FILE_DELETED)
        ] == ["Old.kt"]

    # -- calls ---------------------------------------------------------

    def test_kotlin_calls_captured_and_excluded(self, tmp_path: Path) -> None:
        """A constructor call and a trailing lambda call are real calls;
        ``make().add(5)`` contributes only ``make`` (a call receiver is
        not itself a call), and ``::add`` is a reference, not a call."""
        source = (
            "class Calc {\n"
            "    fun run() {\n"
            "        add(1, 2)\n"
            "        this.add(3, 4)\n"
            "        list.forEach { println(it) }\n"
            "        make().add(5)\n"
            "        1.plus(2)\n"
            "        Calc()\n"
            "        val r = ::add\n"
            "    }\n\n"
            "    fun add(a: Int, b: Int): Int {\n"
            "        return a + b\n"
            "    }\n"
            "}\n\n"
            "fun top() {\n"
            "    helper()\n"
            "}\n"
        )
        changes = self._changes(tmp_path, {}, {"A.kt": source})
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = [c for c in calls if c.caller_name == "run"]
        assert {c.called_name for c in run_calls} == {
            "add",
            "Calc",
            "forEach",
            "make",
            "plus",
            "println",
        }
        assert all(c.parent_class == "Calc" for c in run_calls)
        # The top-level function has no owning class.
        top_calls = [c for c in calls if c.caller_name == "top"]
        assert [(c.called_name, c.parent_class) for c in top_calls] == [
            ("helper", None)
        ]

    def test_kotlin_removed_call_detected(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"app.kt": "fun main() {\n    validate(1)\n}\n"},
            {"app.kt": "fun main() {\n    println(1)\n}\n"},
        )
        removed = _changes_of_type(changes, ChangeType.CALL_REMOVED)
        assert [(c.caller_name, c.called_name) for c in removed] == [
            ("main", "validate")
        ]


class TestDetectPhpChanges:
    """PHP detector matrix: symbols, shells, calls, disjoint facts.

    Uses the real ``RepositoryScanner`` (tree-sitter PHP).  Every row of
    the Phase 4 test matrix is pinned here — traits map to CLASS (PH8),
    declaration-only methods can never fire CHANGED_FUNCTION (PH9),
    anonymous classes produce no symbols (PH5), closures are indexed
    (PH6), attributes are part of their declaration's hash (PH4) and
    interpolation edits are real content (PH11).
    """

    _CLASS = (
        "<?php\n\n"
        "class A\n"
        "{\n"
        "    public $f = 1;\n\n"
        "    public function m(): int\n"
        "    {\n"
        "        return 1;\n"
        "    }\n"
        "}\n"
    )

    def _scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scan_result = RepositoryScanner(tmp_path).scan()
        sym_index = build_symbol_index(scan_result)
        return scan_result, sym_index

    def _changes(
        self,
        tmp_path: Path,
        pre: dict[str, str],
        post: dict[str, str],
    ) -> list[DetectedChange]:
        pre_scan, pre_sym = self._scan(tmp_path / "pre", pre)
        post_scan, post_sym = self._scan(tmp_path / "post", post)
        return detect_changes(pre_scan, post_scan, pre_sym, post_sym)

    # -- symbol add / remove -------------------------------------------

    def test_php_method_added(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": self._CLASS},
            {
                "A.php": (
                    "<?php\n\n"
                    "class A\n"
                    "{\n"
                    "    public $f = 1;\n\n"
                    "    public function m(): int\n"
                    "    {\n"
                    "        return 1;\n"
                    "    }\n\n"
                    "    public function n(): int\n"
                    "    {\n"
                    "        return 2;\n"
                    "    }\n"
                    "}\n"
                )
            },
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("n", "A")]
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_php_method_removed(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": self._CLASS},
            {"A.php": "<?php\n\nclass A\n{\n    public $f = 1;\n}\n"},
        )
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in removed] == [("m", "A")]

    def test_php_top_level_function_added_has_no_parent(self, tmp_path: Path) -> None:
        """PHP has top-level functions (like Kotlin, unlike Java), so the
        claim carries no parent_class."""
        changes = self._changes(
            tmp_path,
            {"app.php": "<?php\n\n$x = 1;\n"},
            {
                "app.php": (
                    "<?php\n\n$x = 1;\n\nfunction hello(): int\n{\n    return 1;\n}\n"
                )
            },
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [("hello", None)]

    def test_php_type_added(self, tmp_path: Path) -> None:
        """class/trait → ADD_CLASS, interface → ADD_INTERFACE, enum →
        ADD_ENUM: a trait maps to CLASS because the claim taxonomy has no
        trait type (PH8)."""
        changes = self._changes(
            tmp_path,
            {},
            {
                "Types.php": (
                    "<?php\n\n"
                    "class A {}\n"
                    "interface I {}\n"
                    "enum E { case One; }\n"
                    "trait T {}\n"
                )
            },
        )
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_CLASS)
        ] == ["A", "T"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_INTERFACE)
        ] == ["I"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_ENUM)
        ] == ["E"]

    def test_php_constructor_added_is_add_function_with_parent(
        self, tmp_path: Path
    ) -> None:
        """``__construct`` is an ordinary METHOD named after its class, so
        adding one fires ADD_FUNCTION with parent_class=Foo — no identity
        collision with the CLASS Foo (kinds differ, PH12)."""
        changes = self._changes(
            tmp_path,
            {"Foo.php": "<?php\n\nclass Foo {}\n"},
            {
                "Foo.php": (
                    "<?php\n\n"
                    "class Foo\n"
                    "{\n"
                    "    public function __construct(int $x)\n"
                    "    {\n"
                    "        $this->x = $x;\n"
                    "    }\n"
                    "}\n"
                )
            },
        )
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [(c.symbol_name, c.parent_class) for c in added] == [
            ("__construct", "Foo")
        ]
        assert not _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert not _changes_of_type(changes, ChangeType.REMOVE_CLASS)

    def test_php_remove_and_recreate_is_remove_plus_add(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": "<?php\n\nclass A {\n    public function old() {}\n}\n"},
            {"A.php": "<?php\n\nclass A {\n    public function fresh() {}\n}\n"},
        )
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        ] == ["old"]
        assert [
            c.symbol_name for c in _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        ] == ["fresh"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    # -- disjoint facts ------------------------------------------------

    def test_php_method_body_edit_is_changed_function_only(
        self, tmp_path: Path
    ) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": self._CLASS},
            {"A.php": self._CLASS.replace("return 1;", "return 2;")},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("m", "A")

    def test_php_property_edit_is_changed_class_only(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": self._CLASS},
            {"A.php": self._CLASS.replace("public $f = 1;", "public $f = 2;")},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_php_class_base_edit_is_changed_class_only(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": "<?php\n\nclass A extends Base {}\n"},
            {"A.php": "<?php\n\nclass A extends Other {}\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_php_constant_edit_is_changed_class_only(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": "<?php\n\nclass A {\n    public const LIMIT = 1;\n}\n"},
            {"A.php": "<?php\n\nclass A {\n    public const LIMIT = 2;\n}\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "A"

    def test_php_trait_body_edit_is_changed_class(self, tmp_path: Path) -> None:
        """PH8: a trait maps to CLASS, so its shell content fires
        CHANGED_CLASS on the trait."""
        pre = "<?php\n\ntrait Loggable\n{\n    public $tag = 'x';\n}\n"
        changes = self._changes(
            tmp_path,
            {"T.php": pre},
            {"T.php": pre.replace("'x'", "'y'")},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "Loggable"

    def test_php_trait_method_edit_is_changed_function_with_trait_parent(
        self, tmp_path: Path
    ) -> None:
        """The disjoint-facts rule holds for traits too: a method edit is
        CHANGED_FUNCTION with parent_class = the trait name."""
        pre = (
            "<?php\n\n"
            "trait Loggable\n"
            "{\n"
            "    public function log(): string\n"
            "    {\n"
            "        return 'a';\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"T.php": pre},
            {"T.php": pre.replace("'a'", "'b'")},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == (
            "log",
            "Loggable",
        )

    def test_php_enum_case_edit_is_changed_class(self, tmp_path: Path) -> None:
        """Enum cases are class-shell content (PH7) → CHANGED_CLASS."""
        changes = self._changes(
            tmp_path,
            {"E.php": "<?php\n\nenum E { case One; }\n"},
            {"E.php": "<?php\n\nenum E { case One; case Two; }\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_CLASS]
        assert changes[0].symbol_name == "E"

    def test_php_enum_method_edit_is_changed_function(self, tmp_path: Path) -> None:
        """Enum methods are METHOD symbols with parent_class = the enum."""
        pre = (
            "<?php\n\n"
            "enum E\n"
            "{\n"
            "    case One;\n\n"
            "    public function label(): string\n"
            "    {\n"
            "        return 'one';\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"E.php": pre},
            {"E.php": pre.replace("'one'", "'1'")},
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.CHANGED_FUNCTION
        assert (changes[0].symbol_name, changes[0].parent_class) == ("label", "E")

    def test_php_interface_method_declaration_edit_is_nothing(
        self, tmp_path: Path
    ) -> None:
        """PH9: an interface method is declaration-only, so it carries
        ``body_hash=None`` — a signature edit can never fire
        CHANGED_FUNCTION (and an INTERFACE has no hash at all)."""
        changes = self._changes(
            tmp_path,
            {"I.php": "<?php\n\ninterface I {\n    public function m();\n}\n"},
            {
                "I.php": (
                    "<?php\n\ninterface I\n{\n    public function m(string $name);\n}\n"
                )
            },
        )
        assert changes == []

    def test_php_abstract_method_declaration_edit_is_nothing(
        self, tmp_path: Path
    ) -> None:
        """PH9 applies to abstract methods as well — no body, no claim."""
        changes = self._changes(
            tmp_path,
            {
                "A.php": (
                    "<?php\n\n"
                    "abstract class A\n"
                    "{\n"
                    "    abstract public function m();\n"
                    "}\n"
                )
            },
            {
                "A.php": (
                    "<?php\n\n"
                    "abstract class A\n"
                    "{\n"
                    "    abstract public function m(): int;\n"
                    "}\n"
                )
            },
        )
        assert changes == []

    def test_php_anonymous_class_body_edit_is_nothing(self, tmp_path: Path) -> None:
        """PH5: ``new class { … }`` yields no symbols, so editing its body
        fires nothing (it is not part of any enclosing symbol's hash —
        the assignment below is at module scope)."""
        pre = (
            "<?php\n\n"
            "$worker = new class {\n"
            "    public function run(): int\n"
            "    {\n"
            "        return 1;\n"
            "    }\n"
            "};\n"
        )
        changes = self._changes(
            tmp_path,
            {"A.php": pre},
            {"A.php": pre.replace("return 1;", "return 2;")},
        )
        assert changes == []

    def test_php_closure_assignment_edit_is_changed_function(
        self, tmp_path: Path
    ) -> None:
        """PH6: ``$f = function () {}`` at module scope is indexed as a
        FUNCTION named without the ``$``, so its edit is CHANGED_FUNCTION
        with no parent."""
        pre = "<?php\n\n$double = function (int $n): int\n{\n    return $n * 2;\n};\n"
        changes = self._changes(
            tmp_path,
            {"C.php": pre},
            {"C.php": pre.replace("return $n * 2;", "return $n + $n;")},
        )
        assert [(c.change_type, c.symbol_name, c.parent_class) for c in changes] == [
            (ChangeType.CHANGED_FUNCTION, "double", None)
        ]

    def test_php_arrow_closure_assignment_edit_is_changed_function(
        self, tmp_path: Path
    ) -> None:
        """PH6 covers arrow functions too: ``$f = fn () => …`` is the same
        symbol."""
        pre = "<?php\n\n$triple = fn (int $n): int => $n * 3;\n"
        changes = self._changes(
            tmp_path,
            {"C.php": pre},
            {"C.php": pre.replace("$n * 3", "$n + $n + $n")},
        )
        assert [(c.change_type, c.symbol_name, c.parent_class) for c in changes] == [
            (ChangeType.CHANGED_FUNCTION, "triple", None)
        ]

    def test_php_closure_inside_a_method_is_changed_function(
        self, tmp_path: Path
    ) -> None:
        """A closure *inside* a method is not a symbol — its edit lands on
        the enclosing method (the local-declaration boundary every
        language shares)."""
        pre = (
            "<?php\n\n"
            "class A\n"
            "{\n"
            "    public function run(): void\n"
            "    {\n"
            "        $inner = function (): int {\n"
            "            return 1;\n"
            "        };\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"A.php": pre},
            {"A.php": pre.replace("return 1;", "return 2;")},
        )
        assert [(c.change_type, c.symbol_name, c.parent_class) for c in changes] == [
            (ChangeType.CHANGED_FUNCTION, "run", "A")
        ]

    def test_php_attribute_edit_is_changed_function(self, tmp_path: Path) -> None:
        """PH4: attributes are *children* of the declaration, so an
        attribute edit is part of that declaration's own hash."""
        pre = (
            "<?php\n\n"
            "#[Route('/home')]\n"
            "function home(): string\n"
            "{\n"
            "    return 'x';\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"A.php": pre},
            {"A.php": pre.replace("'/home'", "'/landing'")},
        )
        assert [(c.change_type, c.symbol_name, c.parent_class) for c in changes] == [
            (ChangeType.CHANGED_FUNCTION, "home", None)
        ]

    def test_php_class_attribute_edit_is_changed_class(self, tmp_path: Path) -> None:
        pre = "<?php\n\n#[Attribute]\nclass A {}\n"
        changes = self._changes(
            tmp_path,
            {"A.php": pre},
            {"A.php": "<?php\n\n#[Attribute(Attribute::TARGET_CLASS)]\nclass A {}\n"},
        )
        assert [(c.change_type, c.symbol_name) for c in changes] == [
            (ChangeType.CHANGED_CLASS, "A")
        ]

    def test_php_interpolation_edit_is_changed_function(self, tmp_path: Path) -> None:
        """PH11: interpolation content is real content (like Kotlin's
        string templates) — editing it is a body change."""
        pre = (
            "<?php\n\n"
            "class A\n"
            "{\n"
            "    public function m(string $name): string\n"
            "    {\n"
            '        return "Hello {$name}";\n'
            "    }\n"
            "}\n"
        )
        changes = self._changes(
            tmp_path,
            {"A.php": pre},
            {"A.php": pre.replace("{$name}", "{$name}!")},
        )
        assert [(c.change_type, c.symbol_name, c.parent_class) for c in changes] == [
            (ChangeType.CHANGED_FUNCTION, "m", "A")
        ]

    def test_php_quote_swap_is_no_change(self, tmp_path: Path) -> None:
        """PH11: ``'x'`` and ``\"x\"`` select different escape rules in
        PHP, but this swap changes neither value nor escapes — the leaf
        normaliser makes it invisible."""
        changes = self._changes(
            tmp_path,
            {"A.php": "<?php\n\nfunction f()\n{\n    return 'x';\n}\n"},
            {"A.php": '<?php\n\nfunction f()\n{\n    return "x";\n}\n'},
        )
        assert changes == []

    def test_php_escaped_quote_swap_stays_a_change(self, tmp_path: Path) -> None:
        """PH11's other half: ``'\\n'`` (backslash-n) and ``\"\\n\"``
        (newline) are different values, so swapping the quotes is a real
        change."""
        changes = self._changes(
            tmp_path,
            {"A.php": "<?php\n\nfunction f()\n{\n    return '\\n';\n}\n"},
            {"A.php": '<?php\n\nfunction f()\n{\n    return "\\n";\n}\n'},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_FUNCTION]

    def test_php_semicolon_is_hashed_as_content(self, tmp_path: Path) -> None:
        """PH10: PHP semicolons are required syntax, so they are *not* in
        the ASI exclusion set — an extra ``;`` (an empty statement, valid
        PHP) is a real body change."""
        changes = self._changes(
            tmp_path,
            {"A.php": "<?php\n\nfunction f(): int\n{\n    return 1;\n}\n"},
            {"A.php": "<?php\n\nfunction f(): int\n{\n    return 1;;\n}\n"},
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_FUNCTION]

    # -- normalisation -------------------------------------------------

    def test_php_reformat_only_is_no_change(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": self._CLASS},
            {
                "A.php": (
                    "<?php\n\n"
                    "class A {"
                    "public $f = 1;"
                    "public function m(): int {"
                    "return 1;"
                    "}}}\n"
                )
            },
        )
        assert changes == []

    def test_php_comment_only_is_no_change(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": self._CLASS},
            {
                "A.php": self._CLASS.replace(
                    "<?php\n",
                    "<?php\n// leading\n# hash style\n/* block */\n",
                )
            },
        )
        assert changes == []

    def test_php_heredoc_to_quoted_swap_stays_a_change(self, tmp_path: Path) -> None:
        """PH11: heredoc keeps its own type token (raw vs interpolated is
        semantically significant), so the swap is a change even when the
        value matches."""
        changes = self._changes(
            tmp_path,
            {
                "A.php": (
                    "<?php\n\nfunction f(): string\n{\n"
                    "    $x = <<<EOT\n    text\n    EOT;\n"
                    "    return $x;\n}\n"
                )
            },
            {
                "A.php": (
                    "<?php\n\nfunction f(): string\n{\n"
                    "    $x = 'text';\n"
                    "    return $x;\n}\n"
                )
            },
        )
        assert [c.change_type for c in changes] == [ChangeType.CHANGED_FUNCTION]

    # -- files ---------------------------------------------------------

    def test_php_file_created_and_deleted(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"Old.php": "<?php\n\nclass Old {}\n"},
            {"New.php": "<?php\n\nclass New {}\n"},
        )
        assert [
            str(c.file_path) for c in _changes_of_type(changes, ChangeType.FILE_CREATED)
        ] == ["New.php"]
        assert [
            str(c.file_path) for c in _changes_of_type(changes, ChangeType.FILE_DELETED)
        ] == ["Old.php"]

    # -- calls ---------------------------------------------------------

    def test_php_calls_captured_and_excluded(self, tmp_path: Path) -> None:
        """The full PH1/PH2/PH3/PH12 call matrix: plain, member, scoped,
        qualified, nullsafe and spread calls are captured; a call receiver,
        ``new``, a magic member and a first-class callable are not."""
        source = (
            "<?php\n\n"
            "class Client\n"
            "{\n"
            "    public function run(): void\n"
            "    {\n"
            "        helper();\n"
            "        $this->other();\n"
            "        self::stat();\n"
            "        static::stat();\n"
            "        parent::boot();\n"
            "        Lib\\util\\slugify('x');\n"
            "        \\App\\Tools\\join_all([1]);\n"
            "        $obj?->maybe();\n"
            "        $chain = build()->run();\n"
            "        new Thing();\n"
            "        strlen(...);\n"
            "        $obj->__construct();\n"
            "        $obj->real();\n"
            "    }\n"
            "}\n\n"
            "function top(): void\n"
            "{\n"
            "    helper_top();\n"
            "}\n"
        )
        changes = self._changes(tmp_path, {}, {"A.php": source})
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = [c for c in calls if c.caller_name == "run"]
        assert {c.called_name for c in run_calls} == {
            "helper",
            "other",
            "stat",
            "boot",
            "slugify",
            "join_all",
            "maybe",
            "build",
            "real",
        }
        assert all(c.parent_class == "Client" for c in run_calls)
        top_calls = [c for c in calls if c.caller_name == "top"]
        assert [(c.called_name, c.parent_class) for c in top_calls] == [
            ("helper_top", None)
        ]

    def test_php_property_hook_calls_are_attributed_to_the_property(
        self, tmp_path: Path
    ) -> None:
        """A property hook is a named body owned by its property (the
        Kotlin accessor rule): its calls carry caller_name = the property
        name and the enclosing class as parent."""
        source = (
            "<?php\n\n"
            "class Person\n"
            "{\n"
            "    public string $full_name {\n"
            "        get => $this->compose();\n"
            "        set (string $value) {\n"
            "            $this->assign($value);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        changes = self._changes(tmp_path, {}, {"A.php": source})
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert {(c.caller_name, c.called_name, c.parent_class) for c in calls} == {
            ("full_name", "compose", "Person"),
            ("full_name", "assign", "Person"),
        }

    def test_php_closure_calls_are_attributed_to_the_closure(
        self, tmp_path: Path
    ) -> None:
        """PH6 for callers: a named closure owns the calls in its body
        (parent_class is ``None`` — a closure lives in no class)."""
        source = "<?php\n\n$fn = function (): void\n{\n    work();\n};\n"
        changes = self._changes(tmp_path, {}, {"A.php": source})
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert [(c.caller_name, c.called_name, c.parent_class) for c in calls] == [
            ("fn", "work", None)
        ]

    def test_php_removed_call_detected(self, tmp_path: Path) -> None:
        changes = self._changes(
            tmp_path,
            {"A.php": "<?php\n\nfunction main()\n{\n    validate(1);\n}\n"},
            {"A.php": "<?php\n\nfunction main()\n{\n    render(1);\n}\n"},
        )
        removed = _changes_of_type(changes, ChangeType.CALL_REMOVED)
        assert [(c.caller_name, c.called_name) for c in removed] == [
            ("main", "validate")
        ]


class TestCallRemovedChanges:
    """P2-03: disappeared call sites surface as CALL_REMOVED."""

    def test_removed_call_detected(self) -> None:
        pre_src = {"app.py": ("def main():\n    validate('x')\n")}
        post_src = {"app.py": "def main():\n    pass\n"}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre_src, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)

        removed = _changes_of_type(changes, ChangeType.CALL_REMOVED)
        assert len(removed) == 1
        assert removed[0].caller_name == "main"
        assert removed[0].called_name == "validate"

    def test_unchanged_calls_not_reported(self) -> None:
        src = {"app.py": "def main():\n    validate('x')\n"}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(src, dict(src))
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        assert not _changes_of_type(changes, ChangeType.CALL_REMOVED)
        assert not _changes_of_type(changes, ChangeType.CALL_DETECTED)

    def test_moved_call_is_remove_plus_add(self) -> None:
        """A call relocated to another function is one removal + one
        addition — both directions reported."""
        pre_src = {"app.py": ("def a():\n    validate('x')\n\ndef b():\n    pass\n")}
        post_src = {"app.py": ("def a():\n    pass\n\ndef b():\n    validate('x')\n")}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre_src, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)

        removed = _changes_of_type(changes, ChangeType.CALL_REMOVED)
        added = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert any(
            c.caller_name == "a" and c.called_name == "validate" for c in removed
        )
        assert any(c.caller_name == "b" and c.called_name == "validate" for c in added)


class TestSymbolIdentityIgnoresLineShift:
    """P2-02: pure line-shifts must not produce phantom ADD/REMOVE."""

    def test_blank_line_insertion_is_invisible(self) -> None:
        pre = {"app.py": "def alpha():\n    return 1\n\ndef beta():\n    return 2\n"}
        post = {
            "app.py": ("\ndef alpha():\n    return 1\n\n\ndef beta():\n    return 2\n")
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre, post)
        symbol_changes = [
            c
            for c in detect_changes(pre_scan, post_scan, pre_sym, post_sym)
            if c.symbol_name is not None
        ]
        assert symbol_changes == []

    def test_renamed_function_still_detected(self) -> None:
        pre = {"app.py": "def old_name():\n    return 1\n"}
        post = {"app.py": "def new_name():\n    return 1\n"}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre, post)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)

        removed = [c for c in changes if c.change_type is ChangeType.REMOVE_FUNCTION]
        added = [c for c in changes if c.change_type is ChangeType.ADD_FUNCTION]
        assert {c.symbol_name for c in removed} == {"old_name"}
        assert {c.symbol_name for c in added} == {"new_name"}

    def test_cross_file_move_detected(self) -> None:
        pre = {"a.py": "def mover():\n    return 1\n", "b.py": ""}
        post = {"a.py": "", "b.py": "def mover():\n    return 1\n"}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre, post)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)

        removed = {
            c.file_path for c in changes if c.change_type is ChangeType.REMOVE_FUNCTION
        }
        added = {
            c.file_path for c in changes if c.change_type is ChangeType.ADD_FUNCTION
        }
        assert Path("a.py") in removed
        assert Path("b.py") in added

    def test_line_number_still_captured_for_display(self) -> None:
        pre = {"app.py": "def alpha():\n    return 1\n"}
        post = {"app.py": "# header comment\n\ndef alpha():\n    return 1\n"}
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre, post)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        # No phantom pair...
        assert not [c for c in changes if c.symbol_name == "alpha"]


# =========================================================================
# Phase 2 (v16): CHANGED_FUNCTION / CHANGED_CLASS body-hash pass
# =========================================================================


class TestChangedFunctionPython:
    """Body-hash change pass — Python sources."""

    @staticmethod
    def _changes(
        pre_src: dict[str, str],
        post_src: dict[str, str],
    ) -> list[DetectedChange]:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre_src, post_src)
        return detect_changes(pre_scan, post_scan, pre_sym, post_sym)

    def test_body_edit_emits_changed_function(self) -> None:
        pre = {"app.py": 'def greet():\n    return "hi"\n'}
        post = {"app.py": 'def greet():\n    return "hello world"\n'}
        changes = self._changes(pre, post)
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["greet"]
        assert changed[0].parent_class is None
        # A pure body edit is identity-exempt — no ADD/REMOVE pair
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)

    def test_comment_only_edit_no_changed(self) -> None:
        pre = {"app.py": "def greet():\n    return 1  # old comment\n"}
        post = {"app.py": "def greet():\n    return 1  # new comment\n"}
        changes = self._changes(pre, post)
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_whitespace_only_edit_no_changed(self) -> None:
        pre = {"app.py": "def greet():\n    return 1\n"}
        post = {"app.py": "def greet():\n\n    return 1\n"}
        changes = self._changes(pre, post)
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)

    def test_docstring_edit_emits_changed_function(self) -> None:
        """Docstrings are body content — CHANGED is intentional."""
        pre = {"app.py": 'def greet():\n    """old doc"""\n    return 1\n'}
        post = {"app.py": 'def greet():\n    """new doc"""\n    return 1\n'}
        changes = self._changes(pre, post)
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["greet"]

    def test_line_shift_within_body_no_changed(self) -> None:
        pre = {"app.py": "def greet():\n    a = 1\n    return a\n"}
        post = {"app.py": "def greet():\n    a = 1\n\n    return a\n"}
        changes = self._changes(pre, post)
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)

    def test_method_body_edit_changed_function_with_parent_class(self) -> None:
        pre = {
            "app.py": textwrap.dedent(
                """\
                class Circle:
                    def draw(self):
                        return "circle"
                """,
            )
        }
        post = {
            "app.py": textwrap.dedent(
                """\
                class Circle:
                    def draw(self):
                        return "square"
                """,
            )
        }
        changes = self._changes(pre, post)
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["draw"]
        assert changed[0].parent_class == "Circle"
        # Method bodies are excluded from the class shell — no CHANGED_CLASS
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_method_add_no_changed_class(self) -> None:
        pre = {
            "app.py": textwrap.dedent(
                """\
                class Circle:
                    def draw(self):
                        return 1
                """,
            )
        }
        post = {
            "app.py": textwrap.dedent(
                """\
                class Circle:
                    def draw(self):
                        return 1

                    def resize(self):
                        return 2
                """,
            )
        }
        changes = self._changes(pre, post)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [c.symbol_name for c in added] == ["resize"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_method_remove_no_changed_class(self) -> None:
        pre = {
            "app.py": textwrap.dedent(
                """\
                class Circle:
                    def draw(self):
                        return 1

                    def resize(self):
                        return 2
                """,
            )
        }
        post = {
            "app.py": textwrap.dedent(
                """\
                class Circle:
                    def draw(self):
                        return 1
                """,
            )
        }
        changes = self._changes(pre, post)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        assert [c.symbol_name for c in removed] == ["resize"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_class_decorator_edit_changed_class_only(self) -> None:
        pre = {"app.py": "@old_deco\nclass C:\n    x = 1\n"}
        post = {"app.py": "@new_deco\nclass C:\n    x = 1\n"}
        changes = self._changes(pre, post)
        changed = _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert [c.symbol_name for c in changed] == ["C"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_class_field_edit_changed_class_only(self) -> None:
        pre = {"app.py": "class C:\n    x = 1\n"}
        post = {"app.py": "class C:\n    x = 2\n"}
        changes = self._changes(pre, post)
        changed = _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert [c.symbol_name for c in changed] == ["C"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_identity_change_is_remove_add_not_changed(self) -> None:
        """A kind swap (function → class) is REMOVE + ADD, never CHANGED."""
        pre = {"app.py": "def greet():\n    return 1\n"}
        post = {"app.py": "class greet:\n    x = 1\n"}
        changes = self._changes(pre, post)
        removed = _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)
        added = _changes_of_type(changes, ChangeType.ADD_CLASS)
        assert [c.symbol_name for c in removed] == ["greet"]
        assert [c.symbol_name for c in added] == ["greet"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_both_hashes_none_defensive_no_changed(self) -> None:
        """None hashes (legacy data) never fabricate a change."""
        pre_sym = SymbolIndex(
            symbols={
                "greet": [
                    Symbol(
                        name="greet",
                        symbol_type=SymbolType.FUNCTION,
                        file_path=Path("app.py"),
                        line_number=1,
                        body_hash=None,
                    )
                ]
            }
        )
        post_sym = SymbolIndex(
            symbols={
                "greet": [
                    Symbol(
                        name="greet",
                        symbol_type=SymbolType.FUNCTION,
                        file_path=Path("app.py"),
                        line_number=1,
                        body_hash=None,
                    )
                ]
            }
        )
        changes = detect_changes(
            ScanResult(),
            ScanResult(),
            pre_sym,
            post_sym,
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_one_side_none_defensive_no_changed(self) -> None:
        """A None on either side aborts the comparison (never fabricate)."""
        pre_sym = SymbolIndex(
            symbols={
                "greet": [
                    Symbol(
                        name="greet",
                        symbol_type=SymbolType.FUNCTION,
                        file_path=Path("app.py"),
                        line_number=1,
                        body_hash=None,
                    )
                ]
            }
        )
        post_sym = SymbolIndex(
            symbols={
                "greet": [
                    Symbol(
                        name="greet",
                        symbol_type=SymbolType.FUNCTION,
                        file_path=Path("app.py"),
                        line_number=1,
                        body_hash="abc123",
                    )
                ]
            }
        )
        changes = detect_changes(
            ScanResult(),
            ScanResult(),
            pre_sym,
            post_sym,
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    # -- P2: async functions participate ----------------------------------

    def test_async_def_added_between_snapshots(self) -> None:
        pre: dict[str, str] = {}
        post = {"app.py": "async def fetch():\n    return 1\n"}
        changes = self._changes(pre, post)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [c.symbol_name for c in added] == ["fetch"]

    def test_async_method_body_edit_changed_function_with_parent_class(self) -> None:
        pre = {
            "app.py": textwrap.dedent(
                """\
                class Api:
                    async def get(self):
                        return 1
                """,
            )
        }
        post = {
            "app.py": textwrap.dedent(
                """\
                class Api:
                    async def get(self):
                        return 2
                """,
            )
        }
        changes = self._changes(pre, post)
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["get"]
        assert changed[0].parent_class == "Api"
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_sync_to_async_conversion_is_changed_function(self) -> None:
        """Symbol identity ignores node type — NOT REMOVE + ADD."""
        pre = {"app.py": "def fetch():\n    return 1\n"}
        post = {"app.py": "async def fetch():\n    return 1\n"}
        changes = self._changes(pre, post)
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["fetch"]
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)


class TestChangedCallCapture:
    """Extended call capture — member/attribute chains (Python)."""

    @staticmethod
    def _call_changes(post_src: dict[str, str]) -> list[DetectedChange]:
        pre_scan, post_scan, pre_sym, post_sym = _pre_post({}, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        return _changes_of_type(changes, ChangeType.CALL_DETECTED)

    def test_self_method_call_captured_with_parent_class(self) -> None:
        post_src = {
            "app.py": textwrap.dedent(
                """\
                class Widget:
                    def render(self):
                        self.draw()
                        return 1
                """,
            )
        }
        calls = self._call_changes(post_src)
        render_calls = [c for c in calls if c.caller_name == "render"]
        assert any(c.called_name == "draw" for c in render_calls)
        assert all(c.parent_class == "Widget" for c in render_calls)

    def test_member_chain_calls_captured_final_name(self) -> None:
        post_src = {
            "app.py": textwrap.dedent(
                """\
                def run():
                    obj.bar()
                    a.b.c()
                    return 1
                """,
            )
        }
        calls = self._call_changes(post_src)
        run_calls = {c.called_name for c in calls if c.caller_name == "run"}
        assert run_calls == {"bar", "c"}
        # Top-level caller carries no parent class
        assert all(c.parent_class is None for c in calls if c.caller_name == "run")

    def test_dunder_attribute_calls_excluded(self) -> None:
        """Dunder member calls are never captured; the inner ``super()``
        simple call stays (pre-existing simple-name rule)."""
        post_src = {
            "app.py": textwrap.dedent(
                """\
                def run():
                    obj.__x__()
                    super().__init__()
                    return 1
                """,
            )
        }
        calls = self._call_changes(post_src)
        run_calls = {c.called_name for c in calls if c.caller_name == "run"}
        assert "__x__" not in run_calls
        assert "__init__" not in run_calls

    def test_call_receiver_calls_excluded(self) -> None:
        """A member call whose receiver is a call is excluded; the inner
        ``f()`` / ``super()`` simple call stays (pre-existing rule)."""
        post_src = {
            "app.py": textwrap.dedent(
                """\
                def run():
                    f().bar()
                    super().foo()
                    return 1
                """,
            )
        }
        calls = self._call_changes(post_src)
        run_calls = {c.called_name for c in calls if c.caller_name == "run"}
        assert "bar" not in run_calls
        assert "foo" not in run_calls
        # Simple receiver calls themselves are captured (pre-existing)
        assert {"f", "super"} <= run_calls


class TestChangedCrossLanguage:
    """Body-hash CHANGED pass + member-call capture — JS/TS/Rust/Go."""

    def _write_and_scan(
        self,
        tmp_path: Path,
        files: dict[str, str],
    ) -> tuple[ScanResult, SymbolIndex]:
        for rel_path, source in files.items():
            abs_path = tmp_path / rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(source, encoding="utf-8")
        from nowreck.scanner.repository_scanner import RepositoryScanner

        scanner = RepositoryScanner(tmp_path)
        scan_result = scanner.scan()
        return scan_result, build_symbol_index(scan_result)

    def _changes_between(
        self,
        tmp_path: Path,
        rel_path: str,
        pre_src: str,
        post_src: str,
    ) -> list[DetectedChange]:
        pre_scan, pre_sym = self._write_and_scan(tmp_path, {rel_path: pre_src})
        post_scan, post_sym = self._write_and_scan(tmp_path, {rel_path: post_src})
        return detect_changes(pre_scan, post_scan, pre_sym, post_sym)

    def test_js_body_edit_emits_changed_function(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "app.js",
            "function greet() { return 'hi'; }\n",
            "function greet() { return 'hello'; }\n",
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["greet"]

    def test_js_reformat_only_edit_no_changed(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "app.js",
            "function greet() { return 'hi'; }\n",
            "function greet() {\n  return 'hi';\n}\n",
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)

    def test_js_quote_style_swap_no_changed(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "app.js",
            "function greet() { return 'hi'; }\n",
            'function greet() { return "hi"; }\n',
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_js_member_chains_captured(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "app.js": (
                    "function run() {\n"
                    "  obj.bar();\n"
                    "  a.b.c();\n"
                    "  this.x();\n"
                    "  return 1;\n"
                    "}\n"
                )
            },
        )
        changes = detect_changes(
            ScanResult(),
            post_scan,
            SymbolIndex(),
            post_sym,
        )
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = {c.called_name for c in calls if c.caller_name == "run"}
        assert run_calls == {"bar", "c", "x"}

    def test_js_method_caller_parent_class(self, tmp_path: Path) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "app.js": (
                    "class Greeter {\n"
                    "  greet() {\n"
                    "    this.format('hi');\n"
                    "    return 1;\n"
                    "  }\n"
                    "}\n"
                )
            },
        )
        changes = detect_changes(
            ScanResult(),
            post_scan,
            SymbolIndex(),
            post_sym,
        )
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        greet_calls = [c for c in calls if c.caller_name == "greet"]
        assert any(c.called_name == "format" for c in greet_calls)
        assert all(c.parent_class == "Greeter" for c in greet_calls)

    def test_ts_method_body_edit_changed_function_with_parent_class(
        self,
        tmp_path: Path,
    ) -> None:
        changes = self._changes_between(
            tmp_path,
            "app.ts",
            ("class C {\n  method() {\n    return 2;\n  }\n}\n"),
            ("class C {\n  method() {\n    return 3;\n  }\n}\n"),
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["method"]
        assert changed[0].parent_class == "C"
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_ts_class_field_edit_changed_class_only(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "app.ts",
            "class C {\n  field = 1;\n  method() {\n    return 2;\n  }\n}\n",
            "class C {\n  field = 2;\n  method() {\n    return 2;\n  }\n}\n",
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert [c.symbol_name for c in changed] == ["C"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_ts_reformat_only_edit_no_changed(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "app.ts",
            "function greet(): string { return 'hi'; }\n",
            "function greet(): string {\n  return 'hi';\n}\n",
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)

    def test_ts_quote_style_swap_no_changed(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "app.ts",
            "function greet(): string { return 'hi'; }\n",
            'function greet(): string { return "hi"; }\n',
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_rust_reformat_only_edit_no_changed(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "main.rs",
            'fn greet() -> &\'static str { "hi" }\n',
            'fn greet() -> &\'static str {\n    "hi"\n}\n',
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)

    def test_rust_raw_string_swap_is_a_change(self, tmp_path: Path) -> None:
        """Rust has one double-quoted string style; the raw-string
        variant is a *separate node type* and is deliberately semantically
        significant (`r"\n"` is literal backslash-n) — so this is a real
        change, not a quote-style swap (pins the hash docstring rule)."""
        changes = self._changes_between(
            tmp_path,
            "main.rs",
            'fn greet() -> &\'static str { "hi" }\n',
            'fn greet() -> &\'static str { r"hi" }\n',
        )
        assert [
            c.symbol_name
            for c in _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        ] == ["greet"]

    def test_go_reformat_only_edit_no_changed(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "main.go",
            'package main\n\nfunc greet() string { return "hi" }\n',
            'package main\n\nfunc greet() string {\n    return "hi"\n}\n',
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert not _changes_of_type(changes, ChangeType.REMOVE_FUNCTION)

    def test_go_raw_string_swap_is_a_change(self, tmp_path: Path) -> None:
        """Go's raw backtick literal is a separate node type from the
        interpreted form — value-equivalent here, but the hash treats
        raw vs interpreted as semantically significant (pins the hash
        docstring rule)."""
        changes = self._changes_between(
            tmp_path,
            "main.go",
            'package main\n\nfunc greet() string { return "hi" }\n',
            "package main\n\nfunc greet() string { return `hi` }\n",
        )
        assert [
            c.symbol_name
            for c in _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        ] == ["greet"]

    def test_ts_method_decorator_edit_changed_function_with_parent_class(
        self,
        tmp_path: Path,
    ) -> None:
        """TS decorators are siblings of the method — a decorator edit
        must fire CHANGED_FUNCTION (Python parity), never be invisible
        and never CHANGED_CLASS (disjoint-facts, Accepted Edges #1)."""
        changes = self._changes_between(
            tmp_path,
            "app.ts",
            ("class C {\n  @dec\n  method() {\n    return 1;\n  }\n}\n"),
            ("class C {\n  @dec2\n  method() {\n    return 1;\n  }\n}\n"),
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["method"]
        assert changed[0].parent_class == "C"
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_tsx_method_decorator_edit_changed_function_with_parent_class(
        self,
        tmp_path: Path,
    ) -> None:
        """TSX uses the same grammar shape — same guarantee."""
        changes = self._changes_between(
            tmp_path,
            "app.tsx",
            ("class C {\n  @dec\n  method() {\n    return 1;\n  }\n}\n"),
            ("class C {\n  @dec2\n  method() {\n    return 1;\n  }\n}\n"),
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["method"]
        assert changed[0].parent_class == "C"
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)

    def test_ts_class_level_decorator_edit_changed_class_only(
        self,
        tmp_path: Path,
    ) -> None:
        """A class-level decorator belongs to the shell → CHANGED_CLASS
        only (and no CHANGED_FUNCTION)."""
        changes = self._changes_between(
            tmp_path,
            "app.ts",
            ("@clsdec\nclass C {\n  method() {\n    return 1;\n  }\n}\n"),
            ("@clsdec2\nclass C {\n  method() {\n    return 1;\n  }\n}\n"),
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert [c.symbol_name for c in changed] == ["C"]
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_ts_interface_edit_never_changed(self, tmp_path: Path) -> None:
        """INTERFACE has no CHANGED claim type — its hash is never compared."""
        changes = self._changes_between(
            tmp_path,
            "app.ts",
            "interface User {\n    name: string;\n}\n",
            "interface User {\n    name: string;\n    age: number;\n}\n",
        )
        assert not _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert not _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)

    def test_rust_fn_body_edit_emits_changed_function(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "main.rs",
            'fn greet() -> &\'static str { "hi" }\n',
            'fn greet() -> &\'static str { "hello" }\n',
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["greet"]

    def test_rust_struct_field_edit_emits_changed_class(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "models.rs",
            "struct User { name: String }\n",
            "struct User { name: String, age: u8 }\n",
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert [c.symbol_name for c in changed] == ["User"]

    def test_rust_impl_method_calls_captured_with_parent_class(
        self,
        tmp_path: Path,
    ) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "calc.rs": (
                    "struct Calc;\n"
                    "impl Calc {\n"
                    "    fn run(&self) -> i32 {\n"
                    "        self.add(1, 2);\n"
                    "        0\n"
                    "    }\n"
                    "}\n"
                )
            },
        )
        changes = detect_changes(
            ScanResult(),
            post_scan,
            SymbolIndex(),
            post_sym,
        )
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = [c for c in calls if c.caller_name == "run"]
        assert any(c.called_name == "add" for c in run_calls)
        assert all(c.parent_class == "Calc" for c in run_calls)

    def test_go_fn_body_edit_emits_changed_function(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "main.go",
            'package main\n\nfunc greet() string { return "hi" }\n',
            'package main\n\nfunc greet() string { return "hello" }\n',
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_FUNCTION)
        assert [c.symbol_name for c in changed] == ["greet"]

    def test_go_struct_field_edit_emits_changed_class(self, tmp_path: Path) -> None:
        changes = self._changes_between(
            tmp_path,
            "models.go",
            "package main\n\ntype User struct {\n    Name string\n}\n",
            "package main\n\ntype User struct {\n    Name string\n    Age int\n}\n",
        )
        changed = _changes_of_type(changes, ChangeType.CHANGED_CLASS)
        assert [c.symbol_name for c in changed] == ["User"]

    def test_go_selector_calls_captured_with_parent_class(
        self,
        tmp_path: Path,
    ) -> None:
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "calc.go": (
                    "package main\n\n"
                    "type Calc struct{}\n\n"
                    "func (c *Calc) run() int {\n"
                    "    c.add(1, 2)\n"
                    '    fmt.Println("x")\n'
                    "    return 0\n"
                    "}\n"
                )
            },
        )
        changes = detect_changes(
            ScanResult(),
            post_scan,
            SymbolIndex(),
            post_sym,
        )
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = [c for c in calls if c.caller_name == "run"]
        assert {c.called_name for c in run_calls} == {"add", "Println"}
        assert all(c.parent_class == "Calc" for c in run_calls)


class TestCallExtractionPathResolution:
    """Path resolution for non-Python call re-parsing (v16 hardening).

    ``_extract_calls`` re-reads JS/TS/Rust/Go files from disk.  With a
    ``repo_root`` on the scan result the relative file paths resolve
    unambiguously; without one, the only safe inputs are absolute
    paths.  Relative paths with no root must be skipped with a warning
    — never guessed against the CWD, which could silently read a
    different file.
    """

    def test_absolute_paths_without_repo_root_still_extract_calls(
        self,
        tmp_path: Path,
    ) -> None:
        """Scanners run without a root store absolute paths; a hand-built
        scan with absolute keys must still produce call evidence."""
        from nowreck.scanner.javascript_scanner import scan_js_file

        abs_path = tmp_path / "app.js"
        abs_path.write_text(
            "function greet() { return print('hi'); }\n",
            encoding="utf-8",
        )
        symbols = scan_js_file(abs_path)  # repo_root=None → absolute paths
        post_scan = ScanResult(js_files={abs_path: symbols}, repo_root=None)
        post_sym = build_symbol_index(post_scan)

        changes = detect_changes(ScanResult(), post_scan, SymbolIndex(), post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        greet_calls = {c.called_name for c in calls if c.caller_name == "greet"}
        assert "print" in greet_calls

    def test_relative_paths_without_repo_root_skipped_with_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Relative paths with no repo_root are never guessed against the
        CWD — even when the file would resolve there — they are skipped
        with a warning instead of producing (possibly wrong) calls."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "app.js").write_text(
            "function greet() { return print('hi'); }\n",
            encoding="utf-8",
        )
        post_scan = ScanResult(js_files={Path("app.js"): []}, repo_root=None)
        post_sym = SymbolIndex()

        with caplog.at_level(
            logging.WARNING,
            logger="nowreck.detector.change_detector",
        ):
            changes = detect_changes(ScanResult(), post_scan, SymbolIndex(), post_sym)

        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert calls == []
        assert any(
            "no repo_root" in record.message and "app.js" in record.message
            for record in caplog.records
        )

    def test_relative_paths_resolve_against_repo_root_when_present(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With a repo_root, relative paths resolve against it even when
        the CWD is elsewhere (the standard pipeline case)."""
        from nowreck.scanner.javascript_scanner import scan_js_file

        monkeypatch.chdir(tmp_path.parent)  # CWD deliberately ≠ repo root
        abs_path = tmp_path / "app.js"
        abs_path.write_text(
            "function greet() { return print('hi'); }\n",
            encoding="utf-8",
        )
        symbols = scan_js_file(abs_path, repo_root=tmp_path)
        post_scan = ScanResult(
            js_files={Path("app.js"): symbols},
            repo_root=tmp_path,
        )
        post_sym = build_symbol_index(post_scan)

        changes = detect_changes(ScanResult(), post_scan, SymbolIndex(), post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        greet_calls = {c.called_name for c in calls if c.caller_name == "greet"}
        assert "print" in greet_calls
