from __future__ import annotations

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
    SymbolIndex,
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
        assert ChangeType.FILE_CREATED
        assert ChangeType.FILE_DELETED
        assert ChangeType.CALL_DETECTED

    def test_values_are_distinct(self) -> None:
        values = {m.value for m in ChangeType}
        assert len(values) == 7


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

    def test_attribute_calls_are_excluded(self) -> None:
        """Method-style calls like obj.method() are out of MVP scope."""
        post_src = {
            "app.py": textwrap.dedent("""\
                def run():
                    return logger.info("started")
            """),
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post({}, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = {c.called_name for c in calls if c.caller_name == "run"}
        # "info" is an attribute call (logger.info()), not a simple name
        assert "info" not in run_calls

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
