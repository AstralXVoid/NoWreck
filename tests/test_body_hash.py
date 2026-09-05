"""v0.16.0 Phase 1 — per-symbol structural body hashes.

Covers the ``body_hash`` that backs the new ``CHANGED_FUNCTION`` /
``CHANGED_CLASS`` claim types in all five languages:

* Python hashes ``ast.dump`` of the definition node (functions/methods)
  or the class *shell* (decorators, bases, keywords, class-level
  statements — methods excluded).
* JS/TS/Rust/Go hash a canonical serialisation of the tree-sitter CST
  (``structural_hash``): node types plus trimmed leaf text, with
  comments and whitespace excluded and string quote style normalised.

One rule everywhere: reformatting is never a "change", edited logic
always is.  The disjoint-facts invariant (a method edit fires a method
change, never a class change) is test-enforced per language.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

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


def _py_index(source: str) -> SymbolIndex:
    """Build a symbol index from Python *source*."""
    module = ast.parse(textwrap.dedent(source))
    return build_symbol_index(
        ScanResult(modules={Path("a.py"): module}),
    )


def _scan_source(
    scanner,
    extension: str,
    code: str,
    tmp_path: Path,
) -> list[Symbol]:
    """Write *code* to a temp file and scan it with *scanner*."""
    file_path = tmp_path / f"sample{extension}"
    file_path.write_text(textwrap.dedent(code))
    return scanner(file_path)


def _only(symbols: list[Symbol]) -> Symbol:
    """Return the sole symbol, failing loudly on ambiguity."""
    assert len(symbols) == 1, f"expected exactly one symbol, got {symbols}"
    return symbols[0]


# ---------------------------------------------------------------------------
# Symbol.body_hash serialisation
# ---------------------------------------------------------------------------


class TestBodyHashSerialisation:
    """Symbol.body_hash: identity-exemption and dict round-tripping."""

    def test_identical_bodies_hash_identically(self) -> None:
        """The same source always yields the same body hash."""
        first = _py_index("def greet():\n    return 'hi'\n")
        second = _py_index("def greet():\n    return 'hi'\n")
        assert (
            _only(first.by_name("greet")).body_hash
            == _only(
                second.by_name("greet"),
            ).body_hash
        )

    def test_body_hash_is_identity_exempt(self) -> None:
        """A body edit changes the hash but not symbol identity.

        This is what lets the detector emit CHANGED_FUNCTION instead of a
        spurious REMOVE+ADD pair.
        """
        before = _only(_py_index("def greet():\n    return 'hi'\n").by_name("greet"))
        after = _only(
            _py_index("def greet():\n    return 'hello world'\n").by_name("greet"),
        )
        assert before == after
        assert hash(before) == hash(after)
        assert before.body_hash != after.body_hash

    def test_to_dict_round_trip_preserves_body_hash(self) -> None:
        """Symbol.to_dict / from_dict preserve the body hash."""
        symbol = _only(_py_index("def greet():\n    return 'hi'\n").by_name("greet"))
        restored = Symbol.from_dict(symbol.to_dict())
        assert restored == symbol
        assert restored.body_hash == symbol.body_hash

    def test_to_dict_omits_body_hash_when_none(self) -> None:
        """Symbols without a hash serialise without the key (legacy-shaped)."""
        symbol = Symbol(
            name="plain",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("a.py"),
            line_number=1,
        )
        assert symbol.body_hash is None
        assert "body_hash" not in symbol.to_dict()

    def test_from_dict_tolerates_missing_body_hash(self) -> None:
        """Old cache payloads (pre-v16, no body_hash key) deserialise to None."""
        with_hash = Symbol(
            name="greet",
            symbol_type=SymbolType.FUNCTION,
            file_path=Path("a.py"),
            line_number=1,
            body_hash="abc123",
        )
        legacy_payload = {
            k: v for k, v in with_hash.to_dict().items() if k != "body_hash"
        }
        restored = Symbol.from_dict(legacy_payload)
        assert restored.body_hash is None
        assert restored == with_hash


# ---------------------------------------------------------------------------
# Python: function / method hashes
# ---------------------------------------------------------------------------


class TestPythonFunctionBodyHash:
    """Python function and method hashes from ast.dump."""

    def test_body_edit_changes_hash(self) -> None:
        """Changing a function body changes its hash."""
        before = _only(_py_index("def greet():\n    return 'hi'\n").by_name("greet"))
        after = _only(
            _py_index("def greet():\n    return 'hello world'\n").by_name("greet"),
        )
        assert before.body_hash != after.body_hash

    def test_whitespace_only_edit_does_not_change_hash(self) -> None:
        """Reformatting a function never registers as a change."""
        original = _only(
            _py_index("def greet():\n    return 'hi'\n").by_name("greet"),
        )
        reformatted = _only(
            _py_index("def  greet( ) :\n  return 'hi'\n").by_name("greet"),
        )
        assert original.body_hash == reformatted.body_hash

    def test_comment_edit_does_not_change_hash(self) -> None:
        """Comments are not AST and never affect the hash."""
        plain = _only(_py_index("def greet():\n    return 'hi'\n").by_name("greet"))
        commented = _only(
            _py_index(
                "# leading comment\ndef greet():\n    # inner comment\n"
                "    return 'hi'\n",
            ).by_name("greet"),
        )
        assert plain.body_hash == commented.body_hash

    def test_line_shift_does_not_change_hash(self) -> None:
        """Shifting a function down the file keeps its hash stable."""
        top = _only(_py_index("def greet():\n    return 'hi'\n").by_name("greet"))
        shifted = _only(
            _py_index(
                "# filler\n# filler\n# filler\n\n\ndef greet():\n    return 'hi'\n",
            ).by_name("greet"),
        )
        assert top.body_hash == shifted.body_hash

    def test_docstring_edit_changes_hash(self) -> None:
        """Docstrings are part of the AST, so editing one is a change."""
        before = _only(
            _py_index('def greet():\n    """Old doc."""\n    return 1\n').by_name(
                "greet",
            ),
        )
        after = _only(
            _py_index('def greet():\n    """New doc."""\n    return 1\n').by_name(
                "greet",
            ),
        )
        assert before.body_hash != after.body_hash

    def test_string_quote_style_does_not_change_hash(self) -> None:
        """'hi' and \"hi\" parse to the same Constant, so hashes match."""
        single = _only(_py_index("def greet():\n    return 'hi'\n").by_name("greet"))
        double = _only(_py_index('def greet():\n    return "hi"\n').by_name("greet"))
        assert single.body_hash == double.body_hash

    def test_operator_change_changes_hash(self) -> None:
        """Changing an operator is a real edit and must be detected."""
        plus = _only(_py_index("def calc():\n    return 1 + 2\n").by_name("calc"))
        minus = _only(_py_index("def calc():\n    return 1 - 2\n").by_name("calc"))
        assert plus.body_hash != minus.body_hash

    def test_signature_edit_changes_hash(self) -> None:
        """Changing parameters changes the hash."""
        before = _only(
            _py_index("def greet(name):\n    return name\n").by_name("greet"),
        )
        after = _only(
            _py_index("def greet(name, title):\n    return title + name\n").by_name(
                "greet",
            ),
        )
        assert before.body_hash != after.body_hash

    def test_method_body_edit_changes_hash(self) -> None:
        """Editing a method body changes the method's hash."""
        before = _only(
            _py_index("class C:\n    def m(self):\n        return 1\n").by_name("m"),
        )
        after = _only(
            _py_index("class C:\n    def m(self):\n        return 2\n").by_name("m"),
        )
        assert before.parent_class == "C"
        assert before.body_hash != after.body_hash


# ---------------------------------------------------------------------------
# Python: class-shell hashes (disjoint-facts rule)
# ---------------------------------------------------------------------------


class TestPythonClassShellHash:
    """Python class hashes cover the shell only, never method bodies."""

    def _class_hash(self, source: str) -> str:
        return _only(_py_index(source).by_name("C")).body_hash

    def test_method_edit_does_not_change_class_hash(self) -> None:
        """A method body edit fires a method change only (disjoint facts)."""
        assert self._class_hash("class C:\n    def m(self):\n        return 1\n") == (
            self._class_hash("class C:\n    def m(self):\n        return 2\n")
        )

    def test_method_signature_edit_does_not_change_class_hash(self) -> None:
        """Even a method signature edit stays out of the class shell."""
        assert self._class_hash(
            "class C:\n    def m(self, x):\n        return x\n",
        ) == self._class_hash(
            "class C:\n    def m(self, x, y):\n        return x + y\n",
        )

    def test_method_add_or_remove_does_not_change_class_hash(self) -> None:
        """Adding/removing a method changes the method set, not the shell."""
        assert self._class_hash("class C:\n    def m(self):\n        return 1\n") == (
            self._class_hash(
                "class C:\n    def m(self):\n        return 1\n"
                "    def n(self):\n        return 2\n",
            )
        )

    def test_method_decorator_edit_does_not_change_class_hash(self) -> None:
        """Python decorators live inside the FunctionDef, so a decorator
        edit is a method change, never a class change."""
        assert self._class_hash(
            "class C:\n    @dec\n    def m(self):\n        return 1\n",
        ) == self._class_hash(
            "class C:\n    @other\n    def m(self):\n        return 1\n",
        )

    def test_base_class_edit_changes_class_hash(self) -> None:
        """Heritage is class-shell content."""
        assert self._class_hash(
            "class C:\n    def m(self):\n        return 1\n",
        ) != self._class_hash(
            "class C(Base):\n    def m(self):\n        return 1\n",
        )

    def test_class_decorator_edit_changes_class_hash(self) -> None:
        """Class-level decorators are class-shell content."""
        assert self._class_hash(
            "@dec\nclass C:\n    def m(self):\n        return 1\n",
        ) != self._class_hash(
            "@other\nclass C:\n    def m(self):\n        return 1\n",
        )

    def test_class_attribute_edit_changes_class_hash(self) -> None:
        """Class-level statements (non-methods) are class-shell content."""
        assert self._class_hash(
            "class C:\n    x = 1\n    def m(self):\n        return 1\n",
        ) != self._class_hash(
            "class C:\n    x = 2\n    def m(self):\n        return 1\n",
        )

    def test_async_method_excluded_from_class_hash(self) -> None:
        """AsyncFunctionDef children are excluded exactly like FunctionDef."""
        assert self._class_hash(
            "class C:\n    async def m(self):\n        return 1\n",
        ) == self._class_hash(
            "class C:\n    async def m(self):\n        return 2\n",
        )

    def test_pass_placeholder_does_not_change_class_hash(self) -> None:
        """Removing the last method leaves a ``pass`` placeholder, which is
        shell-invisible: the edit stays a method change only (B3)."""
        assert self._class_hash(
            "class C:\n    def m(self):\n        return 1\n",
        ) == self._class_hash("class C:\n    pass\n")

    def test_pass_placeholder_is_not_real_content(self) -> None:
        """``pass`` is invisible, but real class-level content still is not."""
        assert self._class_hash("class C:\n    pass\n") != self._class_hash(
            "class C:\n    x = 1\n",
        )

    def test_nested_class_method_edit_does_not_change_outer_shell(self) -> None:
        """The disjoint-facts rule holds at any nesting depth (B4)."""
        assert self._class_hash(
            "class C:\n    class B:\n        def m(self):\n            return 1\n",
        ) == self._class_hash(
            "class C:\n    class B:\n        def m(self):\n            return 2\n",
        )

    def test_nested_class_field_edit_changes_outer_shell(self) -> None:
        """Nested class content is outer-shell content (B4)."""
        assert self._class_hash(
            "class C:\n    class B:\n        x = 1\n",
        ) != self._class_hash(
            "class C:\n    class B:\n        x = 2\n",
        )

    def test_nested_class_rename_changes_outer_shell(self) -> None:
        """Renaming a nested class is a structural change to the outer class."""
        assert self._class_hash(
            "class C:\n    class B:\n        x = 1\n",
        ) != self._class_hash(
            "class C:\n    class D:\n        x = 1\n",
        )


# ---------------------------------------------------------------------------
# Python: async indexing carries a usable body hash (P2)
# ---------------------------------------------------------------------------


class TestPythonAsyncBodyHash:
    """Async functions are indexed with body hashes (v0.16.0, P2)."""

    def test_async_function_has_body_hash(self) -> None:
        """Async defs produce FUNCTION symbols with a hash."""
        symbol = _only(
            _py_index("async def fetch_data():\n    return 1\n").by_name(
                "fetch_data",
            ),
        )
        assert symbol.symbol_type is SymbolType.FUNCTION
        assert symbol.body_hash is not None

    def test_sync_to_async_conversion_changes_hash_but_not_identity(self) -> None:
        """``def f`` → ``async def f`` keeps identity but changes the body.

        This is what makes a sync↔async conversion detectable as
        CHANGED_FUNCTION (not REMOVE+ADD): Symbol equality ignores the
        node kind, while ast.dump of FunctionDef vs AsyncFunctionDef
        differs.
        """
        sync = _only(_py_index("def f():\n    return 1\n").by_name("f"))
        async_ = _only(_py_index("async def f():\n    return 1\n").by_name("f"))
        assert sync == async_
        assert sync.body_hash != async_.body_hash


# ---------------------------------------------------------------------------
# Tree-sitter: structural hash semantics per language
# ---------------------------------------------------------------------------


class TestJsBodyHash:
    """JavaScript body hashes via structural_hash."""

    def _scan(self, code: str, tmp_path: Path) -> list[Symbol]:
        from nowreck.scanner.javascript_scanner import scan_js_file

        return _scan_source(scan_js_file, ".js", code, tmp_path)

    def test_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = _only(self._scan("function greet() { return 1; }\n", tmp_path))
        after = _only(self._scan("function greet() { return 2; }\n", tmp_path))
        assert before.body_hash != after.body_hash

    def test_reformat_does_not_change_hash(self, tmp_path: Path) -> None:
        compact = _only(
            self._scan("function greet() { return 'hi'; }\n", tmp_path),
        )
        expanded = _only(
            self._scan(
                "function  greet( ) {\n    return 'hi';\n}\n",
                tmp_path,
            ),
        )
        assert compact.body_hash == expanded.body_hash

    def test_comment_edit_does_not_change_hash(self, tmp_path: Path) -> None:
        plain = _only(self._scan("function greet() { return 'hi'; }\n", tmp_path))
        commented = _only(
            self._scan(
                "// leading comment\nfunction greet() { /* inner */ return 'hi'; }\n",
                tmp_path,
            ),
        )
        assert plain.body_hash == commented.body_hash

    def test_quote_style_does_not_change_hash(self, tmp_path: Path) -> None:
        single = _only(
            self._scan("function greet() { return 'hi'; }\n", tmp_path),
        )
        double = _only(
            self._scan('function greet() { return "hi"; }\n', tmp_path),
        )
        assert single.body_hash == double.body_hash

    def test_operator_change_changes_hash(self, tmp_path: Path) -> None:
        plus = _only(self._scan("function calc() { return 1 + 2; }\n", tmp_path))
        minus = _only(self._scan("function calc() { return 1 - 2; }\n", tmp_path))
        assert plus.body_hash != minus.body_hash

    def test_arrow_function_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = _only(self._scan("const f = () => 1;\n", tmp_path))
        after = _only(self._scan("const f = () => 2;\n", tmp_path))
        assert before.body_hash != after.body_hash

    def test_method_edit_does_not_change_class_hash(self, tmp_path: Path) -> None:
        """Method edits fire method changes only — never CHANGED_CLASS."""
        symbols_a = {
            s.name: s
            for s in self._scan(
                "class C { m() { return 1; } }\n",
                tmp_path,
            )
        }
        symbols_b = {
            s.name: s
            for s in self._scan(
                "class C { m() { return 2; } }\n",
                tmp_path,
            )
        }
        assert symbols_a["C"].body_hash == symbols_b["C"].body_hash
        assert symbols_a["m"].body_hash != symbols_b["m"].body_hash
        assert symbols_a["m"].parent_class == "C"

    def test_getter_edit_does_not_change_class_hash(self, tmp_path: Path) -> None:
        """Getters/setters are method_definition nodes — shell-excluded."""
        symbols_a = {
            s.name: s
            for s in self._scan(
                "class C { get x() { return 1; } }\n",
                tmp_path,
            )
        }
        symbols_b = {
            s.name: s
            for s in self._scan(
                "class C { get x() { return 2; } }\n",
                tmp_path,
            )
        }
        assert symbols_a["C"].body_hash == symbols_b["C"].body_hash
        assert symbols_a["x"].body_hash != symbols_b["x"].body_hash

    def test_field_edit_changes_class_hash(self, tmp_path: Path) -> None:
        """Class fields are class-shell content."""
        plain = {
            s.name: s
            for s in self._scan(
                "class C { m() { return 1; } }\n",
                tmp_path,
            )
        }
        with_field = {
            s.name: s
            for s in self._scan(
                "class C { m() { return 1; } x = 5; }\n",
                tmp_path,
            )
        }
        assert plain["C"].body_hash != with_field["C"].body_hash

    def test_semicolon_style_does_not_change_hash(self, tmp_path: Path) -> None:
        """ASi makes ``;`` optional — omitting it is not an edit (B1)."""
        semi = _only(
            self._scan("function f() { return 1; }\n", tmp_path),
        )
        asis = _only(
            self._scan("function f() { return 1 }\n", tmp_path),
        )
        assert semi.body_hash == asis.body_hash

    def test_class_body_trailing_semicolon_does_not_change_class_hash(
        self,
        tmp_path: Path,
    ) -> None:
        """An optional ``;`` after a method stays out of the class shell (B1)."""
        plain = {
            s.name: s
            for s in self._scan(
                "class C { m() { return 1; } }\n",
                tmp_path,
            )
        }
        trailing = {
            s.name: s
            for s in self._scan(
                "class C { m() { return 1; }; }\n",
                tmp_path,
            )
        }
        assert plain["C"].body_hash == trailing["C"].body_hash

    def test_trailing_comma_does_not_change_hash(self, tmp_path: Path) -> None:
        """A trailing comma is formatting, not content (B2)."""
        no_trailing = _only(
            self._scan("function f() { return [1, 2, 3]; }\n", tmp_path),
        )
        trailing = _only(
            self._scan("function f() { return [1, 2, 3,]; }\n", tmp_path),
        )
        assert no_trailing.body_hash == trailing.body_hash

    def test_array_elision_comma_still_changes_hash(self, tmp_path: Path) -> None:
        """Mid-list commas are content: ``[1,,2]`` is a sparse array (B2)."""
        dense = _only(
            self._scan("function f() { return [1,2]; }\n", tmp_path),
        )
        sparse = _only(
            self._scan("function f() { return [1,,2]; }\n", tmp_path),
        )
        assert dense.body_hash != sparse.body_hash

    def test_embedded_quote_style_does_not_change_hash(self, tmp_path: Path) -> None:
        """``"it's"`` and ``'it\'s'`` are the same string value (B5)."""
        double = _only(
            self._scan('function f() { return "it\'s"; }\n', tmp_path),
        )
        single = _only(
            self._scan("function f() { return 'it\\'s'; }\n", tmp_path),
        )
        assert double.body_hash == single.body_hash

    def test_escaped_quote_style_does_not_change_hash(self, tmp_path: Path) -> None:
        """``"a\"b"`` and ``'a"b'`` are the same string value (B5)."""
        escaped = _only(
            self._scan('function f() { return "a\\"b"; }\n', tmp_path),
        )
        literal = _only(
            self._scan("function f() { return 'a\"b'; }\n", tmp_path),
        )
        assert escaped.body_hash == literal.body_hash

    def test_escape_semantics_are_preserved(self, tmp_path: Path) -> None:
        """``\n`` (newline) and ``\\n`` (backslash-n) are different values."""
        newline = _only(
            self._scan('function f() { return "a\\nb"; }\n', tmp_path),
        )
        literal = _only(
            self._scan('function f() { return "a\\\\nb"; }\n', tmp_path),
        )
        assert newline.body_hash != literal.body_hash

    def test_hex_escape_equals_plain_char(self, tmp_path: Path) -> None:
        """``\x41`` decodes to ``A`` — same string value (B5)."""
        escaped = _only(
            self._scan('function f() { return "\\x41"; }\n', tmp_path),
        )
        plain = _only(
            self._scan('function f() { return "A"; }\n', tmp_path),
        )
        assert escaped.body_hash == plain.body_hash


class TestTsBodyHash:
    """TypeScript body hashes incl. the decorator edge (Accepted Edges #1)."""

    def _scan(self, code: str, tmp_path: Path) -> list[Symbol]:
        from nowreck.scanner.typescript_scanner import scan_ts_file

        return _scan_source(scan_ts_file, ".ts", code, tmp_path)

    def test_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = _only(
            self._scan("function greet(): number { return 1; }\n", tmp_path),
        )
        after = _only(
            self._scan("function greet(): number { return 2; }\n", tmp_path),
        )
        assert before.body_hash != after.body_hash

    def test_method_decorator_edit_changes_no_hash(self, tmp_path: Path) -> None:
        """TS decorators attach as siblings *outside* method_definition.

        The class shell skips method-attached decorators as one unit, so
        a decorator edit lands in neither the method hash nor the class
        shell hash (Accepted Edges #1 — fixture-verified).  The test pins
        this exact grammar behaviour.
        """
        symbols_a = {
            s.name: s
            for s in self._scan(
                "class Foo { @dec method() {} }\n",
                tmp_path,
            )
        }
        symbols_b = {
            s.name: s
            for s in self._scan(
                "class Foo { @other method() {} }\n",
                tmp_path,
            )
        }
        assert symbols_a["Foo"].body_hash == symbols_b["Foo"].body_hash
        assert symbols_a["method"].body_hash == symbols_b["method"].body_hash

    def test_class_decorator_edit_changes_class_hash(self, tmp_path: Path) -> None:
        """Class-level decorators are children of class_declaration and
        remain class-shell content."""
        symbols_a = {
            s.name: s
            for s in self._scan(
                "@clsDec class Bar {}\n",
                tmp_path,
            )
        }
        symbols_b = {
            s.name: s
            for s in self._scan(
                "@otherDec class Bar {}\n",
                tmp_path,
            )
        }
        assert symbols_a["Bar"].body_hash != symbols_b["Bar"].body_hash

    def test_method_edit_does_not_change_class_hash(self, tmp_path: Path) -> None:
        symbols_a = {
            s.name: s
            for s in self._scan(
                "class Foo { method() { return 1; } }\n",
                tmp_path,
            )
        }
        symbols_b = {
            s.name: s
            for s in self._scan(
                "class Foo { method() { return 2; } }\n",
                tmp_path,
            )
        }
        assert symbols_a["Foo"].body_hash == symbols_b["Foo"].body_hash
        assert symbols_a["method"].body_hash != symbols_b["method"].body_hash

    def test_semicolon_style_does_not_change_hash(self, tmp_path: Path) -> None:
        """TS semicolons are ASI-optional — not an edit (B1)."""
        semi = _only(
            self._scan("function greet(): number { return 1; }\n", tmp_path),
        )
        asis = _only(
            self._scan("function greet(): number { return 1 }\n", tmp_path),
        )
        assert semi.body_hash == asis.body_hash

    def test_trailing_comma_does_not_change_hash(self, tmp_path: Path) -> None:
        """A trailing comma in a call is formatting, not content (B2)."""
        no_trailing = _only(
            self._scan(
                "function greet(): number { return combine(1, 2); }\n",
                tmp_path,
            ),
        )
        trailing = _only(
            self._scan(
                "function greet(): number { return combine(1, 2,); }\n",
                tmp_path,
            ),
        )
        assert no_trailing.body_hash == trailing.body_hash


class TestRustBodyHash:
    """Rust body hashes via structural_hash."""

    def _scan(self, code: str, tmp_path: Path) -> list[Symbol]:
        from nowreck.scanner.rust_scanner import scan_rust_file

        return _scan_source(scan_rust_file, ".rs", code, tmp_path)

    def test_fn_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = _only(
            self._scan("fn greet() -> i32 { 1 }\n", tmp_path),
        )
        after = _only(
            self._scan("fn greet() -> i32 { 2 }\n", tmp_path),
        )
        assert before.body_hash != after.body_hash

    def test_reformat_and_comments_do_not_change_hash(self, tmp_path: Path) -> None:
        compact = _only(
            self._scan("fn greet() -> i32 { 1 }\n", tmp_path),
        )
        padded = _only(
            self._scan(
                "// leading\n/* block */\nfn greet() -> i32 {\n    1\n}\n",
                tmp_path,
            ),
        )
        assert compact.body_hash == padded.body_hash

    def test_impl_method_edit_does_not_change_struct_hash(
        self,
        tmp_path: Path,
    ) -> None:
        """Rust methods live in impl blocks — the struct hash is shell-only."""
        symbols_a = {
            s.name: s
            for s in self._scan(
                "struct S { x: i32 }\nimpl S { fn m(&self) {} }\n",
                tmp_path,
            )
        }
        symbols_b = {
            s.name: s
            for s in self._scan(
                "struct S { x: i32 }\nimpl S { fn m(&self) { let _ = 1; } }\n",
                tmp_path,
            )
        }
        assert symbols_a["S"].body_hash == symbols_b["S"].body_hash
        assert symbols_a["m"].body_hash != symbols_b["m"].body_hash
        assert symbols_a["m"].parent_class == "S"

    def test_field_type_edit_changes_struct_hash(self, tmp_path: Path) -> None:
        before = {
            s.name: s
            for s in self._scan(
                "struct S { x: i32 }\n",
                tmp_path,
            )
        }
        after = {
            s.name: s
            for s in self._scan(
                "struct S { x: i64 }\n",
                tmp_path,
            )
        }
        assert before["S"].body_hash != after["S"].body_hash

    def test_semicolon_is_semantic_in_rust(self, tmp_path: Path) -> None:
        """``{ 1 }`` returns the value, ``{ 1; }`` returns ``()`` — the
        semicolon must keep affecting the hash in Rust (B1 guard)."""
        expr = _only(
            self._scan("fn f() -> i32 { 1 }\n", tmp_path),
        )
        stmt = _only(
            self._scan("fn f() { 1; }\n", tmp_path),
        )
        assert expr.body_hash != stmt.body_hash

    def test_trailing_comma_does_not_change_hash(self, tmp_path: Path) -> None:
        """Rust allows a trailing comma in call args — formatting only (B2)."""
        no_trailing = _only(
            self._scan("fn f() { g(1, 2); }\n", tmp_path),
        )
        trailing = _only(
            self._scan("fn f() { g(1, 2,); }\n", tmp_path),
        )
        assert no_trailing.body_hash == trailing.body_hash


class TestGoBodyHash:
    """Go body hashes via structural_hash."""

    def _scan(self, code: str, tmp_path: Path) -> list[Symbol]:
        from nowreck.scanner.go_scanner import scan_go_file

        return _scan_source(scan_go_file, ".go", code, tmp_path)

    def test_fn_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = _only(
            self._scan("package p\nfunc greet() int { return 1 }\n", tmp_path),
        )
        after = _only(
            self._scan("package p\nfunc greet() int { return 2 }\n", tmp_path),
        )
        assert before.body_hash != after.body_hash

    def test_reformat_and_comments_do_not_change_hash(self, tmp_path: Path) -> None:
        compact = _only(
            self._scan("package p\nfunc greet() int { return 1 }\n", tmp_path),
        )
        padded = _only(
            self._scan(
                "// leading\n/* block */\npackage p\n"
                "func greet() int {\n    return 1\n}\n",
                tmp_path,
            ),
        )
        assert compact.body_hash == padded.body_hash

    def test_method_edit_does_not_change_struct_hash(self, tmp_path: Path) -> None:
        """Go methods are top-level method_declaration nodes — the struct
        hash covers only the struct body."""
        symbols_a = {
            s.name: s
            for s in self._scan(
                "package p\ntype S struct { X int }\nfunc (s *S) M() { _ = 1 }\n",
                tmp_path,
            )
        }
        symbols_b = {
            s.name: s
            for s in self._scan(
                "package p\ntype S struct { X int }\nfunc (s *S) M() { _ = 2 }\n",
                tmp_path,
            )
        }
        assert symbols_a["S"].body_hash == symbols_b["S"].body_hash
        assert symbols_a["M"].body_hash != symbols_b["M"].body_hash
        assert symbols_a["M"].parent_class == "S"

    def test_field_type_edit_changes_struct_hash(self, tmp_path: Path) -> None:
        before = {
            s.name: s
            for s in self._scan(
                "package p\ntype S struct { X int }\n",
                tmp_path,
            )
        }
        after = {
            s.name: s
            for s in self._scan(
                "package p\ntype S struct { X string }\n",
                tmp_path,
            )
        }
        assert before["S"].body_hash != after["S"].body_hash

    def test_interface_has_no_body_hash(self, tmp_path: Path) -> None:
        """INTERFACE/TYPE_ALIAS symbols are not hashed (no CHANGED claim
        types exist for them in v16)."""
        symbols = {
            s.name: s
            for s in self._scan(
                "package p\ntype Shape interface { Area() float64 }\n",
                tmp_path,
            )
        }
        assert symbols["Shape"].body_hash is None

    def test_semicolon_style_does_not_change_hash(self, tmp_path: Path) -> None:
        """Go's ASI makes ``;`` optional — not an edit (B1)."""
        no_semi = _only(
            self._scan("package p\nfunc f() int { return 1 }\n", tmp_path),
        )
        semi = _only(
            self._scan("package p\nfunc f() int { return 1; }\n", tmp_path),
        )
        assert no_semi.body_hash == semi.body_hash

    def test_trailing_comma_does_not_change_hash(self, tmp_path: Path) -> None:
        """A trailing comma in a composite literal is formatting (B2)."""
        no_trailing = _only(
            self._scan(
                "package p\nfunc f() { _ = []int{1, 2} }\n",
                tmp_path,
            ),
        )
        trailing = _only(
            self._scan(
                "package p\nfunc f() { _ = []int{1, 2,} }\n",
                tmp_path,
            ),
        )
        assert no_trailing.body_hash == trailing.body_hash
