from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """The complete, deterministic result of scanning a repository.

    Attributes:
        modules: Mapping of file paths (relative to repo root) to their
            parsed ``ast.Module`` trees. Only successfully parsed files
            appear here.
        failed_files: Mapping of file paths (relative to repo root) to
            the error message produced when parsing failed.
    """

    modules: dict[Path, ast.Module] = field(default_factory=dict)
    failed_files: dict[Path, str] = field(default_factory=dict)

    @property
    def success_count(self) -> int:
        return len(self.modules)

    @property
    def failure_count(self) -> int:
        return len(self.failed_files)


class RepositoryScanner:
    """Scans a repository directory for Python files and parses them into ASTs.

    This scanner discovers ``.py`` files recursively, parses each with
    ``ast.parse``, and collects the results into a :class:`ScanResult`.
    Files that raise a ``SyntaxError``, ``UnicodeDecodeError``, or
    ``OSError`` are recorded in ``failed_files`` rather than halting the
    scan.

    The scanner deliberately avoids any semantic analysis or code
    execution — it treats Python source as structural information only.

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
        """Discover and parse all ``.py`` files under the repository root.

        Returns:
            A :class:`ScanResult` containing all successfully parsed
            modules and any files that failed to parse.
        """
        modules: dict[Path, ast.Module] = {}
        failed: dict[Path, str] = {}

        for py_file in self._discover_python_files():
            relative = py_file.relative_to(self._repo_path)
            parsed, error = self._parse_file(py_file)
            if parsed is not None:
                modules[relative] = parsed
            else:
                assert error is not None
                failed[relative] = error

        return ScanResult(modules=modules, failed_files=failed)

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
