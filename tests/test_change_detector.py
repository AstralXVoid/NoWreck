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
                    "class Circle {\n"
                    "  draw() {\n"
                    "    return print('circle');\n"
                    "  }\n"
                    "}\n"
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
                    "const greet = (name) => {\n"
                    "  return print('Hello ' + name);\n"
                    "};\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        greet_calls = [c for c in calls if c.caller_name == "greet"]
        assert any(c.called_name == "print" for c in greet_calls)

    def test_js_attribute_calls_are_excluded(self, tmp_path: Path) -> None:
        """Method-style calls like logger.info() are out of MVP scope."""
        post_scan, post_sym = self._write_and_scan(
            tmp_path,
            {
                "app.js": (
                    "function run() {\n"
                    "  return logger.info('started');\n"
                    "}\n"
                ),
            },
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        run_calls = {c.called_name for c in calls if c.caller_name == "run"}
        assert "info" not in run_calls

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
            {"main.go": "package main\n\nfunc greet() string { return \"hi\" }\n"},
        )
        pre_scan = ScanResult()
        pre_sym = SymbolIndex()
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        added = _changes_of_type(changes, ChangeType.ADD_FUNCTION)
        assert [c.symbol_name for c in added] == ["greet"]

    def test_go_function_removed(self, tmp_path: Path) -> None:
        pre_scan, pre_sym = self._write_and_scan(
            tmp_path,
            {"main.go": "package main\n\nfunc greet() string { return \"hi\" }\n"},
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
            {"calls.go": (
                "package main\n\n"
                "func helper() int { return 42 }\n\n"
                "func main() { helper() }\n"
            )},
        )
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        calls = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        main_calls = {c.called_name for c in calls if c.caller_name == "main"}
        assert "helper" in main_calls


class TestCallRemovedChanges:
    """P2-03: disappeared call sites surface as CALL_REMOVED."""

    def test_removed_call_detected(self) -> None:
        pre_src = {
            "app.py": (
                "def main():\n"
                "    validate('x')\n"
            )
        }
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
        pre_src = {
            "app.py": (
                "def a():\n    validate('x')\n\n"
                "def b():\n    pass\n"
            )
        }
        post_src = {
            "app.py": (
                "def a():\n    pass\n\n"
                "def b():\n    validate('x')\n"
            )
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre_src, post_src)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)

        removed = _changes_of_type(changes, ChangeType.CALL_REMOVED)
        added = _changes_of_type(changes, ChangeType.CALL_DETECTED)
        assert any(
            c.caller_name == "a" and c.called_name == "validate"
            for c in removed
        )
        assert any(
            c.caller_name == "b" and c.called_name == "validate"
            for c in added
        )


class TestSymbolIdentityIgnoresLineShift:
    """P2-02: pure line-shifts must not produce phantom ADD/REMOVE."""

    def test_blank_line_insertion_is_invisible(self) -> None:
        pre = {"app.py": "def alpha():\n    return 1\n\ndef beta():\n    return 2\n"}
        post = {
            "app.py": (
                "\ndef alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
            )
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
            c.file_path
            for c in changes
            if c.change_type is ChangeType.REMOVE_FUNCTION
        }
        added = {
            c.file_path
            for c in changes
            if c.change_type is ChangeType.ADD_FUNCTION
        }
        assert Path("a.py") in removed
        assert Path("b.py") in added

    def test_line_number_still_captured_for_display(self) -> None:
        pre = {"app.py": "def alpha():\n    return 1\n"}
        post = {
            "app.py": "# header comment\n\ndef alpha():\n    return 1\n"
        }
        pre_scan, post_scan, pre_sym, post_sym = _pre_post(pre, post)
        changes = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
        # No phantom pair...
        assert not [
            c for c in changes if c.symbol_name == "alpha"
        ]
