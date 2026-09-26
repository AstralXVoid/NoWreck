"""Phase 3 fixture probes K1–K16 — Kotlin grammar shapes, pinned.

Every fact the Kotlin scanner depends on was resolved **empirically**
against the pinned grammar (``tree-sitter-kotlin 1.1.0``, ABI 14, on
``tree-sitter 0.26.0``) *before* any collector code was written.  This
module pins each resolution permanently, so a grammar upgrade that
changes a shape fails here instead of silently changing scanner
behaviour.

This is the language where the fixture-first discipline earns its keep:
the pinned grammar is the only Kotlin grammar published on PyPI
(``tree-sitter-kotlin`` 1.0.0 / 1.0.1 / 1.1.0 — the older ``fwcd``
grammar is not distributed there), and it has **seven confirmed
misparses** on ordinary source — three loud (``has_error`` is set) and
four silent, including the stacked-annotation family ``D7`` that
dissolves a declaration and then lets the next declaration absorb it.
Two of them destroy a declaration outright; the shape of the damage is
pinned below (K12b/K12c and K13–K16) so the scanner's recovery rules are
verifiable rather than folklore.

Resolved facts (probe → finding):

K1  ``function_declaration`` is used for *both* top-level functions and
    local ``fun`` inside a body (a direct child of ``block``).  Symbol
    collection walks only direct children of a type body, so local
    functions are never symbols — the same accepted edge as Python
    nested functions — but they *are* callers.
K2  ``interface`` is a **direct token child** of ``class_declaration``
    (never a ``class_modifier``); ``enum``/``data``/``sealed``/``value``/
    ``annotation`` are ``class_modifier`` grandchildren under
    ``modifiers``; ``fun interface`` carries *both* the ``fun`` and
    ``interface`` tokens as direct children.  Every form's name is the
    ``name`` field.
K3  ``object_declaration`` (name + ``class_body``) and ``companion_object``
    (``companion``/``object`` tokens, optional ``name``, ``class_body``)
    are named nodes.  A companion is a child of the *outer* ``class_body``.
K4  An extension receiver is a leading ``user_type`` child (after optional
    ``type_parameters``) followed by a direct ``.`` token; the function's
    own name is still the ``name`` field, so extension functions are
    ``FUNCTION`` with no ``parent_class``.
K5  Calls are ``call_expression`` nodes.  A bare call's callee is an
    ``identifier``; a member call's callee is a ``navigation_expression``
    whose last named child is the member ``identifier`` and whose first
    named child is the receiver — ``identifier``, ``this_expression``,
    ``super_expression``, ``index_expression`` (``a[0].bar()``),
    ``unary_expression`` (``x!!.foo()``) or, the only dynamic one,
    ``call_expression`` (``f().bar()``).  ``Foo::bar`` is a
    ``navigation_expression`` with **no** ``call_expression`` wrapper — a
    reference, never a call.
K6  A lambda value is a ``lambda_literal`` (``{ x -> ... }``) or an
    ``anonymous_function`` (``fun(x) = ...``) held as the value of a
    ``property_declaration``; the property name is the ``variable_declaration``
    child's ``identifier``.  This mirrors the JS/TS ``variable_declarator``
    arrow shape (probes established in v0.17.0 Phase 1).
K7  ``string_literal`` carries ``string_content`` + ``interpolation``
    children; a plain ``$x`` template is split into two ``string_content``
    leaves (``$`` and ``x``) while ``${expr}`` becomes an ``interpolation``
    node.  Raw strings are a distinct ``multiline_string_literal`` node
    type, and ``'a'`` is a ``character_literal`` whose content is *not* a
    child leaf — its text must be hashed from the node span, not its
    children.
K8  Attached annotations live in a ``modifiers`` child of the declaration
    (Java-like: ``modifiers`` → ``annotation`` → ``constructor_invocation``).
    **But** a top-level ``fun`` / ``object`` / ``enum class`` that is
    annotated *and* has a following sibling gets its annotation
    **detached** into a sibling ``annotated_expression`` whose argument
    list is a sibling ``parenthesized_expression`` instead of a
    ``constructor_invocation`` (K12b).  The declaration survives, but the
    same source has two different CST shapes depending on what follows —
    so annotations cannot be hashed by CST shape.
K9  ``type_alias`` names itself with the **``type``** field — there is no
    ``name`` field (unlike every other declaration in this grammar).
K10 Semicolons are optional and are **dropped by the grammar** in blocks
    and class bodies; the only place a ``;`` leaf survives is inside
    ``enum_class_body`` as the entry-list terminator.  Kotlin therefore
    takes the JS/TS/Go ASI exclusion (``;`` never affects the hash),
    unlike Java/Rust.
K11 Class members are ``function_declaration``, ``property_declaration``
    (with optional ``getter``/``setter`` children), ``secondary_constructor``
    and ``anonymous_initializer`` (``init { }``).  ``primary_constructor``
    holds only ``class_parameters``.
K12 Grammar floor + known-unsupported list (see the three defect tests).
K13 Two stacked annotations in front of a top-level plain ``class`` /
    ``interface`` / ``annotation class`` (also ``sealed class`` and
    ``data object``) dissolve it as soon as *any* declaration follows —
    ``has_error`` stays ``False``.  One annotation, only a comment after,
    nothing after, and the same stack nested in a class body are all
    unaffected; ``data class`` / ``value class`` / ``enum class`` /
    ``fun interface`` / ``object`` survive the very same stack.  Which
    heads survive is grammar luck, never a rule (D7).
K14 A *bodyless* destroyed declaration keeps absorbing a following
    ``class`` / ``interface`` into its own ``infix_expression`` chain, so
    two declarations become a single top-level node; a following ``fun``,
    ``object`` or another bodyless class is left alone (D7).
K15 An argument-bearing ``@Ann(1)`` on a top-level ``fun`` detaches into
    a sibling ``annotated_expression`` (annotation plus
    ``parenthesized_expression``) as soon as anything follows — a trailing
    comment counts; a bare ``@Ann`` stays attached in ``modifiers``
    (D4/D7), so the same source has two shapes with one meaning.
K16 The ``annotation`` keyword of ``annotation class`` is itself a
    **childless** node of type ``annotation`` (under ``class_modifier``),
    while a real annotation always carries children.  The scanner's
    blinding rule must therefore test the node's children, not its type
    alone.

Defects pinned here (upstream grammar, reproduced deterministically):

D1  A **one-line class-like body containing a member** fails to parse
    (``has_error``): the body is mislabelled ``enum_class_body`` and its
    member is swallowed by an ``ERROR`` node.  A newline or ``;`` before
    the closing brace avoids it.
D2  An annotated **single-entry enum without a trailing comma**
    (``@A(n) enum class E { A }``) loses the whole declaration: it becomes
    ``annotated_expression → infix_expression(enum, class, call_expression)``.
    Two or more entries, or a trailing comma, parse correctly.
D3  An annotated **``annotation class``** loses the whole declaration:
    ``annotated_expression → infix_expression(annotation, class, <name>)``
    (or a ``call_expression`` when a body is present).

D4  A top-level ``fun``/``object``/``enum class`` whose annotation has a
    following sibling (a trailing comment counts) gets its annotation
    **detached** into a sibling ``annotated_expression``, so the same
    source has two CST shapes (hashed as a leaf-token signature instead).
D5  A ``fun`` named after a type soft keyword (``dynamic``/``suspend``)
    loses its name: inside a type body the declaration survives with a
    zero-width ``MISSING`` name node, at top level it becomes an
    ``anonymous_function`` whose ``ERROR`` child holds the name.
D6  The same two keywords in other identifier positions (``val dynamic``,
    a bare ``dynamic()`` call, a named argument, a lambda parameter)
    collapse the **whole file** into one ``ERROR`` — an accepted edge, and
    a loud one (``has_error`` is set).
D7  A stack of two or more annotations at top level dissolves a plain
    ``class`` / ``interface`` / ``annotation class`` (and ``sealed`` /
    ``data object``, though not ``data class`` / ``enum class`` /
    ``object``) into an ``annotated_expression`` chain ending in an
    ``infix_expression`` as soon as any declaration follows — silently
    (``has_error`` is ``False``).  A bodyless destroyed declaration keeps
    absorbing the next class-like declaration into the same chain, so two
    declarations become one node and both vanish from the CST.  The same
    "sibling follows" trigger detaches an argument-bearing annotation on a
    top-level ``fun`` into a sibling ``annotated_expression`` (a trailing
    comment counts).  This is the family the blinded re-parse exists for:
    the damage is not a property of the declaration, so it cannot be
    recovered declaration by declaration.

D5 is recovered by the scanner from its deterministic damage shape; D1 and D6
are accepted edges, documented in the phase notes and the scope release notes.
The annotation-linked defects (D2/D3/D4/D7) are not recovered shape-by-shape
at all: a file that contains an annotation is blinded — every annotation span
replaced by spaces, offsets and line numbers preserved — and re-parsed, so the
shapes pinned above never reach the collectors.  See ``_prepare_source`` in
``nowreck/scanner/kotlin_scanner.py``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import tree_sitter_kotlin as ts_kotlin
from tree_sitter import Language, Node, Parser

_LANGUAGE = Language(ts_kotlin.language())
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


def _token_types(node: Node) -> list[str]:
    """Direct child types, tokens included (anon tokens keep their text)."""
    return [child.type for child in node.children]


def _named_types(node: Node) -> list[str]:
    return [child.type for child in node.named_children]


def _direct_token(node: Node, token: str) -> bool:
    return any(child.type == token for child in node.children)


def _ancestor_types(node: Node) -> list[str]:
    """Types of every ancestor of *node*, nearest first (root last)."""
    types: list[str] = []
    parent = node.parent
    while parent is not None:
        types.append(parent.type)
        parent = parent.parent
    return types


def _first_decl(root: Node, node_type: str) -> Node:
    for child in root.named_children:
        if child.type == node_type:
            return child
    raise AssertionError(f"no {node_type} among {_named_types(root)}")


def _class_modifier_texts(root: Node, source: str) -> list[str]:
    return [_text(mod, source) for mod in _all(root, "class_modifier")]


# ---------------------------------------------------------------------------
# K1 — top-level vs local functions
# ---------------------------------------------------------------------------


def test_k1_local_function_is_a_nested_function_declaration() -> None:
    """A local ``fun`` is the same node type, but nested inside a ``block``."""
    source = 'fun top() {\n    fun local() { println("x") }\n    local()\n}\n'
    root = _parse(source)
    funcs = _all(root, "function_declaration")
    assert len(funcs) == 2
    top, local = funcs
    assert [f.child_by_field_name("name") for f in funcs] and all(
        f.child_by_field_name("name") is not None for f in funcs
    )
    assert _text(top.child_by_field_name("name"), source) == "top"
    assert _text(local.child_by_field_name("name"), source) == "local"
    # The local one is nested inside a block; the top-level one is not.
    assert root.type == "source_file"
    assert top in list(root.named_children)
    assert local not in list(root.named_children)
    assert _all(root, "block"), "local function must live inside a block"


def test_k1_local_function_calls_are_still_captured() -> None:
    """The call to ``local()`` exists and is a ``call_expression``."""
    root = _parse("fun top() {\n    fun local() {}\n    local()\n}\n")
    calls = _all(root, "call_expression")
    assert len(calls) == 1
    assert calls[0].named_children[0].type == "identifier"


# ---------------------------------------------------------------------------
# K2 — class / interface / enum / modifiers / fun interface
# ---------------------------------------------------------------------------


def test_k2_interface_is_a_direct_token_not_a_class_modifier() -> None:
    root = _parse("interface Api {\n    fun run()\n}\n")
    decl = _first_decl(root, "class_declaration")
    assert _direct_token(decl, "interface")
    assert "class_modifier" not in _named_types(decl)
    assert _text(
        decl.child_by_field_name("name"), "interface Api {\n    fun run()\n}\n"
    ) == ("Api")
    assert _only(root, "class_body").type == "class_body"


@pytest.mark.parametrize(
    ("modifier", "snippet"),
    [
        ("enum", "enum class Color {\n    RED,\n    GREEN\n}\n"),
        ("data", "data class Point(val x: Int, val y: Int)\n"),
        ("value", "value class Meters(val v: Double)\n"),
        ("sealed", "sealed class Shape\n"),
        ("annotation", "annotation class Marker\n"),
    ],
)
def test_k2_class_modifiers_are_nested_in_modifiers(
    modifier: str, snippet: str
) -> None:
    """``enum``/``data``/``value``/``sealed``/``annotation`` are modifiers."""
    root = _parse(snippet)
    decl = _first_decl(root, "class_declaration")
    assert _class_modifier_texts(root, snippet) == [modifier]
    assert not _direct_token(decl, modifier), (
        "the keyword must be a class_modifier, not a direct token"
    )
    assert decl.child_by_field_name("name") is not None


def test_k2_fun_interface_carries_both_tokens() -> None:
    """``fun interface`` puts both keywords as direct children."""
    source = "fun interface Handler {\n    fun handle()\n}\n"
    decl = _first_decl(_parse(source), "class_declaration")
    assert _direct_token(decl, "fun")
    assert _direct_token(decl, "interface")
    assert _class_modifier_texts(_parse(source), source) == []


def test_k2_enum_body_is_enum_class_body() -> None:
    source = "enum class Color {\n    RED,\n    GREEN\n}\n"
    root = _parse(source)
    body = _only(root, "enum_class_body")
    assert _named_types(body) == ["enum_entry", "enum_entry"]
    assert [_text(e.named_children[0], source) for e in _all(root, "enum_entry")] == [
        "RED",
        "GREEN",
    ]


# ---------------------------------------------------------------------------
# K3 — object declarations and companions
# ---------------------------------------------------------------------------


def test_k3_object_declaration_shape() -> None:
    source = "object Singleton {\n    fun go() {}\n}\n"
    root = _parse(source)
    obj = _first_decl(root, "object_declaration")
    assert _text(obj.child_by_field_name("name"), source) == "Singleton"
    assert _only(obj, "class_body").type == "class_body"


def test_k3_companion_object_is_nested_in_the_outer_class_body() -> None:
    source = (
        "class Outer {\n"
        "    companion object {\n"
        "        fun make(): Outer = Outer()\n"
        '        val NAME = "outer"\n'
        "    }\n"
        "}\n"
    )
    root = _parse(source)
    outer = _first_decl(root, "class_declaration")
    companion = _only(outer, "companion_object")
    assert companion.parent is not None
    assert companion.parent.type == "class_body"
    assert companion.parent is outer.child_by_field_name("body") or (
        companion.parent in list(outer.named_children)
    )
    # An anonymous companion has no name field.
    assert companion.child_by_field_name("name") is None
    assert _only(companion, "class_body").type == "class_body"


def test_k3_named_companion_has_a_name_field() -> None:
    source = (
        "class C {\n    companion object Factory {\n        fun make() {}\n    }\n}\n"
    )
    root = _parse(source)
    companion = _only(root, "companion_object")
    assert _text(companion.child_by_field_name("name"), source) == "Factory"


def test_k3_nested_object_is_a_child_of_the_class_body() -> None:
    source = "class C {\n    object Helpers {\n        fun h() {}\n    }\n}\n"
    root = _parse(source)
    outer = _first_decl(root, "class_declaration")
    nested = _only(outer, "object_declaration")
    assert nested.parent is not None and nested.parent.type == "class_body"


# ---------------------------------------------------------------------------
# K4 — extension functions
# ---------------------------------------------------------------------------


def test_k4_extension_receiver_is_a_leading_user_type() -> None:
    source = "fun String.shout(): String = this.uppercase()\n"
    root = _parse(source)
    func = _only(root, "function_declaration")
    assert _text(func.child_by_field_name("name"), source) == "shout"
    assert _direct_token(func, ".")
    # First named child is the receiver type (no type_parameters here).
    assert func.named_children[0].type == "user_type"
    assert _text(func.named_children[0], source) == "String"


def test_k4_generic_extension_puts_type_parameters_first() -> None:
    source = "fun <T> List<T>.second(): T = this[1]\n"
    func = _only(_parse(source), "function_declaration")
    assert _named_types(func)[0] == "type_parameters"
    assert func.named_children[1].type == "user_type"
    assert _text(func.child_by_field_name("name"), source) == "second"


def test_k4_extension_call_shapes() -> None:
    """``this.uppercase()`` and ``this[1]`` both parse as expected."""
    source = (
        "fun String.shout(): String = this.uppercase()\nfun Int.double() = this * 2\n"
    )
    root = _parse(source)
    nav = _only(root, "navigation_expression")
    assert [c.type for c in nav.named_children] == ["this_expression", "identifier"]


# ---------------------------------------------------------------------------
# K5 — call shapes
# ---------------------------------------------------------------------------


_CALL_SOURCE = """fun demo(x: String?, list: List<Int>) {
    foo()
    obj.foo()
    x?.foo()
    x!!.foo()
    this.foo()
    super.foo()
    a.b.c()
    f().bar()
    items[0].bar()
    Foo::bar
}
"""


def _callee_shape(node: Node, source: str) -> tuple[str, str | None]:
    """``(callee type, final member name or None)`` for a call_expression."""
    callee = node.named_children[0]
    if callee.type == "identifier":
        return callee.type, _text(callee, source)
    if callee.type == "navigation_expression":
        last = callee.named_children[-1]
        name = _text(last, source) if last.type == "identifier" else None
        return "navigation_expression", name
    return callee.type, None


def test_k5_call_expression_shapes() -> None:
    root = _parse(_CALL_SOURCE)
    calls = [
        n
        for n in _all(root, "call_expression")
        if n.parent is not None and n.parent.type != "navigation_expression"
    ]
    shapes = {
        _text(call.named_children[0], _CALL_SOURCE): _callee_shape(call, _CALL_SOURCE)
        for call in calls
    }
    assert shapes["foo"] == ("identifier", "foo")
    assert shapes["obj.foo"] == ("navigation_expression", "foo")
    assert shapes["x?.foo"] == ("navigation_expression", "foo")
    assert shapes["x!!.foo"] == ("navigation_expression", "foo")
    assert shapes["this.foo"] == ("navigation_expression", "foo")
    assert shapes["super.foo"] == ("navigation_expression", "foo")
    assert shapes["a.b.c"] == ("navigation_expression", "c")
    assert shapes["f().bar"] == ("navigation_expression", "bar")
    assert shapes["items[0].bar"] == ("navigation_expression", "bar")
    # The inner ``f()`` is a call whose parent nav makes it a receiver only.
    assert all(call.named_children[0].type != "call_expression" for call in calls), (
        "no call's callee is itself a call"
    )
    assert "f()" not in shapes


def test_k5_call_receiver_is_the_only_dynamic_receiver() -> None:
    """``f().bar()``'s receiver is a call; every other receiver is not."""
    root = _parse(_CALL_SOURCE)
    receivers: dict[str, str] = {}
    for nav in _all(root, "navigation_expression"):
        first = nav.named_children[0]
        receivers.setdefault(_text(nav, _CALL_SOURCE), first.type)
    assert receivers["f().bar"] == "call_expression"
    assert receivers["a.b"] == "identifier"
    for receiver_text, receiver_type in receivers.items():
        if receiver_text == "f().bar":
            continue
        assert receiver_type != "call_expression", receiver_text


def test_k5_method_reference_is_not_a_call() -> None:
    """``Foo::bar`` is a ``navigation_expression`` with no call wrapper."""
    root = _parse("fun f() {\n    val r = Foo::bar\n}\n")
    navs = _all(root, "navigation_expression")
    assert len(navs) == 1
    assert _direct_token(navs[0], "::")
    assert not _all(root, "call_expression")


def test_k5_safe_call_operator_is_a_token() -> None:
    """``?.`` is a plain token inside the navigation node, not its own node."""
    root = _parse("fun f(x: String?) {\n    x?.foo()\n}\n")
    nav = _only(root, "navigation_expression")
    assert _direct_token(nav, "?.")


def test_k5_trailing_lambda_hangs_off_the_call() -> None:
    """``list.map { ... }`` is one ``call_expression`` plus an ``annotated_lambda``."""
    root = _parse("fun f(list: List<Int>) {\n    list.map { it + 1 }\n}\n")
    call = _only(root, "call_expression")
    assert _named_types(call) == ["navigation_expression", "annotated_lambda"]


# ---------------------------------------------------------------------------
# K6 — lambda-valued properties
# ---------------------------------------------------------------------------


def test_k6_lambda_property_shapes() -> None:
    source = (
        "val f = { x: Int -> x + 1 }\n"
        "val g = fun(x: Int) = x + 1\n"
        "val h = { println() }\n"
    )
    root = _parse(source)
    props = _all(root, "property_declaration")
    assert len(props) == 3
    assert [_named_types(p)[0] for p in props] == [
        "variable_declaration",
        "variable_declaration",
        "variable_declaration",
    ]
    assert _only(props[0], "lambda_literal").type == "lambda_literal"
    assert _only(props[1], "anonymous_function").type == "anonymous_function"
    assert _all(props[0], "lambda_parameters")
    # The property name is the *direct* ``variable_declaration`` child's
    # identifier (lambda parameters are ``variable_declaration`` nodes too).
    names = [_text(p.named_children[0].named_children[0], source) for p in props]
    assert names == ["f", "g", "h"]


def test_k6_class_body_lambda_property() -> None:
    source = "class C {\n    val field = { y: Int -> y * 2 }\n}\n"
    root = _parse(source)
    prop = _only(root, "property_declaration")
    assert _named_types(prop)[0] == "variable_declaration"
    assert _only(prop, "lambda_literal").type == "lambda_literal"


def test_k6_local_lambda_property_is_a_property_declaration() -> None:
    root = _parse(
        "fun outer() {\n    val twice = { n: Int -> n * 2 }\n    twice(3)\n}\n"
    )
    assert len(_all(root, "property_declaration")) == 1
    assert _only(root, "lambda_literal").type == "lambda_literal"


# ---------------------------------------------------------------------------
# K7 — strings, templates, raw strings, chars
# ---------------------------------------------------------------------------


def test_k7_string_template_shapes() -> None:
    source = (
        "fun f(x: Int) {\n"
        '    val a = "plain"\n'
        '    val b = "score: $x"\n'
        '    val c = "calc: ${x + 1}"\n'
        '    val d = """raw $x text"""\n'
        "}\n"
    )
    root = _parse(source)
    literals = _all(root, "string_literal")
    assert len(literals) == 3
    # ``$x`` splits into two string_content leaves, NOT an interpolation.
    assert [c.type for c in literals[1].named_children] == [
        "string_content",
        "string_content",
        "string_content",
    ]
    assert [_text(c, source) for c in literals[1].named_children][-2:] == ["$", "x"]
    # ``${...}`` is a real interpolation node.
    interps = _all(root, "interpolation")
    assert len(interps) == 2  # one in ``c``, one in the raw string ``d``
    assert _all(interps[0], "binary_expression")
    # Raw strings are a distinct node type.
    raw = _only(root, "multiline_string_literal")
    assert _text(raw, source).startswith('"""')


def test_k7_character_literal_content_is_not_a_child_leaf() -> None:
    """``'a'`` has two ``'`` leaves — the content must come from the span."""
    source = "fun f() {\n    val c = 'a'\n}\n"
    root = _parse(source)
    char = _only(root, "character_literal")
    assert [child.type for child in char.children] == ["'", "'"]
    assert _text(char, source) == "'a'"


# ---------------------------------------------------------------------------
# K8 — annotations
# ---------------------------------------------------------------------------


def test_k8_attached_annotations_live_in_modifiers() -> None:
    source = (
        'class C {\n    @Deprecated("old")\n    fun gone() {}\n'
        "    @JvmField\n    val x = 1\n}\n"
    )
    root = _parse(source)
    func = _only(root, "function_declaration")
    prop = _only(root, "property_declaration")
    for decl in (func, prop):
        assert "modifiers" in _named_types(decl)
        modifiers = _only(decl, "modifiers")
        assert _only(modifiers, "annotation").type == "annotation"


def test_k8_top_level_annotated_function_is_attached_when_last() -> None:
    source = '@Deprecated("old")\nfun gone() {}\n'
    root = _parse(source)
    assert not _all(root, "annotated_expression")
    func = _only(root, "function_declaration")
    assert "modifiers" in _named_types(func)


def test_k8_annotation_detaches_when_a_sibling_follows() -> None:
    """Defect: the same source's CST shape depends on what follows it."""
    source = '@Deprecated("old")\nfun gone() {}\nfun other() {}\n'
    root = _parse(source)
    detached = _all(root, "annotated_expression")
    assert len(detached) == 1, "expected the annotation to detach"
    # The declaration itself survives — only the annotation moves.
    assert len(_all(root, "function_declaration")) == 2
    # The argument list became a sibling ``parenthesized_expression``
    # instead of living inside the annotation's ``constructor_invocation``.
    assert _only(detached[0], "parenthesized_expression").type == (
        "parenthesized_expression"
    )
    assert not _all(detached[0], "constructor_invocation")


def test_k8_a_trailing_comment_also_triggers_detachment() -> None:
    """Comments count as siblings, so this is not an exotic input."""
    root = _parse('@Deprecated("old")\nfun gone() {}\n// trailing\n')
    assert _all(root, "annotated_expression")


# ---------------------------------------------------------------------------
# K9 — typealias
# ---------------------------------------------------------------------------


def test_k9_type_alias_uses_the_type_field_not_name() -> None:
    source = "typealias Handler = (Int) -> Unit\ntypealias Name = String\n"
    root = _parse(source)
    aliases = _all(root, "type_alias")
    assert len(aliases) == 2
    for alias in aliases:
        assert alias.child_by_field_name("name") is None
        assert alias.child_by_field_name("type") is not None
    assert [_text(a.child_by_field_name("type"), source) for a in aliases] == [
        "Handler",
        "Name",
    ]


# ---------------------------------------------------------------------------
# K10 — semicolon policy
# ---------------------------------------------------------------------------


def _semicolon_leaves(root: Node, source: str) -> list[str]:
    return [_text(n, source) for n in _walk(root) if n.type == ";"]


def test_k10_semicolons_are_dropped_in_blocks_and_class_bodies() -> None:
    block = "fun f() {\n    val x = 1;\n    val y = 2\n}\n"
    class_body = "class A {\n    fun f() {}\n    ;\n}\n"
    assert _semicolon_leaves(_parse(block), block) == []
    assert _semicolon_leaves(_parse(class_body), class_body) == []


def test_k10_enum_semicolon_survives_as_the_entry_terminator() -> None:
    source = "enum class E {\n    A,\n    B;\n\n    fun go() {}\n}\n"
    assert len(_semicolon_leaves(_parse(source), source)) == 1


def test_k10_optional_enum_semicolon_is_indistinguishable_from_absent() -> None:
    """``A, B;`` and ``A, B`` differ only by the optional terminator."""
    with_semi = "enum class E {\n    A,\n    B;\n}\n"
    without = "enum class E {\n    A,\n    B\n}\n"
    assert len(_semicolon_leaves(_parse(with_semi), with_semi)) == 1
    assert len(_semicolon_leaves(_parse(without), without)) == 0
    # Both map to the same symbols/structure, which is why ``;`` is excluded
    # from the Kotlin structural hash (K10 policy).


# ---------------------------------------------------------------------------
# K11 — class members
# ---------------------------------------------------------------------------


_MEMBER_SOURCE = """class C(val v: Int) {
    val computed = 1
    var mutable: String = "x"
        get() = field
        set(value) {
            field = value
        }

    init {
        setup()
    }

    constructor(x: Int, y: Int) : this(x + y) {
        extra()
    }

    fun method() {}
}
"""


def test_k11_member_node_shapes() -> None:
    root = _parse(_MEMBER_SOURCE)
    assert len(_all(root, "primary_constructor")) == 1
    assert len(_all(root, "secondary_constructor")) == 1
    assert len(_all(root, "anonymous_initializer")) == 1
    assert len(_all(root, "function_declaration")) == 1
    assert len(_all(root, "property_declaration")) == 2
    assert len(_all(root, "getter")) == 1
    assert len(_all(root, "setter")) == 1


def test_k11_secondary_constructor_has_no_name_and_delegates() -> None:
    source = "class C(val v: Int) {\n    constructor(x: Int) : this(x) {}\n}\n"
    ctor = _only(_parse(source), "secondary_constructor")
    assert ctor.child_by_field_name("name") is None
    assert _only(ctor, "constructor_delegation_call").type == (
        "constructor_delegation_call"
    )


def test_k11_enum_entry_body_is_a_class_body_inside_the_entry() -> None:
    source = "enum class E {\n    A {\n        fun go() {}\n    },\n    B\n}\n"
    root = _parse(source)
    entry = _all(root, "enum_entry")[0]
    assert _only(entry, "class_body").type == "class_body"
    assert _only(entry, "function_declaration").type == "function_declaration"


def test_k11_anonymous_object_is_object_literal_with_no_name() -> None:
    source = (
        "fun f() {\n    val r = object : Runnable {\n        fun run() {}\n    }\n}\n"
    )
    root = _parse(source)
    literal = _only(root, "object_literal")
    assert literal.child_by_field_name("name") is None
    assert _only(literal, "class_body").type == "class_body"


# ---------------------------------------------------------------------------
# K12 — grammar floor and the known-unsupported list
# ---------------------------------------------------------------------------


def test_k12_dependency_floor_is_the_installed_grammar() -> None:
    """The floor is pinned in pyproject; the grammar must load and be ABI-compatible."""
    import importlib.metadata as md

    version = md.version("tree-sitter-kotlin")
    major, minor, *_ = (int(part) for part in version.split("."))
    assert (major, minor) >= (1, 1), version
    assert _LANGUAGE.abi_version == 14, "grammar ABI changed — re-verify probes"
    assert _PARSER.parse(b"fun f() {}\n").root_node.has_error is False


@pytest.mark.parametrize(
    "snippet",
    [
        "data object D\n",
        "value class M(val v: Double)\n",
        "data class P(\n    val x: Int,\n    val y: Int,\n)\n",
        "sealed interface S {\n    fun f()\n}\n",
        "fun interface H {\n    fun h()\n}\n",
        "package a.b.c\n\nimport d.E\n\nclass F\n",
    ],
)
def test_k12_current_syntax_parses(snippet: str) -> None:
    """Data objects, value classes, trailing commas, fun interfaces parse."""
    assert not _parse_tolerantly(snippet).has_error


def test_k12_defect_one_line_class_body_with_member() -> None:
    """D1: a one-line class body holding a member is a parse error."""
    tolerant = _parse_tolerantly("class A { fun f() {} }\n")
    assert tolerant.has_error, "grammar unexpectedly started accepting this"
    # The body is mislabelled and the member is swallowed by an ERROR node,
    # so a member walk that only descends into body containers finds nothing.
    assert _all(tolerant, "enum_class_body")
    nested = _only(tolerant, "function_declaration")
    ancestors = _ancestor_types(nested)
    assert "ERROR" in ancestors
    assert "class_body" not in ancestors
    # A newline (or a semicolon) before the brace avoids the defect entirely.
    assert not _parse_tolerantly("class A { fun f() {}\n}\n").has_error
    assert not _parse_tolerantly("class A { fun f() {}; }\n").has_error


def test_k12_defect_annotated_single_entry_enum() -> None:
    """D2: the whole enum declaration is destroyed (recovered by the scanner)."""
    source = "@Ann(1)\nenum class E {\n    A\n}\n"
    tolerant = _parse_tolerantly(source)
    assert not tolerant.has_error, "the parser reports success while losing the enum"
    assert not _all(tolerant, "class_declaration")
    infix = _only(tolerant, "infix_expression")
    assert [_text(c, source) for c in infix.named_children[:2]] == ["enum", "class"]
    assert infix.named_children[2].type == "call_expression"
    # A trailing comma, or a second entry, parses correctly.
    assert _all(_parse("@Ann(1)\nenum class E {\n    A,\n}\n"), "class_declaration")
    assert _all(
        _parse("@Ann(1)\nenum class E {\n    A,\n    B\n}\n"), "class_declaration"
    )


def test_k12_defect_annotated_annotation_class() -> None:
    """D3: an annotated ``annotation class`` is destroyed (recovered by the scanner)."""
    source = "@Target(1)\nannotation class A\n"
    tolerant = _parse_tolerantly(source)
    assert not tolerant.has_error
    assert not _all(tolerant, "class_declaration")
    infix = _only(tolerant, "infix_expression")
    children = infix.named_children
    assert [_text(c, source) for c in children] == ["annotation", "class", "A"]
    # With a body the name becomes a ``call_expression`` with a lambda body.
    body = _parse_tolerantly("@Target(1)\nannotation class A {\n    val x: Int\n}\n")
    body_infix = _only(body, "infix_expression")
    assert body_infix.named_children[2].type == "call_expression"
    # Unannotated, the declaration parses normally.
    assert _all(_parse("annotation class A\n"), "class_declaration")


def test_k12b_detached_annotation_is_a_sibling_of_its_declaration() -> None:
    """D4: an annotated top-level ``fun`` with a following sibling detaches."""
    source = (
        "@Ann(1)\nfun a(): Int {\n    return 1\n}\n\nfun b(): Int {\n    return 2\n}\n"
    )
    root = _parse_tolerantly(source)
    assert not root.has_error
    children = root.named_children
    assert [c.type for c in children] == [
        "annotated_expression",
        "function_declaration",
        "function_declaration",
    ]
    # The annotation is a *sibling* of its declaration, not a child of it.
    assert _all(children[0], "annotation")
    assert not _all(children[1], "annotation")
    # The same declaration as the last thing in the file keeps its annotation
    # *inside* the modifiers child instead — two shapes, one meaning.
    attached = _parse(
        "fun b(): Int {\n    return 2\n}\n\n@Ann(1)\nfun a(): Int {\n    return 1\n}\n"
    )
    annotated = _all(attached, "function_declaration")[1]
    assert _all(annotated, "annotation")


def test_k12d_fun_named_after_soft_keyword_in_type_body() -> None:
    """D5: a type-body ``fun dynamic()`` keeps its body but loses its name."""
    source = "class C {\n    fun dynamic(): Int {\n        return 1\n    }\n}\n"
    tolerant = _parse_tolerantly(source)
    assert tolerant.has_error, "grammar unexpectedly started accepting this"
    fn = _only(tolerant, "function_declaration")
    name = fn.child_by_field_name("name")
    assert name is not None
    assert name.is_missing
    assert _text(name, source) == ""
    # The swallowed token survives as an unnamed child sitting *immediately*
    # before the zero-width gap — the exact anchor the scanner recovers from.
    gap_index = list(fn.children).index(name)
    swallowed = fn.children[gap_index - 1]
    assert not swallowed.is_named
    assert _text(swallowed, source) == "dynamic"
    assert swallowed.end_byte == name.start_byte
    # The body is intact, so the declaration is complete apart from its name.
    assert _all(fn, "function_body")


def test_k12d_generic_fun_named_after_soft_keyword() -> None:
    """D5: the same mangle survives generic type parameters, without error."""
    source = "fun <T> dynamic(x: T): T {\n    return x\n}\n"
    tolerant = _parse_tolerantly(source)
    assert tolerant.has_error
    fn = _only(tolerant, "function_declaration")
    name = fn.child_by_field_name("name")
    assert name is not None and name.is_missing
    assert _text(fn.children[list(fn.children).index(name) - 1], source) == "dynamic"


def test_k12d_top_level_fun_named_after_soft_keyword() -> None:
    """D5: the same source at top level becomes an ``anonymous_function``."""
    source = "fun dynamic(): Int {\n    return 1\n}\n"
    tolerant = _parse_tolerantly(source)
    assert tolerant.has_error, "grammar unexpectedly started accepting this"
    assert not _all(tolerant, "function_declaration")
    anon = _only(tolerant, "anonymous_function")
    first = anon.named_children[0]
    assert first.type == "ERROR"
    # Here the name *does* survive, as the ERROR node's text.
    assert _text(first, source) == "dynamic"
    assert _all(anon, "function_body")


@pytest.mark.parametrize("keyword", ["dynamic", "suspend"])
def test_k12e_soft_keyword_positions_that_collapse_the_whole_file(keyword: str) -> None:
    """D6: these positions turn the entire file into a single ``ERROR``."""
    collapses = (
        f"fun use() {{\n    val {keyword} = 1\n}}\n",
        f"fun use() {{\n    other({keyword} = 1)\n}}\n",
        f"fun use(xs: List<Int>) {{\n    xs.map {{ {keyword} -> {keyword} }}\n}}\n",
    )
    for source in collapses:
        tolerant = _parse_tolerantly(source)
        assert tolerant.has_error, source
        assert [c.type for c in tolerant.named_children] == ["ERROR"], source


def test_k12e_dynamic_is_the_only_keyword_breaking_a_bare_call() -> None:
    """D6: ``suspend()`` survives as a declaration while ``dynamic()`` does not.

    Neither call is collected — the grammar consumes the name as a modifier
    in both spellings — but the difference matters: ``dynamic()`` collapses
    the file, ``suspend()`` leaves the enclosing declaration intact, so the
    scanner still emits that declaration.  Pinned so a grammar upgrade that
    changes either behaviour is caught here.
    """
    dynamic_call = _parse_tolerantly("fun use() {\n    dynamic()\n}\n")
    assert [c.type for c in dynamic_call.named_children] == ["ERROR"]

    suspend_call = _parse_tolerantly("fun use() {\n    suspend()\n}\n")
    assert [child.type for child in suspend_call.named_children] == [
        "function_declaration"
    ]
    assert not _all(suspend_call, "call_expression")


def test_k12e_soft_keyword_parameter_names_keep_the_declaration() -> None:
    """D6: a soft-keyword *parameter* name damages only the body expression."""
    for keyword in ("dynamic", "suspend"):
        source = f"fun use({keyword}: Int) {{\n    println({keyword})\n}}\n"
        root = _parse_tolerantly(source)
        assert root.has_error, source
        fn = _only(root, "function_declaration")
        assert _text(fn.child_by_field_name("name"), source) == "use"
        # The declaration and the call survive; only the argument is lost.
        assert _all(root, "call_expression")
        assert _all(root, "ERROR")


@pytest.mark.parametrize(
    "keyword",
    ["value", "field", "get", "set", "by", "where", "init", "param", "open", "data"],
)
def test_k12e_ordinary_soft_keywords_are_valid_names(keyword: str) -> None:
    """The other soft keywords really are ordinary identifiers here.

    This is the contrast that makes D5/D6 a *two-keyword* grammar lag rather
    than a general soft-keyword limitation: ``dynamic``/``suspend`` are the
    type modifiers the grammar eats, and every other soft keyword parses as a
    plain name in every position probed above.
    """
    source = (
        f"class {keyword} {{\n"
        f"    fun {keyword}(): Int {{\n"
        f"        val {keyword} = 1\n"
        f"        return {keyword}\n"
        f"    }}\n"
        f"}}\n"
        f"\nfun {keyword}(): Int {{\n    return 1\n}}\n"
    )
    assert not _parse_tolerantly(source).has_error


# ---------------------------------------------------------------------------
# K13 — stacked annotations dissolve a top-level declaration (D7)
# ---------------------------------------------------------------------------


def test_k13_stacked_annotations_destroy_a_top_level_class() -> None:
    """D7: two annotations plus a following declaration erase the class.

    The declaration vanishes and the following declaration takes its
    place — with ``has_error`` ``False``, so nothing but the symbol list
    reveals it.  The shape is an ``annotated_expression`` chain whose
    innermost layer wraps an ``infix_expression``: the ``class`` keyword
    is read as an infix operator, the class name as its left operand and
    the class body as a trailing lambda.
    """
    source = "@A\n@B\nclass B {\n    val x: Int = 1\n}\nclass Z {}\n"
    tolerant = _parse_tolerantly(source)
    assert not tolerant.has_error, "parser reports success while losing B"
    assert _named_types(tolerant) == ["annotated_expression", "class_declaration"]
    assert not any(
        _text(child.child_by_field_name("name"), source) == "B"
        for child in tolerant.named_children
        if child.type == "class_declaration"
    )
    outer, inner = _all(tolerant, "annotated_expression")
    assert _named_types(outer) == ["annotation", "annotated_expression"]
    assert _named_types(inner) == ["annotation", "infix_expression"]
    infix = _only(tolerant, "infix_expression")
    assert [_text(c, source) for c in infix.named_children[:2]] == ["class", "B"]
    assert infix.named_children[2].type == "lambda_literal"
    # The damage is one top-level node, and its span covers the class bytes.
    assert _text(outer, source).endswith("val x: Int = 1\n}")


def test_k13_the_destroy_depends_on_what_follows() -> None:
    """The same declaration parses cleanly when nothing follows it.

    A single annotation is harmless, a trailing comment does not count as
    a follower, and the two-annotation stack nested inside a class body is
    never damaged — so the CST shape is a property of the *file*, not of
    the declaration.
    """
    pair = "@A\n@B\nclass B {\n    val x: Int = 1\n}\n"

    single = _parse("@A\nclass B {\n    val x: Int = 1\n}\nclass Z {}\n")
    assert not _all(single, "infix_expression")
    assert len(_all(single, "class_declaration")) == 2

    last = _parse(pair + "\n\n")
    assert not _all(last, "infix_expression")
    assert len(_all(last, "class_declaration")) == 1

    comment_only = _parse(pair + "// trailing\n")
    assert not _all(comment_only, "infix_expression")
    assert len(_all(comment_only, "class_declaration")) == 1

    nested = _parse(
        "class Outer {\n"
        "    @A\n"
        "    @B\n"
        "    class Inner {\n"
        "        val x: Int = 1\n"
        "    }\n"
        "    class Z\n"
        "}\n"
    )
    assert not _all(nested, "infix_expression")
    assert len(_all(nested, "class_declaration")) == 3


@pytest.mark.parametrize(
    "head",
    [
        "class B {\n    val x: Int = 1\n}",
        "interface B {\n    fun f()\n}",
        "annotation class B {\n    val v: Int\n}",
        "sealed class B {\n    class X : B()\n}",
        "data object B {\n    fun f() {}\n}",
    ],
)
def test_k13_these_heads_are_dissolved_by_the_stack(head: str) -> None:
    """One shape eats plain classes, interfaces and ``annotation class``."""
    source = f"@A\n@B\n{head}\nclass Z {{}}\n"
    tolerant = _parse_tolerantly(source)
    assert not tolerant.has_error
    assert _all(tolerant, "infix_expression"), head
    assert _named_types(tolerant) == ["annotated_expression", "class_declaration"]


@pytest.mark.parametrize(
    ("head", "declaration_type"),
    [
        ("data class B(val x: Int)", "class_declaration"),
        ("value class B(val v: Int)", "class_declaration"),
        ("enum class B {\n    X,\n    Y\n}", "class_declaration"),
        ("fun interface B {\n    fun run()\n}", "class_declaration"),
        ("object B {\n    fun f() {}\n}", "object_declaration"),
    ],
)
def test_k13_other_heads_survive_the_very_same_stack(
    head: str, declaration_type: str
) -> None:
    """The same stack leaves these heads intact — there is no rule to encode."""
    source = f"@A\n@B\n{head}\nclass Z {{}}\n"
    root = _parse(source)
    assert not _all(root, "infix_expression")
    annotated = [
        declaration
        for declaration in _all(root, declaration_type)
        if _text(declaration, source).startswith("@A")
    ]
    assert annotated, "the annotated declaration kept its modifiers"
    assert len(_all(root, "annotation")) == 2


# ---------------------------------------------------------------------------
# K14 — a bodyless destroyed declaration absorbs its successor (D7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sibling", "keyword", "absorbed_name"),
    [
        ("class C {\n    val x: Int = 1\n}\n", "class", "C"),
        ("interface I {\n    fun f()\n}\n", "interface", "I"),
    ],
)
def test_k14_a_bodyless_destroyed_class_absorbs_the_next_declaration(
    sibling: str, keyword: str, absorbed_name: str
) -> None:
    """D7: two declarations become one top-level node, both names gone.

    The chain keeps growing: the absorbed declaration's keyword becomes
    the outer ``infix_expression``'s operator and its body becomes the
    trailing lambda, so a name-based recovery cannot see it at all.
    """
    source = f"@A\n@B\nclass B\n{sibling}"
    tolerant = _parse_tolerantly(source)
    assert not tolerant.has_error, "parser reports success while losing both"
    assert _named_types(tolerant) == ["annotated_expression"]
    outer, inner = _all(tolerant, "infix_expression")
    assert [_text(c, source) for c in inner.named_children[:2]] == ["class", "B"]
    assert _text(inner.named_children[2], source) == keyword
    assert _text(outer.named_children[1], source) == absorbed_name
    assert outer.named_children[2].type == "lambda_literal"
    # The absorbed declaration's whole text lives inside B's node.
    assert f"{keyword} {absorbed_name}" in _text(tolerant.named_children[0], source)


def test_k14_absorption_needs_a_class_like_follower() -> None:
    """A following ``fun``, ``object`` or bodyless class is *not* absorbed."""
    for sibling in (
        "fun g() {\n    println(1)\n}\n",
        "class Z\n",
        "object O {}\n",
    ):
        source = f"@A\n@B\nclass B\n{sibling}"
        root = _parse(source)
        assert not _all(root, "infix_expression"), sibling
        first = root.named_children[0]
        assert first.type == "class_declaration", sibling
        assert _all(first, "annotation"), sibling


# ---------------------------------------------------------------------------
# K15 — an argument-bearing annotation on a ``fun`` detaches (D4/D7)
# ---------------------------------------------------------------------------


def test_k15_argument_bearing_annotation_on_a_top_level_fun_detaches() -> None:
    """``@Ann(1)`` + a following sibling → a sibling ``annotated_expression``."""
    source = "@Ann(1)\nfun a(): Int {\n    return 1\n}\nfun b() {}\n"
    tolerant = _parse_tolerantly(source)
    assert not tolerant.has_error
    assert _named_types(tolerant) == [
        "annotated_expression",
        "function_declaration",
        "function_declaration",
    ]
    detached = tolerant.named_children[0]
    assert _named_types(detached) == ["annotation", "parenthesized_expression"]
    assert _text(detached.named_children[1], source) == "(1)"
    # The detach takes the arguments out of the ``annotation`` node too, so
    # the annotation itself is childless except for its ``@`` and payload.
    assert not _all(tolerant.named_children[1], "annotation")


def test_k15_a_trailing_comment_counts_as_a_follower() -> None:
    """Nothing else follows except a comment — and the annotation still detaches."""
    source = "@Ann(1)\nfun a(): Int {\n    return 1\n}\n// trailing\n"
    tolerant = _parse_tolerantly(source)
    assert not tolerant.has_error
    assert _named_types(tolerant) == [
        "annotated_expression",
        "function_declaration",
        "line_comment",
    ]


def test_k15_without_arguments_the_annotation_stays_attached() -> None:
    """The same source with a bare ``@Ann`` keeps the attached spelling."""
    source = "@Ann\nfun a(): Int {\n    return 1\n}\nfun b() {}\n"
    root = _parse(source)
    assert _named_types(root) == ["function_declaration", "function_declaration"]
    first = root.named_children[0]
    assert _named_types(first)[0] == "modifiers"
    assert _all(first, "annotation")

    # As the last declaration the argument-bearing spelling is attached too.
    last = _parse("@Ann(1)\nfun a(): Int {\n    return 1\n}\n")
    assert _named_types(last) == ["function_declaration"]
    assert _named_types(last.named_children[0])[0] == "modifiers"


# ---------------------------------------------------------------------------
# K16 — the ``annotation`` keyword is a childless ``annotation`` node (D7)
# ---------------------------------------------------------------------------


def test_k16_the_annotation_keyword_shares_the_annotation_node_type() -> None:
    """``annotation class Ann``'s keyword is a childless ``annotation`` leaf.

    A real annotation always carries its ``@`` token and payload.  Any
    rule that treats "every node of type ``annotation``" as an annotation
    would blind the keyword too, and the blinded source would re-parse
    ``annotation class Ann`` as a plain ``class Ann``.
    """
    source = "annotation class Ann\n"
    root = _parse(source)
    keyword = _only(root, "annotation")
    assert keyword.child_count == 0
    assert _text(keyword, source) == "annotation"
    assert keyword.parent is not None
    assert keyword.parent.type == "class_modifier"
    assert _only(root, "class_declaration").child_by_field_name("name") is not None

    annotated = "@Ann\nfun f() {}\n"
    real = _only(_parse(annotated), "annotation")
    assert real.child_count > 0
    assert _text(real, annotated) == "@Ann"
