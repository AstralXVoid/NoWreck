"""Phase 5 fixture probes E1–E14 — C++ grammar shapes, pinned.

Every fact the C++ scanner depends on was resolved **empirically** against
the pinned grammar (``tree-sitter-cpp 0.23.4``, ABI 14, on
``tree-sitter 0.26.0``) *before* any collector code was written — the v16
lesson: a grammar shape must never be assumed.  This module pins each
resolution permanently, so a grammar upgrade that changes a shape fails
here instead of silently changing scanner behaviour.

One assumption the probes **broke**: the scope document names the
``using X = Y`` node ``type_alias_declaration``.  The grammar actually
calls it ``alias_declaration`` (``type_alias_declaration`` exists in
*other* grammars, not this one) — the collector uses the real node type
pinned in :class:`TestE17TypeDeclarations`.

Grammar choice: the package exposes a single ``language()`` covering the
whole C++ grammar.  That grammar **also** parses C — a ``.h`` file is
matched by the extension list, so C headers in a mixed repo are parsed as
C++ (accepted edge, documented for Phase 7).  A C++-only construct in a
``.c`` file is irrelevant here because ``.c`` is not discovered.

Resolved facts (probe → finding):

E1  ``a.b()`` and ``a->b()`` are both a ``call_expression`` whose
    ``function`` field is a ``field_expression``; the member name is the
    ``field`` field (a ``field_identifier``) and the receiver is the
    ``argument`` field.  ``.`` and ``->`` are interchangeable unnamed
    ``operator`` children, so both spellings resolve identically.
E2  ``ns::func()`` / ``Class::static()`` / ``::global_fn()`` are
    ``call_expression`` nodes whose ``function`` field is a
    ``qualified_identifier`` (``scope`` + ``name``); ``a::b::c()`` nests a
    ``qualified_identifier`` in the ``name`` field.  A template call
    (``std::move``) keeps the head identifier in a ``template_function``
    ``name`` child.  The scanner takes the innermost ``name``.
E3  ``operator+`` / ``operator<<`` / ``operator[]`` / ``operator()`` are
    ``operator_name`` nodes (``declarator`` field of the
    ``function_declarator``) holding the ``operator`` keyword plus the
    operator token; the name is the node's text.  A reference return type
    wraps the ``function_declarator`` in a ``reference_declarator``, so a
    declarator walk is required.
E4  ``new Foo()`` is a ``new_expression`` and ``Foo obj(3)`` an
    ``init_declarator`` whose ``value`` is an ``argument_list`` — neither
    is call-shaped, so neither is captured.  ``std::vector<int>(10)``
    **is** a ``call_expression`` (templated type in a ``template_function``
    name) and is captured as ``vector``.  Policy: only grammar-exposed
    call shapes are captured; everything else is excluded, never guessed.
E5  ``template <typename T>`` is a **sibling wrapper**
    (``template_declaration``) around the declaration, holding the
    ``template_parameter_list`` and the wrapped
    ``function_definition``/``class_specifier``/``struct_specifier``/
    ``alias_declaration`` as children.  A template-parameter edit is
    therefore *outside* the wrapped node and must be folded into the
    symbol's hash (the v16 TS-decorator lesson, generalised).
E6  ``#ifdef`` regions are ``preproc_ifdef`` nodes embedded **inside**
    the enclosing ``compound_statement`` (with a ``preproc_else``
    alternative), so a conditional edit is part of the enclosing
    function's span and fires ``CHANGED_FUNCTION``.  There is no
    conditional-aware hashing.
E7  String leaves: ``string_literal`` (with an optional encoding prefix as
    an unnamed child), ``raw_string_literal`` (``R"(...)"``),
    ``char_literal``, and ``concatenated_string`` (adjacent literals).
    Raw strings are a distinct node type, so raw vs interpreted can never
    collide; ``concatenated_string`` is *not* treated as one leaf (it
    recurses into its ``string_literal`` children).  A numeric
    user-defined literal (``1"_km"``) is a grammar parse error (loud).
E8  C++ ``;`` is a required syntax token (a leaf node type ``;``) and is
    **hashed as content** — it is deliberately absent from
    ``ASI_LEAF_EXCLUSIONS``.
E9  Declaration-only members have **no** ``compound_statement``: a
    module-scope ``int add(int,int);`` is a ``declaration`` with a
    ``function_declarator``; a class-body member with a return type
    (``void draw();``) is a ``field_declaration`` with a
    ``function_declarator``; and an in-class constructor/destructor
    declaration is a ``declaration``.  ``= default`` / ``= delete`` are
    ``function_definition`` nodes with **no** body but a
    ``default_method_clause`` / ``delete_method_clause`` child — they are
    definitions, so they are hashed normally.
E10 The comment node type is ``comment``.
E11 Overload semantics are detector-level and pinned in
    ``tests/test_change_detector.py``: ``Symbol`` identity is
    ``(name, kind, file, parent_class)``, so same-identity overloads
    dedupe in the ADD/REMOVE set-diff and the body-hash pass is
    last-wins.  The scanner emits both overloads; the coarse behaviour is
    the detector's.
E12 A lambda is a ``lambda_expression`` (``captures`` +
    ``abstract_function_declarator`` + ``compound_statement`` body).  On
    the right of ``auto f = ...`` it is the ``init_declarator``'s
    ``value``, mirroring the JS ``const f = () => {}`` shape the scanner
    indexes as a FUNCTION.
E13 ``= default`` / ``= delete`` become ``default_method_clause`` /
    ``delete_method_clause`` **inside** the ``function_definition``;
    ``override`` becomes a ``virtual_specifier`` and ``noexcept`` an
    ``noexcept`` child **inside** the ``function_declarator``.  All four
    are hashed naturally with their declaration.
E14 A destructor's name lives in a ``destructor_name`` node (``~`` +
    ``identifier``); a constructor's is a plain ``identifier``.  Both are
    METHOD symbols.  An out-of-line definition
    (``void Widget::draw() {}``) puts a ``qualified_identifier`` in the
    declarator, whose ``scope`` is the class and whose ``name`` is the
    member — how the ``.cpp`` side of a header/impl split is attributed.

Additional boundaries pinned here because the symbol/hash/call model
depends on them (each was probed, not assumed):

- Class-body members appear as ``function_definition`` (a definition,
  including ``= default``/``= delete``), ``field_declaration`` (a data
  field, or a declaration-only method with a ``function_declarator``), or
  ``declaration`` (an in-class constructor/destructor declaration).
- ``enum``/``enum class`` are ``enum_specifier`` with a ``name`` field and
  an ``enumerator_list`` body; ``enum class`` adds a ``class`` child and
  an optional ``base``.
- ``using X = Y`` is an ``alias_declaration``; ``using namespace std;`` is
  a ``using_declaration`` (not an alias); ``typedef`` is a
  ``type_definition``.
- ``namespace_definition``'s body is a ``declaration_list``;
  ``namespace a::b {}`` uses a ``nested_namespace_specifier`` name.
- ``extern "C" { ... }`` is a ``linkage_specification`` with a
  ``declaration_list`` body — a module-scope wrapper like a namespace.
- An attribute (``[[nodiscard]]``) is an ``attribute_declaration``
  **child** of the declaration it annotates (both ``function_definition``
  and ``field_declaration``), so no sibling folding is needed.
- ``friend void helper(V&);`` is a ``friend_declaration`` wrapping a
  ``declaration`` — it declares a non-member, so it yields no symbol.
- A qualified out-of-line declarator's ``scope`` is a
  ``namespace_identifier`` *even when the qualifier is a class* (the
  grammar cannot tell them apart) and a ``template_type`` for
  ``Box<T>::put`` — the scanner keeps the head identifier (``Box``),
  mirroring the Rust generic-``impl`` rule.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import tree_sitter_cpp as ts_cpp
from tree_sitter import Language, Node, Parser

_LANGUAGE = Language(ts_cpp.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: str) -> Node:
    root = _PARSER.parse(source.encode()).root_node
    assert not root.has_error, f"probe snippet failed to parse: {source!r}"
    return root


def _parse_tolerantly(source: str) -> Node:
    """Parse without asserting — for snippets that pin a grammar defect."""
    return _PARSER.parse(source.encode()).root_node


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


def _named_types(node: Node) -> list[str]:
    return [child.type for child in node.named_children]


def _direct_token(node: Node, token: str) -> bool:
    return any(child.type == token for child in node.children)


def _by_text(root: Node, node_type: str, source: str, text: str) -> Node:
    """The unique *node_type* whose source text is exactly *text*."""
    matches = [n for n in _all(root, node_type) if _text(n, source) == text]
    assert len(matches) == 1, f"expected one {node_type} {text!r}, got {len(matches)}"
    return matches[0]


def _field_text(node: Node, field: str, source: str) -> str:
    child = node.child_by_field_name(field)
    assert child is not None, f"field {field!r} missing on {node.type}"
    return _text(child, source)


# ---------------------------------------------------------------------------
# Dependency floor
# ---------------------------------------------------------------------------


class TestDependencyFloor:
    """The pinned grammar floor must load and parse C++ without error."""

    def test_dependency_floor_is_the_installed_grammar(self) -> None:
        import importlib.metadata as md

        version = md.version("tree-sitter-cpp")
        parts = tuple(int(p) for p in version.split(".")[:2])
        assert parts >= (0, 23), f"tree-sitter-cpp {version} below the >=0.23 floor"
        assert _LANGUAGE.abi_version == 14, "grammar ABI changed — re-verify probes"
        assert not _PARSER.parse(b"int main() { return 0; }\n").root_node.has_error

    def test_grammar_also_parses_c_constructs(self) -> None:
        """Accepted edge: the C++ grammar parses C (a ``.h`` C header)."""
        root = _parse("int add(int a, int b) { return a + b; }\n")
        assert _named_types(root) == ["function_definition"]


# ---------------------------------------------------------------------------
# E1 — member and arrow calls
# ---------------------------------------------------------------------------


class TestE1MemberCalls:
    """E1: ``a.b()`` and ``a->b()`` share the ``field_expression`` shape."""

    SOURCE = """\
void f() {
  a.b();
  a->b();
  this->x();
}
"""

    def test_dot_and_arrow_share_one_shape(self) -> None:
        root = _parse(self.SOURCE)
        dot = _by_text(root, "field_expression", self.SOURCE, "a.b")
        arrow = _by_text(root, "field_expression", self.SOURCE, "a->b")
        for node in (dot, arrow):
            assert node.parent is not None and node.parent.type == "call_expression"
            assert node.child_by_field_name("function") is None
            assert _field_text(node, "field", self.SOURCE) == "b"
            assert node.child_by_field_name("argument") is not None
        assert _direct_token(dot, ".") and _direct_token(arrow, "->")

    def test_member_name_is_a_field_identifier(self) -> None:
        root = _parse(self.SOURCE)
        dot = _by_text(root, "field_expression", self.SOURCE, "a.b")
        field = dot.child_by_field_name("field")
        assert field is not None and field.type == "field_identifier"

    def test_this_is_a_plain_receiver(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "field_expression", self.SOURCE, "this->x")
        argument = call.child_by_field_name("argument")
        assert argument is not None and argument.type == "this"


# ---------------------------------------------------------------------------
# E2 — qualified calls
# ---------------------------------------------------------------------------


class TestE2QualifiedCalls:
    """E2: ``ns::f()`` keeps its target in a ``qualified_identifier``."""

    SOURCE = """\
void f() {
  ns::func();
  Class::static_method();
  a::b::c();
  ::global_fn();
  std::vector<int>(x);
}
"""

    def test_qualified_call_shape(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "call_expression", self.SOURCE, "ns::func()")
        target = call.child_by_field_name("function")
        assert target is not None and target.type == "qualified_identifier"
        assert _field_text(target, "scope", self.SOURCE) == "ns"
        assert _field_text(target, "name", self.SOURCE) == "func"

    def test_nested_qualifier_recurses_in_the_name_field(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "call_expression", self.SOURCE, "a::b::c()")
        target = call.child_by_field_name("function")
        assert target is not None
        name = target.child_by_field_name("name")
        assert name is not None and name.type == "qualified_identifier"
        assert _field_text(name, "name", self.SOURCE) == "c"

    def test_leading_scope_operator_has_no_scope_child(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "call_expression", self.SOURCE, "::global_fn()")
        target = call.child_by_field_name("function")
        assert target is not None and target.type == "qualified_identifier"
        assert target.child_by_field_name("scope") is None
        assert _field_text(target, "name", self.SOURCE) == "global_fn"

    def test_templated_call_keeps_head_identifier(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "call_expression", self.SOURCE, "std::vector<int>(x)")
        target = call.child_by_field_name("function")
        assert target is not None
        name = target.child_by_field_name("name")
        assert name is not None and name.type == "template_function"
        assert _field_text(name, "name", self.SOURCE) == "vector"


# ---------------------------------------------------------------------------
# E3 — operator names
# ---------------------------------------------------------------------------


class TestE3OperatorNames:
    """E3: operator declarations put an ``operator_name`` in the declarator."""

    SOURCE = """\
struct V {
  V operator+(const V& o) const { return o; }
  V& operator+=(const V& o) { return *this; }
  int operator[](int i);
  void operator()();
};
"""

    def test_operator_name_holds_the_token(self) -> None:
        root = _parse(self.SOURCE)
        plus = _by_text(root, "operator_name", self.SOURCE, "operator+")
        assert _direct_token(plus, "operator")
        assert _text(plus, self.SOURCE) == "operator+"

    def test_reference_declarator_wraps_the_function_declarator(self) -> None:
        """``V& operator+=`` nests the function declarator under ``&``."""
        root = _parse(self.SOURCE)
        name = _by_text(root, "operator_name", self.SOURCE, "operator+=")
        assert name.parent is not None and name.parent.type == "function_declarator"
        wrapper = name.parent.parent
        assert wrapper is not None and wrapper.type == "reference_declarator"

    @pytest.mark.parametrize("text", ["operator[]", "operator()"])
    def test_subscript_and_call_operators(self, text: str) -> None:
        root = _parse(self.SOURCE)
        node = _by_text(root, "operator_name", self.SOURCE, text)
        assert _text(node, self.SOURCE) == text


# ---------------------------------------------------------------------------
# E4 — constructor invocation policy
# ---------------------------------------------------------------------------


class TestE4ConstructionPolicy:
    """E4: only grammar-exposed call shapes are captured."""

    SOURCE = """\
void f() {
  auto* p = new Foo(1, 2);
  Foo obj(3);
  Foo braced{4};
  auto v = std::vector<int>(10);
  Bar::Bar(5);
}
"""

    def test_new_expression_is_not_call_shaped(self) -> None:
        root = _parse(self.SOURCE)
        node = _by_text(root, "new_expression", self.SOURCE, "new Foo(1, 2)")
        assert not _all(node, "call_expression")

    def test_brace_and_paren_initialisation_is_not_call_shaped(self) -> None:
        root = _parse(self.SOURCE)
        paren = _by_text(root, "init_declarator", self.SOURCE, "obj(3)")
        value = paren.child_by_field_name("value")
        assert value is not None and value.type == "argument_list"
        braced = _by_text(root, "init_declarator", self.SOURCE, "braced{4}")
        brace_value = braced.child_by_field_name("value")
        assert brace_value is not None and brace_value.type == "initializer_list"

    def test_templated_type_construction_is_call_shaped(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "call_expression", self.SOURCE, "std::vector<int>(10)")
        target = call.child_by_field_name("function")
        assert target is not None and target.type == "qualified_identifier"

    def test_qualified_constructor_call_is_call_shaped(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "call_expression", self.SOURCE, "Bar::Bar(5)")
        target = call.child_by_field_name("function")
        assert target is not None and target.type == "qualified_identifier"
        assert _field_text(target, "name", self.SOURCE) == "Bar"


# ---------------------------------------------------------------------------
# E5 — template prefix attachment
# ---------------------------------------------------------------------------


class TestE5TemplatePrefix:
    """E5: ``template <...>`` is a sibling wrapper, not part of the body."""

    SOURCE = """\
template <typename T>
T identity(T x) { return x; }

template <class T>
struct Wrapper { T value; };

template <typename T>
using Alias = Wrapper<T>;
"""

    def test_template_declaration_is_the_wrapper(self) -> None:
        root = _parse(self.SOURCE)
        decls = _all(root, "template_declaration")
        assert len(decls) == 3
        assert _named_types(decls[0]) == [
            "template_parameter_list",
            "function_definition",
        ]
        assert _named_types(decls[1]) == ["template_parameter_list", "struct_specifier"]
        assert _named_types(decls[2]) == [
            "template_parameter_list",
            "alias_declaration",
        ]

    def test_parameter_list_is_outside_the_function_node(self) -> None:
        """A template-param edit must be folded into the symbol's hash."""
        root = _parse(self.SOURCE)
        function = _only(root, "function_definition")
        assert not _all(function, "template_parameter_list")
        wrapper = function.parent
        assert wrapper is not None and wrapper.type == "template_declaration"
        assert _all(wrapper, "template_parameter_list")

    def test_template_parameter_list_is_not_a_symbol_source(self) -> None:
        root = _parse(self.SOURCE)
        params = _all(root, "template_parameter_list")[0]
        assert not _all(params, "function_definition")
        assert not _all(params, "class_specifier")


# ---------------------------------------------------------------------------
# E6 — preprocessor regions
# ---------------------------------------------------------------------------


class TestE6Preprocessor:
    """E6: ``#ifdef`` bodies are embedded in the enclosing function."""

    SOURCE = """\
void f() {
#ifdef DEBUG
  debug_log(x);
#else
  quiet();
#endif
  auto n = 1;
}
"""

    def test_preproc_ifdef_inside_the_body(self) -> None:
        root = _parse(self.SOURCE)
        function = _only(root, "function_definition")
        body = function.child_by_field_name("body")
        assert body is not None and body.type == "compound_statement"
        ifdef = _only(root, "preproc_ifdef")
        assert ifdef.parent == body
        assert _all(ifdef, "preproc_else")

    def test_conditional_calls_live_inside_the_region(self) -> None:
        root = _parse(self.SOURCE)
        ifdef = _only(root, "preproc_ifdef")
        assert _by_text(ifdef, "call_expression", self.SOURCE, "debug_log(x)")
        assert _by_text(ifdef, "call_expression", self.SOURCE, "quiet()")


# ---------------------------------------------------------------------------
# E7 — string leaves
# ---------------------------------------------------------------------------


class TestE7Strings:
    """E7: raw strings are distinct; concatenation is not one leaf."""

    SOURCE = """\
void f() {
  const char* a = "hello";
  const char* b = R"(raw)";
  char c = 'x';
  auto d = "con" "cat";
  auto e = u8"u8";
}
"""

    def test_string_node_types(self) -> None:
        root = _parse(self.SOURCE)
        assert _by_text(root, "string_literal", self.SOURCE, '"hello"')
        assert _by_text(root, "raw_string_literal", self.SOURCE, 'R"(raw)"')
        assert _by_text(root, "char_literal", self.SOURCE, "'x'")

    def test_encoding_prefix_is_an_unnamed_child(self) -> None:
        root = _parse(self.SOURCE)
        literal = _by_text(root, "string_literal", self.SOURCE, 'u8"u8"')
        assert literal.child(0).type == 'u8"'

    def test_concatenation_is_a_container_node(self) -> None:
        root = _parse(self.SOURCE)
        joined = _by_text(root, "concatenated_string", self.SOURCE, '"con" "cat"')
        assert [c.type for c in joined.named_children] == [
            "string_literal",
            "string_literal",
        ]

    def test_raw_and_interpreted_are_different_node_types(self) -> None:
        root = _parse(self.SOURCE)
        raw = _by_text(root, "raw_string_literal", self.SOURCE, 'R"(raw)"')
        plain = _by_text(root, "string_literal", self.SOURCE, '"hello"')
        assert raw.type != plain.type

    def test_user_defined_literal_is_a_loud_parse_error(self) -> None:
        root = _parse_tolerantly('void f() { auto h = 1"_km"; }\n')
        assert root.has_error


# ---------------------------------------------------------------------------
# E8 — semicolons
# ---------------------------------------------------------------------------


class TestE8Semicolons:
    """E8: ``;`` is required syntax and stays in the hash."""

    def test_semicolon_is_a_leaf_token(self) -> None:
        root = _parse("int x;\n")
        assert _direct_token(_only(root, "declaration"), ";")

    def test_semicolon_affects_the_structural_hash(self) -> None:
        """C++ passes no exclusion set, so ``;`` stays in the hash.

        The shared helper can drop a leaf type; hashing the same node with
        ``;`` excluded must change the digest, which is why the C++
        collector never forwards ``ASI_LEAF_EXCLUSIONS``.
        """
        from nowreck.scanner._tree_sitter_helpers import structural_hash

        source = "int x;\n"
        declaration = _only(_parse(source), "declaration")
        data = source.encode()
        assert structural_hash(declaration, data) != structural_hash(
            declaration, data, excluded_leaf_types=frozenset({";"})
        )


# ---------------------------------------------------------------------------
# E9 — declaration-only members
# ---------------------------------------------------------------------------


class TestE9DeclarationOnly:
    """E9: declaration-only members have no ``compound_statement``."""

    SOURCE = """\
int add(int a, int b);

class Widget {
 public:
  Widget();
  ~Widget();
  void draw();
  virtual void update() = 0;
 private:
  int id;
};
"""

    def test_top_level_declaration_shape(self) -> None:
        root = _parse(self.SOURCE)
        decl = _by_text(root, "declaration", self.SOURCE, "int add(int a, int b);")
        declarator = decl.child_by_field_name("declarator")
        assert declarator is not None
        assert declarator.type == "function_declarator"
        assert not _all(decl, "compound_statement")

    def test_class_body_declaration_only_uses_declaration_and_field(self) -> None:
        root = _parse(self.SOURCE)
        ctor = _by_text(root, "declaration", self.SOURCE, "Widget();")
        assert ctor.child_by_field_name("declarator").type == "function_declarator"
        draw = _by_text(root, "field_declaration", self.SOURCE, "void draw();")
        assert draw.child_by_field_name("declarator").type == "function_declarator"
        field = _by_text(root, "field_declaration", self.SOURCE, "int id;")
        assert field.child_by_field_name("declarator").type == "field_identifier"

    def test_pure_virtual_is_a_field_declaration(self) -> None:
        root = _parse(self.SOURCE)
        update = _by_text(
            root, "field_declaration", self.SOURCE, "virtual void update() = 0;"
        )
        assert update.child_by_field_name("default_value") is not None

    def test_default_and_delete_are_definitions_without_a_body(self) -> None:
        root = _parse("class W { public: W() = default; W(const W&) = delete; };\n")
        definitions = _all(root, "function_definition")
        assert len(definitions) == 2
        for node in definitions:
            assert not _all(node, "compound_statement")
        assert _all(root, "default_method_clause")
        assert _all(root, "delete_method_clause")


# ---------------------------------------------------------------------------
# E10 — comments
# ---------------------------------------------------------------------------


class TestE10Comments:
    """E10: the comment node type is ``comment``."""

    def test_comment_node_type(self) -> None:
        root = _parse("// line\n/* block */\nint x;\n")
        comments = _all(root, "comment")
        assert len(comments) == 2

    def test_comment_is_in_the_shared_set(self) -> None:
        from nowreck.scanner._tree_sitter_helpers import COMMENT_NODE_TYPES

        assert "comment" in COMMENT_NODE_TYPES


# ---------------------------------------------------------------------------
# E12 — lambdas
# ---------------------------------------------------------------------------


class TestE12Lambdas:
    """E12: ``auto f = [](){...}`` mirrors the JS arrow-function shape."""

    SOURCE = """\
void f() {
  auto g = [](int x) { return helper(x); };
  auto h = [&](int y) { return y + 1; }(3);
}
"""

    def test_lambda_shape(self) -> None:
        root = _parse(self.SOURCE)
        lambda_node = _by_text(
            root,
            "lambda_expression",
            self.SOURCE,
            "[](int x) { return helper(x); }",
        )
        assert _named_types(lambda_node) == [
            "lambda_capture_specifier",
            "abstract_function_declarator",
            "compound_statement",
        ]
        assert _direct_token(lambda_node.named_children[0], "[")

    def test_assigned_lambda_is_the_init_declarator_value(self) -> None:
        root = _parse(self.SOURCE)
        declarator = _by_text(
            root, "init_declarator", self.SOURCE, "g = [](int x) { return helper(x); }"
        )
        value = declarator.child_by_field_name("value")
        assert value is not None and value.type == "lambda_expression"

    def test_immediately_invoked_lambda_is_a_call_target(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(
            root, "call_expression", self.SOURCE, "[&](int y) { return y + 1; }(3)"
        )
        target = call.child_by_field_name("function")
        assert target is not None and target.type == "lambda_expression"


# ---------------------------------------------------------------------------
# E13 — default/delete/override/noexcept placement
# ---------------------------------------------------------------------------


class TestE13Specifiers:
    """E13: the four specifiers live inside their declaration node."""

    SOURCE = """\
class W {
 public:
  void draw() override;
  void run() noexcept;
};
void W::draw() override { render(); }
"""

    def test_override_and_noexcept_are_inside_the_declarator(self) -> None:
        root = _parse(self.SOURCE)
        draw = _by_text(root, "field_declaration", self.SOURCE, "void draw() override;")
        declarator = draw.child_by_field_name("declarator")
        assert declarator is not None and _all(declarator, "virtual_specifier")
        run = _by_text(root, "field_declaration", self.SOURCE, "void run() noexcept;")
        run_declarator = run.child_by_field_name("declarator")
        assert run_declarator is not None and _all(run_declarator, "noexcept")

    def test_out_of_line_override_is_inside_the_function(self) -> None:
        root = _parse(self.SOURCE)
        definition = _by_text(
            root,
            "function_definition",
            self.SOURCE,
            "void W::draw() override { render(); }",
        )
        assert _all(definition, "virtual_specifier")


# ---------------------------------------------------------------------------
# E14 — constructors, destructors, out-of-line definitions
# ---------------------------------------------------------------------------


class TestE14Constructors:
    """E14: ctor/dtor names and the header/impl qualifier shape."""

    SOURCE = """\
struct Pt {
  Pt(int x) : x_(x) {}
  ~Pt() {}
  int x_;
};
void Pt::draw() { render(); }
"""

    def test_constructor_name_is_an_identifier(self) -> None:
        root = _parse(self.SOURCE)
        definition = _by_text(
            root, "function_definition", self.SOURCE, "Pt(int x) : x_(x) {}"
        )
        declarator = definition.child_by_field_name("declarator")
        assert declarator is not None
        name = declarator.child_by_field_name("declarator")
        assert name is not None and name.type == "identifier"
        assert _text(name, self.SOURCE) == "Pt"

    def test_destructor_name_node(self) -> None:
        root = _parse(self.SOURCE)
        destructor = _by_text(root, "destructor_name", self.SOURCE, "~Pt")
        assert _direct_token(destructor, "~")

    def test_out_of_line_definition_qualifier(self) -> None:
        root = _parse(self.SOURCE)
        definition = _by_text(
            root, "function_definition", self.SOURCE, "void Pt::draw() { render(); }"
        )
        declarator = definition.child_by_field_name("declarator")
        assert declarator is not None
        qualified = declarator.child_by_field_name("declarator")
        assert qualified is not None and qualified.type == "qualified_identifier"
        assert _field_text(qualified, "scope", self.SOURCE) == "Pt"
        assert _field_text(qualified, "name", self.SOURCE) == "draw"

    TEMPLATE_SOURCE = "template <typename T>\nvoid Box<T>::put(T v) { store(v); }\n"

    def test_template_type_scope_keeps_the_head_identifier(self) -> None:
        root = _parse(self.TEMPLATE_SOURCE)
        put = _by_text(
            root,
            "function_definition",
            self.TEMPLATE_SOURCE,
            "void Box<T>::put(T v) { store(v); }",
        )
        declarator = put.child_by_field_name("declarator")
        assert declarator is not None
        qualified = declarator.child_by_field_name("declarator")
        assert qualified is not None
        scope = qualified.child_by_field_name("scope")
        assert scope is not None and scope.type == "template_type"
        head = scope.child_by_field_name("name")
        assert head is not None
        assert _text(head, self.TEMPLATE_SOURCE) == "Box"


# ---------------------------------------------------------------------------
# Type declarations, wrappers, attributes (extra boundaries)
# ---------------------------------------------------------------------------


class TestE17TypeDeclarations:
    """Type-declaration node types: the ``type_alias_declaration`` trap."""

    SOURCE = """\
enum Color { RED, GREEN };
enum class Mode : int { ON, OFF };
using Alias = Widget;
using namespace std;
typedef int IntAlias;
"""

    def test_enum_specifier(self) -> None:
        root = _parse(self.SOURCE)
        color = _by_text(
            root, "enum_specifier", self.SOURCE, "enum Color { RED, GREEN }"
        )
        assert _field_text(color, "name", self.SOURCE) == "Color"
        body = color.child_by_field_name("body")
        assert body is not None and body.type == "enumerator_list"

    def test_scoped_enum_has_a_class_child_and_base(self) -> None:
        root = _parse(self.SOURCE)
        mode = _by_text(
            root, "enum_specifier", self.SOURCE, "enum class Mode : int { ON, OFF }"
        )
        assert _direct_token(mode, "class")
        assert _field_text(mode, "base", self.SOURCE) == "int"

    def test_using_alias_is_alias_declaration_not_type_alias_declaration(self) -> None:
        root = _parse(self.SOURCE)
        alias = _by_text(
            root, "alias_declaration", self.SOURCE, "using Alias = Widget;"
        )
        assert _field_text(alias, "name", self.SOURCE) == "Alias"
        assert not _all(root, "type_alias_declaration")

    def test_using_namespace_is_not_an_alias(self) -> None:
        root = _parse(self.SOURCE)
        using_ns = _by_text(
            root, "using_declaration", self.SOURCE, "using namespace std;"
        )
        assert using_ns.child_by_field_name("name") is None

    def test_typedef_is_a_type_definition(self) -> None:
        root = _parse(self.SOURCE)
        typedef = _by_text(
            root, "type_definition", self.SOURCE, "typedef int IntAlias;"
        )
        assert _field_text(typedef, "declarator", self.SOURCE) == "IntAlias"


class TestE17ModuleWrappers:
    """Namespaces, nested namespaces and ``extern "C"`` all descend."""

    SOURCE = """\
namespace app { void run(); }
namespace a::b { void deep(); }
extern "C" { int c_fn(int); }
"""

    def test_namespace_body_is_a_declaration_list(self) -> None:
        root = _parse(self.SOURCE)
        app = _by_text(
            root, "namespace_definition", self.SOURCE, "namespace app { void run(); }"
        )
        body = app.child_by_field_name("body")
        assert body is not None and body.type == "declaration_list"

    def test_nested_namespace_specifier(self) -> None:
        root = _parse(self.SOURCE)
        deep = _by_text(
            root, "namespace_definition", self.SOURCE, "namespace a::b { void deep(); }"
        )
        name = deep.child_by_field_name("name")
        assert name is not None and name.type == "nested_namespace_specifier"

    def test_linkage_specification_body(self) -> None:
        root = _parse(self.SOURCE)
        linkage = _by_text(
            root, "linkage_specification", self.SOURCE, 'extern "C" { int c_fn(int); }'
        )
        body = linkage.child_by_field_name("body")
        assert body is not None and body.type == "declaration_list"


class TestE17AttributesAndFriend:
    """Attributes are children; friend declarations are not members."""

    SOURCE = """\
[[nodiscard]] int calc() { return 1; }
class V {
 public:
  [[nodiscard]] int member() const;
  friend void helper(V&);
};
"""

    def test_attribute_is_a_child_of_the_function_definition(self) -> None:
        root = _parse(self.SOURCE)
        definition = _by_text(
            root,
            "function_definition",
            self.SOURCE,
            "[[nodiscard]] int calc() { return 1; }",
        )
        assert _named_types(definition)[0] == "attribute_declaration"

    def test_attribute_is_a_child_of_the_field_declaration(self) -> None:
        root = _parse(self.SOURCE)
        member = _by_text(
            root, "field_declaration", self.SOURCE, "[[nodiscard]] int member() const;"
        )
        assert _named_types(member)[0] == "attribute_declaration"

    def test_friend_declaration_wraps_a_declaration(self) -> None:
        root = _parse(self.SOURCE)
        friend = _only(root, "friend_declaration")
        assert _named_types(friend) == ["declaration"]


# ---------------------------------------------------------------------------
# Call-receiver boundaries (shared with JS/TS/PHP)
# ---------------------------------------------------------------------------


class TestCallReceiverBoundaries:
    """A receiver that is itself a call has no static target."""

    SOURCE = """\
void f() {
  a.b.c();
  f().bar();
  (*ptr).m();
  arr[0]();
  p->q->r();
}
"""

    def test_field_chain_keeps_the_final_field(self) -> None:
        root = _parse(self.SOURCE)
        chain = _by_text(root, "field_expression", self.SOURCE, "a.b.c")
        assert _field_text(chain, "field", self.SOURCE) == "c"
        argument = chain.child_by_field_name("argument")
        assert argument is not None and argument.type == "field_expression"

    def test_call_receiver_is_a_call_expression(self) -> None:
        root = _parse(self.SOURCE)
        member = _by_text(root, "field_expression", self.SOURCE, "f().bar")
        argument = member.child_by_field_name("argument")
        assert argument is not None and argument.type == "call_expression"

    def test_parenthesised_receiver_is_not_a_call_node(self) -> None:
        root = _parse(self.SOURCE)
        member = _by_text(root, "field_expression", self.SOURCE, "(*ptr).m")
        argument = member.child_by_field_name("argument")
        assert argument is not None and argument.type == "parenthesized_expression"

    def test_subscript_call_target_is_not_a_static_name(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "call_expression", self.SOURCE, "arr[0]()")
        target = call.child_by_field_name("function")
        assert target is not None and target.type == "subscript_expression"


# ---------------------------------------------------------------------------
# E18 — the Phase 5 review shape set: wrapped types and declarator wrappers
# ---------------------------------------------------------------------------


class TestE18WrappedTypeDeclarations:
    """E18: a type specifier can hide inside a declaration node.

    A *tagged* declaration (``struct Foo { ... } obj;``), a nested type
    member (``struct B { ... };`` in a class body) and a braced ``typedef
    struct { ... } T;`` all wrap their ``struct_specifier``/``enum_specifier``
    as a child of a ``declaration``/``field_declaration``/``type_definition``
    (never as the declaration node itself), so a scope walk that does not
    descend into those nodes loses the type *and* its members.  A bodyless
    ``struct Foo;`` is a bare specifier with no body.
    """

    def test_tagged_declaration_wraps_the_specifier(self) -> None:
        source = "struct Foo { int x; } obj;\n"
        root = _parse(source)
        declaration = _only(root, "declaration")
        specifier = declaration.child_by_field_name("type")
        assert specifier is not None and specifier.type == "struct_specifier"
        assert declaration.child_by_field_name("declarator") is not None
        body = specifier.child_by_field_name("body")
        assert body is not None and body.type == "field_declaration_list"

    @pytest.mark.parametrize(
        ("source", "node_type"),
        [
            ("enum Color { RED } c;\n", "enum_specifier"),
            ("class W { int x; } w;\n", "class_specifier"),
        ],
    )
    def test_tagged_enum_and_class_share_the_shape(
        self, source: str, node_type: str
    ) -> None:
        root = _parse(source)
        specifier = _only(root, node_type)
        assert specifier.parent is not None
        assert specifier.parent.type == "declaration"
        assert specifier.parent.child_by_field_name("type") == specifier

    def test_nested_type_member_lives_in_a_field_declaration(self) -> None:
        source = "struct A { struct B { void m() {} }; };\n"
        root = _parse(source)
        nested = _by_text(root, "struct_specifier", source, "struct B { void m() {} }")
        assert nested.parent is not None and nested.parent.type == "field_declaration"
        assert nested.parent.child_by_field_name("type") == nested

    def test_typedef_wraps_the_specifier_and_the_alias(self) -> None:
        source = "typedef struct Foo { int x; } FooT;\n"
        root = _parse(source)
        definition = _only(root, "type_definition")
        specifier = definition.child_by_field_name("type")
        assert specifier is not None and specifier.type == "struct_specifier"
        tag = specifier.child_by_field_name("name")
        assert tag is not None and _text(tag, source) == "Foo"
        declarator = definition.child_by_field_name("declarator")
        assert declarator is not None and _text(declarator, source) == "FooT"

    def test_a_bodyless_specifier_is_a_forward_declaration(self) -> None:
        source = "struct Foo;\n"
        root = _parse(source)
        specifier = _only(root, "struct_specifier")
        assert specifier.child_by_field_name("body") is None
        assert specifier.parent is not None
        assert specifier.parent.type == "translation_unit"


class TestE18ModuleWrapperSingleDeclaration:
    """E18: the single-declaration ``extern "C"`` form has no body list.

    ``extern "C" { ... }`` puts a ``declaration_list`` in the ``body`` field,
    while ``extern "C" int f() { ... }`` puts the *declaration itself* there —
    so a scope walk that unconditionally recurses into ``body`` visits the
    declarator and the body as if they were declarations and drops the
    symbol.
    """

    def test_block_form_has_a_declaration_list(self) -> None:
        root = _parse('extern "C" { int f() { return 1; } }\n')
        linkage = _only(root, "linkage_specification")
        body = linkage.child_by_field_name("body")
        assert body is not None and body.type == "declaration_list"

    def test_single_definition_form_puts_the_definition_in_body(self) -> None:
        root = _parse('extern "C" int f() { return 1; }\n')
        linkage = _only(root, "linkage_specification")
        body = linkage.child_by_field_name("body")
        assert body is not None and body.type == "function_definition"

    def test_single_declaration_form_puts_the_declaration_in_body(self) -> None:
        root = _parse('extern "C" int f();\n')
        linkage = _only(root, "linkage_specification")
        body = linkage.child_by_field_name("body")
        assert body is not None and body.type == "declaration"


class TestE18DeclaratorWrappers:
    """E18: declarator shapes the name walk must reach through."""

    def test_reference_declarator_has_no_declarator_field(self) -> None:
        source = "struct A { A& get(); };\n"
        root = _parse(source)
        reference = _only(root, "reference_declarator")
        assert reference.child_by_field_name("declarator") is None
        assert _named_types(reference) == ["function_declarator"]

    def test_declaration_only_operator_uses_the_same_wrapper(self) -> None:
        source = "struct A { A& operator+=(int x); };\n"
        root = _parse(source)
        reference = _only(root, "reference_declarator")
        assert reference.child_by_field_name("declarator") is None
        operator = _by_text(root, "operator_name", source, "operator+=")
        assert operator.parent is not None
        assert operator.parent.type == "function_declarator"

    def test_conversion_operator_is_an_operator_cast(self) -> None:
        source = "struct B { operator bool() const { return true; } };\n"
        root = _parse(source)
        definition = _only(root, "function_definition")
        declarator = definition.child_by_field_name("declarator")
        assert declarator is not None and declarator.type == "operator_cast"
        assert _text(declarator, source) == "operator bool() const"
        assert declarator.children[-1].type == "abstract_function_declarator"
        assert _named_types(declarator)[0] == "primitive_type"

    def test_specialisation_name_is_a_template_function(self) -> None:
        source = "template <> void f<int>() {}\n"
        root = _parse(source)
        declarator = _only(root, "function_declarator")
        inner = declarator.child_by_field_name("declarator")
        assert inner is not None and inner.type == "template_function"
        name = inner.child_by_field_name("name")
        assert name is not None and _text(name, source) == "f"

    def test_member_template_call_field_is_a_template_method(self) -> None:
        source = "void f() { box.put<int>(v); }\n"
        root = _parse(source)
        field = _by_text(root, "field_expression", source, "box.put<int>")
        member = field.child_by_field_name("field")
        assert member is not None and member.type == "template_method"
        name = member.child_by_field_name("name")
        assert name is not None and _text(name, source) == "put"


class TestE18ClassFieldLambda:
    """E18: a class-field lambda has no ``init_declarator`` wrapper.

    At module scope ``auto f = [](){};`` is ``declaration`` →
    ``init_declarator`` → ``lambda_expression``; in a class body the grammar
    drops the ``init_declarator`` and puts a bare ``field_identifier`` before
    the lambda, so the field name comes from the lambda's previous sibling
    (a caller, never a symbol — the JS class-field arrow rule).
    """

    SOURCE = "struct W { auto f = []() { return g(); }; };\n"

    def test_field_lambda_is_not_an_init_declarator(self) -> None:
        root = _parse(self.SOURCE)
        field = _only(root, "field_declaration")
        assert _all(field, "init_declarator") == []

    def test_field_name_precedes_the_lambda(self) -> None:
        root = _parse(self.SOURCE)
        lambda_node = _only(root, "lambda_expression")
        previous = lambda_node.prev_named_sibling
        assert previous is not None and previous.type == "field_identifier"
        assert _text(previous, self.SOURCE) == "f"

    def test_module_scope_lambda_still_uses_init_declarator(self) -> None:
        root = _parse("auto f = []() { return g(); };\n")
        declarator = _only(root, "init_declarator")
        assert declarator.child_by_field_name("value") is not None


class TestE18GrammarErrorRecovery:
    """E18: the explicit operator-call syntax is a grammar error.

    ``b.operator bool()`` and ``a.operator+=(b)`` are valid C++ but the
    pinned grammar recovers with an ``ERROR`` node, leaving a stray
    identifier in call position — which the scanner must refuse to name.
    """

    def test_explicit_conversion_call_has_an_error_node(self) -> None:
        root = _parse_tolerantly("void f() { b.operator bool(); }\n")
        assert root.has_error
        assert _all(root, "ERROR")

    def test_explicit_operator_call_has_an_error_node(self) -> None:
        root = _parse_tolerantly("void f() { a.operator+=(b); }\n")
        assert root.has_error
        assert _all(root, "ERROR")
