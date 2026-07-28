from __future__ import annotations

import logging
from pathlib import Path

from tree_sitter import Language, Node, Parser, Tree

from nowreck.scanner.symbol_index import Symbol, SymbolType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-process singleton: load the grammar once and reuse it.
# Tree-sitter grammars are immutable after loading, so this is safe.
# ---------------------------------------------------------------------------
_js_language_cache: Language | None = None


def _get_js_language() -> Language:
    """Return the JavaScript tree-sitter language, loading it on first
    call.

    The ``tree_sitter_javascript`` package is imported **lazily** so that
    importing this module does not fail when the dependency is not
    installed.  This allows the Python-only test suite and the change
    detector to function without the JS parser installed.
    """
    global _js_language_cache  # noqa: PLW0603 — deliberate per-process cache
    if _js_language_cache is None:
        import tree_sitter_javascript as ts_javascript  # noqa: PLC0415

        _js_language_cache = Language(ts_javascript.language())
    return _js_language_cache


def _new_parser() -> Parser:
    """Create a fresh parser wired to the JavaScript grammar."""
    return Parser(_get_js_language())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_of(node: Node, source_bytes: bytes) -> str:
    """Decode the source text spanned by *node*."""
    return source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace",
    )


# ---------------------------------------------------------------------------
# JS-specific scanning logic
# ---------------------------------------------------------------------------

def _collect_top_level_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Walk top-level statements and collect symbols.

    Handles:
        - ``function foo() {}``  →  SymbolType.FUNCTION
        - ``const foo = () => {}``  →  SymbolType.FUNCTION
        - ``class Foo { ... }``  →  SymbolType.CLASS  (+ methods)
        - ``export function foo() {}``  →  (unwrapped, same as above)
        - ``export class Foo {}``  →  (unwrapped, same as above)
        - ``export const foo = () => {}``  →  (unwrapped, same as above)
    """
    symbols: list[Symbol] = []

    for child in root_node.children:
        # Unwrap export_statement: drill into the ``declaration`` field so
        # that ``export function foo() {}`` produces a FUNCTION symbol
        # (not silently dropped).
        node = child
        if node.type == "export_statement":
            declaration_child = node.child_by_field_name("declaration")
            if declaration_child is not None:
                node = declaration_child
        # ``export default`` and bare ``export { ... }`` remain
        # unresolved (no ``declaration`` field) — they fall through to
        # the elif chain below and are correctly ignored.

        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=_text_of(name_node, source_bytes),
                    symbol_type=SymbolType.FUNCTION,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                ))

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                class_name = _text_of(name_node, source_bytes)
                class_line = node.start_point[0] + 1
                symbols.append(Symbol(
                    name=class_name,
                    symbol_type=SymbolType.CLASS,
                    file_path=file_path,
                    line_number=class_line,
                ))
                # Index methods inside this class (one level only)
                _collect_class_methods(
                    node, source_bytes, file_path, class_name, symbols,
                )

        elif node.type in ("lexical_declaration", "variable_declaration"):
            # const foo = () => {}  or  var foo = () => {}
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    _maybe_arrow_function_declarator(
                        declarator, source_bytes, file_path, symbols,
                    )

    return symbols


def _collect_class_methods(
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
                    name=_text_of(name_node, source_bytes),
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=member.start_point[0] + 1,
                    parent_class=class_name,
                ))


def _unwrap_parens(node: Node) -> Node | None:
    """Unwrap a chain of parenthesized expressions to reach the inner node.

    ``((() => {}))`` → after unwrapping → ``() => {}`` (arrow_function)
    Returns ``None`` when the chain is empty (child_count == 0).
    """
    inner: Node | None = node
    while (
        inner is not None
        and inner.type == "parenthesized_expression"
        and inner.child_count > 0
    ):
        inner = inner.child(0)
    return inner


def _maybe_arrow_function_declarator(
    declarator_node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """If a variable declarator's value is an arrow function, emit a Symbol."""
    name_node = declarator_node.child_by_field_name("name")
    value_node = declarator_node.child_by_field_name("value")
    if name_node is None or value_node is None:
        return

    inner = _unwrap_parens(value_node)

    if inner is not None and inner.type == "arrow_function":
        symbols.append(Symbol(
            name=_text_of(name_node, source_bytes),
            symbol_type=SymbolType.FUNCTION,
            file_path=file_path,
            line_number=inner.start_point[0] + 1,
        ))


# ---------------------------------------------------------------------------
# Call detection helpers
# ---------------------------------------------------------------------------


def _collect_js_callers(
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

    Nested functions are collected independently so their calls are
    attributed to them, not to their enclosing function.
    """
    if node.type == "function_declaration":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((_text_of(name_node, source_bytes), node))

    elif node.type == "method_definition":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((_text_of(name_node, source_bytes), node))

    elif node.type == "variable_declarator":
        value_node = node.child_by_field_name("value")
        if value_node is not None:
            inner = _unwrap_parens(value_node)
            if inner is not None and inner.type in (
                "arrow_function",
                "function_expression",
            ):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    result.append((
                        _text_of(name_node, source_bytes), inner,
                    ))

    # Recurse into children to find nested functions
    for child in node.named_children:
        _collect_js_callers(child, source_bytes, result)


def _find_js_calls_in_body(
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
        # from _collect_js_callers.
        if child is not root_func_node:
            if child.type in (
                "function_declaration",
                "method_definition",
                "arrow_function",
                "function_expression",
            ):
                continue
            # Skip const foo = () => {} inside a function body
            if child.type == "variable_declarator":
                value_node = child.child_by_field_name("value")
                if value_node is not None:
                    inner = _unwrap_parens(value_node)
                    if inner is not None and inner.type in (
                        "arrow_function",
                        "function_expression",
                    ):
                        continue

        if child.type == "call_expression":
            func_node = child.child_by_field_name("function")
            if func_node is not None and func_node.type == "identifier":
                called_name = _text_of(func_node, source_bytes)
                calls.add((file_path, caller_name, called_name))

        _find_js_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
        )


def _extract_js_calls_from_tree(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[tuple[Path, str, str]]:
    """Extract all ``(file_path, caller_name, called_name)`` tuples from
    a parsed JavaScript CST.

    1. Finds every function-like node (the *callers*).
    2. For each caller, walks its body looking for ``call_expression``
       nodes whose target is a simple ``identifier``.

    Returns an empty set when there are no calls or no callers.
    """
    calls: set[tuple[Path, str, str]] = set()
    function_nodes: list[tuple[str, Node]] = []

    _collect_js_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node in function_nodes:
        _find_js_calls_in_body(
            func_node,
            caller_name,
            root_func_node=func_node,
            source_bytes=source_bytes,
            file_path=file_path,
            calls=calls,
        )

    return calls


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_js_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single ``.js`` file and return the symbols it defines.

    This is the primary entry point for Phase 1 JavaScript scanning.  It
    uses tree-sitter to parse the file, walks the concrete syntax tree,
    and returns :class:`Symbol` objects that are structurally compatible
    with the existing Python symbol pipeline.

    Args:
        file_path: Path to a JavaScript file.
        repo_root: Optional repository root.  When provided, ``Symbol``
            ``file_path`` values are made relative to this root.  When
            omitted, they are absolute.

    Returns:
        A list of :class:`Symbol` objects found in the file.  Returns an
        empty list when the file contains no recognised symbols.

    Raises:
        FileNotFoundError: When *file_path* does not exist.
        SyntaxError: When the file cannot be parsed at all.
    """
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    parser = _new_parser()
    tree: Tree = parser.parse(source_bytes)
    root = tree.root_node  # type: ignore  # tree-sitter always returns a valid tree

    if root.has_error:
        # tree-sitter is resilient — it still produces a partial CST.
        # Surface the problem but try to extract what we can.
        logger.warning(
            "Syntax error detected in %s — extracting partial symbols",
            path,
        )

    # Determine the path to store in each Symbol
    if repo_root is not None:
        repo_root_path = Path(repo_root).resolve()
        try:
            symbol_path = path.relative_to(repo_root_path)
        except ValueError:
            symbol_path = path  # fall back to absolute
    else:
        symbol_path = path

    return _collect_top_level_symbols(root, source_bytes, symbol_path)


def scan_js_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[tuple[Path, str, str]]:
    """Parse a single ``.js`` file and return all call tuples it contains.

    Each tuple is ``(file_path, caller_name, called_name)`` where
    *caller_name* is the enclosing function/method/arrow-assignee name
    and *called_name* is the name of the function being called.

    Only simple identifier calls are captured (e.g. ``foo()`` — not
    ``obj.method()``), matching the existing Python behaviour.

    Args:
        file_path: Path to a JavaScript file.
        repo_root: Optional repository root for relativising paths.

    Returns:
        A set of ``(file_path, caller_name, called_name)`` tuples.
        Returns an empty set when the file has no calls or no callers.

    Raises:
        FileNotFoundError: When *file_path* does not exist.
        OSError: When the file cannot be read.
    """
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    parser = _new_parser()
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

    return _extract_js_calls_from_tree(root, source_bytes, rel_path)
