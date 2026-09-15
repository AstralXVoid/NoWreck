"""Java scanner — symbol and call extraction via ``tree-sitter-java``.

Phase 2 of v0.17.0.  This is the language that validates the shared
language template, so every grammar shape it depends on was resolved
empirically first and pinned in ``tests/test_java_probes.py``
(probes J1–J12); the module docstring there is the authoritative record
of the resolutions.  The facts that shape this file:

- **No top-level functions exist.**  Everything is a method of a type,
  so ``FUNCTION``-without-``parent_class`` never fires for Java;
  ``METHOD`` + ``parent_class`` covers every callable.
- **One node type for every call form** (J1): ``method_invocation``
  carries the callee in its ``name`` field and an optional ``object``
  field.  The receiver shapes are ``identifier`` (``obj.foo()``),
  ``this``, ``super``, ``field_access`` (``A.B.foo()``),
  ``array_access`` (``a[0].bar()``) and — the only dynamic one —
  ``method_invocation`` (``f().bar()``), which is excluded.  This
  mirrors the JS/TS production rule exactly: every receiver **except a
  call** resolves to the final name.
- **Constructor invocations are not call-shaped** (J2): ``new Foo()``
  is an ``object_creation_expression``, not a ``method_invocation``, so
  it is never emitted as a call — the same boundary JS/TS apply to
  ``new_expression``.
- **Method references are references, not calls** (J3):
  ``Foo::bar`` is a ``method_reference`` node.
- **Annotations are declaration children** (J4): ``@Override`` sits
  inside the ``method_declaration`` (under a ``modifiers`` node), so an
  annotation edit is part of the declaration's own body hash and no
  sibling-folding logic is needed.
- **Text blocks are ``string_literal``** (J7), not the ``text_block``
  node the scope assumed.
- **Semicolons are required syntax** (J12) and are therefore hashed as
  content — ``structural_hash`` is called *without* an exclusion set,
  exactly like Rust.
- **Nested types are real symbols** (J10) and their methods attribute
  to the *immediate* enclosing type.  Local classes (inside a method
  body) and anonymous classes (a ``class_body`` on an
  ``object_creation_expression``) produce no symbols; their methods are
  still callers, with no class attribution for the anonymous case.

Symbol model: ``class_declaration``/``record_declaration`` → CLASS,
``interface_declaration``/``annotation_type_declaration`` → INTERFACE,
``enum_declaration`` → ENUM, ``method_declaration``/
``constructor_declaration``/``compact_constructor_declaration`` →
METHOD with ``parent_class`` set.

Hash model: CLASS and ENUM symbols carry a class-*shell* hash (fields,
enum constants, heritage, annotations — methods excluded, so a method
edit never fires ``CHANGED_CLASS``).  INTERFACE symbols carry no hash:
the claim taxonomy has no ``CHANGED_INTERFACE``, matching TypeScript and
Go.  Every METHOD carries a full-node hash — Java has no header/impl
split, so a signature edit *is* a change to the symbol's content
(interface default and abstract methods included).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser, Tree

from nowreck.scanner._tree_sitter_helpers import (
    class_shell_hash,
    is_dunder_name,
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

_java_language_cache: Language | None = None


def _get_java_language() -> Language:
    """Return the Java tree-sitter language, loading it on first call."""
    global _java_language_cache  # noqa: PLW0603
    if _java_language_cache is None:
        import tree_sitter_java as ts_java  # noqa: PLC0415

        _java_language_cache = Language(ts_java.language())
    return _java_language_cache


def _new_parser(language: Language) -> Parser:
    """Create a fresh parser wired to the given grammar."""
    return Parser(language)


# ---------------------------------------------------------------------------
# Grammar vocabulary (resolved by probes J1-J12)
# ---------------------------------------------------------------------------

# Type declarations that become CLASS / INTERFACE / ENUM symbols.
_TYPE_DECL_KINDS: dict[str, SymbolType] = {
    "class_declaration": SymbolType.CLASS,
    "record_declaration": SymbolType.CLASS,
    "interface_declaration": SymbolType.INTERFACE,
    "annotation_type_declaration": SymbolType.INTERFACE,
    "enum_declaration": SymbolType.ENUM,
}

# Nodes that hold the members of a type.  ``enum_body_declarations`` is
# the second half of an enum body (J11): after the ``;`` the grammar puts
# the enum's fields/constructors/methods in their own node, so member
# discovery has to descend through it.
_TYPE_BODY_CONTAINERS: frozenset[str] = frozenset(
    {
        "class_body",
        "interface_body",
        "enum_body",
        "enum_body_declarations",
        "annotation_type_body",
    }
)

# Callables: methods and constructors (J5).  A record's *compact*
# constructor is its own node type (``compact_constructor_declaration``,
# name + ``block``) rather than a ``constructor_declaration`` — resolved
# while building the sample suite and pinned in ``test_java_probes``.
# It is a constructor of the record, so it maps to a METHOD named after
# the record exactly like the canonical form.
_METHOD_DECL_TYPES: frozenset[str] = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "compact_constructor_declaration",
    }
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_java_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single ``.java`` file and return the symbols it defines."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_java_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(source_bytes)
    root = tree.root_node  # type: ignore

    if root.has_error:
        logger.warning(
            "Syntax error detected in %s — extracting partial symbols",
            path,
        )

    if repo_root is not None:
        repo_root_path = Path(repo_root).resolve()
        try:
            symbol_path = path.relative_to(repo_root_path)
        except ValueError:
            symbol_path = path
    else:
        symbol_path = path

    return _collect_java_symbols(root, source_bytes, symbol_path)


def scan_java_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[CallEvidence]:
    """Parse a single ``.java`` file and return all call evidence it contains."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_java_language()
    parser = _new_parser(language)
    tree: Tree = parser.parse(source_bytes)
    root = tree.root_node

    if repo_root is not None:
        repo_root_path = Path(repo_root).resolve()
        try:
            rel_path = path.relative_to(repo_root_path)
        except ValueError:
            rel_path = path
    else:
        rel_path = path

    return _extract_java_calls(root, source_bytes, rel_path)


# ---------------------------------------------------------------------------
# Java-specific symbol collection
# ---------------------------------------------------------------------------


def _collect_java_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Collect symbols from every top-level type declaration.

    Java statements that are not types (``package`` / ``import``) carry no
    symbols, so they are skipped by construction — the walk only descends
    into ``_TYPE_DECL_KINDS`` nodes.
    """
    symbols: list[Symbol] = []

    for child in root_node.children:
        if child.type in _TYPE_DECL_KINDS:
            _collect_type_declaration(child, source_bytes, file_path, symbols)

    return symbols


def _collect_type_declaration(
    node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Emit the symbol for one type declaration and collect its members.

    Recurses into nested type declarations (J10) so an inner class is its
    own symbol and its methods attribute to it.  Local classes are
    unreachable from here — they live inside method bodies, which this
    walk never enters.
    """
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return

    name = text_of(name_node, source_bytes)
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
    _collect_members(node, source_bytes, file_path, name, symbols)


def _type_shell_hash(
    node: Node,
    symbol_type: SymbolType,
    source_bytes: bytes,
) -> str | None:
    """Shell hash for a type declaration, or ``None`` when it has none.

    CLASS and ENUM bodies are class-shell content: fields, enum
    constants, record components, heritage clauses and annotations are
    hashed, while method-like subtrees are excluded so a method edit can
    never fire ``CHANGED_CLASS``.  INTERFACE declarations carry no hash —
    there is no ``CHANGED_INTERFACE`` claim type in any language (the
    same rule TypeScript and Go follow).
    """
    if symbol_type in (SymbolType.CLASS, SymbolType.ENUM):
        return class_shell_hash(node, source_bytes)
    return None


def _collect_members(
    type_node: Node,
    source_bytes: bytes,
    file_path: Path,
    class_name: str,
    symbols: list[Symbol],
) -> None:
    """Collect methods, constructors and nested types of one declaration."""
    body = type_node.child_by_field_name("body")
    if body is None:
        return
    _walk_members(body, source_bytes, file_path, class_name, symbols)


def _walk_members(
    container: Node,
    source_bytes: bytes,
    file_path: Path,
    class_name: str,
    symbols: list[Symbol],
) -> None:
    """Walk a type body, collecting members directly contained in it.

    Only *direct* members become symbols, so a class declared inside a
    method body (a local class) is not reachable — this walk never
    descends into a method body.  ``enum_body_declarations`` is treated
    as a container so enum members are found (J11).
    """
    for member in container.named_children:
        if member.type in _TYPE_DECL_KINDS:
            _collect_type_declaration(member, source_bytes, file_path, symbols)
        elif member.type in _METHOD_DECL_TYPES:
            name_node = member.child_by_field_name("name")
            if name_node is None:
                continue
            symbols.append(
                Symbol(
                    name=text_of(name_node, source_bytes),
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=member.start_point[0] + 1,
                    parent_class=class_name,
                    body_hash=structural_hash(member, source_bytes),
                )
            )
        elif member.type in _TYPE_BODY_CONTAINERS:
            _walk_members(member, source_bytes, file_path, class_name, symbols)


# ---------------------------------------------------------------------------
# Java-specific call detection
# ---------------------------------------------------------------------------


def _extract_java_calls(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[CallEvidence]:
    """Extract all :class:`CallEvidence` objects from a parsed Java CST."""
    calls: set[CallEvidence] = set()
    function_nodes: list[tuple[str, Node, str | None]] = []

    _collect_java_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node, caller_parent_class in function_nodes:
        _find_java_calls_in_body(
            func_node,
            caller_name,
            func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )

    return calls


def _collect_java_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node, str | None]],
    class_name: str | None = None,
) -> None:
    """Recursively collect every method/constructor that can own calls.

    Methods and constructors of named types carry their *immediate*
    enclosing type as ``parent_class`` (J10).  A method inside an
    anonymous class body is still a caller — its calls need an owner —
    but carries no class attribution, because the class has no name
    (J2 / anonymous-class probe).  Lambdas are deliberately **not**
    callers: they are anonymous functions, so their calls attribute to
    the nearest enclosing named caller, exactly like the JS/TS arrow
    rule the Phase 1 audit established (G1/G2).
    """
    for child in node.named_children:
        if child.type in _TYPE_DECL_KINDS:
            name_node = child.child_by_field_name("name")
            nested_name = (
                text_of(name_node, source_bytes) if name_node is not None else None
            )
            _collect_java_callers(
                child,
                source_bytes,
                result,
                class_name=nested_name,
            )
        elif child.type in _METHOD_DECL_TYPES:
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                result.append((text_of(name_node, source_bytes), child, class_name))
            _collect_java_callers(child, source_bytes, result, class_name=class_name)
        elif child.type == "class_body" and node.type == "object_creation_expression":
            # Anonymous class body: its methods are callers with no class.
            _collect_java_callers(child, source_bytes, result, class_name=None)
        else:
            _collect_java_callers(child, source_bytes, result, class_name=class_name)


def _java_called_name(
    invocation_node: Node,
    source_bytes: bytes,
) -> str | None:
    """Called name of a Java ``method_invocation``.

    The callee is always the ``name`` field (J1).  Returns ``None`` when
    the receiver is itself a call (``f().bar()`` — dynamic, no static
    name) or when a member call's final name is dunder-style
    (``this.__x__()``).  Every other receiver shape — ``identifier``,
    ``this``, ``super``, ``field_access``, ``array_access`` — resolves
    to the final name, mirroring the JS/TS production rule.  A bare
    ``__foo__()`` call has no receiver and is **not** excluded (the
    dunder rule governs member calls only).
    """
    object_node = invocation_node.child_by_field_name("object")
    if object_node is not None and object_node.type == "method_invocation":
        return None
    name_node = invocation_node.child_by_field_name("name")
    if name_node is None:
        return None
    name = text_of(name_node, source_bytes)
    if object_node is not None and is_dunder_name(name):
        return None
    return name


def _find_java_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[CallEvidence],
    caller_parent_class: str | None = None,
) -> None:
    """Walk *node* finding ``method_invocation`` nodes.

    Nested methods/constructors carry their own caller entry, so they are
    skipped (each call is attributed to exactly one caller).  Lambdas are
    deliberately *not* skipped — they have no entry of their own, so
    calls inside them belong to the nearest enclosing named caller.
    """
    for child in node.named_children:
        if child is not root_func_node and child.type in _METHOD_DECL_TYPES:
            continue

        if child.type == "method_invocation":
            called_name = _java_called_name(child, source_bytes)
            if called_name is not None:
                calls.add(
                    CallEvidence(
                        file_path=file_path,
                        caller_name=caller_name,
                        called_name=called_name,
                        caller_parent_class=caller_parent_class,
                    )
                )

        _find_java_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )
