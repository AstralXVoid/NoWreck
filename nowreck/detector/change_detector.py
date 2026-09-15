from __future__ import annotations

import ast
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum, auto
from pathlib import Path

from nowreck.scanner._tree_sitter_helpers import is_dunder_name
from nowreck.scanner.call_evidence import CallEvidence
from nowreck.scanner.repository_scanner import ScanResult
from nowreck.scanner.symbol_index import Symbol, SymbolIndex, SymbolType

logger = logging.getLogger(__name__)


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
    ADD_INTERFACE = auto()
    REMOVE_INTERFACE = auto()
    ADD_ENUM = auto()
    REMOVE_ENUM = auto()
    ADD_TYPE_ALIAS = auto()
    REMOVE_TYPE_ALIAS = auto()
    CHANGED_FUNCTION = auto()
    CHANGED_CLASS = auto()
    FILE_CREATED = auto()
    FILE_DELETED = auto()
    CALL_DETECTED = auto()
    CALL_REMOVED = auto()


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

        # 2. Body-hash changes (same identity, different body)
        changes.extend(
            ChangeDetector._detect_body_hash_changes(pre_symbols, post_symbols)
        )

        # 3. File-level changes (set-diff on module paths)
        changes.extend(ChangeDetector._detect_file_changes(pre_scan, post_scan))

        # 4. Call detection (compare pre/post call sets)
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
        elif symbol.symbol_type is SymbolType.INTERFACE:
            change_type = (
                ChangeType.ADD_INTERFACE if is_addition else ChangeType.REMOVE_INTERFACE
            )
        elif symbol.symbol_type is SymbolType.ENUM:
            change_type = ChangeType.ADD_ENUM if is_addition else ChangeType.REMOVE_ENUM
        elif symbol.symbol_type is SymbolType.TYPE_ALIAS:
            change_type = (
                ChangeType.ADD_TYPE_ALIAS
                if is_addition
                else ChangeType.REMOVE_TYPE_ALIAS
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
    # Body-hash detection
    # ------------------------------------------------------------------

    @staticmethod
    def _symbol_change_kind(symbol_type: SymbolType) -> str | None:
        """Group a symbol type for body-hash comparison.

        FUNCTION and METHOD collapse into one kind (methods carry
        ``parent_class`` to disambiguate); CLASS is its own kind.  ENUM
        also collapses into CLASS: an enum body is class-shell content
        (constants, fields, heritage), so an enum edit surfaces as
        ``CHANGED_CLASS`` — there is no ``CHANGED_ENUM`` claim type, the
        same way there is no ``CHANGED_METHOD``.  This is inert for
        languages whose enum symbols carry no hash (TypeScript, Rust),
        and is what makes Java enum-constant edits visible (v0.17.0
        Phase 2, probe J11).  INTERFACE/TYPE_ALIAS return ``None`` —
        they have no ``CHANGED_*`` claim types, so their hashes are
        never compared.
        """
        if symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
            return "FUNCTION"
        if symbol_type in (SymbolType.CLASS, SymbolType.ENUM):
            return "CLASS"
        return None

    @staticmethod
    def _detect_body_hash_changes(
        pre: SymbolIndex,
        post: SymbolIndex,
    ) -> list[DetectedChange]:
        """Emit ``CHANGED_FUNCTION`` / ``CHANGED_CLASS`` for symbols
        present in both snapshots whose structural body hash differs.

        Identity is ``(name, kind, file_path, parent_class)`` where kind
        groups FUNCTION+METHOD.  Because ``body_hash`` is
        identity-exempt, a body edit alone produces no ADD/REMOVE — this
        pass is the only signal for it — while remove+recreate still
        yields REMOVE + ADD (never CHANGED).

        **Defensive None rule:** if either side's ``body_hash`` is
        ``None`` (legacy cache data or an unhashable symbol kind), emit
        nothing — a change is never fabricated from an uncomputable
        comparison.
        """
        changes: list[DetectedChange] = []
        pre_by_key: dict[tuple[str, str, Path, str | None], Symbol] = {}
        for sym in pre.all_symbols:
            kind = ChangeDetector._symbol_change_kind(sym.symbol_type)
            if kind is None:
                continue
            pre_by_key[(sym.name, kind, sym.file_path, sym.parent_class)] = sym

        for sym in post.all_symbols:
            kind = ChangeDetector._symbol_change_kind(sym.symbol_type)
            if kind is None:
                continue
            pre_sym = pre_by_key.get((sym.name, kind, sym.file_path, sym.parent_class))
            if pre_sym is None:
                continue
            if pre_sym.body_hash is None or sym.body_hash is None:
                continue
            if pre_sym.body_hash == sym.body_hash:
                continue
            changes.append(
                DetectedChange(
                    change_type=(
                        ChangeType.CHANGED_FUNCTION
                        if kind == "FUNCTION"
                        else ChangeType.CHANGED_CLASS
                    ),
                    file_path=sym.file_path,
                    symbol_name=sym.name,
                    parent_class=sym.parent_class,
                    line_number=sym.line_number,
                )
            )

        return changes

    # ------------------------------------------------------------------
    # File-level detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_file_changes(
        pre: ScanResult,
        post: ScanResult,
    ) -> list[DetectedChange]:
        """Compare file sets to find created and deleted files.

        Includes every scanned language in the file set, so that adding
        or removing any source file surfaces a ``FILE_CREATED`` /
        ``FILE_DELETED`` change.
        """
        changes: list[DetectedChange] = []
        pre_files: set[Path] = (
            set(pre.modules)
            | set(pre.js_files)
            | set(pre.ts_files)
            | set(pre.rust_files)
            | set(pre.go_files)
            | set(pre.java_files)
            | set(pre.failed_files)
        )
        post_files: set[Path] = (
            set(post.modules)
            | set(post.js_files)
            | set(post.ts_files)
            | set(post.rust_files)
            | set(post.go_files)
            | set(post.java_files)
            | set(post.failed_files)
        )

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
    def _call_sort_key(c: CallEvidence) -> tuple[str, str, str, str]:
        """Deterministic sort key for :class:`CallEvidence` (the frozen
        dataclass is not ``order=True``)."""
        return (
            str(c.file_path),
            c.caller_name,
            c.called_name,
            c.caller_parent_class or "",
        )

    @staticmethod
    def _detect_calls(pre: ScanResult, post: ScanResult) -> list[DetectedChange]:
        """Compare call sets from pre and post states.

        Scans both snapshots for function calls and reports calls that
        **appeared** (``CALL_DETECTED``) or **disappeared**
        (``CALL_REMOVED``) between the two states.  Unchanged calls are
        not reported.

        Method/attribute calls (``obj.method()``, ``self.foo()``,
        ``s.foo()``, ``pkg.Func()``) are captured with
        ``caller_parent_class`` and surface on the resulting change as
        ``parent_class``.

        Nested function bodies are walked independently so that calls
        in ``inner()`` are attributed to ``inner``, not ``outer``.
        """
        pre_calls = ChangeDetector._extract_calls(pre)
        post_calls = ChangeDetector._extract_calls(post)

        new_calls = post_calls - pre_calls
        removed_calls = pre_calls - post_calls

        changes: list[DetectedChange] = []
        for ev in sorted(new_calls, key=ChangeDetector._call_sort_key):
            changes.append(
                DetectedChange(
                    change_type=ChangeType.CALL_DETECTED,
                    file_path=ev.file_path,
                    caller_name=ev.caller_name,
                    called_name=ev.called_name,
                    parent_class=ev.caller_parent_class,
                )
            )
        for ev in sorted(removed_calls, key=ChangeDetector._call_sort_key):
            changes.append(
                DetectedChange(
                    change_type=ChangeType.CALL_REMOVED,
                    file_path=ev.file_path,
                    caller_name=ev.caller_name,
                    called_name=ev.called_name,
                    parent_class=ev.caller_parent_class,
                )
            )

        return changes

    @staticmethod
    def _iter_python_callers(
        module: ast.Module,
    ) -> Iterable[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]]:
        """Yield ``(caller_node, enclosing_class_name)`` for every
        function-like node in a module.

        Tracks the enclosing ``ClassDef`` lexically: top-level functions
        carry ``None``, methods carry their class name, and nested
        functions inside methods stay lexically inside the class.  The
        walk descends through every statement position (``if``/``try``/
        ``with`` blocks included) exactly like the old flat ``ast.walk``,
        so caller discovery is unchanged — only the class context is new.
        """

        def walk(
            nodes: Iterable[ast.AST],
            parent_class: str | None,
        ) -> Iterable[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]]:
            for node in nodes:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield node, parent_class
                    yield from walk(node.body, parent_class)
                elif isinstance(node, ast.ClassDef):
                    yield from walk(node.body, node.name)
                else:
                    yield from walk(ast.iter_child_nodes(node), parent_class)

        yield from walk(module.body, None)

    @staticmethod
    def _resolve_call_file(
        repo_root: Path | None,
        file_path: Path,
    ) -> Path | None:
        """Resolve *file_path* to an absolute path for call re-parsing.

        Returns ``None`` — after logging a warning — when the file
        cannot be located with certainty, so callers skip it instead of
        guessing.

        Resolution rules:

        * ``repo_root`` is present → ``repo_root / file_path``.  This is
          the standard pipeline case: scan file paths are relative to
          the repository root.
        * ``repo_root`` is ``None`` and *file_path* is absolute → the
          path is used as-is.  (Scanners running without a root store
          absolute paths, so this is the hand-built-scan case.)
        * ``repo_root`` is ``None`` and *file_path* is relative → the
          original root is unknowable; resolving against the CWD could
          silently read a different file, so the file is skipped.
        """
        if repo_root is not None:
            return (repo_root / file_path).resolve()
        if file_path.is_absolute():
            return file_path
        logger.warning(
            "Cannot locate %s for call detection: scan result has no "
            "repo_root and the path is relative; skipping instead of "
            "guessing against the CWD.",
            file_path,
        )
        return None

    @staticmethod
    def _extract_calls(
        scan: ScanResult,
    ) -> set[CallEvidence]:
        """Extract all :class:`CallEvidence` objects from a scan result.

        Handles Python, JavaScript, TypeScript, Rust, Go, and Java source
        files:

        **Python:** walks every function/method body looking for
        ``ast.Call`` nodes with a simple ``ast.Name`` or an
        ``ast.Attribute`` chain (``self.foo()``, ``a.b.c()``) function
        expression, carrying the enclosing class name.

        **JavaScript/TypeScript/Rust/Go/Java:** re-parses each file
        listed in ``scan.js_files``, ``scan.ts_files``,
        ``scan.rust_files``, ``scan.go_files``, or ``scan.java_files``
        using the respective tree-sitter scanner and extracts a
        ``call_expression`` (Java: ``method_invocation``) whose target is
        a simple ``identifier``, a member/field/selector chain, or — for
        Java — the invocation's own ``name``.

        Non-Python files are re-read from disk.  File paths are resolved
        through :meth:`_resolve_call_file`: against ``scan.repo_root``
        when present, as-is when absolute, and skipped with a warning
        when relative with no root — the original root is unknowable in
        that case, and guessing against the CWD could silently read the
        wrong file.
        """
        # Local import to avoid circular dependency at module level:
        #   change_detector → javascript_scanner → symbol_index → repository_scanner
        from nowreck.scanner.javascript_scanner import scan_js_calls  # noqa: PLC0415

        calls: set[CallEvidence] = set()

        # --- Python calls ---
        for file_path, module in scan.modules.items():
            for caller_node, parent_class in ChangeDetector._iter_python_callers(
                module,
            ):
                called_names = ChangeDetector._find_call_names(
                    caller_node,
                    skip_owner=caller_node,
                )
                for called in called_names:
                    calls.add(
                        CallEvidence(
                            file_path=file_path,
                            caller_name=caller_node.name,
                            called_name=called,
                            caller_parent_class=parent_class,
                        )
                    )

        # --- JavaScript calls ---
        repo_root = scan.repo_root
        for file_path in scan.js_files:
            abs_path = ChangeDetector._resolve_call_file(repo_root, file_path)
            if abs_path is None:
                continue
            try:
                js_calls = scan_js_calls(abs_path, repo_root=repo_root)
                calls.update(js_calls)
            except (FileNotFoundError, OSError) as exc:
                logger.warning(
                    "Could not re-read JS file for call detection: %s — %s",
                    abs_path,
                    exc,
                )

        # --- TypeScript calls ---
        from nowreck.scanner.typescript_scanner import scan_ts_calls  # noqa: PLC0415

        for file_path in scan.ts_files:
            abs_path = ChangeDetector._resolve_call_file(repo_root, file_path)
            if abs_path is None:
                continue
            try:
                ts_calls = scan_ts_calls(abs_path, repo_root=repo_root)
                calls.update(ts_calls)
            except (FileNotFoundError, OSError) as exc:
                logger.warning(
                    "Could not re-read TS file for call detection: %s — %s",
                    abs_path,
                    exc,
                )

        # --- Rust calls ---
        from nowreck.scanner.rust_scanner import scan_rust_calls  # noqa: PLC0415

        for file_path in scan.rust_files:
            abs_path = ChangeDetector._resolve_call_file(repo_root, file_path)
            if abs_path is None:
                continue
            try:
                rust_calls = scan_rust_calls(abs_path, repo_root=repo_root)
                calls.update(rust_calls)
            except (FileNotFoundError, OSError) as exc:
                logger.warning(
                    "Could not re-read Rust file for call detection: %s — %s",
                    abs_path,
                    exc,
                )

        # --- Go calls ---
        from nowreck.scanner.go_scanner import scan_go_calls  # noqa: PLC0415

        for file_path in scan.go_files:
            abs_path = ChangeDetector._resolve_call_file(repo_root, file_path)
            if abs_path is None:
                continue
            try:
                go_calls = scan_go_calls(abs_path, repo_root=repo_root)
                calls.update(go_calls)
            except (FileNotFoundError, OSError) as exc:
                logger.warning(
                    "Could not re-read Go file for call detection: %s — %s",
                    abs_path,
                    exc,
                )

        # --- Java calls ---
        from nowreck.scanner.java_scanner import scan_java_calls  # noqa: PLC0415

        for file_path in scan.java_files:
            abs_path = ChangeDetector._resolve_call_file(repo_root, file_path)
            if abs_path is None:
                continue
            try:
                java_calls = scan_java_calls(abs_path, repo_root=repo_root)
                calls.update(java_calls)
            except (FileNotFoundError, OSError) as exc:
                logger.warning(
                    "Could not re-read Java file for call detection: %s — %s",
                    abs_path,
                    exc,
                )

        return calls

    @staticmethod
    def _find_call_names(
        root: ast.AST,
        skip_owner: ast.AST | None = None,
    ) -> set[str]:
        """Collect all called names within *root*.

        Walks the tree manually, **skipping** any ``FunctionDef`` or
        ``AsyncFunctionDef`` node that is not *skip_owner*.  This
        prevents calls in nested functions from being attributed to
        their enclosing function.

        Captures ``ast.Call`` nodes whose function is a simple
        ``ast.Name`` (``print()``, ``sorted()``) or an ``ast.Attribute``
        chain whose receiver is a ``Name`` or ``Attribute``
        (``self.foo()``, ``a.b.c()`` — the final attribute name is the
        called name).  Dunder-style attributes (``obj.__x__()``) and
        call receivers (``super().foo()``, ``f().bar()``) are excluded.
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

            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    calls.add(func.id)
                elif isinstance(func, ast.Attribute) and not is_dunder_name(
                    func.attr,
                ):
                    if isinstance(func.value, (ast.Name, ast.Attribute)):
                        # ``self.foo()``, ``obj.bar()``, ``a.b.c()``.
                        # A ``Call`` receiver (``super().foo()``) is
                        # neither a Name nor an Attribute, so it is
                        # excluded by construction.
                        calls.add(func.attr)

            todo.extend(ast.iter_child_nodes(node))

        return calls


# Convenience alias
detect_changes = ChangeDetector.detect
