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
    build_symbol_index_from_symbols,
)

# A few stock Symbol objects used for JS-style test data
_FN_SYM = Symbol(
    name="greet",
    symbol_type=SymbolType.FUNCTION,
    file_path=Path("app.js"),
    line_number=1,
)
_CLS_SYM = Symbol(
    name="Widget",
    symbol_type=SymbolType.CLASS,
    file_path=Path("app.js"),
    line_number=5,
)
_METHOD_SYM = Symbol(
    name="render",
    symbol_type=SymbolType.METHOD,
    file_path=Path("app.js"),
    line_number=6,
    parent_class="Widget",
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

    # ------------------------------------------------------------------
    # Mixed Python + JS build
    # ------------------------------------------------------------------

    def test_build_with_js_files(self) -> None:
        """build() processes js_files alongside modules."""
        py_tree = _make_module("def py_func(): pass\n")
        result = ScanResult(
            modules={Path("m.py"): py_tree},
            js_files={
                Path("app.js"): [_FN_SYM],
            },
        )
        idx = build_symbol_index(result)

        # Both the Python function and JS function should be indexed
        py_funcs = idx.by_name("py_func")
        assert len(py_funcs) == 1
        assert py_funcs[0].symbol_type is SymbolType.FUNCTION
        assert py_funcs[0].file_path == Path("m.py")

        js_funcs = idx.by_name("greet")
        assert len(js_funcs) == 1
        assert js_funcs[0].file_path == Path("app.js")

    def test_build_js_only(self) -> None:
        """build() with only JS files (no Python modules)."""
        result = ScanResult(
            js_files={
                Path("app.js"): [_FN_SYM, _CLS_SYM, _METHOD_SYM],
            },
        )
        idx = build_symbol_index(result)

        assert len(idx.functions) == 1
        assert idx.functions[0].name == "greet"
        assert len(idx.classes) == 1
        assert idx.classes[0].name == "Widget"
        assert len(idx.methods) == 1
        assert idx.methods[0].name == "render"
        assert idx.methods[0].parent_class == "Widget"

    def test_build_mixed_same_name_across_languages(self) -> None:
        """Same-named symbols in Python and JS files are merged."""
        py_tree = _make_module("def util(): pass\n")
        js_sym = Symbol(
            name="util",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("util.js"),
            line_number=1,
        )
        result = ScanResult(
            modules={Path("util.py"): py_tree},
            js_files={Path("util.js"): [js_sym]},
        )
        idx = build_symbol_index(result)

        symbols = idx.by_name("util")
        assert len(symbols) == 2
        files = {s.file_path for s in symbols}
        assert files == {Path("util.py"), Path("util.js")}

    def test_build_mixed_all_symbols_merged(self) -> None:
        """all_symbols properly merges Python and JS symbols."""
        py_tree = _make_module(
            "def py_func(): pass\nclass PyClass:\n    def method(self): pass\n",
        )
        js_symbols = [
            Symbol(
                name="js_func",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("code.js"),
                line_number=1,
            ),
            Symbol(
                name="JsClass",
                symbol_type=SymbolType.CLASS,
                file_path=Path("code.js"),
                line_number=5,
            ),
            Symbol(
                name="doStuff",
                symbol_type=SymbolType.METHOD,
                file_path=Path("code.js"),
                line_number=6,
                parent_class="JsClass",
            ),
        ]
        result = ScanResult(
            modules={Path("app.py"): py_tree},
            js_files={Path("code.js"): js_symbols},
        )
        idx = build_symbol_index(result)

        # Total symbol count: Python gives 3 (py_func, PyClass, method),
        # JS gives 3 (js_func, JsClass, doStuff) = 6 total
        assert len(idx.all_symbols) == 6

        # Type-specific queries work
        assert len(idx.functions) == 2  # py_func + js_func
        assert len(idx.classes) == 2  # PyClass + JsClass
        assert len(idx.methods) == 2  # method + doStuff

    def test_build_mixed_deterministic(self) -> None:
        """Mixed Python+JS build produces deterministic results."""
        py_tree = _make_module("def a(): pass\ndef b(): pass\n")
        js_symbols = [
            Symbol(
                name="c",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("c.js"),
                line_number=1,
            ),
        ]
        result = ScanResult(
            modules={Path("a.py"): py_tree},
            js_files={Path("c.js"): js_symbols},
        )
        idx1 = build_symbol_index(result)
        idx2 = build_symbol_index(result)
        assert idx1.symbols == idx2.symbols
        assert idx1.all_symbols == idx2.all_symbols


# ---------------------------------------------------------------------------
# SymbolIndexBuilder.from_symbols (JS pathway)
# ---------------------------------------------------------------------------


class TestSymbolIndexBuilderFromSymbols:
    """Tests for building a SymbolIndex from a flat list of Symbol objects.

    This is the entry point used by the JavaScript scanner (``scan_js_file``)
    which produces ``Symbol`` objects directly, without an intermediate
    ``ScanResult`` or AST walk.
    """

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_list_produces_empty_index(self) -> None:
        idx = build_symbol_index_from_symbols([])
        assert idx.symbols == {}
        assert idx.by_name("anything") == []
        assert idx.all_symbols == []

    # ------------------------------------------------------------------
    # Single symbols
    # ------------------------------------------------------------------

    def test_single_function(self) -> None:
        sym = Symbol(
            name="greet",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("app.js"),
            line_number=1,
        )
        idx = build_symbol_index_from_symbols([sym])
        assert len(idx.by_name("greet")) == 1
        assert idx.by_name("greet")[0] is sym
        assert len(idx.functions) == 1
        assert len(idx.classes) == 0
        assert len(idx.methods) == 0

    def test_single_class(self) -> None:
        sym = Symbol(
            name="MyClass",
            symbol_type=SymbolType.CLASS,
            file_path=Path("models.js"),
            line_number=5,
        )
        idx = build_symbol_index_from_symbols([sym])
        assert len(idx.by_name("MyClass")) == 1
        assert idx.by_name("MyClass")[0].symbol_type is SymbolType.CLASS
        assert len(idx.classes) == 1

    def test_single_method_with_parent_class(self) -> None:
        sym = Symbol(
            name="render",
            symbol_type=SymbolType.METHOD,
            file_path=Path("widget.js"),
            line_number=10,
            parent_class="Widget",
        )
        idx = build_symbol_index_from_symbols([sym])
        assert len(idx.by_name("render")) == 1
        s = idx.by_name("render")[0]
        assert s.parent_class == "Widget"
        assert len(idx.methods) == 1

    # ------------------------------------------------------------------
    # Multiple symbols of mixed types
    # ------------------------------------------------------------------

    def test_mixed_types(self) -> None:
        """Functions, classes, and methods all indexed from a flat list."""
        symbols = [
            Symbol(
                name="helper",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("utils.js"),
                line_number=1,
            ),
            Symbol(
                name="Processor",
                symbol_type=SymbolType.CLASS,
                file_path=Path("utils.js"),
                line_number=10,
            ),
            Symbol(
                name="run",
                symbol_type=SymbolType.METHOD,
                file_path=Path("utils.js"),
                line_number=11,
                parent_class="Processor",
            ),
        ]
        idx = build_symbol_index_from_symbols(symbols)
        assert len(idx.by_name("helper")) == 1
        assert len(idx.by_name("Processor")) == 1
        assert len(idx.by_name("run")) == 1
        assert len(idx.functions) == 1
        assert len(idx.classes) == 1
        assert len(idx.methods) == 1

    def test_multiple_files(self) -> None:
        """Symbols from different files are merged into one index."""
        symbols = [
            Symbol(
                name="foo",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("a.js"),
                line_number=1,
            ),
            Symbol(
                name="bar",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("b.js"),
                line_number=1,
            ),
        ]
        idx = build_symbol_index_from_symbols(symbols)
        assert len(idx.by_name("foo")) == 1
        assert idx.by_name("foo")[0].file_path == Path("a.js")
        assert len(idx.by_name("bar")) == 1
        assert idx.by_name("bar")[0].file_path == Path("b.js")

    # ------------------------------------------------------------------
    # Name collisions
    # ------------------------------------------------------------------

    def test_same_name_different_types(self) -> None:
        """A function and a class sharing a name are both preserved."""
        symbols = [
            Symbol(
                name="Config",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("utils.js"),
                line_number=1,
            ),
            Symbol(
                name="Config",
                symbol_type=SymbolType.CLASS,
                file_path=Path("utils.js"),
                line_number=10,
            ),
        ]
        idx = build_symbol_index_from_symbols(symbols)
        results = idx.by_name("Config")
        assert len(results) == 2
        types = {s.symbol_type for s in results}
        assert types == {SymbolType.FUNCTION, SymbolType.CLASS}

    def test_same_method_name_different_classes(self) -> None:
        """Same-named methods in different classes produce two symbols."""
        symbols = [
            Symbol(
                name="draw",
                symbol_type=SymbolType.METHOD,
                file_path=Path("shapes.js"),
                line_number=2,
                parent_class="Circle",
            ),
            Symbol(
                name="draw",
                symbol_type=SymbolType.METHOD,
                file_path=Path("shapes.js"),
                line_number=10,
                parent_class="Square",
            ),
        ]
        idx = build_symbol_index_from_symbols(symbols)
        draws = idx.by_name("draw")
        assert len(draws) == 2
        parents = {s.parent_class for s in draws}
        assert parents == {"Circle", "Square"}

    def test_identical_symbols_deduplicated(self) -> None:
        """Duplicates are preserved in the name group; ``all_symbols``
        deduplicates via its internal set.

        ``Symbol`` is a frozen dataclass with ``order=True``, so
        ``sorted()`` on a list containing the same object twice works but
        ``all_symbols`` deduplicates via a set.
        """
        sym = Symbol(
            name="util",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("app.js"),
            line_number=1,
        )
        idx = build_symbol_index_from_symbols([sym, sym])
        # by_name returns the raw list (no dedup at that level)
        assert len(idx.by_name("util")) == 2
        # all_symbols deduplicates via set
        assert len(idx.all_symbols) == 1

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_is_deterministic(self) -> None:
        """Same input always produces the same index."""
        symbols = [
            Symbol(
                name="b",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("app.js"),
                line_number=2,
            ),
            Symbol(
                name="a",
                symbol_type=SymbolType.CLASS,
                file_path=Path("app.js"),
                line_number=1,
            ),
        ]
        idx1 = build_symbol_index_from_symbols(symbols)
        idx2 = build_symbol_index_from_symbols(symbols)
        assert idx1.symbols == idx2.symbols
        assert idx1.all_symbols == idx2.all_symbols

    def test_output_is_sorted(self) -> None:
        """Name groups are sorted alphabetically by name; symbols within
        each group are sorted by their natural ordering."""
        symbols = [
            Symbol(
                name="zebra",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("app.js"),
                line_number=10,
            ),
            Symbol(
                name="alpha",
                symbol_type=SymbolType.FUNCTION,
                file_path=Path("app.js"),
                line_number=1,
            ),
        ]
        idx = build_symbol_index_from_symbols(symbols)
        # dict keys are in insertion order (Python 3.7+), but the builder
        # explicitly sorts them — assert that "alpha" comes first
        keys = list(idx.symbols)
        assert keys == ["alpha", "zebra"]

    # ------------------------------------------------------------------
    # Interchangeability with the Python build() path
    # ------------------------------------------------------------------

    def test_interchangeable_with_build(self) -> None:
        """``from_symbols(build().all_symbols)`` produces an identical
        index to ``build()`` directly."""
        source = {
            "app.py": textwrap.dedent("""\
                def helper():
                    pass

                class Processor:
                    def run(self):
                        pass
                """),
        }
        result = _scan_result(source)
        py_idx = build_symbol_index(result)

        # Round-trip through from_symbols
        js_idx = build_symbol_index_from_symbols(py_idx.all_symbols)

        assert js_idx.symbols == py_idx.symbols
        assert js_idx.all_symbols == py_idx.all_symbols
        assert js_idx.functions == py_idx.functions
        assert js_idx.classes == py_idx.classes
        assert js_idx.methods == py_idx.methods
