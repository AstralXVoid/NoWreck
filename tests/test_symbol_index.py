from __future__ import annotations

import ast
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from nowreck.scanner.repository_scanner import ScanResult
from nowreck.scanner.symbol_index import (
    Symbol,
    SymbolIndex,
    SymbolIndexBuilder,
    SymbolType,
    build_symbol_index,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module(source: str) -> ast.Module:
    """Parse *source* into an ``ast.Module``."""
    return ast.parse(source)


def _scan_result(modules: dict[str, str]) -> ScanResult:
    """Build a ``ScanResult`` from a dict of relative-path → source code."""
    parsed: dict[Path, ast.Module] = {}
    for rel_path, source in modules.items():
        parsed[Path(rel_path)] = _make_module(source)
    return ScanResult(modules=parsed)


# ---------------------------------------------------------------------------
# SymbolType
# ---------------------------------------------------------------------------


class TestSymbolType:
    def test_values_are_distinct(self) -> None:
        """Each enum member has a unique value."""
        values = {m.value for m in SymbolType}
        assert len(values) == 3

    def test_has_all_required_types(self) -> None:
        assert SymbolType.FUNCTION
        assert SymbolType.CLASS
        assert SymbolType.METHOD


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------


class TestSymbol:
    def test_minimal_creation(self) -> None:
        s = Symbol(
            name="greet",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("main.py"),
            line_number=1,
        )
        assert s.name == "greet"
        assert s.symbol_type is SymbolType.FUNCTION
        assert s.parent_class is None

    def test_method_with_parent_class(self) -> None:
        s = Symbol(
            name="render",
            symbol_type=SymbolType.METHOD,
            file_path=Path("widget.py"),
            line_number=10,
            parent_class="Widget",
        )
        assert s.parent_class == "Widget"

    def test_frozen_cannot_be_mutated(self) -> None:
        s = Symbol(
            name="x",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=1,
        )
        with pytest.raises(AttributeError):
            s.name = "y"  # type: ignore[misc]

    def test_symbols_with_same_fields_are_equal(self) -> None:
        a = Symbol(
            name="f",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=1,
        )
        b = replace(a)
        assert a == b
        assert hash(a) == hash(b)

    def test_symbols_differing_by_type_are_not_equal(self) -> None:
        base = dict(name="X", file_path=Path("m.py"), line_number=1)
        fn = Symbol(symbol_type=SymbolType.FUNCTION, **base)  # type: ignore[arg-type]
        cls = Symbol(symbol_type=SymbolType.CLASS, **base)  # type: ignore[arg-type]
        assert fn != cls


# ---------------------------------------------------------------------------
# SymbolIndex
# ---------------------------------------------------------------------------


class TestSymbolIndex:
    def test_empty_index(self) -> None:
        idx = SymbolIndex()
        assert idx.symbols == {}
        assert idx.by_name("anything") == []
        assert idx.by_type(SymbolType.FUNCTION) == []
        assert idx.all_symbols == []

    def test_by_name_exact_match(self) -> None:
        s = Symbol(
            name="greet",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=1,
        )
        idx = SymbolIndex(symbols={"greet": [s]})
        assert idx.by_name("greet") == [s]

    def test_by_name_no_match_returns_empty_list(self) -> None:
        s = Symbol(
            name="greet",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=1,
        )
        idx = SymbolIndex(symbols={"greet": [s]})
        assert idx.by_name("nonexistent") == []

    def test_by_type_filters_correctly(self) -> None:
        fn = Symbol(
            name="f",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=1,
        )
        cls = Symbol(
            name="C",
            symbol_type=SymbolType.CLASS,
            file_path=Path("m.py"),
            line_number=5,
        )
        idx = SymbolIndex(symbols={"f": [fn], "C": [cls]})
        assert idx.by_type(SymbolType.FUNCTION) == [fn]
        assert idx.by_type(SymbolType.CLASS) == [cls]
        assert idx.by_type(SymbolType.METHOD) == []

    def test_functions_property(self) -> None:
        fn = Symbol(
            name="f",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=1,
        )
        idx = SymbolIndex(symbols={"f": [fn]})
        assert idx.functions == [fn]
        assert idx.classes == []
        assert idx.methods == []

    def test_classes_property(self) -> None:
        cls = Symbol(
            name="C",
            symbol_type=SymbolType.CLASS,
            file_path=Path("m.py"),
            line_number=1,
        )
        idx = SymbolIndex(symbols={"C": [cls]})
        assert idx.classes == [cls]
        assert idx.functions == []
        assert idx.methods == []

    def test_methods_property(self) -> None:
        m = Symbol(
            name="m",
            symbol_type=SymbolType.METHOD,
            file_path=Path("m.py"),
            line_number=2,
            parent_class="C",
        )
        idx = SymbolIndex(symbols={"m": [m]})
        assert idx.methods == [m]
        assert idx.functions == []
        assert idx.classes == []

    def test_all_symbols_deduplicates(self) -> None:
        s = Symbol(
            name="f",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=1,
        )
        idx = SymbolIndex(symbols={"f": [s, s]})
        assert len(idx.all_symbols) == 1  # set dedup via frozen dataclass

    def test_all_symbols_returns_sorted(self) -> None:
        s1 = Symbol(
            name="a",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("m.py"),
            line_number=2,
        )
        s2 = Symbol(
            name="b",
            symbol_type=SymbolType.CLASS,
            file_path=Path("m.py"),
            line_number=1,
        )
        idx = SymbolIndex(symbols={"a": [s1], "b": [s2]})
        # order=True sorts by declaration order: (name, type, file, line, parent)
        # Since "a" < "b", s1 (name="a") comes first
        assert idx.all_symbols == [s1, s2]


# ---------------------------------------------------------------------------
# SymbolIndexBuilder
# ---------------------------------------------------------------------------


class TestSymbolIndexBuilder:
    def test_build_empty_scan_result(self) -> None:
        result = ScanResult()
        idx = SymbolIndexBuilder.build(result)
        assert idx.symbols == {}

    def test_build_no_python_files(self) -> None:
        result = ScanResult(modules={})
        idx = build_symbol_index(result)
        assert idx.symbols == {}

    def test_build_top_level_function(self) -> None:
        result = _scan_result({"app.py": "def greet(name: str) -> str: ...\n"})
        idx = build_symbol_index(result)
        symbols = idx.by_name("greet")
        assert len(symbols) == 1
        s = symbols[0]
        assert s.name == "greet"
        assert s.symbol_type is SymbolType.FUNCTION
        assert s.file_path == Path("app.py")
        assert s.line_number == 1
        assert s.parent_class is None

    def test_build_top_level_class(self) -> None:
        result = _scan_result({"models.py": "class User:\n    pass\n"})
        idx = build_symbol_index(result)
        symbols = idx.by_name("User")
        assert len(symbols) == 1
        s = symbols[0]
        assert s.name == "User"
        assert s.symbol_type is SymbolType.CLASS
        assert s.file_path == Path("models.py")
        assert s.line_number == 1
        assert s.parent_class is None

    def test_build_class_with_methods(self) -> None:
        result = _scan_result(
            {
                "widget.py": textwrap.dedent("""\
                    class Widget:
                        def render(self) -> str:
                            return "hello"

                        def resize(self, factor: float) -> None:
                            ...
                    """)
            }
        )
        idx = build_symbol_index(result)

        # Class
        assert len(idx.by_name("Widget")) == 1
        assert idx.by_name("Widget")[0].symbol_type is SymbolType.CLASS

        # Methods
        render = idx.by_name("render")
        assert len(render) == 1
        assert render[0].symbol_type is SymbolType.METHOD
        assert render[0].parent_class == "Widget"
        assert render[0].line_number == 2

        resize = idx.by_name("resize")
        assert len(resize) == 1
        assert resize[0].symbol_type is SymbolType.METHOD
        assert resize[0].parent_class == "Widget"

    def test_build_same_method_name_in_different_classes(self) -> None:
        """Two classes with a same-named method should produce two symbols."""
        result = _scan_result(
            {
                "shapes.py": textwrap.dedent("""\
                    class Circle:
                        def draw(self) -> None: ...

                    class Square:
                        def draw(self) -> None: ...
                    """)
            }
        )
        idx = build_symbol_index(result)
        draws = idx.by_name("draw")
        assert len(draws) == 2
        parents = {s.parent_class for s in draws}
        assert parents == {"Circle", "Square"}

    def test_build_function_and_class_with_same_name(self) -> None:
        """Name collision between different symbol types is preserved."""
        result = _scan_result(
            {
                "utils.py": textwrap.dedent("""\
                    def Config() -> dict: ...

                    class Config:
                        ...
                    """)
            }
        )
        idx = build_symbol_index(result)
        symbols = idx.by_name("Config")
        assert len(symbols) == 2
        types = {s.symbol_type for s in symbols}
        assert types == {SymbolType.FUNCTION, SymbolType.CLASS}

    def test_build_multiple_files(self) -> None:
        result = _scan_result(
            {
                "a.py": "def foo(): pass\n",
                "b.py": "def bar(): pass\n",
            }
        )
        idx = build_symbol_index(result)
        assert len(idx.by_name("foo")) == 1
        assert len(idx.by_name("bar")) == 1
        assert idx.by_name("foo")[0].file_path == Path("a.py")
        assert idx.by_name("bar")[0].file_path == Path("b.py")

    def test_build_nested_functions_are_ignored(self) -> None:
        """Nested functions (functions inside functions) are out of scope."""
        result = _scan_result(
            {
                "utils.py": textwrap.dedent("""\
                    def outer():
                        def inner():
                            pass
                        return inner
                    """)
            }
        )
        idx = build_symbol_index(result)
        assert len(idx.by_name("outer")) == 1
        assert len(idx.by_name("inner")) == 0

    def test_build_async_functions_are_not_indexed(self) -> None:
        """Async functions use AsyncFunctionDef nodes, not FunctionDef.
        Async support is out of scope for the MVP symbol index.
        """
        result = _scan_result({"async_utils.py": "async def fetch_data(): ...\n"})
        idx = build_symbol_index(result)
        assert len(idx.by_name("fetch_data")) == 0

    def test_build_non_function_class_members_ignored(self) -> None:
        """Class body attributes that aren't FunctionDef are skipped."""
        result = _scan_result(
            {
                "settings.py": textwrap.dedent("""\
                    class Settings:
                        timeout: int = 30
                        def activate(self) -> None: ...
                    """)
            }
        )
        idx = build_symbol_index(result)
        assert len(idx.by_name("Settings")) == 1
        assert len(idx.by_name("activate")) == 1
        assert idx.by_name("Settings")[0].symbol_type is SymbolType.CLASS
        assert idx.by_name("activate")[0].symbol_type is SymbolType.METHOD

    def test_build_failed_files_are_ignored(self) -> None:
        """Symbol index should skip files that failed to parse."""
        tree = _make_module("def working(): pass\n")
        result = ScanResult(
            modules={Path("good.py"): tree},
            failed_files={Path("bad.py"): "SyntaxError"},
        )
        idx = build_symbol_index(result)
        assert len(idx.by_name("working")) == 1
        assert len(idx.by_name("nonexistent")) == 0

    def test_build_is_deterministic(self) -> None:
        """Scanning the same repo twice must produce identical results."""
        source = {"a.py": "def foo(): pass\ndef bar(): pass\n"}
        result = _scan_result(source)
        idx1 = build_symbol_index(result)
        idx2 = build_symbol_index(result)
        assert idx1.symbols == idx2.symbols
        assert idx1.all_symbols == idx2.all_symbols

    def test_build_returns_types_properties(self) -> None:
        result = _scan_result(
            {
                "app.py": textwrap.dedent("""\
                    def helper(): ...

                    class Processor:
                        def run(self): ...
                    """)
            }
        )
        idx = build_symbol_index(result)
        assert len(idx.functions) == 1
        assert idx.functions[0].name == "helper"
        assert len(idx.classes) == 1
        assert idx.classes[0].name == "Processor"
        assert len(idx.methods) == 1
        assert idx.methods[0].name == "run"

    def test_build_decorated_functions_are_indexed(self) -> None:
        """Decorators don't affect the FunctionDef node structure."""
        result = _scan_result({"routes.py": "@app.route('/')\ndef index(): ...\n"})
        idx = build_symbol_index(result)
        assert len(idx.by_name("index")) == 1
        assert idx.by_name("index")[0].symbol_type is SymbolType.FUNCTION
