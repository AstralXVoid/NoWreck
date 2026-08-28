"""Tests for the git integration module."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nowreck.git_integration import GitError, GitSnapshot, extract_snapshot

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _init_git_repo(tmp_path: Path) -> Path:
    """Initialize a git repo with one commit in tmp_path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    (repo / "app.py").write_text("def old(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return repo


# ---------------------------------------------------------------------------
# GitSnapshot
# ---------------------------------------------------------------------------


class TestGitSnapshot:
    """Test the GitSnapshot class."""

    def test_extract_head(self, tmp_path: Path) -> None:
        """Should extract HEAD successfully."""
        repo = _init_git_repo(tmp_path)

        # Change directory to the repo for git commands
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(repo)
            with GitSnapshot("HEAD") as snapshot:
                assert snapshot.path.exists()
                assert (snapshot.path / "app.py").exists()
        finally:
            os.chdir(old_cwd)

    def test_extract_ref(self, tmp_path: Path) -> None:
        """Should extract a specific commit hash."""
        repo = _init_git_repo(tmp_path)

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(repo)
            # Get the commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            )
            commit_hash = result.stdout.strip()

            with GitSnapshot(commit_hash) as snapshot:
                assert snapshot.path.exists()
                assert (snapshot.path / "app.py").exists()
        finally:
            os.chdir(old_cwd)

    def test_invalid_ref_raises_error(self, tmp_path: Path) -> None:
        """Should raise GitError for invalid ref."""
        repo = _init_git_repo(tmp_path)

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(repo)
            with pytest.raises(GitError, match="ref nonexistent_ref_12345 not found"):
                with GitSnapshot("nonexistent_ref_12345"):
                    pass
        finally:
            os.chdir(old_cwd)

    def test_not_git_repo_raises_error(self, tmp_path: Path) -> None:
        """Should raise GitError when not in a git repo."""
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(GitError, match="not a git repository"):
                with GitSnapshot("HEAD"):
                    pass
        finally:
            os.chdir(old_cwd)

    def test_ref_property(self, tmp_path: Path) -> None:
        """Should return the ref used."""
        repo = _init_git_repo(tmp_path)

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(repo)
            with GitSnapshot("HEAD") as snapshot:
                assert snapshot.ref == "HEAD"
        finally:
            os.chdir(old_cwd)

    def test_path_before_extract_raises_error(self, tmp_path: Path) -> None:
        """Should raise GitError if path accessed before extraction."""
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            snapshot = GitSnapshot("HEAD")
            with pytest.raises(GitError, match="not extracted yet"):
                _ = snapshot.path
        finally:
            os.chdir(old_cwd)

    def test_cleanup(self, tmp_path: Path) -> None:
        """Should clean up temp directory."""
        repo = _init_git_repo(tmp_path)

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(repo)
            snapshot = GitSnapshot("HEAD")
            snapshot.extract()
            path = snapshot.path
            assert path.exists()
            snapshot.cleanup()
            assert snapshot._path is None
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# extract_snapshot
# ---------------------------------------------------------------------------


class TestExtractSnapshot:
    """Test the extract_snapshot function."""

    def test_extract_to_directory(self, tmp_path: Path) -> None:
        """Should extract to a target directory."""
        repo = _init_git_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(repo)
            extract_snapshot("HEAD", target)
            assert (target / "app.py").exists()
        finally:
            os.chdir(old_cwd)
