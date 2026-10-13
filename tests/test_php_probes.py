"""Phase 4 fixture probes PH1–PH12 — PHP grammar shapes, pinned.

Every fact the PHP scanner depends on was resolved **empirically** against
the pinned grammar (``tree-sitter-php 0.24.1``, ABI 15, on
``tree-sitter 0.26.0``) *before* any collector code was written — the
v16 lesson: a grammar shape must never be assumed.  This module pins each
resolution permanently, so a grammar upgrade that changes a shape fails
here instead of silently changing scanner behaviour.

Grammar choice: the package ships **two** grammars —
``language_php()`` (the HTML-embedded grammar that matches the ``.php``
file format) and ``language_php_only()`` (a pure-source grammar).  The
choice is pinned by evidence below: ``php_only`` hard-errors on an HTML
template (``<html>`` + ``<?php ... ?>``), while ``php`` parses both a
template and a pure code file.  ``php`` is therefore the grammar the
scanner loads; a plain ``.php`` file that never opens ``<?php`` is
correctly one ``text`` node (PHP itself would treat those bytes as HTML
output, not code) and contributes no symbols.

Resolved facts (probe → finding):

PH1  ``$obj->method()`` is a ``member_call_expression`` whose ``name``
     field holds the method name and whose first named child is the
     receiver; ``$obj->prop`` (no call) is a ``member_access_expression``
     — a different node type, so property reads are never calls.
     ``$obj?->method()`` is its own node type
     (``nullsafe_member_call_expression``) with the same ``name`` field.
     A bare call is a ``function_call_expression`` whose callee sits in
     the **``function``** field — *not* ``name`` (the probe caught this
     assumption: ``function_call_expression.child_by_field_name("name")``
     is ``None``) — holding a ``name`` or ``qualified_name`` node.
PH2  ``Class::method()`` / ``self::`` / ``static::`` / ``parent::`` are
     ``scoped_call_expression`` nodes; the method name is the ``name``
     field, while the scope is a ``name``, ``qualified_name`` or
     ``relative_scope`` child.  A dynamic name (``Foo::$m()``) still
     occupies the ``name`` field, as a ``variable_name`` node — so the
     scanner's static-name test is the field's **node type**, not its
     presence (``$obj->{'weird'}()`` puts a ``string`` there, and
     ``$obj->$m()`` a ``variable_name``).
PH3  Namespaced calls resolve through ``qualified_name``: ``ns\\func()``
     is a ``function_call_expression`` whose ``function`` field is the
     ``qualified_name`` (whose own children are ``namespace_name`` +
     ``\\`` + ``name``), and ``Foo\\Bar::baz()`` keeps ``baz`` in the
     ``name`` field.  The scanner takes the final segment in both cases.
PH4  Attributes ``#[Route("/x")]`` are **children** of the declaration
     they annotate (an ``attribute_list`` child that starts the node),
     exactly like Java annotations — no sibling folding is needed, and an
     attribute edit is part of the declaration's own hash.
PH5  An anonymous class is an ``anonymous_class`` child of its
     ``object_creation_expression`` with **no** ``name`` field; its body
     is a ``declaration_list``.  It is never a symbol; its methods are
     callers with no class attribution.
PH6  A closure assignment is an ``assignment_expression`` whose left side
     is a ``variable_name`` and whose right side is an
     ``anonymous_function`` (``function () {}``) or ``arrow_function``
     (``fn () => ...``); ``static`` adds a ``static_modifier`` child.
     This is the PHP spelling of the JS ``const f = () => {}`` shape the
     scanner indexes as a FUNCTION symbol.
PH7  ``enum`` (PHP 8.1) is an ``enum_declaration`` with a ``name`` field
     and an ``enum_declaration_list`` holding ``enum_case`` nodes plus
     ordinary ``method_declaration`` members.
PH8  ``trait`` is a ``trait_declaration`` with a ``name`` field and a
     ``declaration_list`` whose members are ordinary
     ``method_declaration`` nodes — so trait methods carry ``parent_class``
     = the trait name when traits map to CLASS.
PH9  An interface method is an ordinary ``method_declaration`` **without**
     a ``compound_statement`` body (the declaration ends with ``;``), so
     the scanner can detect declaration-only methods structurally.
PH10 Semicolons are required syntax: every statement ends with a ``;``
     leaf (never excluded from the hash), and an optional closing
     ``?>`` tag exists but is not required at EOF.
PH11 Strings: ``"x"`` is an ``encapsed_string`` and ``'x'`` a ``string``;
     each carries ``string_content`` and ``escape_sequence`` children.
     Double-quoted interpolation ``$name`` is a ``variable_name`` child
     and ``{$obj->prop}`` an ``{ `` + expression + ``}`` sequence, so an
     *edit* inside an interpolation is visible CST content.  Heredocs and
     nowdocs are distinct node types (``heredoc``/``nowdoc``) whose bodies
     are ``heredoc_body``/``nowdoc_body``; a ``heredoc_body`` holds
     ``string_content``/``escape_sequence``/interpolation children while a
     ``nowdoc_body`` holds a raw ``nowdoc_string``.
PH12 Magic methods are ordinary ``method_declaration`` nodes named
     ``__construct`` etc. (the dunder heuristic governs *call capture*
     only, never symbol indexing); ``$this->m()`` and ``?->`` chain and
     are captured like any other member call.

Additional boundaries pinned here because the call/symbol/hash model
depends on them (each was probed, not assumed):

- ``new Foo()`` is an ``object_creation_expression`` — not call-shaped —
  so constructor invocations are never captured, matching the
  JS/TS/Java ``new`` boundary.
- First-class callable syntax ``strlen(...)`` **is** a
  ``function_call_expression`` but its arguments hold a lone
  ``variadic_placeholder``; the scanner excludes that shape (a reference,
  not a call — the PHP analogue of Kotlin's ``Foo::bar``).  A spread
  call ``f(...$args)`` instead nests an ``argument`` +
  ``variadic_unpacking`` and stays a call.
- ``echo``/``print``/``include``/``require`` are statements or intrinsics
  (``echo_statement``, ``print_intrinsic``, ``include_expression``),
  never ``function_call_expression`` nodes.
- Comments attach outside declarations (``program`` / ``declaration_list``
  children) and are skipped by the shared comment set.
- Property hooks (PHP 8.4) parse as a ``property_hook_list`` inside the
  ``property_declaration``; each ``property_hook`` is a named body.
- Grammar-version boundary: asymmetric visibility (``private(set)`` /
  ``protected(set)``) inside a **promoted constructor parameter** is
  rejected by older grammar builds as an ``ERROR`` node, while newer
  builds accept it as a ``property_promotion_parameter``. A standalone
  property with the same modifier parses cleanly on both; the probe pins
  both outcomes so a grammar upgrade is deliberate rather than surprising.
- ``namespace App { ... }`` blocks parse into a
  ``namespace_definition`` → ``compound_statement``; the ``;`` form is a
  declaration followed by siblings.  ``declare(ticks=1) { ... }`` wraps
  its body in a ``compound_statement`` too.  Declarations inside either
  body are top-level by scope and therefore symbols.
- An HTML template parses (``text`` + ``php_tag`` + ``echo_statement`` +
  ``text_interpolation``); a file with no ``<?php`` tag is a single
  ``text`` node with no error — no symbols, matching PHP semantics.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import tree_sitter_php as ts_php
from tree_sitter import Language, Node, Parser

_LANGUAGE = Language(ts_php.language_php())
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


# ---------------------------------------------------------------------------
# Dependency floor and grammar choice
# ---------------------------------------------------------------------------


class TestDependencyFloor:
    """The pinned grammar floor must load, parse, and be the HTML grammar."""

    def test_dependency_floor_is_the_installed_grammar(self) -> None:
        import importlib.metadata as md

        version = md.version("tree-sitter-php")
        parts = tuple(int(p) for p in version.split(".")[:2])
        assert parts >= (0, 24), f"tree-sitter-php {version} below the >=0.24 floor"
        assert _LANGUAGE.abi_version == 15, "grammar ABI changed — re-verify probes"
        assert not _PARSER.parse(b"<?php function f() {}\n").root_node.has_error

    def test_php_grammar_parses_an_html_template_without_error(self) -> None:
        """The HTML-embedded grammar handles ``.php`` templates by design."""
        source = "<html>\n<body>\n<?php echo greet($name); ?>\n</body>\n</html>\n"
        root = _parse(source)
        assert [c.type for c in root.named_children] == [
            "text",
            "php_tag",
            "echo_statement",
            "text_interpolation",
        ]

    def test_php_only_grammar_hard_errors_on_the_same_template(self) -> None:
        """Evidence for choosing ``language_php`` over ``language_php_only``."""
        only = Parser(Language(ts_php.language_php_only()))
        root = only.parse(
            b"<html>\n<body>\n<?php echo greet($name); ?>\n</body>\n</html>\n"
        ).root_node
        assert root.has_error, "php_only unexpectedly started accepting templates"

    def test_file_without_php_tag_is_text_and_has_no_error(self) -> None:
        """A ``.php`` file with no ``<?php`` is HTML output, not code.

        PHP itself would print those bytes; the scanner must not invent
        symbols for them.  The shape is a single ``text`` node.
        """
        root = _parse("class Foo {\n    public function m() {}\n}\n")
        assert [c.type for c in root.named_children] == ["text"]
        assert not _all(root, "class_declaration")

    def test_tagged_file_starts_with_php_tag(self) -> None:
        root = _parse("<?php\nclass Foo {}\n")
        assert [c.type for c in root.named_children] == [
            "php_tag",
            "class_declaration",
        ]


# ---------------------------------------------------------------------------
# PH1 — member calls and property access
# ---------------------------------------------------------------------------


class TestPH1MemberCalls:
    """PH1: ``->``/``?->`` calls are call nodes; property reads are not."""

    SOURCE = """\
<?php
function demo($obj, $other) {
    helper(1);
    $obj->method(2);
    $obj->prop;
    $obj?->nullable(3);
    $obj?->plainProp;
    $this->local(4);
}
"""

    def test_member_call_node_shape(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "member_call_expression", self.SOURCE, "$obj->method(2)")
        assert _named_types(call) == [
            "variable_name",
            "name",
            "arguments",
        ]
        assert _direct_token(call, "->")

    def test_property_access_is_not_a_call_node(self) -> None:
        root = _parse(self.SOURCE)
        access = _by_text(root, "member_access_expression", self.SOURCE, "$obj->prop")
        assert _text(access.child_by_field_name("name"), self.SOURCE) == "prop"
        # ``$obj->prop`` must not be reachable as any call node type.
        assert all(
            _text(call, self.SOURCE) != "$obj->prop"
            for call in _walk(root)
            if call.type.endswith("call_expression")
        )

    def test_nullsafe_member_call_is_its_own_node_type(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(
            root,
            "nullsafe_member_call_expression",
            self.SOURCE,
            "$obj?->nullable(3)",
        )
        assert _direct_token(call, "?->")
        assert _text(call.child_by_field_name("name"), self.SOURCE) == "nullable"

    def test_nullsafe_property_access_is_not_a_call(self) -> None:
        root = _parse(self.SOURCE)
        assert all(
            _text(n, self.SOURCE) != "$obj?->plainProp"
            for n in _all(root, "nullsafe_member_call_expression")
        )

    def test_this_is_a_plain_variable_name_receiver(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "member_call_expression", self.SOURCE, "$this->local(4)")
        assert call.named_children[0].type == "variable_name"

    def test_bare_call_carries_its_callee_in_the_function_field(self) -> None:
        """``function_call_expression`` names its callee with ``function``.

        The field is **not** ``name`` (a trap this probe caught: the
        ``name`` field is ``None`` for bare calls) — the callee is the
        ``function`` field, which holds a ``name`` or ``qualified_name``
        node.
        """
        root = _parse(self.SOURCE)
        call = _by_text(root, "function_call_expression", self.SOURCE, "helper(1)")
        assert call.child_by_field_name("name") is None
        callee = call.child_by_field_name("function")
        assert callee is not None and callee.type == "name"
        assert _text(callee, self.SOURCE) == "helper"


# ---------------------------------------------------------------------------
# PH2 — scoped calls
# ---------------------------------------------------------------------------


class TestPH2ScopedCalls:
    """PH2: ``Class::m()``/``self::``/``static::``/``parent::`` shape."""

    SOURCE = """\
<?php
function demo() {
    ClassName::staticMethod(5);
    self::own(6);
    static::late(7);
    parent::inherited(8);
}
"""

    def test_named_scope_is_a_name_child(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(
            root, "scoped_call_expression", self.SOURCE, "ClassName::staticMethod(5)"
        )
        assert call.named_children[0].type == "name"
        assert _text(call.child_by_field_name("name"), self.SOURCE) == "staticMethod"

    @pytest.mark.parametrize("scope", ["self", "static", "parent"])
    def test_relative_scopes_are_relative_scope_nodes(self, scope: str) -> None:
        root = _parse(self.SOURCE)
        matches = [
            n
            for n in _all(root, "scoped_call_expression")
            if _text(n, self.SOURCE).startswith(f"{scope}::")
        ]
        assert len(matches) == 1
        call = matches[0]
        assert call.named_children[0].type == "relative_scope"
        assert _text(call.named_children[0], self.SOURCE) == scope
        assert call.child_by_field_name("name") is not None

    def test_dynamic_scoped_name_is_a_variable_name_in_the_name_field(self) -> None:
        """A dynamic method name *does* sit in the ``name`` field — as a
        ``variable_name`` node, not a ``name`` node.  The scanner's
        static-name test is therefore the field's **node type**, not the
        field's presence."""
        source = "<?php\nfunction d() {\n    Foo::$m();\n}\n"
        root = _parse(source)
        call = _only(root, "scoped_call_expression")
        name_field = call.child_by_field_name("name")
        assert name_field is not None and name_field.type == "variable_name"


# ---------------------------------------------------------------------------
# PH3 — namespaced targets
# ---------------------------------------------------------------------------


class TestPH3QualifiedNames:
    """PH3: ``ns\\func()`` and ``Foo\\Bar::baz()`` resolve to the last name."""

    SOURCE = """\
<?php
function demo() {
    ns\\func(10);
    Foo\\Bar::baz(9);
}
"""

    def test_namespaced_function_call_uses_qualified_name(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "function_call_expression", self.SOURCE, "ns\\func(10)")
        qualified = call.child_by_field_name("function")
        assert qualified is not None and qualified.type == "qualified_name"
        assert _text(qualified, self.SOURCE) == "ns\\func"

    def test_namespaced_scoped_call_keeps_method_in_name_field(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "scoped_call_expression", self.SOURCE, "Foo\\Bar::baz(9)")
        assert call.named_children[0].type == "qualified_name"
        assert _text(call.child_by_field_name("name"), self.SOURCE) == "baz"

    def test_qualified_name_children_are_namespace_name_then_name(self) -> None:
        """``A\\B\\c`` nests the prefix into a ``namespace_name`` child."""
        source = "<?php\nfunction d() {\n    A\\B\\c();\n}\n"
        root = _parse(source)
        qualified = _only(root, "qualified_name")
        assert [c.type for c in qualified.children] == ["namespace_name", "\\", "name"]
        assert _text(qualified.children[-1], source) == "c"
        assert _text(qualified.children[0], source) == "A\\B"

    def test_qualified_name_is_the_callee_field(self) -> None:
        source = "<?php\nfunction d() {\n    A\\c();\n}\n"
        root = _parse(source)
        call = _only(root, "function_call_expression")
        callee = call.child_by_field_name("function")
        assert callee is not None and callee.type == "qualified_name"


# ---------------------------------------------------------------------------
# PH4 — attributes
# ---------------------------------------------------------------------------


class TestPH4Attributes:
    """PH4: attributes are children of the declaration they annotate."""

    SOURCE = """\
<?php
#[Route("/home")]
function controller(): void {}

#[Attribute]
class Marker {
    #[Inject]
    public function boot(): void {}
}
"""

    def test_attribute_list_starts_the_function_node(self) -> None:
        root = _parse(self.SOURCE)
        functions = [
            n
            for n in _all(root, "function_definition")
            if _text(n, self.SOURCE).startswith("#[Route")
        ]
        assert len(functions) == 1
        assert functions[0].named_children[0].type == "attribute_list"
        assert functions[0].start_point[0] + 1 == 2

    def test_attribute_list_is_a_class_child(self) -> None:
        root = _parse(self.SOURCE)
        cls = [
            n
            for n in _all(root, "class_declaration")
            if _text(n, self.SOURCE).startswith("#[Attribute]")
        ]
        assert len(cls) == 1
        assert cls[0].named_children[0].type == "attribute_list"

    def test_method_attribute_is_inside_the_method(self) -> None:
        root = _parse(self.SOURCE)
        method = [
            n
            for n in _all(root, "method_declaration")
            if _text(n, self.SOURCE).startswith("#[Inject]")
        ]
        assert len(method) == 1
        assert method[0].named_children[0].type == "attribute_list"

    def test_attribute_arguments_are_children(self) -> None:
        root = _parse(self.SOURCE)
        attributes = _all(root, "attribute")
        assert len(attributes) == 3
        route = [a for a in attributes if _text(a, self.SOURCE).startswith("Route")]
        assert len(route) == 1
        assert _all(route[0], "arguments")


# ---------------------------------------------------------------------------
# PH5 — anonymous classes
# ---------------------------------------------------------------------------


class TestPH5AnonymousClasses:
    """PH5: ``new class {...}`` has no name and is never a symbol."""

    SOURCE = """\
<?php
function build() {
    $x = new class(1) extends Base implements Iface {
        use SomeTrait;
        public function anon(): void { helper(); }
    };
    $y = new class {};
}
"""

    def test_anonymous_class_has_no_name_field(self) -> None:
        root = _parse(self.SOURCE)
        anons = _all(root, "anonymous_class")
        assert len(anons) == 2
        assert all(a.child_by_field_name("name") is None for a in anons)

    def test_anonymous_class_is_wrapped_in_object_creation(self) -> None:
        root = _parse(self.SOURCE)
        creations = _all(root, "object_creation_expression")
        assert len(creations) == 2
        assert all(_all(c, "anonymous_class") for c in creations)

    def test_anonymous_class_body_is_a_declaration_list(self) -> None:
        root = _parse(self.SOURCE)
        anon = _all(root, "anonymous_class")[0]
        declaration_list = _only(anon, "declaration_list")
        types = {c.type for c in declaration_list.named_children}
        assert "method_declaration" in types
        assert "use_declaration" in types


# ---------------------------------------------------------------------------
# PH6 — closures and arrow functions
# ---------------------------------------------------------------------------


class TestPH6Closures:
    """PH6: ``$f = function () {}`` / ``$f = fn () => ...`` shapes."""

    SOURCE = """\
<?php
$fn = function () { return 1; };
$arrow = fn () => 1;
$static_fn = static function () { return 2; };
$static_arrow = static fn () => 2;
"""

    @pytest.mark.parametrize(
        ("name", "value_type"),
        [
            ("$fn", "anonymous_function"),
            ("$arrow", "arrow_function"),
            ("$static_fn", "anonymous_function"),
            ("$static_arrow", "arrow_function"),
        ],
    )
    def test_closure_assignment_shape(self, name: str, value_type: str) -> None:
        root = _parse(self.SOURCE)
        assignment = [
            n
            for n in _all(root, "assignment_expression")
            if _text(n, self.SOURCE).startswith(name)
        ]
        assert len(assignment) == 1
        assert assignment[0].named_children[0].type == "variable_name"
        assert assignment[0].named_children[1].type == value_type

    def test_variable_name_strips_the_dollar_sign(self) -> None:
        root = _parse(self.SOURCE)
        assignment = _by_text(
            root,
            "assignment_expression",
            self.SOURCE,
            "$fn = function () { return 1; }",
        )
        variable = assignment.named_children[0]
        assert _direct_token(variable, "$")
        assert _text(variable.named_children[0], self.SOURCE) == "fn"

    def test_static_modifier_is_a_child_of_the_function_value(self) -> None:
        root = _parse(self.SOURCE)
        assignment = _by_text(
            root,
            "assignment_expression",
            self.SOURCE,
            "$static_fn = static function () { return 2; }",
        )
        function = assignment.named_children[1]
        assert function.named_children[0].type == "static_modifier"

    def test_assignment_to_a_property_is_not_a_variable_name_target(self) -> None:
        """``$this->f = function () {}`` has no ``variable_name`` left side."""
        source = "<?php\nclass C {\n    public function m() {\n"
        source += "        $this->f = function () { return 1; };\n    }\n}\n"
        root = _parse(source)
        assignment = _only(root, "assignment_expression")
        assert assignment.named_children[0].type == "member_access_expression"


# ---------------------------------------------------------------------------
# PH7 — enums
# ---------------------------------------------------------------------------


class TestPH7Enums:
    """PH7: ``enum`` → ``enum_declaration`` + ``enum_declaration_list``."""

    SOURCE = """\
<?php
enum Suit: string implements HasColor {
    case Hearts = 'H';
    case Spades = 'S';

    public function color(): string { return "red"; }

    const DEFAULT = self::Hearts;
}
"""

    def test_enum_declaration_shape(self) -> None:
        root = _parse(self.SOURCE)
        enum = _only(root, "enum_declaration")
        assert _text(enum.child_by_field_name("name"), self.SOURCE) == "Suit"
        assert _all(enum, "enum_declaration_list")

    def test_enum_cases_and_methods_share_the_list(self) -> None:
        root = _parse(self.SOURCE)
        body = _only(root, "enum_declaration_list")
        types = [c.type for c in body.named_children]
        assert types.count("enum_case") == 2
        assert "method_declaration" in types

    def test_enum_case_has_name_and_value(self) -> None:
        root = _parse(self.SOURCE)
        cases = {
            _text(c.child_by_field_name("name"), self.SOURCE): c  # type: ignore[arg-type]
            for c in _all(root, "enum_case")
        }
        assert set(cases) == {"Hearts", "Spades"}
        assert _all(cases["Hearts"], "string")


# ---------------------------------------------------------------------------
# PH8 — traits
# ---------------------------------------------------------------------------


class TestPH8Traits:
    """PH8: ``trait`` → ``trait_declaration``; methods are ordinary members."""

    SOURCE = """\
<?php
trait Helper {
    public function assist(): string { return "a"; }
    abstract public function must(): void;
}
"""

    def test_trait_shape(self) -> None:
        root = _parse(self.SOURCE)
        trait = _only(root, "trait_declaration")
        assert _text(trait.child_by_field_name("name"), self.SOURCE) == "Helper"
        assert _only(trait, "declaration_list")

    def test_trait_methods_are_method_declarations(self) -> None:
        root = _parse(self.SOURCE)
        methods = _all(root, "method_declaration")
        assert {_text(m.child_by_field_name("name"), self.SOURCE) for m in methods} == {
            "assist",
            "must",
        }

    def test_trait_abstract_method_has_no_body(self) -> None:
        root = _parse(self.SOURCE)
        methods = {
            _text(m.child_by_field_name("name"), self.SOURCE): m
            for m in _all(root, "method_declaration")
        }
        assert _all(methods["must"], "compound_statement") == []
        assert _all(methods["assist"], "compound_statement")


# ---------------------------------------------------------------------------
# PH9 — interface methods are declaration-only
# ---------------------------------------------------------------------------


class TestPH9InterfaceMethods:
    """PH9: interface methods end with ``;`` and have no body node."""

    SOURCE = """\
<?php
interface Api {
    const LIMIT = 10;
    public function go(): void;
}
"""

    def test_interface_method_has_no_compound_statement(self) -> None:
        root = _parse(self.SOURCE)
        method = _only(root, "method_declaration")
        assert _all(method, "compound_statement") == []
        assert _direct_token(method, ";")

    def test_interface_body_holds_constants_and_methods(self) -> None:
        root = _parse(self.SOURCE)
        body = _only(root, "declaration_list")
        types = {c.type for c in body.named_children}
        assert types == {"const_declaration", "method_declaration"}


# ---------------------------------------------------------------------------
# PH10 — semicolons are required syntax
# ---------------------------------------------------------------------------


class TestPH10Semicolons:
    """PH10: ``;`` are real leaf tokens — hashed content, never excluded."""

    SOURCE = """\
<?php
function f(): int {
    $x = 1;
    return $x;
}
"""

    def test_semicolons_are_leaf_tokens(self) -> None:
        root = _parse(self.SOURCE)
        semicolons = [n for n in _walk(root) if n.type == ";"]
        assert len(semicolons) == 2
        assert all(n.child_count == 0 for n in semicolons)

    def test_closing_tag_is_optional(self) -> None:
        with_close = "<?php\nfunction f() { return 1; }\n?>\n"
        without_close = "<?php\nfunction f() { return 1; }\n"
        assert not _parse_tolerantly(with_close).has_error
        assert not _parse_tolerantly(without_close).has_error
        # The ``?>`` produces a ``php_end_tag`` leaf that the scanner must
        # skip when reading the declaration (the declaration itself is
        # byte-identical with and without it).
        root = _parse_tolerantly(with_close)
        assert _all(root, "php_end_tag")


# ---------------------------------------------------------------------------
# PH11 — strings, interpolation, heredocs
# ---------------------------------------------------------------------------


class TestPH11Strings:
    """PH11: quoted strings, escapes, interpolation, heredoc/nowdoc."""

    def test_quote_styles_are_two_node_types(self) -> None:
        root = _parse("<?php\n$a = \"x\";\n$b = 'y';\n")
        double = _only(root, "encapsed_string")
        single = _only(root, "string")
        assert _text(double, "<?php\n$a = \"x\";\n$b = 'y';\n") == '"x"'
        assert _text(single, "<?php\n$a = \"x\";\n$b = 'y';\n") == "'y'"
        # Both carry string_content children; neither is a bare leaf.
        assert _all(double, "string_content")
        assert _all(single, "string_content")

    def test_escape_sequences_are_distinct_children(self) -> None:
        source = "<?php\n$a = \"a\\nb \\$x \\\\ \\x41\";\n$b = 'it\\'s';\n"
        root = _parse(source)
        double = _only(root, "encapsed_string")
        escapes = [_text(e, source) for e in _all(double, "escape_sequence")]
        assert escapes == ["\\n", "\\$", "\\\\", "\\x41"]
        single = _only(root, "string")
        # Single-quoted escapes are distinct too (``\\'`` here).
        assert [_text(e, source) for e in _all(single, "escape_sequence")] == ["\\'"]

    def test_interpolation_children_are_real_nodes(self) -> None:
        source = '<?php\n$s = "hello $name and {$obj->prop} and ${legacy}";\n'
        root = _parse(source)
        encapsed = _only(root, "encapsed_string")
        types = [c.type for c in encapsed.children]
        assert "variable_name" in types
        assert "member_access_expression" in types
        assert "dynamic_variable_name" in types

    def test_call_inside_interpolation_is_a_call_node(self) -> None:
        """An interpolation edit / call is visible CST content, not opaque."""
        source = '<?php\n$s = "{$this->helper(1)}";\n'
        root = _parse(source)
        call = _only(root, "member_call_expression")
        assert _text(call.child_by_field_name("name"), source) == "helper"

    def test_heredoc_and_nowdoc_are_distinct_node_types(self) -> None:
        source = (
            "<?php\n$h = <<<EOT\nline $var text\nEOT;\n$n = <<<'EOT'\nraw $var\nEOT;\n"
        )
        root = _parse(source)
        heredoc = _only(root, "heredoc")
        nowdoc = _only(root, "nowdoc")
        assert _all(heredoc, "heredoc_body")
        assert _all(nowdoc, "nowdoc_body")
        # The heredoc body interpolates; the nowdoc body is raw text.
        assert _all(heredoc, "variable_name")
        assert _all(nowdoc, "nowdoc_string")

    def test_heredoc_body_carries_escapes_and_content(self) -> None:
        source = "<?php\n$h = <<<EOT\nhi $name!\\n\nEOT;\n"
        root = _parse(source)
        body = _only(root, "heredoc_body")
        types = [c.type for c in body.named_children]
        assert "string_content" in types
        assert "escape_sequence" in types
        assert "variable_name" in types

    def test_heredoc_marker_is_not_inside_the_body(self) -> None:
        source = "<?php\n$h = <<<EOT\nbody\nEOT;\n"
        root = _parse(source)
        body = _only(root, "heredoc_body")
        assert _text(body, source).strip() == "body"


# ---------------------------------------------------------------------------
# PH12 — magic methods and member calls
# ---------------------------------------------------------------------------


class TestPH12MagicMethods:
    """PH12: magic methods index as METHODs; member calls chain like JS."""

    SOURCE = """\
<?php
class Service {
    public function __construct() { $this->setup(); }
    public function __destruct() {}
    public function __toString(): string { return "s"; }
    public function run($o) {
        $o->method()->chained();
        $o?->first()?->second();
        f()->dynamic();
        ($this->x)->y();
    }
}
"""

    def test_magic_methods_are_ordinary_method_declarations(self) -> None:
        root = _parse(self.SOURCE)
        names = {
            _text(m.child_by_field_name("name"), self.SOURCE)
            for m in _all(root, "method_declaration")
        }
        assert {"__construct", "__destruct", "__toString", "run"} <= names

    def test_this_call_inside_a_magic_method_is_a_member_call(self) -> None:
        root = _parse(self.SOURCE)
        call = _by_text(root, "member_call_expression", self.SOURCE, "$this->setup()")
        assert _all(call, "variable_name")

    def test_chained_call_receiver_is_a_call(self) -> None:
        root = _parse(self.SOURCE)
        outer = _by_text(
            root, "member_call_expression", self.SOURCE, "$o->method()->chained()"
        )
        assert outer.named_children[0].type == "member_call_expression"

    def test_nullsafe_chain_receiver_is_a_call(self) -> None:
        root = _parse(self.SOURCE)
        outer = _by_text(
            root,
            "nullsafe_member_call_expression",
            self.SOURCE,
            "$o?->first()?->second()",
        )
        assert outer.named_children[0].type == "nullsafe_member_call_expression"

    def test_call_receiver_of_plain_call_is_a_call(self) -> None:
        root = _parse(self.SOURCE)
        outer = _by_text(root, "member_call_expression", self.SOURCE, "f()->dynamic()")
        assert outer.named_children[0].type == "function_call_expression"

    def test_parenthesized_receiver_is_not_a_call(self) -> None:
        root = _parse(self.SOURCE)
        outer = _by_text(root, "member_call_expression", self.SOURCE, "($this->x)->y()")
        assert outer.named_children[0].type == "parenthesized_expression"


# ---------------------------------------------------------------------------
# Additional boundaries the call/symbol/hash model depends on
# ---------------------------------------------------------------------------


class TestExtraBoundaries:
    """``new``, first-class callables, statements, comments, hooks, lag."""

    def test_new_is_object_creation_not_a_call(self) -> None:
        source = "<?php\nfunction f() {\n    $x = new Foo(1);\n}\n"
        root = _parse(source)
        creation = _only(root, "object_creation_expression")
        assert _text(creation.named_children[0], source) == "Foo"
        assert _all(root, "function_call_expression") == []

    def test_first_class_callable_is_call_shaped_but_placeholder(self) -> None:
        source = "<?php\n$c = strlen(...);\n"
        root = _parse(source)
        call = _only(root, "function_call_expression")
        arguments = _only(call, "arguments")
        assert _named_types(arguments) == ["variadic_placeholder"]
        assert _text(arguments.named_children[0], source) == "..."

    def test_spread_call_is_not_a_placeholder(self) -> None:
        source = "<?php\nfunction f($args) {\n    array_map(...$args);\n}\n"
        root = _parse(source)
        arguments = _only(root, "arguments")
        assert _named_types(arguments) == ["argument"]
        assert _all(arguments, "variadic_unpacking")
        assert _all(root, "variadic_placeholder") == []

    def test_dynamic_member_name_is_a_variable_name(self) -> None:
        source = "<?php\nfunction d($obj, $m) {\n    $obj->$m();\n}\n"
        root = _parse(source)
        call = _only(root, "member_call_expression")
        name_field = call.child_by_field_name("name")
        assert name_field is not None and name_field.type == "variable_name"

    def test_dynamic_string_name_is_a_string(self) -> None:
        source = "<?php\nfunction d($obj) {\n    $obj->{'weird'}();\n}\n"
        root = _parse(source)
        call = _only(root, "member_call_expression")
        name_field = call.child_by_field_name("name")
        assert name_field is not None and name_field.type == "string"

    @pytest.mark.parametrize(
        "statement",
        ['echo "hi";', 'print "x";', 'include "f.php";', 'require_once "g.php";'],
    )
    def test_statements_are_not_function_call_expressions(self, statement: str) -> None:
        source = f"<?php\nfunction f() {{\n    {statement}\n}}\n"
        root = _parse(source)
        assert _all(root, "function_call_expression") == []

    def test_include_expression_shape(self) -> None:
        source = '<?php\nfunction f() {\n    include "f.php";\n}\n'
        root = _parse(source)
        assert _only(root, "include_expression").type == "include_expression"

    def test_comments_attach_outside_declarations(self) -> None:
        source = "<?php\n// lead\nfunction f() {} // trailing\n"
        root = _parse(source)
        comments = _all(root, "comment")
        assert len(comments) == 2
        # Both comments are program children, not declaration children.
        assert all(
            c.parent is not None and c.parent.type == "program" for c in comments
        )
        function = _only(root, "function_definition")
        assert _all(function, "comment") == []

    def test_property_hooks_parse_as_named_bodies(self) -> None:
        source = (
            "<?php\nclass P {\n"
            "    public string $name {\n"
            "        get => $this->name;\n"
            "        set (string $value) { $this->name = $value; }\n"
            "    }\n}\n"
        )
        root = _parse(source)
        hooks = _all(root, "property_hook")
        assert len(hooks) == 2
        # A hook's name is its first named child (there is no ``name``
        # *field* on this node type — another assumption the probes caught).
        names = {_text(h.named_children[0], source) for h in hooks}
        assert names == {"get", "set"}
        # The property itself stays a single declaration.
        assert len(_all(root, "property_declaration")) == 1

    def test_namespace_block_form_nests_declarations(self) -> None:
        source = "<?php\nnamespace App {\n    function inBlock() {}\n}\n"
        root = _parse(source)
        namespace = _only(root, "namespace_definition")
        assert _all(namespace, "compound_statement")
        assert _all(namespace, "function_definition")

    def test_namespace_semicolon_form_keeps_declarations_top_level(self) -> None:
        source = "<?php\nnamespace App\\Deep;\nfunction f() {}\n"
        root = _parse(source)
        namespace = _only(root, "namespace_definition")
        assert _all(namespace, "compound_statement") == []
        assert [c.type for c in root.named_children] == [
            "php_tag",
            "namespace_definition",
            "function_definition",
        ]

    def test_declare_block_nests_declarations(self) -> None:
        source = "<?php\ndeclare(ticks=1) {\n    function inside() {}\n}\n"
        root = _parse(source)
        statement = _only(root, "declare_statement")
        assert _all(statement, "compound_statement")
        assert _all(statement, "function_definition")

    def test_canonical_full_php_file_parses_clean(self) -> None:
        """The everyday file shape the scanner must handle without a warning."""
        source = """\
<?php
declare(strict_types=1);

namespace App\\Service;

use App\\Base\\Thing;

final class Greeter implements Greets
{
    public const KIND = "greeter";

    public function __construct(private readonly string $name) {}

    public function greet(int $times = 1): string
    {
        $parts = [];
        for ($i = 0; $i < $times; $i++) {
            $parts[] = $this->format($this->name);
        }
        return implode(", ", $parts);
    }

    private function format(string $name): string
    {
        return trim($name);
    }
}
"""
        assert not _parse_tolerantly(source).has_error

    def test_asymmetric_visibility_in_promoted_parameter_tracks_grammar_support(
        self,
    ) -> None:
        """Pin old grammar rejection and new grammar support for PHP 8.4 syntax."""
        promoted = (
            "<?php\nclass P {\n"
            "    public function __construct(public private(set) int $id) {}\n"
            "}\n"
        )
        root = _parse_tolerantly(promoted)
        if root.has_error:
            # Older grammar builds must expose the unsupported syntax.
            assert _all(root, "ERROR")
        else:
            # Newer builds accept it as a property-promotion parameter.
            assert len(_all(root, "property_promotion_parameter")) == 1

        standalone = "<?php\nclass P {\n    public private(set) int $id = 0;\n}\n"
        assert not _parse_tolerantly(standalone).has_error


if __name__ == "__main__":  # pragma: no cover - manual probe aid
    raise SystemExit(pytest.main([__file__, "-v"]))
