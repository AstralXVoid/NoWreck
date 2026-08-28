"""Git integration for extracting repository states from commits.

Provides functionality to extract repository states from git commits
using ``git archive`` for use with NoWreck's pre/post comparison mode.
"""

from __future__ import annotations

import subprocess
import tarfile
import tempfile
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""


class GitSnapshot:
    """Extract and manage repository states from git commits.

    Uses ``git archive`` to extract commit states to temporary directories.
    Temporary directories are automatically cleaned up when the context
    manager exits.

    Example::

        with GitSnapshot("HEAD~1") as pre:
            with GitSnapshot("HEAD") as post:
                # pre.path and post.path are temporary directories
                # containing the repository state at each commit
                pass
    """

    def __init__(self, ref: str) -> None:
        """Initialize a git snapshot for a given ref.

        Args:
            ref: A valid git ref (commit hash, branch, tag, HEAD~N, etc.)

        Raises:
            GitError: If git is not installed or the ref is invalid.
        """
        self._ref = ref
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None
        self._path: Path | None = None

    def __enter__(self) -> GitSnapshot:
        self._extract()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()

    @property
    def path(self) -> Path:
        """Return the path to the extracted repository state."""
        if self._path is None:
            raise GitError("Snapshot not extracted yet")
        return self._path

    @property
    def ref(self) -> str:
        """Return the git ref for this snapshot."""
        return self._ref

    def extract(self) -> Path:
        """Extract the repository state to a temporary directory.

        Returns:
            Path to the temporary directory containing the extracted state.

        Raises:
            GitError: If extraction fails.
        """
        self._extract()
        return self.path

    def cleanup(self) -> None:
        """Clean up the temporary directory."""
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None
            self._path = None

    def _extract(self) -> None:
        """Internal extraction logic."""
        if self._path is not None:
            return

        # Verify git is installed
        self._check_git_installed()

        # Verify this is a git repository
        self._check_is_git_repo()

        # Verify the ref exists
        self._check_ref_exists(self._ref)

        # Create temp directory and extract
        self._temp_dir = tempfile.TemporaryDirectory(prefix="nowreck_git_")
        self._path = Path(self._temp_dir.name)

        try:
            # Use git archive to extract the commit state
            result = subprocess.run(
                ["git", "archive", self._ref],
                capture_output=True,
                cwd=self._find_git_root(),
            )
            if result.returncode != 0:
                raise GitError(
                    f"git archive failed for ref '{self._ref}': "
                    f"{result.stderr.decode().strip()}"
                )

            # Extract the tar archive
            import io

            with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
                tar.extractall(path=self._path, filter="data")

        except GitError:
            self.cleanup()
            raise
        except Exception as exc:
            self.cleanup()
            raise GitError(f"Failed to extract ref '{self._ref}': {exc}") from exc

    def _find_git_root(self) -> Path:
        """Find the git repository root directory."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise GitError("Not a git repository")
            return Path(result.stdout.strip())
        except FileNotFoundError as exc:
            raise GitError("git is not installed") from exc

    def _check_git_installed(self) -> None:
        """Verify git is installed."""
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
            )
            if result.returncode != 0:
                raise GitError("git is required for --compare mode")
        except FileNotFoundError as exc:
            raise GitError("git is required for --compare mode") from exc

    def _check_is_git_repo(self) -> None:
        """Verify we're in a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
            )
            if result.returncode != 0:
                raise GitError("not a git repository")
        except FileNotFoundError as exc:
            raise GitError("git is not installed") from exc

    def _check_ref_exists(self, ref: str) -> None:
        """Verify a git ref exists."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                capture_output=True,
            )
            if result.returncode != 0:
                raise GitError(f"ref {ref} not found")
        except FileNotFoundError as exc:
            raise GitError("git is required for --compare mode") from exc


def extract_snapshot(ref: str, target_dir: Path) -> None:
    """Extract a git ref to a target directory.

    This is a standalone function for cases where context manager
    usage is not convenient.

    Args:
        ref: A valid git ref.
        target_dir: Directory to extract into (must exist).

    Raises:
        GitError: If extraction fails.
    """
    snapshot = GitSnapshot(ref)
    try:
        snapshot.extract()
        # Copy from temp to target
        import shutil

        shutil.copytree(snapshot.path, target_dir, dirs_exist_ok=True)
    finally:
        snapshot.cleanup()
