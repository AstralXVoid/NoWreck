from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from nowreck.scanner.scan_cache import CacheEntry, ScanCache, file_content_hash

if TYPE_CHECKING:
    from nowreck.scanner.symbol_index import Symbol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """The complete, deterministic result of scanning a repository.

    Attributes:
        modules: Mapping of file paths (relative to repo root) to their
            parsed ``ast.Module`` trees. Only successfully parsed Python
            files appear here.
        js_files: Mapping of file paths (relative to repo root) to the
            list of ``Symbol`` objects extracted from each successfully
            parsed JavaScript file.
        ts_files: Mapping of file paths (relative to repo root) to the
            list of ``Symbol`` objects extracted from each successfully
            parsed TypeScript-family file (``.ts`` and ``.tsx``).
        rust_files: Mapping of file paths (relative to repo root) to the
            list of ``Symbol`` objects extracted from each successfully
            parsed Rust file (``.rs``).
        go_files: Mapping of file paths (relative to repo root) to the
            list of ``Symbol`` objects extracted from each successfully
            parsed Go file (``.go``).
        failed_files: Mapping of file paths (relative to repo root) to
            the error message produced when parsing failed.
    """

    modules: dict[Path, ast.Module] = field(default_factory=dict)
    js_files: dict[Path, list[Symbol]] = field(default_factory=dict)
    ts_files: dict[Path, list[Symbol]] = field(default_factory=dict)
    rust_files: dict[Path, list[Symbol]] = field(default_factory=dict)
    go_files: dict[Path, list[Symbol]] = field(default_factory=dict)
    failed_files: dict[Path, str] = field(default_factory=dict)
    repo_root: Path | None = None

    @property
    def success_count(self) -> int:
        return (
            len(self.modules)
            + len(self.js_files)
            + len(self.ts_files)
            + len(self.rust_files)
            + len(self.go_files)
        )

    @property
    def failure_count(self) -> int:
        return len(self.failed_files)


class RepositoryScanner:
    """Scans a repository directory for Python, JavaScript, TypeScript,
    Rust, and Go files and parses them into their respective structural
    representations.

    This scanner discovers ``.py`` files recursively and parses each with
    ``ast.parse``, discovers ``.js`` files and parses each with the
    tree-sitter-based JavaScript scanner, discovers ``.ts``/``.tsx`` files
    and parses each with the tree-sitter-based TypeScript scanner,
    discovers ``.rs`` files and parses each with the Rust scanner, and
    discovers ``.go`` files and parses each with the Go scanner.  The
    results are collected into a :class:`ScanResult`.

    Files that raise a ``SyntaxError``, ``UnicodeDecodeError``, or
    ``OSError`` are recorded in ``failed_files`` rather than halting the
    scan.

    The scanner deliberately avoids any semantic analysis or code
    execution — it treats source as structural information only.

    Args:
        repo_path: Absolute or relative path to the repository root
            directory. Resolved to an absolute path on init.
    """

    def __init__(self, repo_path: str | Path, *, use_cache: bool = True) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._use_cache = use_cache

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    def scan(self) -> ScanResult:
        """Discover and parse all ``.py``, ``.js``, ``.ts``, ``.rs``,
        and ``.go`` files under the repository root.

        When the scan cache is enabled (the default), previously parsed
        files are cached on disk and reused if their mtime and size
        haven't changed.  The cache is transparent — the returned
        ``ScanResult`` is identical whether warm or cold.

        Returns:
            A :class:`ScanResult` containing all successfully parsed
            modules, JS/TS/Rust/Go symbol lists, and any files
            that failed to parse.
        """
        from nowreck.scanner.symbol_index import Symbol as SymbolClass  # noqa: PLC0415

        cache = ScanCache(self._repo_path) if self._use_cache else None

        modules: dict[Path, ast.Module] = {}
        js_files: dict[Path, list[Symbol]] = {}
        ts_files: dict[Path, list[Symbol]] = {}
        rust_files: dict[Path, list[Symbol]] = {}
        go_files: dict[Path, list[Symbol]] = {}
        failed: dict[Path, str] = {}

        # --- Python files ---
        for py_file in self._discover_files(".py"):
            relative = py_file.relative_to(self._repo_path)
            try:
                stat = py_file.stat()
                mtime = stat.st_mtime
                size = stat.st_size
            except OSError as exc:
                failed[relative] = f"OSError: {exc}"
                continue

            content_hash = file_content_hash(py_file)
            cached = (
                cache.get(relative, mtime, size, content_hash)
                if cache is not None
                else None
            )
            if cached is not None and cached.source is not None:
                # Cache hit: re-parse source to ast.Module
                try:
                    modules[relative] = ast.parse(
                        cached.source, filename=str(py_file)
                    )
                except SyntaxError as exc:
                    failed[relative] = f"SyntaxError: {exc}"
            else:
                # Cache miss: parse normally
                parsed, error = self._parse_file(py_file)
                if parsed is not None:
                    modules[relative] = parsed
                    if cache is not None:
                        try:
                            source = py_file.read_text(encoding="utf-8")
                        except (OSError, UnicodeDecodeError):
                            source = ""
                        cache.put(
                            relative,
                            mtime,
                            size,
                            CacheEntry(
                                mtime=mtime,
                                size=size,
                                language="python",
                                content_hash=content_hash,
                                source=source,
                            ),
                        )
                elif error is not None:
                    failed[relative] = error

        # --- JavaScript files ---
        for js_file in self._discover_files(".js"):
            relative = js_file.relative_to(self._repo_path)
            try:
                stat = js_file.stat()
                mtime = stat.st_mtime
                size = stat.st_size
            except OSError as exc:
                failed[relative] = f"OSError: {exc}"
                continue

            js_hash = file_content_hash(js_file)
            cached = (
                cache.get(relative, mtime, size, js_hash)
                if cache is not None
                else None
            )
            if cached is not None and cached.symbols:
                # Cache hit: deserialise symbols
                js_files[relative] = [
                    SymbolClass.from_dict(s) for s in cached.symbols
                ]
            else:
                # Cache miss: parse normally
                symbols, error = self._parse_js_file(js_file)
                if symbols is not None:
                    js_files[relative] = symbols
                    if cache is not None:
                        cache.put(
                            relative,
                            mtime,
                            size,
                            CacheEntry(
                                mtime=mtime,
                                size=size,
                                language="javascript",
                                content_hash=js_hash,
                                symbols=[s.to_dict() for s in symbols],
                            ),
                        )
                elif error is not None:
                    failed[relative] = error

        # --- TypeScript files ---
        for ts_file in self._discover_files(".ts", ".tsx"):
            relative = ts_file.relative_to(self._repo_path)
            try:
                stat = ts_file.stat()
                mtime = stat.st_mtime
                size = stat.st_size
            except OSError as exc:
                failed[relative] = f"OSError: {exc}"
                continue

            ts_hash = file_content_hash(ts_file)
            cached = (
                cache.get(relative, mtime, size, ts_hash)
                if cache is not None
                else None
            )
            if cached is not None and cached.symbols:
                ts_files[relative] = [
                    SymbolClass.from_dict(s) for s in cached.symbols
                ]
            else:
                symbols, error = self._parse_ts_file(ts_file)
                if symbols is not None:
                    ts_files[relative] = symbols
                    if cache is not None:
                        cache.put(
                            relative,
                            mtime,
                            size,
                            CacheEntry(
                                mtime=mtime,
                                size=size,
                                language="typescript",
                                content_hash=ts_hash,
                                symbols=[s.to_dict() for s in symbols],
                            ),
                        )
                elif error is not None:
                    failed[relative] = error

        # --- Rust files ---
        for rust_file in self._discover_files(".rs"):
            relative = rust_file.relative_to(self._repo_path)
            try:
                stat = rust_file.stat()
                mtime = stat.st_mtime
                size = stat.st_size
            except OSError as exc:
                failed[relative] = f"OSError: {exc}"
                continue

            rs_hash = file_content_hash(rust_file)
            cached = (
                cache.get(relative, mtime, size, rs_hash)
                if cache is not None
                else None
            )
            if cached is not None and cached.symbols:
                rust_files[relative] = [
                    SymbolClass.from_dict(s) for s in cached.symbols
                ]
            else:
                symbols, error = self._parse_rust_file(rust_file)
                if symbols is not None:
                    rust_files[relative] = symbols
                    if cache is not None:
                        cache.put(
                            relative,
                            mtime,
                            size,
                            CacheEntry(
                                mtime=mtime,
                                size=size,
                                language="rust",
                                content_hash=rs_hash,
                                symbols=[s.to_dict() for s in symbols],
                            ),
                        )
                elif error is not None:
                    failed[relative] = error

        # --- Go files ---
        for go_file in self._discover_files(".go"):
            relative = go_file.relative_to(self._repo_path)
            try:
                stat = go_file.stat()
                mtime = stat.st_mtime
                size = stat.st_size
            except OSError as exc:
                failed[relative] = f"OSError: {exc}"
                continue

            go_hash = file_content_hash(go_file)
            cached = (
                cache.get(relative, mtime, size, go_hash)
                if cache is not None
                else None
            )
            if cached is not None and cached.symbols:
                go_files[relative] = [
                    SymbolClass.from_dict(s) for s in cached.symbols
                ]
            else:
                symbols, error = self._parse_go_file(go_file)
                if symbols is not None:
                    go_files[relative] = symbols
                    if cache is not None:
                        cache.put(
                            relative,
                            mtime,
                            size,
                            CacheEntry(
                                mtime=mtime,
                                size=size,
                                language="go",
                                content_hash=go_hash,
                                symbols=[s.to_dict() for s in symbols],
                            ),
                        )
                elif error is not None:
                    failed[relative] = error

        # Persist cache at the end of a successful scan.
        if cache is not None:
            cache.save()

        # Phase 5 / 3.5: Log a one-line failure-rate summary so users
        # see aggregate parse health even if individual failures were
        # silently logged at the per-file level.
        total = (
            len(modules)
            + len(js_files)
            + len(ts_files)
            + len(rust_files)
            + len(go_files)
            + len(failed)
        )
        success = total - len(failed)
        if total > 0 and failed:
            rate = len(failed) / total * 100
            logger.warning(
                "Scan complete: %d/%d files parsed successfully "
                "(%.1f%% failure rate across %d languages)",
                success,
                total,
                rate,
                sum(1 for _ in (modules, js_files, ts_files, rust_files, go_files)),
            )
        elif total > 0:
            logger.debug(
                "Scan complete: %d/%d files parsed successfully",
                success,
                total,
            )

        return ScanResult(
            modules=modules,
            js_files=js_files,
            ts_files=ts_files,
            rust_files=rust_files,
            go_files=go_files,
            failed_files=failed,
            repo_root=self._repo_path,
        )

    def _discover_files(self, *suffixes: str) -> list[Path]:
        """Recursively discover files matching any of the given
        suffixes, skipping hidden directories.

        Phase 5 / 3.1: replaces the five language-specific discovery
        methods (``_discover_python_files``, ``_discover_js_files``,
        ``_discover_ts_files``, ``_discover_rust_files``,
        ``_discover_go_files``) with one shared implementation.
        TypeScript uses two suffixes (``.ts`` and ``.tsx``); all other
        languages use a single suffix.

        Hidden directories (names starting with ``.``) are excluded by
        default to avoid scanning ``.git``, ``.nowreck``, ``.venv``, etc.

        Args:
            *suffixes: One or more file suffixes to match (e.g.
                ``".py"``, or ``".ts"``, ``".tsx"``).

        Returns:
            A deterministically sorted list of file paths matching
            any of the supplied suffixes.
        """
        if not suffixes:
            raise ValueError("At least one suffix must be provided")

        found: list[Path] = []
        if not self._repo_path.is_dir():
            logger.warning("Repository path is not a directory: %s", self._repo_path)
            return found

        for suffix in suffixes:
            for entry in self._repo_path.rglob(f"*{suffix}"):
                # Skip files inside hidden directories (e.g. .git, .venv)
                if any(
                    part.startswith(".")
                    for part in entry.relative_to(self._repo_path).parts
                ):
                    continue
                found.append(entry)

        return sorted(found)  # deterministic ordering

    def _discover_python_files(self) -> list[Path]:
        """Recursively discover all ``.py`` files, skipping hidden dirs.

        Hidden directories (names starting with ``.``) are excluded by
        default to avoid scanning ``.git``, ``.nowreck``, ``.venv``, etc.

        .. deprecated::
            Use :meth:`_discover_files` directly. Retained as a thin
            wrapper for any external callers and for the scanner's own
            unit tests that may import it.
        """
        return self._discover_files(".py")

    def _discover_js_files(self) -> list[Path]:
        """Recursively discover all ``.js`` files, skipping hidden dirs.

        Hidden directories (names starting with ``.``) are excluded by
        default to avoid scanning ``.git``, ``.nowreck``, ``.venv``, etc.

        .. deprecated::
            Use :meth:`_discover_files` directly.
        """
        return self._discover_files(".js")

    def _parse_file(self, file_path: Path) -> tuple[ast.Module | None, str | None]:
        """Parse a single Python file into an ``ast.Module``.

        Returns a ``(module, error)`` tuple. If parsing succeeds,
        ``module`` is the parsed AST and ``error`` is ``None``.
        If parsing fails, ``module`` is ``None`` and ``error`` is a
        human-readable message describing the failure.
        """
        try:
            source = file_path.read_text(encoding="utf-8")
            return ast.parse(source, filename=str(file_path)), None
        except SyntaxError as exc:
            msg = f"SyntaxError: {exc}"
            logger.warning("Failed to parse %s: %s", file_path, msg)
            return None, msg
        except (UnicodeDecodeError, ValueError) as exc:
            # ValueError covers null bytes in source; UnicodeDecodeError
            # covers binary files pretending to be text.
            exc_type = type(exc).__name__
            msg = f"{exc_type}: {exc}"
            logger.warning("Failed to read %s: %s", file_path, msg)
            return None, msg
        except OSError as exc:
            msg = f"OSError: {exc}"
            logger.warning("Failed to read %s: %s", file_path, msg)
            return None, msg

    def _discover_ts_files(self) -> list[Path]:
        """Recursively discover all ``.ts`` and ``.tsx`` files, skipping
        hidden dirs.

        Both extensions belong to the same TypeScript family and fold
        into the single ``ts_files`` field.  Hidden directories (names
        starting with ``.``) are excluded by default to avoid scanning
        ``.git``, ``.nowreck``, ``.venv``, etc.

        .. deprecated::
            Use :meth:`_discover_files` directly.
        """
        return self._discover_files(".ts", ".tsx")

    def _parse_js_file(
        self,
        file_path: Path,
    ) -> tuple[list[Symbol] | None, str | None]:
        """Parse a single JavaScript file using the tree-sitter scanner.

        Returns a ``(symbols, error)`` tuple.  If parsing succeeds,
        ``symbols`` is the list of :class:`Symbol` objects found in the
        file and ``error`` is ``None``.  If parsing fails (e.g. file not
        found, I/O error), ``symbols`` is ``None`` and ``error`` is a
        human-readable message.

        Note that tree-sitter is resilient to syntax errors — it produces
        a partial CST and logs a warning rather than raising.  Therefore
        most real-world ``.js`` files will produce a non-``None`` result
        even with syntax issues.
        """
        # Local import to avoid circular dependency:
        #   repository_scanner → javascript_scanner → symbol_index → repository_scanner
        from nowreck.scanner.javascript_scanner import scan_js_file  # noqa: PLC0415

        try:
            symbols = scan_js_file(file_path, repo_root=self._repo_path)
            return symbols, None
        except (FileNotFoundError, SyntaxError, OSError) as exc:
            exc_type = type(exc).__name__
            msg = f"{exc_type}: {exc}"
            logger.warning("Failed to parse %s: %s", file_path, msg)
            return None, msg

    def _parse_ts_file(
        self,
        file_path: Path,
    ) -> tuple[list[Symbol] | None, str | None]:
        """Parse a single TypeScript file using the tree-sitter scanner.

        Returns a ``(symbols, error)`` tuple.  If parsing succeeds,
        ``symbols`` is the list of :class:`Symbol` objects found in the
        file and ``error`` is ``None``.  If parsing fails (e.g. file not
        found, I/O error), ``symbols`` is ``None`` and ``error`` is a
        human-readable message.

        Note that tree-sitter is resilient to syntax errors — it produces
        a partial CST and logs a warning rather than raising.  Therefore
        most real-world ``.ts`` files will produce a non-``None`` result
        even with syntax issues.
        """
        # Local import to avoid circular dependency:
        #   repository_scanner -> typescript_scanner -> _tree_sitter_helpers
        #   -> symbol_index -> repository_scanner
        from nowreck.scanner.typescript_scanner import scan_ts_file  # noqa: PLC0415

        try:
            symbols = scan_ts_file(file_path, repo_root=self._repo_path)
            return symbols, None
        except (FileNotFoundError, SyntaxError, OSError) as exc:
            exc_type = type(exc).__name__
            msg = f"{exc_type}: {exc}"
            logger.warning("Failed to parse %s: %s", file_path, msg)
            return None, msg

    # ------------------------------------------------------------------
    # Rust discovery and parsing
    # ------------------------------------------------------------------

    def _discover_rust_files(self) -> list[Path]:
        """Recursively discover all ``.rs`` files, skipping hidden dirs.

        Hidden directories (names starting with ``.``) are excluded by
        default to avoid scanning ``.git``, ``.nowreck``, ``.venv``, etc.

        .. deprecated::
            Use :meth:`_discover_files` directly.
        """
        return self._discover_files(".rs")

    def _parse_rust_file(
        self,
        file_path: Path,
    ) -> tuple[list[Symbol] | None, str | None]:
        """Parse a single Rust file using the tree-sitter scanner.

        Returns a ``(symbols, error)`` tuple.  If parsing succeeds,
        ``symbols`` is the list of :class:`Symbol` objects found in the
        file and ``error`` is ``None``.  If parsing fails, ``symbols``
        is ``None`` and ``error`` is a human-readable message.
        """
        from nowreck.scanner.rust_scanner import scan_rust_file  # noqa: PLC0415

        try:
            symbols = scan_rust_file(file_path, repo_root=self._repo_path)
            return symbols, None
        except (FileNotFoundError, SyntaxError, OSError) as exc:
            exc_type = type(exc).__name__
            msg = f"{exc_type}: {exc}"
            logger.warning("Failed to parse %s: %s", file_path, msg)
            return None, msg

    # ------------------------------------------------------------------
    # Go discovery and parsing
    # ------------------------------------------------------------------

    def _discover_go_files(self) -> list[Path]:
        """Recursively discover all ``.go`` files, skipping hidden dirs.

        Hidden directories (names starting with ``.``) are excluded by
        default to avoid scanning ``.git``, ``.nowreck``, ``.venv``, etc.

        .. deprecated::
            Use :meth:`_discover_files` directly.
        """
        return self._discover_files(".go")

    def _parse_go_file(
        self,
        file_path: Path,
    ) -> tuple[list[Symbol] | None, str | None]:
        """Parse a single Go file using the tree-sitter scanner.

        Returns a ``(symbols, error)`` tuple.  If parsing succeeds,
        ``symbols`` is the list of :class:`Symbol` objects found in the
        file and ``error`` is ``None``.  If parsing fails, ``symbols``
        is ``None`` and ``error`` is a human-readable message.
        """
        from nowreck.scanner.go_scanner import scan_go_file  # noqa: PLC0415

        try:
            symbols = scan_go_file(file_path, repo_root=self._repo_path)
            return symbols, None
        except (FileNotFoundError, SyntaxError, OSError) as exc:
            exc_type = type(exc).__name__
            msg = f"{exc_type}: {exc}"
            logger.warning("Failed to parse %s: %s", file_path, msg)
            return None, msg
