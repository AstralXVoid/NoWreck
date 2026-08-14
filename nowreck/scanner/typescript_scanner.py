from __future__ import annotations

import logging
from pathlib import Path

from tree_sitter import Language, Parser, Tree

from nowreck.scanner._tree_sitter_helpers import (
    collect_top_level_symbols,
    extract_tree_sitter_calls_from_tree,
)
from nowreck.scanner.symbol_index import Symbol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-process singleton: load the grammar once and reuse it.
# ---------------------------------------------------------------------------
_ts_language_cache: Language | None = None


def _get_ts_language() -> Language:
    """Return the TypeScript tree-sitter language, loading it on first call.

    The ``tree_sitter_typescript`` package is imported **lazily** so that
    importing this module does not fail when the dependency is not
    installed.  This allows the Python-only test suite and the change
    detector to function without the TS parser installed.
    """
    global _ts_language_cache  # noqa: PLW0603 — deliberate per-process cache
    if _ts_language_cache is None:
        import tree_sitter_typescript as ts_typescript  # noqa: PLC0415

        _ts_language_cache = Language(ts_typescript.language_typescript())
    return _ts_language_cache


def _new_parser() -> Parser:
    """Create a fresh parser wired to the TypeScript grammar."""
    return Parser(_get_ts_language())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_ts_file(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> list[Symbol]:
    """Parse a single ``.ts`` file and return the symbols it defines.

    This is the primary entry point for TypeScript scanning.  It uses
    tree-sitter to parse the file, walks the concrete syntax tree,
    and returns :class:`Symbol` objects that are structurally compatible
    with the existing symbol pipeline.

    Args:
        file_path: Path to a TypeScript file.
        repo_root: Optional repository root.  When provided, ``Symbol``
            ``file_path`` values are made relative to this root.

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

    return collect_top_level_symbols(root, source_bytes, symbol_path)


def scan_ts_calls(
    file_path: str | Path,
    repo_root: str | Path | None = None,
) -> set[tuple[Path, str, str]]:
    """Parse a single ``.ts`` file and return all call tuples it contains.

    Each tuple is ``(file_path, caller_name, called_name)`` where
    *caller_name* is the enclosing function/method/arrow-assignee name
    and *called_name* is the name of the function being called.

    Only simple identifier calls are captured (e.g. ``foo()`` — not
    ``obj.method()``), matching the existing behaviour.

    Args:
        file_path: Path to a TypeScript file.
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

    return extract_tree_sitter_calls_from_tree(root, source_bytes, rel_path)
