from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser, Tree

from nowreck.scanner._tree_sitter_helpers import is_dunder_name, structural_hash
from nowreck.scanner.call_evidence import CallEvidence
from nowreck.scanner.symbol_index import Symbol

if TYPE_CHECKING:
    from tree_sitter import Node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-process singleton: load the grammar once and reuse it.
# ---------------------------------------------------------------------------

_rs_language_cache: Language | None = None


def _get_rs_language() -> Language:
    """Return the Rust tree-sitter language, loading it on first call."""
    global _rs_language_cache  # noqa: PLW0603
    if _rs_language_cache is None:
        import tree_sitter_rust as ts_rust  # noqa: PLC0415

        _rs_language_cache = Language(ts_rust.language())
    return _rs_language_cache


def _new_parser(language: Language) -> Parser:
    """Create a fresh parser wired to the given grammar."""
    return Parser(language)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_rust_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single ``.rs`` file and return the symbols it defines."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_rs_language()
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

    return _collect_rust_symbols(root, source_bytes, symbol_path)


def scan_rust_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[CallEvidence]:
    """Parse a single ``.rs`` file and return all call evidence it contains."""
    path = Path(file_path).resolve()
    source_bytes = path.read_bytes()

    language = _get_rs_language()
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

    return _extract_rust_calls(root, source_bytes, rel_path)


# ---------------------------------------------------------------------------
# Rust-specific symbol collection
# ---------------------------------------------------------------------------


def _collect_rust_symbols(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> list[Symbol]:
    """Walk top-level Rust declarations and collect symbols."""
    symbols: list[Symbol] = []

    for child in root_node.children:
        node = child

        if node.type == "function_item":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=_text_of(name_node, source_bytes),
                        symbol_type=_FUNCTION_TYPE,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        body_hash=structural_hash(node, source_bytes),
                    )
                )

        elif node.type == "struct_item":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=_text_of(name_node, source_bytes),
                        symbol_type=_CLASS_TYPE,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                        body_hash=structural_hash(node, source_bytes),
                    )
                )

        elif node.type == "impl_item":
            _collect_impl_methods(node, source_bytes, file_path, symbols)

        elif node.type == "trait_item":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=_text_of(name_node, source_bytes),
                        symbol_type=_INTERFACE_TYPE,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    )
                )

        elif node.type == "enum_item":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=_text_of(name_node, source_bytes),
                        symbol_type=_ENUM_TYPE,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    )
                )

        elif node.type == "type_item":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=_text_of(name_node, source_bytes),
                        symbol_type=_TYPE_ALIAS_TYPE,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,
                    )
                )

    return symbols


def _impl_struct_name(
    impl_node: Node,
    source_bytes: bytes,
) -> str | None:
    """Type name an ``impl`` block targets.

    Handles both simple ``impl Foo { ... }`` and generic
    ``impl<T> Foo<T> { ... }`` forms.  Returns ``None`` when the block
    has no target type (e.g. a bare ``impl`` for a primitive).
    """
    body_node = impl_node.child_by_field_name("body")
    if body_node is None:
        return None

    for m in impl_node.children:
        if m == body_node:
            break
        # Simple case: ``impl Foo { ... }``
        if m.type == "type_identifier":
            return _text_of(m, source_bytes)
        # Generic case: ``impl<T> Foo<T> { ... }``
        if m.type == "generic_type":
            name_node = m.child_by_field_name("type")
            if name_node is None:
                name_node = m.child_by_field_name("name")
            if name_node is not None:
                return _text_of(name_node, source_bytes)
    return None


def _collect_impl_methods(
    impl_node: Node,
    source_bytes: bytes,
    file_path: Path,
    symbols: list[Symbol],
) -> None:
    """Extract methods from an ``impl`` block."""
    body_node = impl_node.child_by_field_name("body")
    struct_name = _impl_struct_name(impl_node, source_bytes)

    if body_node is None or struct_name is None:
        return

    for member in body_node.children:
        if member.type == "function_item":
            name_node = member.child_by_field_name("name")
            if name_node is not None:
                symbols.append(
                    Symbol(
                        name=_text_of(name_node, source_bytes),
                        symbol_type=_METHOD_TYPE,
                        file_path=file_path,
                        line_number=member.start_point[0] + 1,
                        parent_class=struct_name,
                        body_hash=structural_hash(member, source_bytes),
                    )
                )


# ---------------------------------------------------------------------------
# Rust-specific call detection
# ---------------------------------------------------------------------------


def _extract_rust_calls(
    root_node: Node,
    source_bytes: bytes,
    file_path: Path,
) -> set[CallEvidence]:
    """Extract all :class:`CallEvidence` objects from a parsed Rust CST."""
    calls: set[CallEvidence] = set()
    function_nodes: list[tuple[str, Node, str | None]] = []

    _collect_rust_callers(root_node, source_bytes, function_nodes)

    for caller_name, func_node, caller_parent_class in function_nodes:
        _find_rust_calls_in_body(
            func_node,
            caller_name,
            func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )

    return calls


def _collect_rust_callers(
    node: Node,
    source_bytes: bytes,
    result: list[tuple[str, Node, str | None]],
    parent_class: str | None = None,
) -> None:
    """Recursively collect every ``function_item`` node.

    Functions inside an ``impl`` block carry the target type as their
    ``parent_class`` (methods); every other function carries ``None``.
    """
    if node.type == "impl_item":
        impl_type = _impl_struct_name(node, source_bytes)
        for child in node.named_children:
            _collect_rust_callers(
                child,
                source_bytes,
                result,
                parent_class=impl_type,
            )
        return

    if node.type == "function_item":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            result.append((_text_of(name_node, source_bytes), node, parent_class))

    for child in node.named_children:
        _collect_rust_callers(
            child,
            source_bytes,
            result,
            parent_class=parent_class,
        )


def _rust_called_name(func_node: Node, source_bytes: bytes) -> str | None:
    """Called name of a Rust call target.

    Accepts simple ``identifier`` targets (``foo()``) and
    ``field_expression`` targets (``s.foo()``, ``s.a.b()``), resolving
    to the final field name.  Returns ``None`` when the receiver is
    itself a call (``f().bar()``), the field is dunder-style, or the
    target is any other shape (``pkg::func()`` stays uncaptured).
    """
    if func_node.type == "identifier":
        return _text_of(func_node, source_bytes)
    if func_node.type == "field_expression":
        value_node = func_node.child_by_field_name("value")
        if value_node is not None and value_node.type == "call_expression":
            return None
        field_node = func_node.child_by_field_name("field")
        if field_node is None:
            return None
        name = _text_of(field_node, source_bytes)
        if is_dunder_name(name):
            return None
        return name
    return None


def _find_rust_calls_in_body(
    node: Node,
    caller_name: str,
    root_func_node: Node,
    source_bytes: bytes,
    file_path: Path,
    calls: set[CallEvidence],
    caller_parent_class: str | None = None,
) -> None:
    """Walk *node* finding ``call_expression`` with ``identifier`` or
    ``field_expression`` targets."""
    for child in node.named_children:
        if child is not root_func_node and child.type == "function_item":
            continue

        if child.type == "call_expression":
            func_node = child.child_by_field_name("function")
            if func_node is not None:
                called_name = _rust_called_name(func_node, source_bytes)
                if called_name is not None:
                    calls.add(
                        CallEvidence(
                            file_path=file_path,
                            caller_name=caller_name,
                            called_name=called_name,
                            caller_parent_class=caller_parent_class,
                        )
                    )

        _find_rust_calls_in_body(
            child,
            caller_name,
            root_func_node,
            source_bytes,
            file_path,
            calls,
            caller_parent_class=caller_parent_class,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_of(node: Node, source_bytes: bytes) -> str:
    """Decode the source text spanned by *node*."""
    return source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace"
    )


from nowreck.scanner.symbol_index import SymbolType as _SymbolType  # noqa: E402

_FUNCTION_TYPE = _SymbolType.FUNCTION
_CLASS_TYPE = _SymbolType.CLASS
_METHOD_TYPE = _SymbolType.METHOD
_INTERFACE_TYPE = _SymbolType.INTERFACE
_ENUM_TYPE = _SymbolType.ENUM
_TYPE_ALIAS_TYPE = _SymbolType.TYPE_ALIAS
