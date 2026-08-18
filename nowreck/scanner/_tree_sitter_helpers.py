from __future__ import annotations

import logging
from pathlib import Path

from tree_sitter import Node

from nowreck.scanner.symbol_index import Symbol, SymbolType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Generic tree-sitter helpers (language-agnostic)
# ---------------------------------------------------------------------------


def text_of(node: Node, source_bytes: bytes) -> str:
    """Decode the source text spanned by *node*."""
    return source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace",
    )


def unwrap_parens(node: Node) -> Node | None:
    """Unwrap a chain of parenthesized expressions to reach the inner node.

    ``((() => {}))`` → after unwrapping → ``() => {}`` (arrow_function)
    Returns ``None`` when the chain is empty (named_child_count == 0).

    Uses ``named_child(0)`` (not ``child(0)``) to skip syntactic tokens
    like ``(`` and ``)`` and reach the actual expression inside the parens.
    """
    inner: Node | None = node
    while (
        inner is not None
        and inner.type == "parenthesized_expression"
        and inner.named_child_count > 0
    ):
        inner = inner.named_child(0)
    return inner


def is_iife(node: Node) -> bool:
    """Check whether *node* is a ``call_expression`` whose callee is a
    ``function_expression``, ``arrow_function``, or ``generator_function``
    (possibly wrapped in ``parenthesized_expression``).

    Returns ``False`` for ordinary function calls like ``foo()`` where
    the callee is an ``identifier`` or ``member_expression``.
    """
    if node.type == "call_expression":
        func_node = node.child_by_field_name("function")
        if func_node is not None:
            inner = unwrap_parens(func_node)
            if inner is not None and inner.type in (
                "function_expression",
                "arrow_function",
                "generator_function",
            ):
                return True
    # ``void function() { ... }()`` — void wraps a call_expression.
    if node.type == "unary_expression" and node.named_child_count > 0:
        operand = node.named_child(0)
        if operand is not None and operand.type == "call_expression":
            return is_iife(operand)
    return False


# ---------------------------------------------------------------------------
# Symbol collection (language-agnostic — node types are identical between
# JavaScript and TypeScript tree-sitter grammars for all in-scope patterns)
# ---------------------------------------------------------------------------


def collect_top_level_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Walk top-level statements and collect symbols.

    Handles:
        - ``function foo() {}``  →  SymbolType.FUNCTION
        - ``const foo = () => {}``  →  SymbolType.FUNCTION
        - ``class Foo { ... }``  →  SymbolType.CLASS  (+ methods)
        - ``interface Foo { ... }``  →  SymbolType.INTERFACE
        - ``enum Color { ... }``  →  SymbolType.ENUM
        - ``type T = ...``  →  SymbolType.TYPE_ALIAS
        - ``export function foo() {}``  →  (unwrapped, same as above)
        - ``export class Foo {}``  →  (unwrapped, same as above)
        - ``export const foo = () => {}``  →  (unwrapped, same as above)

    The interface/enum/type-alias node types only ever occur in the
    TypeScript and TSX grammars, so JavaScript scanning behaviour is
    untouched by construction.  Members (interface method signatures,
    enum members, generic parameters) are structural detail and are
    intentionally NOT captured — same one-level-deep philosophy as class
    methods.
    """
    symbols: list[Symbol] = []

    for child in root_node.children:
        # Unwrap export_statement: drill into the ``declaration`` field so
        # that ``export function foo() {}`` produces a FUNCTION symbol.
        node = child
        if node.type == "export_statement":
            declaration_child = node.child_by_field_name("declaration")
            if declaration_child is not None:
                node = declaration_child

        if node.type in ("function_declaration", "generator_function_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=text_of(name_node, source_bytes),
                    symbol_type=SymbolType.FUNCTION,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                ))

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                class_name = text_of(name_node, source_bytes)
                class_line = node.start_point[0] + 1
                symbols.append(Symbol(
                    name=class_name,
                    symbol_type=SymbolType.CLASS,
                    file_path=file_path,
                    line_number=class_line,
                ))
                collect_class_methods(
                    node, source_bytes, file_path, class_name, symbols,
                )

        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=text_of(name_node, source_bytes),
                    symbol_type=SymbolType.INTERFACE,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                ))

        elif node.type == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=text_of(name_node, source_bytes),
                    symbol_type=SymbolType.ENUM,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                ))

        elif node.type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=text_of(name_node, source_bytes),
                    symbol_type=SymbolType.TYPE_ALIAS,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                ))

        elif node.type == "expression_statement":
            # Standalone IIFE: ``(function() { ... })()``
            if node.named_child_count > 0:
                expr = node.named_child(0)
                if expr is not None and is_iife(expr):
                    logger.debug("Skipping top-level IIFE at line %d",
                                 node.start_point[0] + 1)
                    continue

        elif node.type in ("lexical_declaration", "variable_declaration"):
            # const foo = () => {}  or  var foo = () => {}
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    maybe_arrow_function_declarator(
                        declarator, source_bytes, file_path, symbols,
                    )

    return symbols


def collect_class_methods(
    class_node: Node,
    source_bytes: bytes,
    file_path: Path,
    class_name: str,
    symbols: list[Symbol],
) -> None:
    """Index ``method_definition`` nodes inside a class body."""
    body_node = class_node.child_by_field_name("body")
    if body_node is None:
        return

    for member in body_node.children:
        if member.type == "method_definition":
            name_node = member.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=text_of(name_node, source_bytes),
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=member.start_point[0] + 1,
                    parent_class=class_name,
                ))


def maybe_arrow_function_declarator(
    declarator_node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """If a variable declarator's value is an arrow function or generator
    expression, emit a Symbol.

    IIFEs (e.g. ``const x = (function() { ... })()``) are explicitly
    skipped rather than falling through silently.
    """
    name_node = declarator_node.child_by_field_name("name")
    value_node = declarator_node.child_by_field_name("value")
    if name_node is None or value_node is None:
        return

    if is_iife(value_node):
        logger.debug("Skipping IIFE assignment to %s at line %d",
                     text_of(name_node, source_bytes),
                     value_node.start_point[0] + 1)
        return

    inner = unwrap_parens(value_node)

    if inner is not None and inner.type in (
        "arrow_function",
        "generator_function",
    ):
        symbols.append(Symbol(
            name=text_of(name_node, source_bytes),
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            line_number=inner.start_point[0] + 1,
        ))


# ---------------------------------------------------------------------------
# Call detection helpers (language-agnostic)
# ---------------------------------------------------------------------------


def collect_tree_sitter_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node]],
) -> None:
    """Recursively collect every ``function_declaration``,
    ``method_definition``, and named ``arrow_function`` / ``function_expression``
    assignee in the tree.

    Each entry is ``(caller_name, function_node)`` where *function_node* is
    the CST node whose body should be searched for ``call_expression``
    children.
    """
    if node.type in ("function_declaration", "generator_function_declaration"):
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((text_of(name_node, source_bytes), node))

    elif node.type == "method_definition":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((text_of(name_node, source_bytes), node))

    elif node.type == "variable_declarator":
        value_node = node.child_by_field_name("value")
        if value_node is not None:
            inner = unwrap_parens(value_node)
            if inner is not None and inner.type in (
                "arrow_function",
                "function_expression",
                "generator_function",
            ):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    result.append((
                        text_of(name_node, source_bytes), inner,
                    ))

    # Recurse into children to find nested functions
    for child in node.named_children:
        collect_tree_sitter_callers(child, source_bytes, result)


def find_tree_sitter_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[tuple[Path, str, str]],
) -> None:
    """Walk *node* finding ``call_expression`` children whose function
    target is a simple ``identifier`` (e.g. ``foo()`` — not
    ``obj.method()``).

    Skips nested function-like nodes that are not *root_func_node* so
    their calls are not misattributed to the outer function.
    """
    for child in node.named_children:
        # Skip nested function-like nodes — they have their own entry
        if child is not root_func_node:
            if child.type in (
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
                "arrow_function",
                "function_expression",
                "generator_function",
            ):
                continue
            # Skip const foo = () => {} inside a function body
            if child.type == "variable_declarator":
                value_node = child.child_by_field_name("value")
                if value_node is not None:
                    inner = unwrap_parens(value_node)
                    if inner is not None and inner.type in (
                        "arrow_function",
                        "function_expression",
                        "generator_function",
                    ):
                        continue

        if child.type == "call_expression":
            func_node = child.child_by_field_name("function")
            if func_node is not None and func_node.type == "identifier":
                called_name = text_of(func_node, source_bytes)
                calls.add((file_path, caller_name, called_name))

        find_tree_sitter_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
        )


def extract_tree_sitter_calls_from_tree(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[tuple[Path, str, str]]:
    """Extract all ``(file_path, caller_name, called_name)`` tuples from
    a parsed tree-sitter CST.

    1. Finds every function-like node (the *callers*).
    2. For each caller, walks its body looking for ``call_expression``
       nodes whose target is a simple ``identifier``.
    """
    calls: set[tuple[Path, str, str]] = set()
    function_nodes: list[tuple[str, Node]] = []

    collect_tree_sitter_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node in function_nodes:
        find_tree_sitter_calls_in_body(
            func_node,
            caller_name,
            root_func_node=func_node,
            source_bytes=source_bytes,
            file_path=file_path,
            calls=calls,
        )

    return calls
