from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import IntEnum, auto
from pathlib import Path

from nowreck.scanner.repository_scanner import ScanResult
from nowreck.scanner.symbol_index import Symbol, SymbolIndex, SymbolType


def change_sort_key(c: DetectedChange) -> tuple[int, str, str, str, int, str, str]:
    """Sort key that handles ``None`` fields gracefully.

    Without this, Python refuses to compare ``str`` against ``None``
    when two changes with the same ``change_type`` and ``file_path``
    fall through to nullable fields like ``symbol_name``.
    """
    return (
        c.change_type.value,
        str(c.file_path),
        c.symbol_name or "",
        c.parent_class or "",
        c.line_number if c.line_number is not None else -1,
        c.caller_name or "",
        c.called_name or "",
    )


class ChangeType(IntEnum):
    """The kind of a structural change between two repository snapshots.

    Values are ordered by specificity for deterministic comparison.
    """

    ADD_FUNCTION = auto()
    REMOVE_FUNCTION = auto()
    ADD_CLASS = auto()
    REMOVE_CLASS = auto()
    FILE_CREATED = auto()
    FILE_DELETED = auto()
    CALL_DETECTED = auto()


@dataclass(frozen=True)
class DetectedChange:
    """A single structural change detected between pre and post snapshots.

    This is the **single source of truth** for Nowreck.  Every fact that
    can be verified must first pass through a ``DetectedChange``.  The
    :class:`~nowreck.verifier.verifier.ClaimVerifier` operates exclusively
    on lists of these objects.

    Attributes:
        change_type: The category of change.
        file_path: Path relative to the repository root.
        symbol_name: Name of the affected function, class, or method.
            ``None`` for file-level changes.
        parent_class: For methods, the enclosing class name.
            ``None`` for top-level symbols and file changes.
        line_number: 1-based line number where the definition starts.
            ``None`` for file and call changes.
        caller_name: For ``CALL_DETECTED``, the function or method that
            contains the call.  ``None`` for other change types.
        called_name: For ``CALL_DETECTED``, the name of the function
            being called.  ``None`` for other change types.
    """

    change_type: ChangeType
    file_path: Path
    symbol_name: str | None = None
    parent_class: str | None = None
    line_number: int | None = None
    caller_name: str | None = None
    called_name: str | None = None


class ChangeDetector:
    """Detects structural changes between two repository snapshots.

    Accepts a pre-change and post-change :class:`ScanResult` and
    :class:`SymbolIndex`, then produces a deterministic list of
    :class:`DetectedChange` objects.

    The detector performs **no semantic analysis** — all operations are
    set-diffs on symbol names and structural AST walking for call
    detection.
    """

    @staticmethod
    def detect(
        pre_scan: ScanResult,
        post_scan: ScanResult,
        pre_symbols: SymbolIndex,
        post_symbols: SymbolIndex,
    ) -> list[DetectedChange]:
        """Detect all structural changes between pre and post snapshots.

        Args:
            pre_scan: The scanned state *before* the change.
            post_scan: The scanned state *after* the change.
            pre_symbols: Symbol index built from *pre_scan*.
            post_symbols: Symbol index built from *post_scan*.

        Returns:
            A chronologically-ordered list of detected changes.
        """
        changes: list[DetectedChange] = []

        # 1. Symbol-level changes (set-diff on all_symbols)
        changes.extend(ChangeDetector._detect_symbol_changes(pre_symbols, post_symbols))

        # 2. File-level changes (set-diff on module paths)
        changes.extend(ChangeDetector._detect_file_changes(pre_scan, post_scan))

        # 3. Call detection (compare pre/post call sets)
        changes.extend(ChangeDetector._detect_calls(pre_scan, post_scan))

        return sorted(changes, key=change_sort_key)

    # ------------------------------------------------------------------
    # Symbol-level detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_symbol_changes(
        pre: SymbolIndex,
        post: SymbolIndex,
    ) -> list[DetectedChange]:
        """Compare symbol sets to find added and removed symbols."""
        changes: list[DetectedChange] = []
        pre_set: set[Symbol] = set(pre.all_symbols)
        post_set: set[Symbol] = set(post.all_symbols)

        added = post_set - pre_set
        removed = pre_set - post_set

        changes.extend(
            ChangeDetector._symbol_to_change(sym, is_addition=True)
            for sym in sorted(added)
        )
        changes.extend(
            ChangeDetector._symbol_to_change(sym, is_addition=False)
            for sym in sorted(removed)
        )

        return changes

    @staticmethod
    def _symbol_to_change(
        symbol: Symbol,
        is_addition: bool,
    ) -> DetectedChange:
        """Convert a :class:`Symbol` into the corresponding change."""
        if symbol.symbol_type is SymbolType.FUNCTION:
            change_type = (
                ChangeType.ADD_FUNCTION if is_addition else ChangeType.REMOVE_FUNCTION
            )
        elif symbol.symbol_type is SymbolType.CLASS:
            change_type = (
                ChangeType.ADD_CLASS if is_addition else ChangeType.REMOVE_CLASS
            )
        else:
            # Methods are tracked under function changes since the claim
            # taxonomy doesn't distinguish them — parent_class provides
            # the context.
            change_type = (
                ChangeType.ADD_FUNCTION if is_addition else ChangeType.REMOVE_FUNCTION
            )

        return DetectedChange(
            change_type=change_type,
            file_path=symbol.file_path,
            symbol_name=symbol.name,
            parent_class=symbol.parent_class,
            line_number=symbol.line_number,
        )

    # ------------------------------------------------------------------
    # File-level detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_file_changes(
        pre: ScanResult,
        post: ScanResult,
    ) -> list[DetectedChange]:
        """Compare file sets to find created and deleted files."""
        changes: list[DetectedChange] = []
        pre_files: set[Path] = set(pre.modules) | set(pre.failed_files)
        post_files: set[Path] = set(post.modules) | set(post.failed_files)

        created = sorted(post_files - pre_files)
        deleted = sorted(pre_files - post_files)

        changes.extend(
            DetectedChange(change_type=ChangeType.FILE_CREATED, file_path=path)
            for path in created
        )
        changes.extend(
            DetectedChange(change_type=ChangeType.FILE_DELETED, file_path=path)
            for path in deleted
        )

        return changes

    # ------------------------------------------------------------------
    # Call detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_calls(pre: ScanResult, post: ScanResult) -> list[DetectedChange]:
        """Compare call sets from pre and post states to find **new** calls.

        Scans both the pre and post snapshot for function calls, then
        reports only calls that exist in the post state but **not** in
        the pre state.  This prevents false positives when a function
        with calls exists in both states unchanged.

        Attribute/method calls (e.g. ``obj.method()``) are excluded from
        MVP scope.

        Nested function bodies are walked independently so that calls
        in ``inner()`` are attributed to ``inner``, not ``outer``.
        """
        pre_calls = ChangeDetector._extract_calls(pre)
        post_calls = ChangeDetector._extract_calls(post)

        # Only new calls — those in post but not in pre
        new_calls = post_calls - pre_calls

        changes: list[DetectedChange] = []
        for file_path, caller_name, called_name in sorted(new_calls):
            changes.append(
                DetectedChange(
                    change_type=ChangeType.CALL_DETECTED,
                    file_path=file_path,
                    caller_name=caller_name,
                    called_name=called_name,
                )
            )

        return changes

    @staticmethod
    def _extract_calls(
        scan: ScanResult,
    ) -> set[tuple[Path, str, str]]:
        """Extract all (file_path, caller_name, called_name) tuples from
        a scan result.

        Walks every function/method body looking for ``ast.Call`` nodes
        with a simple ``ast.Name`` function expression.
        """
        calls: set[tuple[Path, str, str]] = set()

        for file_path, module in scan.modules.items():
            for node in ast.walk(module):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                caller_name = node.name
                called_names = ChangeDetector._find_call_names(
                    node,
                    skip_owner=node,
                )
                for called in called_names:
                    calls.add((file_path, caller_name, called))

        return calls

    @staticmethod
    def _find_call_names(
        root: ast.AST,
        skip_owner: ast.AST | None = None,
    ) -> set[str]:
        """Collect all simple function names called within *root*.

        Walks the tree manually, **skipping** any ``FunctionDef`` or
        ``AsyncFunctionDef`` node that is not *skip_owner*.  This
        prevents calls in nested functions from being attributed to
        their enclosing function.

        Only captures ``ast.Call`` nodes where the function is a simple
        ``ast.Name`` (e.g. ``print()``, ``sorted()``).
        """
        calls: set[str] = set()
        todo: list[ast.AST] = [root]

        while todo:
            node = todo.pop()

            # Skip nested function bodies — their calls are found
            # separately when we encounter them in the outer walk.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if skip_owner is not None and node is not skip_owner:
                    continue

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)

            todo.extend(ast.iter_child_nodes(node))

        return calls


# Convenience alias
detect_changes = ChangeDetector.detect
