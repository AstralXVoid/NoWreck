from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser, Tree

from nowreck.scanner.symbol_index import Symbol

if TYPE_CHECKING:
    from tree_sitter import Node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-process singleton: load the grammar once and reuse it.
# ---------------------------------------------------------------------------

_go_language_cache: Language | None = None


def _get_go_language() -> Language:
    """Return the Go tree-sitter language, loading it on first call."""
    global _go_language_cache  # noqa: PLW0603
    if _go_language_cache is None:
        import tree_sitter_go as ts_go  # noqa: PLC0415

        _go_language_cache = Language(ts_go.language())
    return _go_language_cache


def _new_parser(language: Language) -> Parser:
    """Create a fresh parser wired to the given grammar."""
    return Parser(language)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_go_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single ``.go`` file and return the symbols it defines."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_go_language()
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

    return _collect_go_symbols(root, source_bytes, symbol_path)


def scan_go_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[tuple[Path, str, str]]:
    """Parse a single ``.go`` file and return all call tuples it contains."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_go_language()
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

    return _extract_go_calls(root, source_bytes, rel_path)


# ---------------------------------------------------------------------------
# Go-specific symbol collection
# ---------------------------------------------------------------------------


def _collect_go_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Walk top-level Go declarations and collect symbols."""
    symbols: list[Symbol] = []

    for child in root_node.children:
        node = child

        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=_text_of(name_node, source_bytes),
                    symbol_type=_FUNCTION_TYPE,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                ))

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            rcv_node = node.child_by_field_name("receiver")
            if name_node is not None and rcv_node is not None:
                receiver_type = _extract_receiver_type(rcv_node, source_bytes)
                symbols.append(Symbol(
                    name=_text_of(name_node, source_bytes),
                    symbol_type=_METHOD_TYPE,
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    parent_class=receiver_type,
                ))

        elif node.type == "type_declaration":
            _collect_type_symbols(node, source_bytes, file_path, symbols)

    return symbols


def _collect_type_symbols(
    type_decl: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Extract symbols from a ``type_declaration`` node.

    Handles both ``type X Struct`` (type_spec) and
    ``type X = Y`` (type_alias, Go 1.9+) forms.
    """
    for child in type_decl.children:
        if child.type == "type_spec":
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            if name_node is None or type_node is None:
                continue

            if type_node.type == "struct_type":
                symbol_type = _CLASS_TYPE
            elif type_node.type == "interface_type":
                symbol_type = _INTERFACE_TYPE
            else:
                symbol_type = _TYPE_ALIAS_TYPE

            symbols.append(Symbol(
                name=_text_of(name_node, source_bytes),
                symbol_type=symbol_type,
                file_path=file_path,
                line_number=type_decl.start_point[0] + 1,
            ))

        elif child.type == "type_alias":
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                symbols.append(Symbol(
                    name=_text_of(name_node, source_bytes),
                    symbol_type=_TYPE_ALIAS_TYPE,
                    file_path=file_path,
                    line_number=type_decl.start_point[0] + 1,
                ))


def _extract_receiver_type(
    receiver_node: Node,
    source_bytes: bytes,
) -> str:
    """Extract the type name from a Go method receiver."""
    text = _text_of(receiver_node, source_bytes)
    inner = text.strip("()")
    parts = inner.split()
    if not parts:
        return ""
    return parts[-1].lstrip("*")


# ---------------------------------------------------------------------------
# Go-specific call detection
# ---------------------------------------------------------------------------


def _extract_go_calls(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[tuple[Path, str, str]]:
    """Extract all call tuples from a parsed Go CST."""
    calls: set[tuple[Path, str, str]] = set()
    function_nodes: list[tuple[str, Node]] = []

    _collect_go_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node in function_nodes:
        _find_go_calls_in_body(
            func_node, caller_name, func_node, source_bytes, file_path, calls,
        )

    return calls


def _collect_go_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node]],
) -> None:
    """Recursively collect every function/method declaration node."""
    if node.type in ("function_declaration", "method_declaration"):
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((_text_of(name_node, source_bytes), node))

    for child in node.named_children:
        _collect_go_callers(child, source_bytes, result)


def _find_go_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[tuple[Path, str, str]],
) -> None:
    """Walk *node* finding ``call_expression`` with simple ``identifier`` targets."""
    for child in node.named_children:
        if child is not root_func_node:
            if child.type in ("function_declaration", "method_declaration"):
                continue

        if child.type == "call_expression":
            func_node = child.child_by_field_name("function")
            if func_node is not None and func_node.type == "identifier":
                calls.add((file_path, caller_name, _text_of(func_node, source_bytes)))

        _find_go_calls_in_body(
            child, caller_name, root_func_node,
            source_bytes, file_path, calls,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_of(node: Node, source_bytes: bytes) -> str:
    """Decode the source text spanned by *node*."""
    return (
        source_bytes[node.start_byte : node.end_byte]
        .decode("utf-8", errors="replace")
    )


from nowreck.scanner.symbol_index import SymbolType as _SymbolType  # noqa: E402

_FUNCTION_TYPE = _SymbolType.FUNCTION
_CLASS_TYPE = _SymbolType.CLASS
_METHOD_TYPE = _SymbolType.METHOD
_INTERFACE_TYPE = _SymbolType.INTERFACE
_TYPE_ALIAS_TYPE = _SymbolType.TYPE_ALIAS
