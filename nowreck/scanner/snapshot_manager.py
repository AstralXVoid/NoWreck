"""Snapshot-based repository state capture for v10 independent verification.

The SnapshotManager captures a directory's state before and after the
model modifies files, enabling the verifier to compare independently
observed changes rather than relying on the model's own claims.

Two strategies are supported:

1. **Git stash** (preferred) — fast, atomic, native to git repos.
2. **Temp directory copy** (fallback) — works without git.

The caller uses the captured ``ScanResult`` + ``SymbolIndex`` pairs to
feed ``ChangeDetector.detect()``, producing independent evidence that
is completely decoupled from the model's claims.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nowreck.scanner.repository_scanner import RepositoryScanner, ScanResult
from nowreck.scanner.symbol_index import SymbolIndex, SymbolIndexBuilder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    """A captured repository state.

    Attributes:
        scan_result: The ``ScanResult`` from scanning the directory.
        symbol_index: The ``SymbolIndex`` built from the scan.
        snapshot_dir: If created via temp copy, the temp directory.
            ``None`` when the snapshot was created via direct scan
            (no copy needed).
    """

    scan_result: ScanResult
    symbol_index: SymbolIndex
    snapshot_dir: Path | None = None


class SnapshotManager:
    """Captures and restores repository state for independent verification.

    Usage::

        mgr = SnapshotManager(Path("/path/to/repo"))

        # Capture before state
        before = mgr.capture()

        # ... model modifies files ...

        # Capture after state
        after = mgr.capture()

        # Compare
        changes = ChangeDetector.detect(
            before.scan_result, after.scan_result,
            before.symbol_index, after.symbol_index,
        )

        # Restore original state if needed
        mgr.cleanup(before)
    """

    def __init__(self, repo_path: str | Path) -> None:
        self._repo_path = Path(repo_path).resolve()

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture(self) -> Snapshot:
        """Scan the current repository state and return a Snapshot.

        This performs a fresh scan of the working tree.  It does NOT
        create a copy — the scan reads files directly.  Use
        :meth:`save_before` if you need to restore the original state
        after the model makes changes.
        """
        scanner = RepositoryScanner(self._repo_path)
        scan_result = scanner.scan()
        symbol_index = SymbolIndexBuilder.build(scan_result)
        return Snapshot(scan_result=scan_result, symbol_index=symbol_index)

    # ------------------------------------------------------------------
    # Save / restore (for cases where the model modifies files)
    # ------------------------------------------------------------------

    def save_before(self) -> Snapshot:
        """Save the current repository state and create a copy.

        Returns a Snapshot that includes the ``snapshot_dir`` (a temp
        copy).  Use :meth:`restore` with this snapshot to put the
        working tree back.

        Tries git stash first.  Falls back to temp directory copy.
        """
        # Try git stash
        stash_dir = self._git_stash()
        if stash_dir is not None:
            logger.info("Used git stash to save before state")
            # After stash, scan the clean repo
            scanner = RepositoryScanner(self._repo_path)
            scan_result = scanner.scan()
            symbol_index = SymbolIndexBuilder.build(scan_result)
            return Snapshot(
                scan_result=scan_result,
                symbol_index=symbol_index,
                snapshot_dir=stash_dir,  # sentinel: git stash mode
            )

        # Fallback: copy entire directory
        tmp = tempfile.mkdtemp(prefix="nowreck_snapshot_")
        snapshot_dir = Path(tmp)
        shutil.copytree(
            self._repo_path,
            snapshot_dir / "repo",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git", "__pycache__", ".venv", "node_modules",
            ),
        )
        logger.info("Copied repo to %s for snapshot", snapshot_dir)

        # Scan the original (before copy is modified)
        scanner = RepositoryScanner(self._repo_path)
        scan_result = scanner.scan()
        symbol_index = SymbolIndexBuilder.build(scan_result)
        return Snapshot(
            scan_result=scan_result,
            symbol_index=symbol_index,
            snapshot_dir=snapshot_dir,
        )

    def restore(self, snapshot: Snapshot) -> bool:
        """Restore the repository to the state captured in *snapshot*.

        Returns ``True`` if restoration succeeded, ``False`` otherwise.
        """
        if snapshot.snapshot_dir is None:
            logger.warning("No snapshot_dir — cannot restore")
            return False

        # Check if this was a git stash
        stash_marker = snapshot.snapshot_dir / ".git_stash"
        if stash_marker.exists():
            return self._git_stash_pop()

        # Temp directory copy — restore from copy
        copy_dir = snapshot.snapshot_dir / "repo"
        if not copy_dir.is_dir():
            logger.warning("Snapshot copy dir missing: %s", copy_dir)
            return False

        # Remove current files (except .git)
        for item in self._repo_path.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Copy snapshot contents back
        for item in copy_dir.iterdir():
            dest = self._repo_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        logger.info("Restored repo from snapshot %s", snapshot.snapshot_dir)
        return True

    def cleanup(self, snapshot: Snapshot) -> None:
        """Remove temporary files created during snapshot.

        Must be called after :meth:`restore` (or after verification
        if no restore is needed).
        """
        if snapshot.snapshot_dir is None:
            return

        # Git stash — nothing to clean up (stash lives in .git)
        stash_marker = snapshot.snapshot_dir / ".git_stash"
        if stash_marker.exists():
            stash_marker.unlink(missing_ok=True)
            return

        # Temp directory — remove it
        if snapshot.snapshot_dir.is_dir():
            shutil.rmtree(snapshot.snapshot_dir, ignore_errors=True)
            logger.info("Cleaned up snapshot dir %s", snapshot.snapshot_dir)

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def _is_git_repo(self) -> bool:
        """Check if the repo path is inside a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _git_stash(self) -> Path | None:
        """Stash uncommitted changes.  Returns sentinel Path on success."""
        if not self._is_git_repo():
            return None

        try:
            # Check if there's anything to stash
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if not status.stdout.strip():
                # Clean working tree — no stash needed
                sentinel = Path(tempfile.mkdtemp(prefix="nowreck_stash_"))
                (sentinel / ".git_stash").touch()
                return sentinel

            result = subprocess.run(
                ["git", "stash", "push", "-m", "nowreck-snapshot"],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                sentinel = Path(tempfile.mkdtemp(prefix="nowreck_stash_"))
                (sentinel / ".git_stash").touch()
                return sentinel

            logger.warning("git stash failed: %s", result.stderr.strip())
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("git stash error: %s", exc)
            return None

    def _git_stash_pop(self) -> bool:
        """Restore stashed changes."""
        if not self._is_git_repo():
            return False

        try:
            result = subprocess.run(
                ["git", "stash", "pop"],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("git stash pop succeeded")
                return True

            logger.warning("git stash pop failed: %s", result.stderr.strip())
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("git stash pop error: %s", exc)
            return False
