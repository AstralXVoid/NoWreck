from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import IntEnum, auto
from pathlib import Path

from nowreck.scanner.repository_scanner import ScanResult


class SymbolType(IntEnum):
    """The kind of a structural symbol in a Python codebase.

    Values are ordered by specificity for deterministic comparison.
    ``IntEnum`` is used so that ``order=True`` on :class:`Symbol`
    can sort by symbol type (``IntEnum`` supports comparison).
    """

    FUNCTION = auto()
    CLASS = auto()
    METHOD = auto()


@dataclass(frozen=True, order=True)
class Symbol:
    """A single structural symbol extracted from a parsed AST.

    Represents a function, class, or method found at a specific location
    in the repository.  Methods carry their enclosing class name in
    *parent_class* so that e.g. ``Widget.render`` and ``Window.render``
    are distinct symbols.

    Attributes:
        name: The symbol name as written in source.
        symbol_type: Whether this is a function, class, or method.
        file_path: Path relative to the repository root.
        line_number: 1-based line number where the definition starts.
        parent_class: For methods, the enclosing class name.  ``None``
            for top-level functions and classes.
    """

    name: str
    symbol_type: SymbolType
    file_path: Path
    line_number: int
    parent_class: str | None = None


@dataclass(frozen=True)
class SymbolIndex:
    """A flat, deterministic index of all structural symbols in a repository.

    Symbols are grouped by name so that name collisions (e.g. a function
    and a class sharing the same name, or same-named methods in different
    classes) are preserved rather than silently overwritten.

    The index is intentionally *flat* — there is no package or module
    hierarchy.  Lookups are always by exact name.

    Attributes:
        symbols: Mapping of symbol name → sorted list of ``Symbol``
            objects sharing that name.
    """

    symbols: dict[str, list[Symbol]] = field(default_factory=dict)

    def by_name(self, name: str) -> list[Symbol]:
        """Return all symbols whose name matches *name*.

        Returns an empty list when no symbols have that name.
        """
        return self.symbols.get(name, [])

    def by_type(self, symbol_type: SymbolType) -> list[Symbol]:
        """Return every symbol of the given *symbol_type*."""
        return [
            symbol
            for symbols in self.symbols.values()
            for symbol in symbols
            if symbol.symbol_type is symbol_type
        ]

    @property
    def functions(self) -> list[Symbol]:
        """All top-level functions in the index."""
        return self.by_type(SymbolType.FUNCTION)

    @property
    def classes(self) -> list[Symbol]:
        """All top-level classes in the index."""
        return self.by_type(SymbolType.CLASS)

    @property
    def methods(self) -> list[Symbol]:
        """All methods (inside classes) in the index."""
        return self.by_type(SymbolType.METHOD)

    @property
    def all_symbols(self) -> list[Symbol]:
        """Every symbol in the index, deduplicated and sorted."""
        seen: set[Symbol] = set()
        for syms in self.symbols.values():
            seen.update(syms)
        return sorted(seen)


class SymbolIndexBuilder:
    """Builds a :class:`SymbolIndex` from a :class:`ScanResult`.

    Walks the parsed AST trees in a ``ScanResult`` and extracts top-level
    functions, top-level classes, and methods (one level of nesting only).

    The builder performs **no semantic analysis** — it treats the AST as
    structural information only.  Nested functions, decorators, async
    functions, and imports are ignored.
    """

    @staticmethod
    def build(scan_result: ScanResult) -> SymbolIndex:
        """Construct a ``SymbolIndex`` from a completed scan.

        Args:
            scan_result: The output of :meth:`RepositoryScanner.scan`.

        Returns:
            A populated ``SymbolIndex``.  Repositories with no Python
            files produce an empty index.
        """
        index: dict[str, list[Symbol]] = {}

        for file_path, module in scan_result.modules.items():
            SymbolIndexBuilder._process_module(index, file_path, module)

        # Sort each name group for deterministic output
        ordered: dict[str, list[Symbol]] = {}
        for name in sorted(index):
            ordered[name] = sorted(index[name])

        return SymbolIndex(symbols=ordered)

    @staticmethod
    def _process_module(
        index: dict[str, list[Symbol]],
        file_path: Path,
        module: ast.Module,
    ) -> None:
        """Walk one module's top-level statements and index symbols."""
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                symbol = Symbol(
                    name=node.name,
                    symbol_type=SymbolType.FUNCTION,
                    file_path=file_path,
                    line_number=node.lineno,
                )
                index.setdefault(node.name, []).append(symbol)

            elif isinstance(node, ast.ClassDef):
                symbol = Symbol(
                    name=node.name,
                    symbol_type=SymbolType.CLASS,
                    file_path=file_path,
                    line_number=node.lineno,
                )
                index.setdefault(node.name, []).append(symbol)
                # Index methods inside this class (one level only)
                SymbolIndexBuilder._process_class_body(index, file_path, node)

    @staticmethod
    def _process_class_body(
        index: dict[str, list[Symbol]],
        file_path: Path,
        class_node: ast.ClassDef,
    ) -> None:
        """Index methods directly inside a class body."""
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef):
                symbol = Symbol(
                    name=node.name,
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=node.lineno,
                    parent_class=class_node.name,
                )
                index.setdefault(node.name, []).append(symbol)


# Convenience alias for brevity in tests and callers
build_symbol_index = SymbolIndexBuilder.build
