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

    def test_method_decorator_edit_changes_method_hash_not_class_hash(
        self, tmp_path: Path
    ) -> None:
        """TS decorators attach as siblings *outside* method_definition.

        The class shell skips method-attached decorators as one unit, and
        the method hash folds the attached decorator run in — so a
        decorator edit fires ``CHANGED_FUNCTION`` (Python parity) and
        never ``CHANGED_CLASS`` (Accepted Edges #1 — outcome now
        test-enforced, no silent divergence between languages).
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
        # Disjoint-facts: the class shell is untouched…
        assert symbols_a["Foo"].body_hash == symbols_b["Foo"].body_hash
        # …and the edit is visible on the method it decorates.
        assert symbols_a["method"].body_hash != symbols_b["method"].body_hash

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


class TestJavaBodyHash:
    """Java body hashes via structural_hash (v0.17.0 Phase 2).

    Java has no header/impl split, so every method/constructor hash covers
    the whole declaration (annotations included — probe J4); CLASS and
    ENUM symbols hash the class *shell* (fields, enum constants, heritage)
    with method subtrees excluded.
    """

    def _scan(self, code: str, tmp_path: Path) -> list[Symbol]:
        from nowreck.scanner.java_scanner import scan_java_file

        return _scan_source(scan_java_file, ".java", code, tmp_path)

    def _one(
        self,
        code: str,
        name: str,
        tmp_path: Path,
        kind: SymbolType | None = None,
    ) -> Symbol:
        """The single symbol named *name* (optionally of *kind*).

        ``kind`` matters for Java: a class and its constructor share a
        name, so ``class A { A() {} }`` yields two symbols named ``A``.
        """
        found = [
            s
            for s in self._scan(code, tmp_path)
            if s.name == name and (kind is None or s.symbol_type is kind)
        ]
        assert len(found) == 1, f"expected one symbol named {name}, got {found}"
        return found[0]

    def test_method_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = self._one("class A { int m() { return 1; } }", "m", tmp_path)
        after = self._one("class A { int m() { return 2; } }", "m", tmp_path)
        assert before.body_hash != after.body_hash

    def test_reformat_and_comments_do_not_change_hash(self, tmp_path: Path) -> None:
        compact = self._one("class A { int m() { return 1; } }", "m", tmp_path)
        padded = self._one(
            "// lead\n"
            "class A {\n"
            "    /* block */\n"
            "    int m() {\n"
            "        return 1;\n"
            "    }\n"
            "}\n",
            "m",
            tmp_path,
        )
        assert compact.body_hash == padded.body_hash

    def test_method_edit_does_not_change_class_hash(self, tmp_path: Path) -> None:
        before = self._one("class A { int f = 1; void m() {} }", "A", tmp_path)
        after = self._one("class A { int f = 1; void m() { call(); } }", "A", tmp_path)
        assert before.body_hash == after.body_hash

    def test_field_edit_changes_class_hash(self, tmp_path: Path) -> None:
        before = self._one("class A { int f = 1; void m() {} }", "A", tmp_path)
        after = self._one("class A { int f = 2; void m() {} }", "A", tmp_path)
        assert before.body_hash != after.body_hash

    def test_annotation_is_inside_the_method_hash(self, tmp_path: Path) -> None:
        plain = self._one("class A { void m() {} }", "m", tmp_path)
        annotated = self._one("class A { @Deprecated void m() {} }", "m", tmp_path)
        assert plain.body_hash != annotated.body_hash

    def test_text_block_quote_style_is_normalised(self, tmp_path: Path) -> None:
        quoted = self._one('class A { String m() { return "x"; } }', "m", tmp_path)
        block = self._one('class A { String m() { return """x"""; } }', "m", tmp_path)
        assert quoted.body_hash == block.body_hash

    def test_text_block_content_edit_changes_hash(self, tmp_path: Path) -> None:
        one = self._one('class A { String m() { return """aa"""; } }', "m", tmp_path)
        two = self._one('class A { String m() { return """bb"""; } }', "m", tmp_path)
        assert one.body_hash != two.body_hash

    def test_semicolon_is_hashed_content(self, tmp_path: Path) -> None:
        """Java ``;`` is required syntax, so it is deliberately *not* in
        the ASI exclusion set: adding an empty statement changes the hash.
        """
        without = self._one("class A { void m() { } }", "m", tmp_path)
        with_empty = self._one("class A { void m() { ; } }", "m", tmp_path)
        assert without.body_hash != with_empty.body_hash

    def test_enum_constant_edit_changes_enum_hash(self, tmp_path: Path) -> None:
        before = self._one("enum E { A, B; void m() {} }", "E", tmp_path)
        after = self._one("enum E { A, C; void m() {} }", "E", tmp_path)
        assert before.body_hash != after.body_hash

    def test_constructor_edit_changes_its_own_hash_only(self, tmp_path: Path) -> None:
        before_src = "class A { A(int x) { this.x = x; } int x; }"
        after_src = "class A { A(int x) { this.x = x + 1; } int x; }"
        # A class and its constructor share the name “A”, so filter by kind.
        ctor_before = self._one(before_src, "A", tmp_path, SymbolType.METHOD)
        ctor_after = self._one(after_src, "A", tmp_path, SymbolType.METHOD)
        shell_before = self._one(before_src, "A", tmp_path, SymbolType.CLASS)
        shell_after = self._one(after_src, "A", tmp_path, SymbolType.CLASS)
        assert ctor_before.body_hash != ctor_after.body_hash
        assert shell_before.body_hash == shell_after.body_hash


class TestPhpBodyHash:
    """PHP body hashes (v0.17.0 Phase 4).

    PHP is the one language whose quote style selects the escape rules, so
    its strings go through a dedicated leaf normaliser (PH11): quote
    style is neutral, escape *values* are not, and an interpolation is
    marked so a literal backslash-dollar can never collide with an
    interpolated variable.  A
    type's shell hash excludes ``method_declaration`` subtrees (the
    disjoint-facts rule), so properties, constants, enum cases and trait
    uses are shell content while methods are not.  Semicolons are
    required syntax and are hashed as content (PH10), and attributes are
    *children* of their declaration (PH4), so they hash with it.
    """

    def _scan(self, code: str, tmp_path: Path) -> list[Symbol]:
        from nowreck.scanner.php_scanner import scan_php_file

        return _scan_source(scan_php_file, ".php", code, tmp_path)

    def _one(
        self,
        code: str,
        name: str,
        tmp_path: Path,
        kind: SymbolType | None = None,
    ) -> Symbol:
        """The single symbol named *name* (optionally of *kind*)."""
        found = [
            s
            for s in self._scan(code, tmp_path)
            if s.name == name and (kind is None or s.symbol_type is kind)
        ]
        assert len(found) == 1, f"expected one symbol named {name}, got {found}"
        return found[0]

    # -- disjoint facts ------------------------------------------------

    def test_method_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\nclass A\n{\n    public function m(): int\n    {\n"
            "        return 1;\n    }\n}\n",
            "m",
            tmp_path,
        )
        after = self._one(
            "<?php\nclass A\n{\n    public function m(): int\n    {\n"
            "        return 2;\n    }\n}\n",
            "m",
            tmp_path,
        )
        assert before.body_hash != after.body_hash

    def test_method_edit_does_not_change_class_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\nclass A\n{\n    public $f = 1;\n\n"
            "    public function m()\n    {\n    }\n}\n",
            "A",
            tmp_path,
        )
        after = self._one(
            "<?php\nclass A\n{\n    public $f = 1;\n\n"
            "    public function m()\n    {\n        work();\n    }\n}\n",
            "A",
            tmp_path,
        )
        assert before.body_hash == after.body_hash

    def test_property_edit_changes_class_hash(self, tmp_path: Path) -> None:
        before = self._one("<?php\nclass A { public $f = 1; }\n", "A", tmp_path)
        after = self._one("<?php\nclass A { public $f = 2; }\n", "A", tmp_path)
        assert before.body_hash != after.body_hash

    def test_class_constant_edit_changes_class_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\nclass A { public const LIMIT = 1; }\n", "A", tmp_path
        )
        after = self._one("<?php\nclass A { public const LIMIT = 2; }\n", "A", tmp_path)
        assert before.body_hash != after.body_hash

    def test_reformat_and_comments_do_not_change_hash(self, tmp_path: Path) -> None:
        compact = self._one(
            "<?php\nclass A { public function m(): string { return 'hi'; } }\n",
            "m",
            tmp_path,
        )
        padded = self._one(
            "<?php\n"
            "// lead\n"
            "# hash comment\n"
            "class A\n"
            "{\n"
            "    /* block */\n"
            "    public function m(): string  {  return  'hi';  } // trailing\n"
            "}\n",
            "m",
            tmp_path,
        )
        assert compact.body_hash == padded.body_hash

    # -- enum and trait shells (PH7 / PH8) -----------------------------

    def test_enum_case_edit_changes_enum_hash(self, tmp_path: Path) -> None:
        before = self._one("<?php\nenum E { case A; case B; }\n", "E", tmp_path)
        after = self._one("<?php\nenum E { case A; case C; }\n", "E", tmp_path)
        assert before.body_hash != after.body_hash

    def test_enum_method_edit_does_not_change_enum_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\nenum E\n{\n    case A;\n\n"
            "    public function label(): string\n    {\n        return 'a';\n"
            "    }\n}\n",
            "E",
            tmp_path,
        )
        after = self._one(
            "<?php\nenum E\n{\n    case A;\n\n"
            "    public function label(): string\n    {\n        return 'b';\n"
            "    }\n}\n",
            "E",
            tmp_path,
        )
        assert before.body_hash == after.body_hash

    def test_trait_method_edit_keeps_trait_shell(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\ntrait T\n{\n    public $f = 1;\n\n"
            "    public function m()\n    {\n    }\n}\n",
            "T",
            tmp_path,
        )
        after = self._one(
            "<?php\ntrait T\n{\n    public $f = 1;\n\n"
            "    public function m()\n    {\n        work();\n    }\n}\n",
            "T",
            tmp_path,
        )
        assert before.body_hash == after.body_hash

    def test_trait_property_edit_changes_trait_shell(self, tmp_path: Path) -> None:
        before = self._one("<?php\ntrait T { public $f = 1; }\n", "T", tmp_path)
        after = self._one("<?php\ntrait T { public $f = 2; }\n", "T", tmp_path)
        assert before.body_hash != after.body_hash

    # -- declaration-only members (PH9) --------------------------------

    def test_interface_carries_no_hash(self, tmp_path: Path) -> None:
        """There is no ``CHANGED_INTERFACE`` claim, so an interface's
        ``body_hash`` is ``None``."""
        iface = self._one(
            "<?php\ninterface I { public function m(); }\n", "I", tmp_path
        )
        assert iface.body_hash is None

    def test_declaration_only_method_has_no_hash(self, tmp_path: Path) -> None:
        """PH9: a method with no body can never fire ``CHANGED_FUNCTION``."""
        method = self._one(
            "<?php\ninterface I { public function m(): int; }\n",
            "m",
            tmp_path,
            SymbolType.METHOD,
        )
        assert method.body_hash is None

    def test_an_abstract_method_has_no_hash(self, tmp_path: Path) -> None:
        method = self._one(
            "<?php\nabstract class A { abstract public function m(); }\n",
            "m",
            tmp_path,
            SymbolType.METHOD,
        )
        assert method.body_hash is None

    # -- string normalisation (PH11) ------------------------------------

    def test_quote_swap_is_hash_neutral(self, tmp_path: Path) -> None:
        single = self._one(
            "<?php\nfunction f(): string\n{\n    return 'x';\n}\n", "f", tmp_path
        )
        double = self._one(
            '<?php\nfunction f(): string\n{\n    return "x";\n}\n', "f", tmp_path
        )
        assert single.body_hash == double.body_hash

    def test_single_quoted_newline_differs_from_double_quoted(
        self, tmp_path: Path
    ) -> None:
        """``'\\n'`` is backslash-n (two characters) while ``"\\n"`` is a
        real newline — PHP's quote style *selects* the escape rules, so
        this swap must stay visible."""
        literal = self._one(
            "<?php\nfunction f(): string\n{\n    return '\\n';\n}\n", "f", tmp_path
        )
        newline = self._one(
            '<?php\nfunction f(): string\n{\n    return "\\n";\n}\n', "f", tmp_path
        )
        assert literal.body_hash != newline.body_hash

    def test_escaped_dollar_does_not_collide_with_interpolation(
        self, tmp_path: Path
    ) -> None:
        literal = self._one(
            '<?php\nfunction f(): string\n{\n    return "\\$x";\n}\n', "f", tmp_path
        )
        interpolated = self._one(
            '<?php\nfunction f(): string\n{\n    return "$x";\n}\n', "f", tmp_path
        )
        assert literal.body_hash != interpolated.body_hash

    def test_interpolation_edit_changes_hash(self, tmp_path: Path) -> None:
        before = self._one(
            '<?php\nfunction f(string $n): string\n{\n    return "Hi {$n}";\n}\n',
            "f",
            tmp_path,
        )
        after = self._one(
            '<?php\nfunction f(string $n): string\n{\n    return "Hi {$n}!";\n}\n',
            "f",
            tmp_path,
        )
        assert before.body_hash != after.body_hash

    def test_heredoc_nowdoc_and_quoted_stay_distinct(self, tmp_path: Path) -> None:
        quoted = self._one(
            "<?php\nfunction f(): string\n{\n    $x = 'text';\n    return $x;\n}\n",
            "f",
            tmp_path,
        )
        heredoc = self._one(
            "<?php\nfunction f(): string\n{\n"
            "    $x = <<<EOT\n    text\n    EOT;\n    return $x;\n}\n",
            "f",
            tmp_path,
        )
        nowdoc = self._one(
            "<?php\nfunction f(): string\n{\n"
            "    $x = <<<'EOT'\n    text\n    EOT;\n    return $x;\n}\n",
            "f",
            tmp_path,
        )
        # Raw vs interpolated is semantically significant (the Kotlin raw
        # string rule): every pair differs, even with identical text.
        assert quoted.body_hash != heredoc.body_hash
        assert quoted.body_hash != nowdoc.body_hash
        assert heredoc.body_hash != nowdoc.body_hash

    def test_heredoc_marker_rename_is_neutral(self, tmp_path: Path) -> None:
        one = self._one(
            "<?php\nfunction f(): string\n{\n"
            "    $x = <<<EOT\n    text\n    EOT;\n    return $x;\n}\n",
            "f",
            tmp_path,
        )
        two = self._one(
            "<?php\nfunction f(): string\n{\n"
            "    $x = <<<ZZZ\n    text\n    ZZZ;\n    return $x;\n}\n",
            "f",
            tmp_path,
        )
        assert one.body_hash == two.body_hash

    # -- semicolons and attributes (PH10 / PH4) -------------------------

    def test_semicolon_is_hashed_content(self, tmp_path: Path) -> None:
        """PH10: PHP semicolons are required syntax, so they are *not* in
        the ASI exclusion set — an extra ``;`` (a valid empty statement)
        changes the hash."""
        without = self._one(
            "<?php\nfunction f(): int\n{\n    return 1;\n}\n", "f", tmp_path
        )
        with_empty = self._one(
            "<?php\nfunction f(): int\n{\n    return 1;;\n}\n", "f", tmp_path
        )
        assert without.body_hash != with_empty.body_hash

    def test_trailing_comma_is_invisible(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\nfunction f(): array\n{\n    return [1, 2];\n}\n", "f", tmp_path
        )
        after = self._one(
            "<?php\nfunction f(): array\n{\n    return [1, 2,];\n}\n", "f", tmp_path
        )
        assert before.body_hash == after.body_hash

    def test_attribute_is_inside_the_function_hash(self, tmp_path: Path) -> None:
        """PH4: attributes are *children* of the declaration, so no folding
        is needed — the attribute and its arguments hash with it."""
        plain = self._one(
            "<?php\nfunction f(): int\n{\n    return 1;\n}\n", "f", tmp_path
        )
        annotated = self._one(
            "<?php\n#[Route('/home')]\nfunction f(): int\n{\n    return 1;\n}\n",
            "f",
            tmp_path,
        )
        assert plain.body_hash != annotated.body_hash

        one = self._one(
            "<?php\n#[Route('/one')]\nfunction f(): int\n{\n    return 1;\n}\n",
            "f",
            tmp_path,
        )
        two = self._one(
            "<?php\n#[Route('/two')]\nfunction f(): int\n{\n    return 1;\n}\n",
            "f",
            tmp_path,
        )
        assert one.body_hash != two.body_hash

    def test_attribute_is_inside_the_class_shell_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\n#[Attribute]\nclass A { public $f = 1; }\n", "A", tmp_path
        )
        after = self._one(
            "<?php\n#[Attribute(Attribute::TARGET_CLASS)]\n"
            "class A { public $f = 1; }\n",
            "A",
            tmp_path,
        )
        assert before.body_hash != after.body_hash

    # -- closures (PH6) -------------------------------------------------

    def test_closure_edit_changes_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "<?php\n$f = function (): int\n{\n    return 1;\n};\n", "f", tmp_path
        )
        after = self._one(
            "<?php\n$f = function (): int\n{\n    return 2;\n};\n", "f", tmp_path
        )
        assert before.body_hash is not None
        assert before.body_hash != after.body_hash

    def test_arrow_closure_edit_changes_hash(self, tmp_path: Path) -> None:
        before = self._one("<?php\n$f = fn (): int => 1;\n", "f", tmp_path)
        after = self._one("<?php\n$f = fn (): int => 2;\n", "f", tmp_path)
        assert before.body_hash != after.body_hash


class TestKotlinBodyHash:
    """Kotlin body hashes (v0.17.0 Phase 3).

    Kotlin has no header/impl split either, so a method hash covers the
    whole declaration — annotations included, because probe K8 attaches
    them to the declaration and the hash canonicalises them by their
    leaf-token signature (that is what makes the grammar's *detached*
    shape, defect D4, hash identically).  A type's shell hash excludes
    every method-like subtree, ``function_declaration`` and
    ``secondary_constructor`` included.
    """

    def _scan(self, code: str, tmp_path: Path) -> list[Symbol]:
        from nowreck.scanner.kotlin_scanner import scan_kotlin_file

        return _scan_source(scan_kotlin_file, ".kt", code, tmp_path)

    def _one(
        self,
        code: str,
        name: str,
        tmp_path: Path,
        kind: SymbolType | None = None,
    ) -> Symbol:
        """The single symbol named *name* (optionally of *kind*).

        ``kind`` matters for Kotlin as it does for Java: a class and its
        secondary constructor share a name, so ``class A { constructor() }``
        yields two symbols named ``A``.
        """
        found = [
            s
            for s in self._scan(code, tmp_path)
            if s.name == name and (kind is None or s.symbol_type is kind)
        ]
        assert len(found) == 1, f"expected one symbol named {name}, got {found}"
        return found[0]

    def test_method_body_edit_changes_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "class A {\n    fun m(): Int {\n        return 1\n    }\n}\n",
            "m",
            tmp_path,
        )
        after = self._one(
            "class A {\n    fun m(): Int {\n        return 2\n    }\n}\n",
            "m",
            tmp_path,
        )
        assert before.body_hash != after.body_hash

    def test_reformat_and_comments_do_not_change_hash(self, tmp_path: Path) -> None:
        compact = self._one('class A {\n    fun m(): String = "hi"\n}\n', "m", tmp_path)
        padded = self._one(
            "// lead\n"
            "class A {\n"
            "    /* block */\n"
            '    fun m(): String  =  "hi"   // trailing\n'
            "}\n",
            "m",
            tmp_path,
        )
        assert compact.body_hash == padded.body_hash

    def test_method_edit_does_not_change_class_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "class A {\n    val f = 1\n\n    fun m() {}\n}\n", "A", tmp_path
        )
        after = self._one(
            "class A {\n    val f = 1\n\n    fun m() {\n        work()\n    }\n}\n",
            "A",
            tmp_path,
        )
        assert before.body_hash == after.body_hash

    def test_property_edit_changes_class_hash(self, tmp_path: Path) -> None:
        before = self._one(
            "class A {\n    val f = 1\n\n    fun m() {}\n}\n", "A", tmp_path
        )
        after = self._one(
            "class A {\n    val f = 2\n\n    fun m() {}\n}\n", "A", tmp_path
        )
        assert before.body_hash != after.body_hash

    def test_annotation_is_inside_the_method_hash(self, tmp_path: Path) -> None:
        plain = self._one("class A {\n    fun m() {}\n}\n", "m", tmp_path)
        annotated = self._one(
            'class A {\n    @Deprecated("x")\n    fun m() {}\n}\n', "m", tmp_path
        )
        assert plain.body_hash != annotated.body_hash

    def test_annotation_argument_edit_changes_hash(self, tmp_path: Path) -> None:
        one = self._one(
            'class A {\n    @Suppress("one")\n    fun m() {}\n}\n', "m", tmp_path
        )
        two = self._one(
            'class A {\n    @Suppress("two")\n    fun m() {}\n}\n', "m", tmp_path
        )
        assert one.body_hash != two.body_hash

    def test_attached_and_detached_annotation_hash_alike(self, tmp_path: Path) -> None:
        """Defect D4 pin: the grammar *detaches* an annotation from a
        declaration when a sibling — even a trailing comment — follows it,
        producing two different CST shapes for the same source.  The hash
        must be identical, so adding a comment can never register as a
        change (and an annotated declaration is never lost).
        """
        attached = self._one(
            'class A {\n    @Deprecated("x")\n    fun m() {}\n}\n', "m", tmp_path
        )
        detached = self._one(
            'class A {\n    @Deprecated("x")\n    fun m() {}\n\n'
            "    // a trailing comment detaches the annotation\n}\n",
            "m",
            tmp_path,
        )
        assert attached.body_hash == detached.body_hash

    def test_string_content_edit_changes_hash(self, tmp_path: Path) -> None:
        one = self._one(
            'class A {\n    fun m(): String {\n        return "aa"\n    }\n}\n',
            "m",
            tmp_path,
        )
        two = self._one(
            'class A {\n    fun m(): String {\n        return "bb"\n    }\n}\n',
            "m",
            tmp_path,
        )
        assert one.body_hash != two.body_hash

    def test_escape_sequence_is_content(self, tmp_path: Path) -> None:
        """Kotlin processes escapes in a quoted string, so ``\\n`` and
        ``n`` are different values and must not collide.
        """
        escaped = self._one(
            'class A {\n    fun m(): String {\n        return "\\n"\n    }\n}\n',
            "m",
            tmp_path,
        )
        plain = self._one(
            'class A {\n    fun m(): String {\n        return "n"\n    }\n}\n',
            "m",
            tmp_path,
        )
        assert escaped.body_hash != plain.body_hash

    def test_raw_string_is_not_a_quoted_string(self, tmp_path: Path) -> None:
        """A Kotlin raw string is *semantically* different from a quoted
        one — a three-quote raw string holding a backslash-n is two
        characters, while a quoted backslash-n is a newline — so the
        delimiter style is content, not formatting.  This is the one
        place the family rule diverges from Java's text blocks, whose
        delimiter shares one node type and *is* normalised away.
        """
        quoted = self._one(
            'class A {\n    fun m(): String {\n        return "x"\n    }\n}\n',
            "m",
            tmp_path,
        )
        raw = self._one(
            'class A {\n    fun m(): String {\n        return """x"""\n    }\n}\n',
            "m",
            tmp_path,
        )
        assert quoted.body_hash != raw.body_hash

    def test_raw_string_whitespace_is_content(self, tmp_path: Path) -> None:
        """Whitespace inside a raw string is string content, not source
        formatting: re-indenting it must register as a change.
        """
        one = self._one(
            'class A {\n    fun m(): String {\n        return """a b"""\n    }\n}\n',
            "m",
            tmp_path,
        )
        two = self._one(
            'class A {\n    fun m(): String {\n        return """a   b"""\n    }\n}\n',
            "m",
            tmp_path,
        )
        assert one.body_hash != two.body_hash

    def test_semicolon_is_invisible(self, tmp_path: Path) -> None:
        """Kotlin semicolons are optional syntax, so they are excluded
        from the hash (the ASI rule JS/TS/Go share).
        """
        without = self._one(
            "class A {\n    fun m() {\n        work()\n    }\n}\n", "m", tmp_path
        )
        with_semi = self._one(
            "class A {\n    fun m() {\n        work();\n    }\n}\n", "m", tmp_path
        )
        assert without.body_hash == with_semi.body_hash

    def test_enum_constant_edit_changes_enum_hash(self, tmp_path: Path) -> None:
        before = self._one("enum class E {\n    A,\n    B\n}\n", "E", tmp_path)
        after = self._one("enum class E {\n    A,\n    C\n}\n", "E", tmp_path)
        assert before.body_hash != after.body_hash

    def test_enum_entry_body_is_not_a_symbol(self, tmp_path: Path) -> None:
        """An enum-entry body's methods are not symbols (probe K11), so
        only the abstract declaration is indexed.
        """
        code = (
            "enum class E {\n"
            "    A {\n"
            "        override fun label(): String {\n"
            '            return "a"\n'
            "        }\n"
            "    };\n\n"
            "    abstract fun label(): String\n"
            "}\n"
        )
        assert [s.name for s in self._scan(code, tmp_path)] == ["E", "label"]

    def test_companion_method_edit_leaves_the_outer_shell(self, tmp_path: Path) -> None:
        """A companion object is a type body inside the class (probe K3):
        its methods are the outer class's methods, so editing one fires
        CHANGED_FUNCTION without dragging a coarse CHANGED_CLASS along.
        """
        before = (
            "class A {\n"
            "    val x = 1\n\n"
            "    companion object {\n"
            "        fun create(): A {\n"
            "            return A()\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        after = (
            "class A {\n"
            "    val x = 1\n\n"
            "    companion object {\n"
            "        fun create(): A {\n"
            "            val a = A()\n"
            "            return a\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        shell_before = self._one(before, "A", tmp_path, SymbolType.CLASS)
        shell_after = self._one(after, "A", tmp_path, SymbolType.CLASS)
        method_before = self._one(before, "create", tmp_path)
        method_after = self._one(after, "create", tmp_path)
        assert method_before.parent_class == "A"
        assert shell_before.body_hash == shell_after.body_hash
        assert method_before.body_hash != method_after.body_hash

    def test_secondary_constructor_edit_changes_its_own_hash_only(
        self, tmp_path: Path
    ) -> None:
        before_src = (
            "class A {\n"
            "    var x = 0\n\n"
            "    constructor(value: Int) {\n"
            "        this.x = value\n"
            "    }\n"
            "}\n"
        )
        after_src = (
            "class A {\n"
            "    var x = 0\n\n"
            "    constructor(value: Int) {\n"
            "        this.x = value + 1\n"
            "    }\n"
            "}\n"
        )
        # A secondary constructor is a METHOD named after its class.
        ctor_before = self._one(before_src, "A", tmp_path, SymbolType.METHOD)
        ctor_after = self._one(after_src, "A", tmp_path, SymbolType.METHOD)
        shell_before = self._one(before_src, "A", tmp_path, SymbolType.CLASS)
        shell_after = self._one(after_src, "A", tmp_path, SymbolType.CLASS)
        assert ctor_before.parent_class == "A"
        assert ctor_before.body_hash != ctor_after.body_hash
        assert shell_before.body_hash == shell_after.body_hash
