"""Phase 2 fixture probes J1–J12 — Java grammar shapes, pinned.

Every fact the Java scanner depends on was resolved **empirically**
against the pinned grammar (``tree-sitter-java 0.23.5``, ABI 14, on
``tree-sitter 0.26.0``) *before* any collector code was written — the
v16 lesson: a TS method-decorator bug shipped because a grammar shape
was assumed.  This module pins each resolution permanently, so a grammar
upgrade that changes a shape fails here instead of silently changing
scanner behaviour.

Resolved facts (probe → finding):

J1  ``method_invocation`` — one node type for every call form:
    ``foo()`` (no ``object`` field), ``obj.foo()`` (``object`` =
    ``identifier``), ``this.foo()`` (``object`` = ``this``),
    ``super.foo()`` (``object`` = ``super`` — a distinct keyword node,
    *not* a call), ``A.B.foo()`` (``object`` = ``field_access``),
    ``f().bar()`` (``object`` = ``method_invocation`` — the only shape
    whose receiver is a call), ``a[0].bar()`` (``object`` =
    ``array_access``).  The callee name is always the ``name`` field.
J2  ``new Foo(a)`` is an ``object_creation_expression`` (``type`` +
    ``arguments``) — **not** a ``method_invocation``.  Constructor
    invocations are therefore not call-shaped and are never captured as
    calls, matching the JS/TS ``new_expression`` boundary.
J3  ``Foo::bar`` is a ``method_reference`` node — a reference, not a
    call; excluded.
J4  Annotations are **children** of the declaration (wrapped in a
    ``modifiers`` node): ``@Override`` on a method lives *inside*
    ``method_declaration``; class-level ``@Deprecated`` inside
    ``class_declaration``.  No sibling-decorator folding is needed —
    annotation edits are part of the declaration's own hash.
J5  Constructors are ``constructor_declaration`` with ``name`` =
    the class name and ``body`` = ``constructor_body``.  A record's
    **compact** constructor is a *different* node type —
    ``compact_constructor_declaration`` (``name`` + ``body`` =
    ``block``) — discovered while building the sample suite and pinned
    here so the scanner cannot silently drop it (it is the record's
    canonical constructor).
J6  ``record_declaration`` (→ CLASS) and ``annotation_type_declaration``
    (``@interface``, → INTERFACE) both carry a ``name`` field;
    ``record`` bodies are ``class_body``.
J7  Java 15 text blocks are **not** a distinct node type: they parse as
    ``string_literal`` with ``\"\"\"`` delimiter tokens and a
    ``multiline_string_fragment`` child.  ``text_block`` (the name the
    v17 scope assumed) is not a node type in this grammar — quote
    normalization instead has to strip the three-character delimiter.
J8  Generics live in a ``type_parameters`` field (class and method) and
    ``generic_type``/``type_arguments`` nodes; the ``name`` field is a
    plain ``identifier``, so name extraction is unaffected.
J9  Interface default/static methods are ordinary ``method_declaration``
    nodes *with* a ``body`` field; abstract interface methods are the
    same node type *without* one.
J10 Nested/inner classes are ``class_declaration`` nodes that are direct
    children of the enclosing ``class_body``.
J11 ``enum_declaration`` → ``enum_body`` holding ``enum_constant``
    nodes plus an optional ``enum_body_declarations`` block that
    *contains* the enum's fields/constructors/methods.
J12 Semicolons are required syntax and appear as ``;`` leaf tokens —
    hashed as content (never in the ASI exclusion set).

Additional boundaries pinned here because the call/symbol model depends
on them: local classes (``class_declaration`` inside a ``block``),
anonymous classes (``object_creation_expression`` with a ``class_body``
child — no name), ``lambda_expression`` (an anonymous function), and
``explicit_constructor_invocation`` (``this(0)`` / ``super(0)``).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import tree_sitter_java as ts_java
from tree_sitter import Language, Node, Parser

_LANGUAGE = Language(ts_java.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: str) -> Node:
    root = _PARSER.parse(source.encode()).root_node
    assert not root.has_error, f"probe snippet failed to parse: {source!r}"
    return root


def _walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _all(root: Node, node_type: str) -> list[Node]:
    return [n for n in _walk(root) if n.type == node_type]


def _text(node: Node, source: str) -> str:
    return source.encode()[node.start_byte : node.end_byte].decode()


def _only(root: Node, node_type: str) -> Node:
    found = _all(root, node_type)
    assert len(found) == 1, f"expected exactly one {node_type}, got {len(found)}"
    return found[0]


def _expr(node: Node, source: str, text: str) -> Node:
    """The unique ``method_invocation`` whose source text is exactly *text*."""
    matches = [
        n
        for n in _all(node, "method_invocation")
        if _text(n, source) == text or _text(n, source) == text + ";"
    ]
    assert len(matches) == 1, f"expected one invocation {text!r}, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# J1 — method_invocation receiver shapes
# ---------------------------------------------------------------------------


class TestJ1MethodInvocationShapes:
    """J1: every call form is a ``method_invocation``; the callee is ``name``."""

    SOURCE = """\
class A {
  void m() {
    foo();
    obj.foo();
    this.foo();
    super.foo();
    A.B.foo();
    f().bar();
    a[0].baz();
  }
}
"""

    def test_plain_call_has_no_object_field(self) -> None:
        node = _expr(_parse(self.SOURCE), self.SOURCE, "foo()")
        assert node.child_by_field_name("name") is not None
        assert _text(node.child_by_field_name("name"), self.SOURCE) == "foo"  # type: ignore[arg-type]
        assert node.child_by_field_name("object") is None

    def test_identifier_receiver_is_object_field(self) -> None:
        node = _expr(_parse(self.SOURCE), self.SOURCE, "obj.foo()")
        obj = node.child_by_field_name("object")
        assert obj is not None and obj.type == "identifier"

    def test_this_receiver_is_this_node(self) -> None:
        node = _expr(_parse(self.SOURCE), self.SOURCE, "this.foo()")
        obj = node.child_by_field_name("object")
        assert obj is not None and obj.type == "this"

    def test_super_receiver_is_super_node_not_a_call(self) -> None:
        """``super.foo()`` — ``super`` is a keyword node, not a call receiver."""
        node = _expr(_parse(self.SOURCE), self.SOURCE, "super.foo()")
        obj = node.child_by_field_name("object")
        assert obj is not None and obj.type == "super"

    def test_qualified_receiver_is_field_access(self) -> None:
        node = _expr(_parse(self.SOURCE), self.SOURCE, "A.B.foo()")
        obj = node.child_by_field_name("object")
        assert obj is not None and obj.type == "field_access"

    def test_call_receiver_is_method_invocation(self) -> None:
        """``f().bar()`` — the only receiver shape that is itself a call."""
        node = _expr(_parse(self.SOURCE), self.SOURCE, "f().bar()")
        obj = node.child_by_field_name("object")
        assert obj is not None and obj.type == "method_invocation"

    def test_index_receiver_is_array_access(self) -> None:
        node = _expr(_parse(self.SOURCE), self.SOURCE, "a[0].baz()")
        obj = node.child_by_field_name("object")
        assert obj is not None and obj.type == "array_access"


# ---------------------------------------------------------------------------
# J2 — constructor invocation is not call-shaped
# ---------------------------------------------------------------------------


class TestJ2ObjectCreation:
    """J2: ``new Foo(...)`` is ``object_creation_expression``, never a call."""

    SOURCE = """\
class A {
  void m() {
    Foo f = new Foo(a);
  }
}
"""

    def test_object_creation_node_shape(self) -> None:
        root = _parse(self.SOURCE)
        creation = _only(root, "object_creation_expression")
        assert _text(creation.child_by_field_name("type"), self.SOURCE) == "Foo"  # type: ignore[arg-type]
        assert creation.child_by_field_name("arguments") is not None

    def test_no_method_invocation_for_new(self) -> None:
        root = _parse(self.SOURCE)
        assert _all(root, "method_invocation") == []


# ---------------------------------------------------------------------------
# J3 — method references are not calls
# ---------------------------------------------------------------------------


class TestJ3MethodReference:
    """J3: ``Foo::bar`` is a ``method_reference``, not a call."""

    SOURCE = """\
class A {
  void m() {
    Runnable r = Foo::bar;
  }
}
"""

    def test_method_reference_node(self) -> None:
        root = _parse(self.SOURCE)
        assert len(_all(root, "method_reference")) == 1
        assert _all(root, "method_invocation") == []


# ---------------------------------------------------------------------------
# J4 — annotations are declaration children
# ---------------------------------------------------------------------------


class TestJ4Annotations:
    """J4: annotations live inside the declaration, under ``modifiers``."""

    METHOD_SOURCE = """\
class A {
  @Override
  void m() {}
}
"""

    CLASS_SOURCE = """\
@Deprecated
class A {
  @SuppressWarnings("x")
  int f = 1;
}
"""

    def test_method_annotation_is_inside_method_declaration(self) -> None:
        root = _parse(self.METHOD_SOURCE)
        method = _only(root, "method_declaration")
        assert _text(method, self.METHOD_SOURCE).startswith("@Override")
        modifiers = _only(method, "modifiers")
        assert (
            _only(modifiers, "marker_annotation").child_by_field_name("name")
            is not None
        )

    def test_annotated_declaration_starts_at_its_annotation(self) -> None:
        """Because annotations are *inside* the declaration, the node's
        start line — and therefore the symbol's ``line_number`` — is the
        first annotation's line.  This matches TypeScript, where a
        decorated ``class_declaration`` node also starts at its
        decorator; it is pinned so the behaviour is deliberate, not
        accidental."""
        root = _parse(self.METHOD_SOURCE)
        method = _only(root, "method_declaration")
        assert method.start_point[0] + 1 == 2  # ``@Override`` is line 2
        class_root = _parse(self.CLASS_SOURCE)
        cls = _only(class_root, "class_declaration")
        assert cls.start_point[0] + 1 == 1  # ``@Deprecated`` is line 1

    def test_class_and_field_annotations_are_children(self) -> None:
        root = _parse(self.CLASS_SOURCE)
        cls = _only(root, "class_declaration")
        assert _text(cls, self.CLASS_SOURCE).startswith("@Deprecated")
        field = _only(root, "field_declaration")
        assert _text(field, self.CLASS_SOURCE).startswith("@SuppressWarnings")
        # Exactly one class-body member: the field.  If the annotation were
        # a sibling it would appear as its own member and this would be 2.
        body = cls.child_by_field_name("body")
        assert body is not None
        assert len(body.named_children) == 1


# ---------------------------------------------------------------------------
# J5 — constructors
# ---------------------------------------------------------------------------


class TestJ5Constructors:
    """J5: ``constructor_declaration``, name = class name."""

    SOURCE = """\
class Foo {
  Foo(int x) { this.x = x; }
}
"""

    def test_constructor_shape(self) -> None:
        root = _parse(self.SOURCE)
        ctor = _only(root, "constructor_declaration")
        name = ctor.child_by_field_name("name")
        assert name is not None and _text(name, self.SOURCE) == "Foo"
        body = ctor.child_by_field_name("body")
        assert body is not None and body.type == "constructor_body"

    def test_explicit_constructor_invocation_is_not_a_method_invocation(self) -> None:
        src = """\
class Foo {
  Foo() { this(0); }
}
"""
        root = _parse(src)
        assert len(_all(root, "explicit_constructor_invocation")) == 1
        assert _all(root, "method_invocation") == []

    def test_compact_constructor_is_its_own_node_type(self) -> None:
        """A record's compact constructor is ``compact_constructor_declaration``."""
        src = """\
record Point(int x, int y) {
  public Point {
    if (x < 0) { throw new IllegalArgumentException(\"x\"); }
  }
}
"""
        root = _parse(src)
        compact = _only(root, "compact_constructor_declaration")
        name = compact.child_by_field_name("name")
        assert name is not None and _text(name, src) == "Point"
        body = compact.child_by_field_name("body")
        assert body is not None and body.type == "block"
        # The canonical form is still an ordinary constructor_declaration.
        assert _all(root, "constructor_declaration") == []


# ---------------------------------------------------------------------------
# J6 — records and annotation types
# ---------------------------------------------------------------------------


class TestJ6RecordsAndAnnotationTypes:
    """J6: record_declaration → CLASS, annotation_type_declaration → INTERFACE."""

    def test_record_declaration(self) -> None:
        src = "public record Point(int x, int y) {}\n"
        root = _parse(src)
        record = _only(root, "record_declaration")
        name = record.child_by_field_name("name")
        assert name is not None and _text(name, src) == "Point"
        assert record.child_by_field_name("body") is not None

    def test_annotation_type_declaration(self) -> None:
        src = 'public @interface Marker { String value() default "x"; }\n'
        root = _parse(src)
        annotation_type = _only(root, "annotation_type_declaration")
        name = annotation_type.child_by_field_name("name")
        assert name is not None and _text(name, src) == "Marker"
        body = annotation_type.child_by_field_name("body")
        assert body is not None and body.type == "annotation_type_body"


# ---------------------------------------------------------------------------
# J7 — text blocks and character literals
# ---------------------------------------------------------------------------


class TestJ7TextBlocks:
    """J7: text blocks are ``string_literal`` with ``\"\"\"`` delimiters."""

    SOURCE = '''\
class A {
  String s = """
      hello
      world""";
  String t = "plain";
  char c = 'x';
}
'''

    def test_text_block_is_a_string_literal(self) -> None:
        root = _parse(self.SOURCE)
        # ``text_block`` — the name the scope assumed — is not a node type.
        assert _all(root, "text_block") == []
        literals = _all(root, "string_literal")
        assert len(literals) == 2

    def test_text_block_delimiter_and_fragment(self) -> None:
        root = _parse(self.SOURCE)
        block = [
            n
            for n in _all(root, "string_literal")
            if _text(n, self.SOURCE).startswith('"""')
        ]
        assert len(block) == 1
        assert _all(block[0], "multiline_string_fragment")
        # The raw text keeps all three delimiter characters on each side —
        # one-character stripping would mangle it (the J7 finding).
        assert _text(block[0], self.SOURCE).startswith('"""')
        assert _text(block[0], self.SOURCE).endswith('"""')

    def test_character_literal_node_type(self) -> None:
        root = _parse(self.SOURCE)
        chars = _all(root, "character_literal")
        assert len(chars) == 1
        assert _text(chars[0], self.SOURCE) == "'x'"


# ---------------------------------------------------------------------------
# J8 — generics
# ---------------------------------------------------------------------------


class TestJ8Generics:
    """J8: generics are ``type_parameters``; the name field stays an identifier."""

    SOURCE = """\
class Box<T extends Comparable<T>> {
  <U> U id(U u) { return u; }
}
"""

    def test_class_type_parameters_field(self) -> None:
        root = _parse(self.SOURCE)
        cls = _only(root, "class_declaration")
        assert cls.child_by_field_name("type_parameters") is not None
        name = cls.child_by_field_name("name")
        assert name is not None and name.type == "identifier"

    def test_method_type_parameters_field(self) -> None:
        root = _parse(self.SOURCE)
        method = _only(root, "method_declaration")
        assert method.child_by_field_name("type_parameters") is not None
        name = method.child_by_field_name("name")
        assert name is not None and _text(name, self.SOURCE) == "id"


# ---------------------------------------------------------------------------
# J9 — interface method bodies
# ---------------------------------------------------------------------------


class TestJ9InterfaceMethods:
    """J9: default methods have a body; abstract ones do not."""

    SOURCE = """\
interface Greeter {
  String name();
  default String greet() { return "hi " + name(); }
}
"""

    def test_abstract_method_has_no_body_field(self) -> None:
        root = _parse(self.SOURCE)
        methods = {
            _text(m.child_by_field_name("name"), self.SOURCE): m
            for m in _all(root, "method_declaration")
        }  # type: ignore[arg-type]
        assert methods["name"].child_by_field_name("body") is None
        assert methods["greet"].child_by_field_name("body") is not None


# ---------------------------------------------------------------------------
# J10 — nested classes
# ---------------------------------------------------------------------------


class TestJ10NestedClasses:
    """J10: nested classes are ``class_declaration`` children of a ``class_body``."""

    SOURCE = """\
class Outer {
  static class Nested {
    void nm() {}
  }
}
"""

    def test_nested_class_is_a_class_body_child(self) -> None:
        root = _parse(self.SOURCE)
        outer = [n for n in _all(root, "class_declaration")][0]
        outer_body = outer.child_by_field_name("body")
        assert outer_body is not None
        nested = [c for c in outer_body.named_children if c.type == "class_declaration"]
        assert len(nested) == 1
        assert _text(nested[0].child_by_field_name("name"), self.SOURCE) == "Nested"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# J11 — enums
# ---------------------------------------------------------------------------


class TestJ11Enums:
    """J11: ``enum_declaration`` → ``enum_body`` with ``enum_constant``s."""

    SOURCE = """\
enum Planet {
  EARTH(1), MARS(2);
  private final int n;
  Planet(int n) { this.n = n; }
  int n() { return n; }
}
"""

    def test_enum_shape(self) -> None:
        root = _parse(self.SOURCE)
        enum = _only(root, "enum_declaration")
        assert _text(enum.child_by_field_name("name"), self.SOURCE) == "Planet"  # type: ignore[arg-type]
        constants = _all(root, "enum_constant")
        assert len(constants) == 2
        declarations = _only(root, "enum_body_declarations")
        types = {c.type for c in declarations.named_children}
        assert "field_declaration" in types
        assert "constructor_declaration" in types
        assert "method_declaration" in types


# ---------------------------------------------------------------------------
# J12 — semicolons are required syntax
# ---------------------------------------------------------------------------


class TestJ12Semicolons:
    """J12: ``;`` are real leaf tokens (hashed content, never excluded)."""

    SOURCE = """\
class A {
  void m() {
    int x = 1;
    return;
  }
}
"""

    def test_semicolons_are_leaf_tokens(self) -> None:
        root = _parse(self.SOURCE)
        semicolons = [n for n in _walk(root) if n.type == ";"]
        assert len(semicolons) == 2
        assert all(n.child_count == 0 for n in semicolons)


# ---------------------------------------------------------------------------
# Extra boundaries the call/symbol model depends on
# ---------------------------------------------------------------------------


class TestExtraBoundaries:
    """Local/anonymous classes, lambdas — resolved because the model needs them."""

    def test_local_class_sits_inside_a_block(self) -> None:
        src = """\
class A {
  void m() {
    class Local { void lm() {} }
  }
}
"""
        root = _parse(src)
        blocks = [
            b
            for b in _all(root, "block")
            if any(c.type == "class_declaration" for c in b.named_children)
        ]
        assert len(blocks) == 1, "local class must sit directly inside the method block"

    def test_anonymous_class_is_an_object_creation_with_class_body(self) -> None:
        src = """\
class A {
  Runnable r = new Runnable() { public void run() { helper(); } };
}
"""
        root = _parse(src)
        creation = _only(root, "object_creation_expression")
        bodies = [c for c in creation.children if c.type == "class_body"]
        assert len(bodies) == 1
        # No name node — an anonymous class has no class identifier.
        assert creation.child_by_field_name("name") is None

    def test_lambda_is_a_lambda_expression(self) -> None:
        src = """\
class A {
  void m() {
    xs.forEach(x -> helper(x));
  }
}
"""
        root = _parse(src)
        lambda_node = _only(root, "lambda_expression")
        assert lambda_node.child_by_field_name("body") is not None


# ---------------------------------------------------------------------------
# Dependency floor
# ---------------------------------------------------------------------------


class TestDependencyFloor:
    """The pinned grammar floor must actually load and parse."""

    def test_grammar_floor_holds(self) -> None:
        import importlib.metadata as md

        version = md.version("tree-sitter-java")
        parts = tuple(int(p) for p in version.split(".")[:2])
        assert parts >= (0, 23), f"tree-sitter-java {version} below the >=0.23 floor"

    def test_language_loads_and_abi_is_supported(self) -> None:
        import tree_sitter

        assert _LANGUAGE is not None
        # tree-sitter 0.26 supports ABI 13–15; the grammar reports 14.
        assert 13 <= _LANGUAGE.abi_version <= 15
        assert tree_sitter.__version__ >= "0.26"

    def test_clean_parse_smoke(self) -> None:
        root = _PARSER.parse(b"class A { void m() { foo(); } }").root_node
        assert not root.has_error
        assert root.type == "program"


if __name__ == "__main__":  # pragma: no cover - manual probe aid
    raise SystemExit(pytest.main([__file__, "-v"]))
