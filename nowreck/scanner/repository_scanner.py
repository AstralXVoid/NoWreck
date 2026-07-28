from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

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
        failed_files: Mapping of file paths (relative to repo root) to
            the error message produced when parsing failed.
    """

    modules: dict[Path, ast.Module] = field(default_factory=dict)
    js_files: dict[Path, list[Symbol]] = field(default_factory=dict)
    failed_files: dict[Path, str] = field(default_factory=dict)
    repo_root: Path | None = None

    @property
    def success_count(self) -> int:
        return len(self.modules) + len(self.js_files)

    @property
    def failure_count(self) -> int:
        return len(self.failed_files)


class RepositoryScanner:
    """Scans a repository directory for Python and JavaScript files and
    parses them into their respective structural representations.

    This scanner discovers ``.py`` files recursively and parses each with
    ``ast.parse``, and discovers ``.js`` files recursively and parses each
    with the tree-sitter-based JavaScript scanner.  The results are
    collected into a :class:`ScanResult`.

    Files that raise a ``SyntaxError``, ``UnicodeDecodeError``, or
    ``OSError`` are recorded in ``failed_files`` rather than halting the
    scan.

    The scanner deliberately avoids any semantic analysis or code
    execution — it treats source as structural information only.

    Args:
        repo_path: Absolute or relative path to the repository root
            directory. Resolved to an absolute path on init.
    """

    def __init__(self, repo_path: str | Path) -> None:
        self._repo_path = Path(repo_path).resolve()

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    def scan(self) -> ScanResult:
        """Discover and parse all ``.py`` and ``.js`` files under the
        repository root.

        Returns:
            A :class:`ScanResult` containing all successfully parsed
            modules and JS symbol lists, and any files that failed to
            parse.
        """
        modules: dict[Path, ast.Module] = {}
        js_files: dict[Path, list[Symbol]] = {}
        failed: dict[Path, str] = {}

        for py_file in self._discover_python_files():
            relative = py_file.relative_to(self._repo_path)
            parsed, error = self._parse_file(py_file)
            if parsed is not None:
                modules[relative] = parsed
            else:
                assert error is not None
                failed[relative] = error

        for js_file in self._discover_js_files():
            relative = js_file.relative_to(self._repo_path)
            symbols, error = self._parse_js_file(js_file)
            if symbols is not None:
                js_files[relative] = symbols
            else:
                assert error is not None
                failed[relative] = error

        return ScanResult(
            modules=modules,
            js_files=js_files,
            failed_files=failed,
            repo_root=self._repo_path,
        )

    def _discover_python_files(self) -> list[Path]:
        """Recursively discover all ``.py`` files, skipping hidden dirs.

        Hidden directories (names starting with ``.``) are excluded by
        default to avoid scanning ``.git``, ``.nowreck``, ``.venv``, etc.
        """
        py_files: list[Path] = []
        if not self._repo_path.is_dir():
            logger.warning("Repository path is not a directory: %s", self._repo_path)
            return py_files

        for entry in self._repo_path.rglob("*.py"):
            # Skip files inside hidden directories (e.g. .git, .venv, __pycache__)
            if any(
                part.startswith(".")
                for part in entry.relative_to(self._repo_path).parts
            ):
                continue
            py_files.append(entry)

        return sorted(py_files)  # deterministic ordering

    def _discover_js_files(self) -> list[Path]:
        """Recursively discover all ``.js`` files, skipping hidden dirs.

        Hidden directories (names starting with ``.``) are excluded by
        default to avoid scanning ``.git``, ``.nowreck``, ``.venv``, etc.
        """
        js_files: list[Path] = []
        if not self._repo_path.is_dir():
            logger.warning("Repository path is not a directory: %s", self._repo_path)
            return js_files

        for entry in self._repo_path.rglob("*.js"):
            # Skip files inside hidden directories (e.g. .git, .venv)
            if any(
                part.startswith(".")
                for part in entry.relative_to(self._repo_path).parts
            ):
                continue
            js_files.append(entry)

        return sorted(js_files)  # deterministic ordering

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

    def _parse_js_file(
        self, file_path: Path,
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
