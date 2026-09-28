"""PHP scanner — symbol and call extraction via ``tree-sitter-php``.

Phase 4 of v0.17.0.  The grammar (``tree-sitter-php 0.24.1``, ABI 15, on
``tree-sitter 0.26.0``) ships **two** languages; this scanner loads
``language_php()`` — the HTML-embedded grammar that matches the ``.php``
file format — because the pure-source ``language_php_only()`` hard-errors
on an HTML template (probe evidence in ``tests/test_php_probes.py``).
A ``.php`` file that never opens ``<?php`` parses as one ``text`` node
with no error: PHP itself would output those bytes, so "no symbols" is
the correct answer rather than a silent gap.

Every grammar shape this file depends on was resolved empirically
**before** any collector code was written and is pinned in
``tests/test_php_probes.py`` (probes PH1–PH12 plus the extra boundaries
listed there).  The facts that shape the code:

- ``function_call_expression`` carries its callee in the **``function``**
  field (PH1) — a ``name`` or ``qualified_name`` — *not* in ``name``.
- Member calls (``->``), nullsafe calls (``?->``) and scoped calls
  (``::``) carry the method name in the ``name`` field (PH1/PH2); for a
  *dynamic* name that field holds a ``variable_name`` or ``string``
  instead of a ``name`` node, and only a ``name`` is a static target.
- ``new Foo()`` is an ``object_creation_expression`` — not call-shaped —
  so constructor invocations are never captured, matching the JS/TS/Java
  ``new`` boundary.  ``Foo::__construct()`` is excluded by the magic-name
  rule below.
- First-class callable syntax (``strlen(...)``, ``$obj->m(...)``) parses
  as a call node whose arguments hold a lone ``variadic_placeholder``; it
  is a reference, not an invocation, and is excluded.  A spread call
  (``f(...$args)``) nests an ``argument`` instead and stays a call.
- Attributes (``#[Route]``) are **children** of the declaration (PH4), so
  an attribute edit is part of that declaration's own hash — no sibling
  folding is needed.
- Property hooks (PHP 8.4) are named bodies inside the property; the
  property stays class-shell content while each hook owns the calls in
  its body (the Kotlin accessor rule).

Symbol model: ``class_declaration`` → CLASS, ``interface_declaration`` →
INTERFACE, ``enum_declaration`` → ENUM, ``trait_declaration`` → **CLASS**
(PH8 — the claim taxonomy has no trait type; trait methods carry
``parent_class`` = the trait name), a ``function_definition`` at module
scope (top level, inside a ``namespace`` body, or inside a ``declare``
block) → FUNCTION, a class-body ``method_declaration`` → METHOD with
``parent_class``, and a top-level closure assignment
(``$fn = function () {}`` / ``$fn = fn () => ...``) → FUNCTION named
without the ``$`` (PH6, the PHP spelling of the JS ``const f = ...``
rule).  ``TYPE_ALIAS`` never fires — PHP has no type-alias construct.
``namespace_definition`` descends (it is not a symbol, like Python
modules); anonymous classes (``new class {...}``) produce no symbol
(PH5); a closure *inside* a function body is a caller, not a symbol (the
local-declaration boundary every language shares).

Callers: a named body owns the calls in it.  Methods, functions, closure
assignments and property hooks (named after their property, mirroring
Kotlin's accessors) are callers; an unnamed body — a bare lambda, a call
argument, an array value — owns nothing, so its calls belong to the
nearest enclosing named caller (the Phase 1 G1/G2 rule).  Methods of an
anonymous class are callers with no class attribution.  ``$this->m()``,
``self::m()``/``static::m()``/``parent::m()``, ``Foo\\Bar::baz()``,
``?->`` chains, subscript/object receivers and parenthesised receivers
all resolve to the final name; a receiver that is itself a call
(``f()->m()``, ``$o->a()->b()``) is excluded, exactly like JS/TS.

Magic methods: ``__construct``/``__toString``/... are ordinary METHOD
symbols (PH12) — the dunder heuristic governs *call capture* only.  PHP
spells its magic methods with a leading ``__`` and no trailing pair
(unlike Python's ``__init__``), so a member/scoped call whose name starts
with ``__`` is not captured; a bare ``__foo()`` call is, exactly as the
shared dunder rule treats bare calls in every other language.

Hash model: CLASS/ENUM/trait symbols carry a class-*shell* hash with
``method_declaration`` subtrees excluded, so a method edit fires
``CHANGED_FUNCTION`` only (the disjoint-facts rule); properties, enum
cases, trait uses, constants and attributes stay shell content, so
editing one fires ``CHANGED_CLASS``.  INTERFACE symbols carry no hash —
there is no ``CHANGED_INTERFACE`` claim type.  METHODS carry a full-node
hash, except **declaration-only** methods (interface methods and abstract
methods), which carry ``body_hash=None`` and can never fire
``CHANGED_FUNCTION`` (PH9).  PHP semicolons are required syntax and are
hashed as content (PH10), and trailing commas stay hash-invisible like
every other language (the shared rule).

String hashing: PHP is the one language whose *quote style selects the
escape rules*, so its strings get a dedicated leaf normaliser
(:func:`php_string_leaf`): ``'x'`` and ``"x"`` hash identically, while
``'\\n'`` (backslash-n) and ``"\\n"`` (newline) stay different;
interpolation spans are marked so a literal ``"\\$x"`` can never collide
with an interpolated ``"$x"``; heredoc and nowdoc keep their distinct
node types, and their marker lines are delimiter formatting rather than
content (probe PH11).

Accepted edges (loud, or correct-by-design): a file without ``<?php``
contributes no symbols (PHP semantics, pinned); asymmetric visibility in
a *promoted constructor parameter* is a grammar parse error (loud —
``has_error`` is set, so the family's parse warning fires), while a
standalone property with the same modifier parses cleanly (pinned).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser, Tree

from nowreck.scanner._tree_sitter_helpers import (
    class_shell_hash,
    structural_hash,
    text_of,
)
from nowreck.scanner.call_evidence import CallEvidence
from nowreck.scanner.symbol_index import Symbol, SymbolType

if TYPE_CHECKING:
    from tree_sitter import Node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-process singleton: load the grammar once and reuse it.
# ---------------------------------------------------------------------------

_php_language_cache: Language | None = None


def _get_php_language() -> Language:
    """Return the PHP tree-sitter language, loading it on first call.

    Loads ``language_php()`` — the HTML-embedded grammar matching the
    ``.php`` file format — not ``language_php_only()``, which hard-errors
    on templates (see the module docstring and probe PH-dep).
    """
    global _php_language_cache  # noqa: PLW0603
    if _php_language_cache is None:
        import tree_sitter_php as ts_php  # noqa: PLC0415

        _php_language_cache = Language(ts_php.language_php())
    return _php_language_cache


def _new_parser(language: Language) -> Parser:
    """Create a fresh parser wired to the given grammar."""
    return Parser(language)


# ---------------------------------------------------------------------------
# Grammar vocabulary (resolved by probes PH1-PH12)
# ---------------------------------------------------------------------------

# Type declarations that become symbols.  ``trait`` maps to CLASS (PH8):
# the claim taxonomy has no trait type, so a trait is a class-like type
# whose methods still carry ``parent_class``.
_TYPE_DECL_KINDS: dict[str, SymbolType] = {
    "class_declaration": SymbolType.CLASS,
    "interface_declaration": SymbolType.INTERFACE,
    "enum_declaration": SymbolType.ENUM,
    "trait_declaration": SymbolType.CLASS,
}

# Nodes that hold a type's members: a class/interface/trait body and an
# enum's declaration list (PH7 — enum cases and methods share one node).
_TYPE_BODY_CONTAINERS: frozenset[str] = frozenset(
    {"declaration_list", "enum_declaration_list"}
)

# PHP methods are ``method_declaration`` (inside a type body); top-level
# functions are ``function_definition``.  ``method_declaration`` is part
# of the shared method-node set, so a class *shell* excludes it without a
# per-language extension (the disjoint-facts rule).
_METHOD_DECL_TYPES: frozenset[str] = frozenset({"method_declaration"})

# Closure values on the right of an assignment (PH6).
_FUNCTION_VALUE_TYPES: frozenset[str] = frozenset(
    {"anonymous_function", "arrow_function"}
)

# Statements whose bodies are module scope: a namespace block and a
# ``declare(...) { ... }`` block both wrap declarations in a
# ``compound_statement``, and declarations inside them are top-level
# (probes PH-extra).
_MODULE_WRAPPERS: frozenset[str] = frozenset(
    {"namespace_definition", "declare_statement"}
)

# Every call-shaped node type (probe PH1/PH2/PH12).
_CALL_NODE_TYPES: frozenset[str] = frozenset(
    {
        "function_call_expression",
        "member_call_expression",
        "nullsafe_member_call_expression",
        "scoped_call_expression",
    }
)

# Receiver shapes that are themselves calls: a member call whose receiver
# is one of these has no static target (``f()->m()``, ``$o->a()->b()``).
_CALL_RECEIVER_TYPES: frozenset[str] = frozenset(_CALL_NODE_TYPES)

# Interpolation marker for the string value normaliser: a private-use
# byte that ordinary string content does not contain, so an interpolated
# expression can never hash equal to literal text.
_INTERPOLATION_MARK = "\x1c"


# ---------------------------------------------------------------------------
# String value normalisation (PH11)
# ---------------------------------------------------------------------------


def php_string_leaf(node: Node, source_bytes: bytes) -> tuple[str, str]:
    """Canonical ``(type token, value)`` of a PHP string leaf (hash input).

    PHP's quote style selects both the node type and the escape rules —
    ``'\\n'`` is two characters while ``"\\n"`` is one — so the hash
    cannot be neutral to the quote character *and* faithful to the value
    by stripping delimiters alone.  This normaliser therefore owns the
    whole leaf: ``string`` and ``encapsed_string`` share one canonical
    type token (so ``'x'``/``"x"`` hash equally, the PH11 requirement)
    and each literal is reconstructed from its children:

    * ``string_content`` / ``nowdoc_string`` contribute their text;
    * ``escape_sequence`` contributes the decoded value of the escape;
    * an interpolation child contributes a marked copy of its source text,
      so ``"\\$x"`` (a literal dollar) and ``"$x"`` (an interpolated
      variable) can never collide.

    Heredoc and nowdoc keep their **own** type tokens, exactly like
    Kotlin's raw strings: raw vs interpolated is semantically
    significant, so switching ``'abc'`` to ``<<<'EOT'`` stays a change
    even though the value matches.  Their bodies are read the same way,
    which excludes the delimiter lines (the newline after ``<<<EOT`` and
    the one before the closing marker are not part of the body's content).
    """
    if node.type in ("string", "encapsed_string"):
        return "php-string", _php_string_value(node, source_bytes)
    return node.type, _php_string_value(node, source_bytes)


def _php_string_value(node: Node, source_bytes: bytes) -> str:
    """The value text of a PHP string literal (see :func:`php_string_leaf`)."""
    if node.type in ("heredoc", "nowdoc"):
        body_type = "heredoc_body" if node.type == "heredoc" else "nowdoc_body"
        body = next(
            (child for child in node.named_children if child.type == body_type),
            None,
        )
        if body is None:
            # An empty heredoc/nowdoc has no body node at all.
            return ""
        return _string_children_text(
            body, source_bytes, double_quoted=node.type == "heredoc"
        )
    return _string_children_text(
        node, source_bytes, double_quoted=node.type != "string"
    )


def _string_children_text(
    node: Node,
    source_bytes: bytes,
    *,
    double_quoted: bool,
) -> str:
    """Reconstruct a string node's value from its named children."""
    parts: list[str] = []
    for child in node.named_children:
        if child.type in ("string_content", "nowdoc_string"):
            parts.append(text_of(child, source_bytes))
        elif child.type == "escape_sequence":
            parts.append(
                _decode_escape(
                    text_of(child, source_bytes), double_quoted=double_quoted
                )
            )
        else:
            # An interpolation expression — runtime-evaluated content.
            parts.append(_INTERPOLATION_MARK + text_of(child, source_bytes))
    return "".join(parts)


# Simple double-quoted escapes, per the PHP manual.
_SIMPLE_ESCAPES: dict[str, str] = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "e": "\x1b",
    "f": "\f",
    "\\": "\\",
    "$": "$",
    '"': '"',
}


def _decode_escape(escape: str, *, double_quoted: bool) -> str:
    """Decode one ``escape_sequence`` token to its value text.

    Single-quoted strings decode exactly ``\\\\`` and ``\\'``; double-quoted
    strings (and heredocs) decode the documented escape set — simple
    escapes, octal, ``\\xHH`` and ``\\u{...}`` — and anything unrecognised
    is kept verbatim, which is also what PHP does with an unknown escape.
    """
    if len(escape) < 2 or escape[0] != "\\":
        return escape
    body = escape[1:]
    if not double_quoted:
        return body if body in ("\\", "'") else escape
    if body in _SIMPLE_ESCAPES:
        return _SIMPLE_ESCAPES[body]
    if (
        body.startswith("x")
        and 1 <= len(body) - 1 <= 2
        and all(char in "0123456789abcdefABCDEF" for char in body[1:])
    ):
        return chr(int(body[1:], 16))
    if body.startswith("u{") and body.endswith("}"):
        digits = body[2:-1]
        if digits and all(char in "0123456789abcdefABCDEF" for char in digits):
            code = int(digits, 16)
            if code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF:
                return chr(code)
        return escape
    if body and len(body) <= 3 and all(char in "01234567" for char in body):
        # PHP octal escapes wrap to one byte.
        return chr(int(body, 8) & 0xFF)
    return escape


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_php_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single ``.php`` file and return the symbols it defines."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_php_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(source_bytes)
    root = tree.root_node  # type: ignore[attr-defined]

    if root.has_error:
        logger.warning(
            "Syntax error detected in %s — extracting partial symbols",
            path,
        )

    symbol_path = _relative_to(path, repo_root)
    return _collect_php_symbols(root, source_bytes, symbol_path)


def scan_php_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[CallEvidence]:
    """Parse a single ``.php`` file and return all call evidence it contains."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_php_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(source_bytes)
    root = tree.root_node  # type: ignore[attr-defined]

    rel_path = _relative_to(path, repo_root)
    return _extract_php_calls(root, source_bytes, rel_path)


def _relative_to(path: Path, repo_root: str | Path | None) -> Path:
    """Resolve *path* against *repo_root*, falling back to the absolute path."""
    if repo_root is None:
        return path
    try:
        return path.relative_to(Path(repo_root).resolve())
    except ValueError:
        return path


# ---------------------------------------------------------------------------
# Hashes
# ---------------------------------------------------------------------------


def _declaration_hash(node: Node, source_bytes: bytes) -> str:
    """Content hash for one function-like declaration.

    PHP semicolons are required syntax (PH10), so no leaf type is
    excluded; the string normaliser gives ``'x'`` and ``"x"`` one value.
    """
    return structural_hash(node, source_bytes, string_normaliser=php_string_leaf)


def _type_shell_hash(
    node: Node,
    symbol_type: SymbolType,
    source_bytes: bytes,
) -> str | None:
    """Shell hash for a type declaration, or ``None`` when it has none.

    CLASS/ENUM/trait bodies are class-shell content: properties, enum
    cases, constants, trait uses and attributes are hashed, while
    ``method_declaration`` subtrees are excluded so a method edit can
    never fire ``CHANGED_CLASS``.  INTERFACE declarations carry no hash —
    there is no ``CHANGED_INTERFACE`` claim type.
    """
    if symbol_type in (SymbolType.CLASS, SymbolType.ENUM):
        return class_shell_hash(node, source_bytes, string_normaliser=php_string_leaf)
    return None


# ---------------------------------------------------------------------------
# Symbol collection
# ---------------------------------------------------------------------------


def _collect_php_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Collect symbols from module scope.

    Only module scope yields symbols: the walk visits a file's top-level
    declarations and the bodies of ``namespace``/``declare`` wrappers,
    never a function or method body — the local-declaration boundary
    every language shares.  Statements other than declarations
    (``use``, ``declare``, echo, expressions) carry no symbols, except a
    closure assignment (:func:`_collect_closure_symbol`).
    """
    symbols: list[Symbol] = []
    _collect_module_declarations(root_node, source_bytes, file_path, symbols)
    return symbols


def _collect_module_declarations(
    container: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Walk one module-scope container, collecting its declarations."""
    for child in container.named_children:
        if child.type in _TYPE_DECL_KINDS:
            _collect_type_declaration(child, source_bytes, file_path, symbols)
        elif child.type == "function_definition":
            _collect_function(child, source_bytes, file_path, symbols)
        elif child.type == "expression_statement":
            _collect_closure_symbol(child, source_bytes, file_path, symbols)
        elif child.type in _MODULE_WRAPPERS:
            body = _wrapper_body(child)
            if body is not None:
                _collect_module_declarations(body, source_bytes, file_path, symbols)


def _wrapper_body(node: Node) -> Node | None:
    """The ``compound_statement`` body of a namespace/declare wrapper.

    The ``namespace App;`` form has no body — its declarations follow as
    siblings — so ``None`` is returned and the walk simply continues.
    """
    for child in node.named_children:
        if child.type == "compound_statement":
            return child
    return None


def _collect_function(
    node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Emit a module-scope ``FUNCTION`` symbol."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = text_of(name_node, source_bytes)
    if not name:
        return
    symbols.append(
        Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            body_hash=_declaration_hash(node, source_bytes),
        )
    )


def _collect_closure_symbol(
    statement: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Emit a ``FUNCTION`` symbol for ``$f = function () {}`` (PH6).

    Only the statement's own assignment is inspected: a closure nested
    anywhere deeper is a caller, not a symbol, and a closure assigned to
    anything but a plain variable (``$this->f``, an array element) has no
    name to index.
    """
    if statement.named_child_count == 0:
        return
    assignment = statement.named_children[0]
    owned = _closure_assignment(assignment)
    if owned is None:
        return
    target, function_node = owned
    name = _variable_name_text(target, source_bytes)
    if not name:
        return
    symbols.append(
        Symbol(
            name=name,
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            line_number=function_node.start_point[0] + 1,
            body_hash=_declaration_hash(function_node, source_bytes),
        )
    )


def _collect_type_declaration(
    node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Emit a type declaration's symbol and collect its members."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = text_of(name_node, source_bytes)
    if not name:
        return

    symbol_type = _TYPE_DECL_KINDS[node.type]
    symbols.append(
        Symbol(
            name=name,
            symbol_type=symbol_type,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            body_hash=_type_shell_hash(node, symbol_type, source_bytes),
        )
    )

    body = _type_body(node)
    if body is not None:
        _walk_members(body, source_bytes, file_path, name, symbols)


def _type_body(node: Node) -> Node | None:
    """The body container of a type declaration, or ``None``."""
    for child in node.named_children:
        if child.type in _TYPE_BODY_CONTAINERS:
            return child
    return None


def _walk_members(
    container: Node,
    source_bytes: bytes,
    file_path: Path,
    class_name: str,
    symbols: list[Symbol],
) -> None:
    """Collect the direct members of one type body.

    Only *direct* members become symbols — this walk never descends into
    a method body, so a local function or class inside one is not a
    symbol.  PHP has no nested type declarations, so a type node here
    (which only a malformed file produces) is collected without an
    enclosing class.  A ``method_declaration`` without a body (an
    interface method or an abstract method, PH9) carries
    ``body_hash=None`` so it can never fire ``CHANGED_FUNCTION``.
    """
    for member in container.named_children:
        if member.type in _TYPE_DECL_KINDS:
            _collect_type_declaration(member, source_bytes, file_path, symbols)
        elif member.type in _METHOD_DECL_TYPES:
            name_node = member.child_by_field_name("name")
            if name_node is None:
                continue
            name = text_of(name_node, source_bytes)
            if not name:
                continue
            symbols.append(
                Symbol(
                    name=name,
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=member.start_point[0] + 1,
                    parent_class=class_name,
                    body_hash=_method_body_hash(member, source_bytes),
                )
            )


def _method_body_hash(node: Node, source_bytes: bytes) -> str | None:
    """Full-node hash of a method, or ``None`` when it has no body (PH9).

    A declaration-only method (an interface method, an abstract method)
    ends with ``;`` instead of a ``compound_statement``; it is
    defensive-``None`` so the claim taxonomy never reports a body change
    for a body that does not exist.
    """
    for child in node.named_children:
        if child.type == "compound_statement":
            return _declaration_hash(node, source_bytes)
    return None


# ---------------------------------------------------------------------------
# Call detection
# ---------------------------------------------------------------------------


def _extract_php_calls(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[CallEvidence]:
    """Extract all :class:`CallEvidence` objects from a parsed PHP CST."""
    calls: set[CallEvidence] = set()
    function_nodes: list[tuple[str, Node, str | None]] = []

    _collect_php_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node, caller_parent_class in function_nodes:
        _find_php_calls_in_body(
            func_node,
            caller_name,
            func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )

    return calls


def _collect_php_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node, str | None]],
    class_name: str | None = None,
) -> None:
    """Recursively collect every function-like node that owns calls.

    Each entry is ``(caller_name, function_node, caller_parent_class)``.
    Type declarations set the class attribution for their subtree; an
    anonymous class resets it to ``None`` because the type has no name
    (PH5).  Closures are callers only when a plain variable names them
    (PH6) — an unnamed lambda has no name to attribute its calls to, so
    those calls belong to the nearest enclosing named caller.
    """
    for child in node.named_children:
        if child.type in _TYPE_DECL_KINDS:
            name_node = child.child_by_field_name("name")
            nested_name = (
                text_of(name_node, source_bytes) if name_node is not None else None
            )
            _collect_php_callers(child, source_bytes, result, class_name=nested_name)
        elif child.type == "anonymous_class":
            _collect_php_callers(child, source_bytes, result, class_name=None)
        elif child.type in ("method_declaration", "function_definition"):
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                result.append((text_of(name_node, source_bytes), child, class_name))
            _collect_php_callers(child, source_bytes, result, class_name=class_name)
        elif child.type == "property_declaration":
            for property_name, hook_node in _property_hooks(child, source_bytes):
                result.append((property_name, hook_node, class_name))
            _collect_php_callers(child, source_bytes, result, class_name=class_name)
        elif child.type == "assignment_expression":
            owned = _closure_assignment(child)
            if owned is not None:
                target, function_node = owned
                name = _variable_name_text(target, source_bytes)
                if name:
                    result.append((name, function_node, class_name))
            _collect_php_callers(child, source_bytes, result, class_name=class_name)
        else:
            _collect_php_callers(child, source_bytes, result, class_name=class_name)


def _property_hooks(node: Node, source_bytes: bytes) -> list[tuple[str, Node]]:
    """``(property name, hook node)`` for each property hook (PHP 8.4).

    A hook is a named body — ``get`` / ``set`` — attached to one
    property, so its calls are attributed to the property, mirroring the
    Kotlin accessor rule.  A property declaring several elements at once
    (``public int $a, $b;``) is skipped: PHP gives hooks to a single
    property, and guessing which name owns them is exactly the over-reach
    the scanners avoid.
    """
    hooks = [
        child for child in node.named_children if child.type == "property_hook_list"
    ]
    if not hooks:
        return []
    elements = [
        child for child in node.named_children if child.type == "property_element"
    ]
    if len(elements) != 1:
        return []
    variables = [
        child for child in elements[0].named_children if child.type == "variable_name"
    ]
    if len(variables) != 1:
        return []
    name = _variable_name_text(variables[0], source_bytes)
    if not name:
        return []
    return [
        (name, hook) for hook in hooks[0].named_children if hook.type == "property_hook"
    ]


def _closure_assignment(
    node: Node,
) -> tuple[Node, Node] | None:
    """``(variable_name node, function node)`` for ``$f = function () {}``.

    Returns ``None`` unless the assignment's left side is a plain
    variable and its right side is a function value (PH6) — a closure
    stored anywhere else has no name to index.
    """
    if node.type != "assignment_expression":
        return None
    children = node.named_children
    if len(children) != 2:
        return None
    target, value = children
    if target.type != "variable_name":
        return None
    if value.type not in _FUNCTION_VALUE_TYPES:
        return None
    return target, value


def _variable_name_text(node: Node, source_bytes: bytes) -> str | None:
    """The declared name of a ``variable_name`` (``$fn`` → ``fn``)."""
    for child in node.named_children:
        if child.type == "name":
            name = text_of(child, source_bytes)
            return name or None
    return None


def _has_own_php_caller(node: Node, source_bytes: bytes) -> bool:
    """Whether *node* carries its own caller entry."""
    if node.type in ("method_declaration", "function_definition", "property_hook"):
        return True
    if node.type == "assignment_expression":
        return _closure_assignment(node) is not None
    return False


def _find_php_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[CallEvidence],
    caller_parent_class: str | None = None,
) -> None:
    """Walk *node* finding call nodes.

    Nested callers (methods, functions, named closures, property hooks)
    carry their own entry, so they are skipped — each call is attributed
    to exactly one caller.  Unnamed lambdas are deliberately *not*
    skipped: they have no entry of their own, so calls inside them belong
    to the nearest enclosing named caller (the Phase 1 G1/G2 rule).
    """
    for child in node.named_children:
        if child is not root_func_node and _has_own_php_caller(child, source_bytes):
            continue

        if child.type in _CALL_NODE_TYPES:
            called_name = _php_called_name(child, source_bytes)
            if called_name is not None:
                calls.add(
                    CallEvidence(
                        file_path=file_path,
                        caller_name=caller_name,
                        called_name=called_name,
                        caller_parent_class=caller_parent_class,
                    )
                )

        _find_php_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )


def _php_called_name(node: Node, source_bytes: bytes) -> str | None:
    """Called name of a PHP call node, or ``None`` when there is none.

    * ``function_call_expression`` — the callee is the ``function`` field
      (PH1): a ``name`` or a ``qualified_name`` whose final segment is
      the function name.  First-class callable syntax is a reference, not
      a call, and is excluded.
    * ``member_call_expression`` / ``nullsafe_member_call_expression`` —
      the method name is the ``name`` field, which must be a ``name``
      node (a dynamic ``$obj->$m()`` puts a ``variable_name`` there, and
      ``$obj->{'m'}()`` a ``string``).  A receiver that is itself a call
      (``f()->m()``, ``$o->a()->b()``) is excluded, exactly like JS/TS.
    * ``scoped_call_expression`` — the method name is the ``name`` field;
      the scope (``self``/``static``/``parent``/class/qualified name) is
      never a call.

    A member or scoped name starting with ``__`` is a PHP magic-method
    call and is not captured (PH12); a bare ``__foo()`` is, matching the
    shared dunder rule for bare calls.
    """
    if node.type == "function_call_expression":
        if _is_first_class_callable(node):
            return None
        callee = node.child_by_field_name("function")
        if callee is None:
            return None
        if callee.type == "name":
            return text_of(callee, source_bytes)
        if callee.type == "qualified_name":
            return _last_qualified_segment(callee, source_bytes)
        return None

    if node.type not in (
        "member_call_expression",
        "nullsafe_member_call_expression",
        "scoped_call_expression",
    ):
        return None

    if _is_first_class_callable(node):
        return None

    if node.type != "scoped_call_expression":
        children = node.named_children
        if children and children[0].type in _CALL_RECEIVER_TYPES:
            return None

    name_node = node.child_by_field_name("name")
    if name_node is None or name_node.type != "name":
        return None
    name = text_of(name_node, source_bytes)
    if name.startswith("__"):
        return None
    return name


def _last_qualified_segment(node: Node, source_bytes: bytes) -> str | None:
    """The final ``name`` of a ``qualified_name`` (``ns\\func`` → ``func``)."""
    children = node.named_children
    if not children:
        return None
    last = children[-1]
    if last.type != "name":
        return None
    name = text_of(last, source_bytes)
    return name or None


def _is_first_class_callable(node: Node) -> bool:
    """Whether a call node's arguments are the lone ``...`` placeholder.

    ``strlen(...)`` and ``$obj->method(...)`` are ``function_call_expression``
    / ``member_call_expression`` nodes, but they create a closure from the
    callable rather than invoking it — the PHP analogue of Kotlin's
    ``Foo::bar`` reference — so they are never emitted as calls.  A spread
    call (``f(...$args)``) puts an ``argument`` wrapper around the
    ``variadic_unpacking`` and stays a call.
    """
    arguments = next(
        (child for child in node.named_children if child.type == "arguments"),
        None,
    )
    if arguments is None:
        return False
    named = arguments.named_children
    return len(named) == 1 and named[0].type == "variadic_placeholder"
