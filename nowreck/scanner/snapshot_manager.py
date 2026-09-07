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
class _StashResult:
    """Outcome of :meth:`SnapshotManager._git_stash`.

    Attributes:
        mode: ``"clean"`` (nothing stashed) or ``"stashed"`` (a stash
            was pushed and must be popped on restore).
        sentinel_dir: Temp directory marking git-snapshot mode.
    """

    mode: str
    sentinel_dir: Path


@dataclass(frozen=True)
class Snapshot:
    """A captured repository state.

    Attributes:
        scan_result: The ``ScanResult`` from scanning the directory.
        symbol_index: The ``SymbolIndex`` built from the scan.
        snapshot_dir: If created via temp copy, the temp directory.
            ``None`` when the snapshot was created via direct scan
            (no copy needed).
        restore_mode: How ``restore()`` should put the tree back:
            ``"copy"`` (temp-directory copy), ``"clean"`` (git repo,
            clean tree — nothing stashed), or ``"stashed"`` (git repo,
            uncommitted changes pushed to a stash).
        cache_pre_existed: Whether ``.nowreck/cache/`` existed inside
            the repo *before* this run started scanning.  When False,
            ``restore()`` removes the cache directory the run created
            (Part B P1/P3 — prompt mode must not litter the user's
            tree with a cache that wasn't there before).
    """

    scan_result: ScanResult
    symbol_index: SymbolIndex
    snapshot_dir: Path | None = None
    restore_mode: str = "copy"
    cache_pre_existed: bool = False

    @property
    def from_git(self) -> bool:
        """True when the snapshot was taken via the git strategy."""
        return self.restore_mode in ("clean", "stashed")


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

    def __init__(
        self,
        repo_path: str | Path,
        *,
        use_cache: bool | None = None,
    ) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._use_cache = use_cache

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    def _cache_enabled(self) -> bool:
        """Decide whether scans should use the persistent on-disk cache.

        ``use_cache=None`` (the default) enables the cache **only when
        the scanned root is the current working directory** — the live
        project (prompt mode, ``--pre .``).  External snapshot
        directories (``--pre A --post B``, git-archive temps, manual
        prompt snapshots) are inputs, not scratch space, so they run
        with the cache disabled (Part B P3).  An explicit ``True`` /
        ``False`` always wins.
        """
        if self._use_cache is not None:
            return self._use_cache
        return self._repo_path == Path.cwd().resolve()

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
        scanner = RepositoryScanner(self._repo_path, use_cache=self._cache_enabled())
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

        The snapshot records *which* strategy was used (``restore_mode``
        is ``"clean"`` / ``"stashed"`` / ``"copy"``) so ``restore()``
        can undo exactly what was done — a clean git tree pushes no
        stash, a dirty one pushes one, and the copy strategy captures
        everything except ``.git``.

        It also records whether ``.nowreck/cache/`` already existed so
        the run-created cache can be removed on restore (Part B P1/P3).
        """
        cache_pre_existed = (self._repo_path / ".nowreck" / "cache").is_dir()

        # Try git stash
        stash = self._git_stash()
        if stash is not None:
            logger.info("Used git stash to save before state")
            # After stash, scan the clean repo
            scanner = RepositoryScanner(
                self._repo_path, use_cache=self._cache_enabled()
            )
            scan_result = scanner.scan()
            symbol_index = SymbolIndexBuilder.build(scan_result)
            return Snapshot(
                scan_result=scan_result,
                symbol_index=symbol_index,
                snapshot_dir=stash.sentinel_dir,
                restore_mode=stash.mode,
                cache_pre_existed=cache_pre_existed,
            )

        # Fallback: copy entire directory.  The snapshot copy excludes
        # only ``.git`` — a pre-existing ``.venv`` / ``node_modules`` /
        # ``__pycache__`` must be captured so restore can put it back
        # instead of deleting it forever (Part B P1).
        tmp = tempfile.mkdtemp(prefix="nowreck_snapshot_")
        snapshot_dir = Path(tmp)
        shutil.copytree(
            self._repo_path,
            snapshot_dir / "repo",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git"),
        )
        logger.info("Copied repo to %s for snapshot", snapshot_dir)

        # Scan the original (before copy is modified)
        scanner = RepositoryScanner(self._repo_path, use_cache=self._cache_enabled())
        scan_result = scanner.scan()
        symbol_index = SymbolIndexBuilder.build(scan_result)
        return Snapshot(
            scan_result=scan_result,
            symbol_index=symbol_index,
            snapshot_dir=snapshot_dir,
            restore_mode="copy",
            cache_pre_existed=cache_pre_existed,
        )

    def restore(
        self,
        snapshot: Snapshot,
        *,
        applied_files: list[str] | None = None,
        revert_files: bool = True,
    ) -> bool:
        """Restore the repository to the state captured in *snapshot*.

        Args:
            snapshot: The snapshot to restore from.
            applied_files: Relative paths of the files the model's
                patch touched.  Only these files are reverted (git
                strategy) — never a blanket checkout.
            revert_files: Whether to undo the patch's file changes at
                all.  ``False`` skips the revert but **still pops a
                pushed stash** (the stash holds the user's own
                uncommitted work — it must return home).  Also used to
                settle the run-created cache when nothing was applied.

        Returns:
            ``True`` if restoration succeeded, ``False`` otherwise.

        Failure semantics (git strategy): a failed revert surfaces
        loudly (error logged, stash preserved, ``False`` returned) —
        never a silent partial restore.  A failed stash pop also
        returns ``False`` with the stash left in place.
        """
        if snapshot.snapshot_dir is None:
            logger.warning("No snapshot_dir — cannot restore")
            return False

        # Part B P1/P3: remove the cache dir this run created inside
        # the repo (prompt mode scans the CWD, which writes
        # `.nowreck/cache/`).  A pre-existing cache is left untouched.
        self._remove_cache_if_created(snapshot)

        if snapshot.restore_mode in ("clean", "stashed"):
            return self._restore_git(
                snapshot, applied_files=applied_files, revert_files=revert_files
            )

        # Temp directory copy — restore from copy
        if not revert_files:
            return True

        copy_dir = snapshot.snapshot_dir / "repo"
        if not copy_dir.is_dir():
            logger.warning("Snapshot copy dir missing: %s", copy_dir)
            return False

        # Remove patch artifacts: anything now in the tree that was not
        # captured by the snapshot copy (files the patch created, the
        # run-created cache, generated pycache, etc.).  Never touches
        # `.git`.
        for item in self._repo_path.iterdir():
            if item.name == ".git":
                continue
            if not (copy_dir / item.name).exists():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        # Remove current files (except .git) and copy snapshot contents
        # back — captured entries round-trip exactly.
        for item in self._repo_path.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for item in copy_dir.iterdir():
            dest = self._repo_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        logger.info("Restored repo from snapshot %s", snapshot.snapshot_dir)
        return True

    def _restore_git(
        self,
        snapshot: Snapshot,
        *,
        applied_files: list[str] | None,
        revert_files: bool,
    ) -> bool:
        """Git-strategy restore: revert the patch's files, then pop.

        Order matters (Part B P1): revert-first makes the same-file
        case succeed by construction — stash push (user's edit to
        HEAD) → patch edits the file → revert to HEAD → stash pop
        restores the user's edit.  Patch gone, user edit intact, no
        conflict.

        The revert is scoped to exactly ``applied_files``; unrelated
        untracked files and ignored dirs (``.venv``, ``node_modules``)
        are untouchable.
        """
        if not self._is_git_repo():
            logger.error(
                "Git restore requested but %s is not a git repo", self._repo_path
            )
            return False

        if revert_files and applied_files:
            for rel in applied_files:
                if not self._git_checkout_head(rel):
                    # The file could not be reverted.  If it is
                    # untracked it was created by the patch — delete it.
                    # Otherwise this is a genuine revert failure that
                    # must surface loudly (stash preserved, error
                    # returned) rather than silently leaving a
                    # partially-reverted tree.
                    if self._git_is_untracked(rel):
                        (self._repo_path / rel).unlink(missing_ok=True)
                        continue
                    logger.error(
                        "Revert failed for %s — earlier applied files "
                        "(if any) were already reverted; stash preserved",
                        rel,
                    )
                    return False

        if snapshot.restore_mode == "stashed":
            if not self._git_stash_pop():
                logger.error(
                    "git stash pop failed — uncommitted changes remain "
                    "in 'git stash list'"
                )
                return False

        return True

    def _git_checkout_head(self, relative_path: str) -> bool:
        """Revert one tracked file to HEAD.  Returns False on failure."""
        try:
            result = subprocess.run(
                ["git", "checkout", "HEAD", "--", relative_path],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("git checkout error: %s", exc)
            return False

    def _git_is_untracked(self, relative_path: str) -> bool:
        """True when git does not track the given path."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", relative_path],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode != 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _remove_cache_if_created(self, snapshot: Snapshot) -> None:
        """Remove ``.nowreck/cache/`` when this run created it."""
        if snapshot.cache_pre_existed:
            return
        cache_dir = self._repo_path / ".nowreck" / "cache"
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
            nowreck_dir = cache_dir.parent
            if nowreck_dir.is_dir() and not any(nowreck_dir.iterdir()):
                nowreck_dir.rmdir()

    def cleanup(self, snapshot: Snapshot) -> None:
        """Remove temporary files created during snapshot.

        Must be called after :meth:`restore` (or after verification
        if no restore is needed).
        """
        if snapshot.snapshot_dir is None:
            return

        # Git stash — the stash lives in .git, but the sentinel dir
        # was created with mkdtemp() and must be removed too.
        if snapshot.restore_mode in ("clean", "stashed"):
            (snapshot.snapshot_dir / ".git_stash").unlink(missing_ok=True)
            shutil.rmtree(snapshot.snapshot_dir, ignore_errors=True)
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

    def _git_stash(self) -> _StashResult | None:
        """Stash uncommitted changes.

        Returns a ``_StashResult`` describing what happened, or ``None``
        when the repo is not git or stashing failed (caller falls back
        to the temp copy).  Part B P1: a **clean** tree pushes no stash
        (mode ``"clean"``) — only a dirty tree pushes one (mode
        ``"stashed"``) — so restore knows whether a pop is owed.
        """
        if not self._is_git_repo():
            return None

        try:
            # Check if there's anything to stash.  Untracked files are
            # NOT stashed by `git stash push` (no -u), so they never
            # make the tree dirty for our purposes — only tracked
            # modifications (staged or unstaged) need stashing.
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            dirty_lines = [
                line
                for line in status.stdout.splitlines()
                if line.strip() and not line.startswith("??")
            ]
            if not dirty_lines:
                # Clean working tree — no stash needed
                sentinel = Path(tempfile.mkdtemp(prefix="nowreck_stash_"))
                (sentinel / ".git_stash").touch()
                return _StashResult(mode="clean", sentinel_dir=sentinel)

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
                return _StashResult(mode="stashed", sentinel_dir=sentinel)

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
