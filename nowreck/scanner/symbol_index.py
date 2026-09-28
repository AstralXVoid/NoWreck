from __future__ import annotations

import ast
import hashlib
from collections.abc import Sequence
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
    INTERFACE = auto()
    ENUM = auto()
    TYPE_ALIAS = auto()


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
            **Identity-exempt** — excluded from ``__eq__``/``__hash__``
            so that a pure line-shift is not reported as a structural
            remove+add pair.
        parent_class: For methods, the enclosing class name.  ``None``
            for top-level functions and classes.
        body_hash: Structural hash of the symbol's definition content
            (v0.16.0).  **Identity-exempt** — excluded from
            ``__eq__``/``__hash__`` exactly like ``line_number`` so that
            a pure body edit is not reported as a remove+add pair.
            ``None`` when the symbol has no hash (pre-v16 cache data or
            a symbol kind whose content is not hashed).
    """

    name: str
    symbol_type: SymbolType
    file_path: Path
    line_number: int = field(compare=False)
    parent_class: str | None = None
    body_hash: str | None = field(default=None, compare=False)

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-compatible dict.

        ``file_path`` is stored as a string; ``symbol_type`` is stored
        as its string name (e.g. ``"FUNCTION"``).  ``body_hash`` is
        included only when present so legacy payloads remain readable.
        """
        result: dict[str, object] = {
            "name": self.name,
            "symbol_type": self.symbol_type.name,
            "file_path": str(self.file_path),
            "line_number": self.line_number,
            "parent_class": self.parent_class,
        }
        if self.body_hash is not None:
            result["body_hash"] = self.body_hash
        return result

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Symbol:
        """Deserialise from a JSON dict.

        ``body_hash`` is read tolerantly (``None`` when absent) so old
        payloads deserialise cleanly; the cache version bump guarantees
        such payloads are never used for comparison.
        """
        return cls(
            name=str(d["name"]),
            symbol_type=SymbolType[str(d["symbol_type"])],
            file_path=Path(str(d["file_path"])),
            line_number=int(d["line_number"]),  # type: ignore[arg-type]
            parent_class=(
                str(d["parent_class"]) if d.get("parent_class") is not None else None
            ),
            body_hash=(str(d["body_hash"]) if d.get("body_hash") is not None else None),
        )


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
    def interfaces(self) -> list[Symbol]:
        """All top-level interfaces (TypeScript) in the index."""
        return self.by_type(SymbolType.INTERFACE)

    @property
    def enums(self) -> list[Symbol]:
        """All top-level enums (TypeScript) in the index."""
        return self.by_type(SymbolType.ENUM)

    @property
    def type_aliases(self) -> list[Symbol]:
        """All top-level type aliases (TypeScript) in the index."""
        return self.by_type(SymbolType.TYPE_ALIAS)

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
    structural information only.  Nested functions, decorators, and imports
    are ignored.  Async functions and methods are indexed on equal footing
    with their synchronous counterparts (v0.16.0).
    """

    @staticmethod
    def build(scan_result: ScanResult) -> SymbolIndex:
        """Construct a ``SymbolIndex`` from a completed repository scan.

        Processes both Python modules (``scan_result.modules``) and
        JavaScript symbol lists (``scan_result.js_files``) into a single
        unified index.  The resulting index is structurally identical
        regardless of whether the symbols came from Python or JS.

        Args:
            scan_result: The output of :meth:`RepositoryScanner.scan`.

        Returns:
            A populated ``SymbolIndex``.  Repositories with no source
            files produce an empty index.
        """
        index: dict[str, list[Symbol]] = {}

        # Process Python files (AST-based)
        for file_path, module in scan_result.modules.items():
            SymbolIndexBuilder._process_module(index, file_path, module)

        # Process JavaScript files (tree-sitter-based)
        for file_path, symbols in scan_result.js_files.items():
            for sym in symbols:
                index.setdefault(sym.name, []).append(sym)

        # Process TypeScript files (tree-sitter-based)
        for file_path, symbols in scan_result.ts_files.items():
            for sym in symbols:
                index.setdefault(sym.name, []).append(sym)

        # Process Rust files (tree-sitter-based)
        for file_path, symbols in scan_result.rust_files.items():
            for sym in symbols:
                index.setdefault(sym.name, []).append(sym)

        # Process Go files (tree-sitter-based)
        for file_path, symbols in scan_result.go_files.items():
            for sym in symbols:
                index.setdefault(sym.name, []).append(sym)

        # Process Java files (tree-sitter-based)
        for file_path, symbols in scan_result.java_files.items():
            for sym in symbols:
                index.setdefault(sym.name, []).append(sym)

        # Process Kotlin files (tree-sitter-based)
        for file_path, symbols in scan_result.kotlin_files.items():
            for sym in symbols:
                index.setdefault(sym.name, []).append(sym)

        # Process PHP files (tree-sitter-based)
        for file_path, symbols in scan_result.php_files.items():
            for sym in symbols:
                index.setdefault(sym.name, []).append(sym)

        # Sort each name group for deterministic output
        ordered: dict[str, list[Symbol]] = {}
        for name in sorted(index):
            ordered[name] = sorted(index[name])

        return SymbolIndex(symbols=ordered)

    @staticmethod
    def from_symbols(symbols: list[Symbol]) -> SymbolIndex:
        """Build a ``SymbolIndex`` from a flat list of ``Symbol`` objects.

        This is the JS pathway: the JS scanner (``scan_js_file``) already
        produces ``Symbol`` objects directly, so there is no intermediate
        ``ScanResult`` or AST walk needed.  This method groups them by
        name and returns a ready-to-use index that is interchangeable
        with the Python-built equivalent.

        All ``Symbol`` objects in the input list must carry a meaningful
        ``file_path`` — typically a path relative to the repository root.

        Args:
            symbols: A flat list of ``Symbol`` objects, e.g. from
                :func:`~nowreck.scanner.javascript_scanner.scan_js_file`.

        Returns:
            A populated ``SymbolIndex``.  An empty list produces an
            empty index.
        """
        index: dict[str, list[Symbol]] = {}

        for sym in symbols:
            index.setdefault(sym.name, []).append(sym)

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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = Symbol(
                    name=node.name,
                    symbol_type=SymbolType.FUNCTION,
                    file_path=file_path,
                    line_number=node.lineno,
                    body_hash=SymbolIndexBuilder._python_body_hash(node),
                )
                index.setdefault(node.name, []).append(symbol)

            elif isinstance(node, ast.ClassDef):
                symbol = Symbol(
                    name=node.name,
                    symbol_type=SymbolType.CLASS,
                    file_path=file_path,
                    line_number=node.lineno,
                    body_hash=SymbolIndexBuilder._python_class_shell_hash(node),
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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = Symbol(
                    name=node.name,
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    line_number=node.lineno,
                    parent_class=class_node.name,
                    body_hash=SymbolIndexBuilder._python_body_hash(node),
                )
                index.setdefault(node.name, []).append(symbol)

    @staticmethod
    def _python_body_hash(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        """Structural hash of a function or method definition node.

        Uses ``ast.dump`` with ``include_attributes=False`` so line
        numbers and source offsets never affect the hash — a pure line
        shift produces an identical hash.  Comments and whitespace are
        not part of the AST and therefore never affect it either.
        """
        return hashlib.sha256(
            ast.dump(node, include_attributes=False).encode("utf-8"),
        ).hexdigest()

    @staticmethod
    def _python_class_shell_hash(class_node: ast.ClassDef) -> str:
        """Structural hash of a class *shell only*.

        Covers decorators, base classes, keyword arguments, generic type
        parameters (Python 3.12+), and every class-body statement except
        method subtrees, ``pass`` placeholders, and the method bodies of
        nested classes.  Method bodies live inside their own
        ``FunctionDef``/``AsyncFunctionDef`` nodes and are excluded so a
        method edit never fires ``CHANGED_CLASS`` (disjoint-facts rule);
        nested classes are hashed as shells recursively, so the rule
        holds at any nesting depth.  ``pass`` is the syntactic "empty
        class" placeholder and carries no information, so removing the
        last method of a class (``def m`` -> ``pass``) stays a method
        change only.
        """
        return hashlib.sha256(
            "|".join(SymbolIndexBuilder._python_class_shell_parts(class_node)).encode(
                "utf-8"
            )
        ).hexdigest()

    @staticmethod
    def _python_class_shell_parts(class_node: ast.ClassDef) -> list[str]:
        """Collect the shell-hash parts of a class node."""
        parts: list[str] = [
            SymbolIndexBuilder._dump_list(class_node.decorator_list),
            SymbolIndexBuilder._dump_list(class_node.bases),
            SymbolIndexBuilder._dump_list(class_node.keywords),
        ]
        type_params = getattr(class_node, "type_params", None)
        if type_params:
            parts.append(SymbolIndexBuilder._dump_list(type_params))
        for stmt in class_node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Pass)):
                continue
            if isinstance(stmt, ast.ClassDef):
                # Nested classes are shell content of the outer class and
                # are themselves hashed as shells (methods and ``pass``
                # excluded at every depth).  The name is included:
                # renaming a nested class is a structural change to the
                # outer class.
                parts.append(stmt.name)
                parts.append(SymbolIndexBuilder._python_class_shell_hash(stmt))
                continue
            parts.append(ast.dump(stmt, include_attributes=False))
        return parts

    @staticmethod
    def _dump_list(nodes: Sequence[ast.AST]) -> str:
        """Serialize a list of AST nodes deterministically.

        ``ast.dump`` only accepts a single node, so lists (decorators,
        bases, keywords, type params) are serialized element by element.
        ``Sequence`` keeps the parameter covariant: the concrete lists
        (``list[expr]``, ``list[keyword]``, ...) are all assignable.
        """
        return "|".join(ast.dump(n, include_attributes=False) for n in nodes)


# Convenience aliases for brevity in tests and callers
build_symbol_index = SymbolIndexBuilder.build
build_symbol_index_from_symbols = SymbolIndexBuilder.from_symbols
