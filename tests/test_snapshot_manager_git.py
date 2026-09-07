"""Real-git restore coverage for the Part B P1 fix, plus P3 cache policy.

These tests create real ``git init`` repositories and exercise
:class:`SnapshotManager` end to end:

- P1: clean-tree restore removes the patch; dirty-tree restore keeps
  user edits and removes the patch; patch-created files are deleted;
  patch-deleted files are restored; the same-file stash case succeeds
  (revert-first ordering); revert failure surfaces loudly with the
  stash preserved; ``restore_after=False`` keeps the patch but still
  pops a pushed stash.
- P3: scanning the CWD (prompt mode) creates ``.nowreck/cache/`` and
  restore removes it when it did not pre-exist; a pre-existing cache
  is left alone; scanning an external dir never writes ``.nowreck/``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nowreck.scanner.snapshot_manager import SnapshotManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "NoWreck Test",
    "GIT_AUTHOR_EMAIL": "test@nowreck.local",
    "GIT_COMMITTER_NAME": "NoWreck Test",
    "GIT_COMMITTER_EMAIL": "test@nowreck.local",
}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command inside *root* with deterministic identity."""
    env = dict(os.environ)
    env.update(_GIT_ENV)
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def _init_repo(root: Path, files: dict[str, str]) -> None:
    """Create a git repo at *root* with the given files committed."""
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    result = _git(root, "init")
    assert result.returncode == 0, result.stderr
    assert _git(root, "add", ".").returncode == 0
    assert _git(root, "commit", "-m", "init").returncode == 0


def _stash_list(root: Path) -> list[str]:
    result = _git(root, "stash", "list")
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# P1: git restore behaviour
# ---------------------------------------------------------------------------


class TestGitRestore:
    """Real-git restore semantics (Part B P1)."""

    def test_clean_tree_restore_removes_patch(self, tmp_path: Path) -> None:
        """A clean-tree snapshot records mode 'clean' (no stash pushed);
        restore reverts the patch's file to HEAD."""
        repo = tmp_path / "repo"
        _init_repo(repo, {"app.py": "def greet():\n    return 'hi'\n"})

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "clean"

        # Model patch modifies app.py
        (repo / "app.py").write_text(
            "def greet():\n    return 'hello'\n", encoding="utf-8"
        )

        assert mgr.restore(before, applied_files=["app.py"]) is True
        assert (repo / "app.py").read_text(encoding="utf-8") == (
            "def greet():\n    return 'hi'\n"
        )
        assert _stash_list(repo) == []
        mgr.cleanup(before)

    def test_dirty_tree_restore_keeps_user_edits_removes_patch(
        self, tmp_path: Path
    ) -> None:
        """A dirty-tree snapshot pushes a stash; restore reverts only the
        patched file and pops the stash, returning the user's edit."""
        repo = tmp_path / "repo"
        _init_repo(
            repo,
            {
                "a.py": "def user_fn():\n    return 'orig'\n",
                "b.py": "def model_fn():\n    return 'orig'\n",
            },
        )

        # User edits a.py (dirty tree)
        (repo / "a.py").write_text(
            "def user_fn():\n    return 'user-edit'\n", encoding="utf-8"
        )

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "stashed"
        stashes = _stash_list(repo)
        assert len(stashes) == 1
        assert "nowreck-snapshot" in stashes[0]

        # Model patch modifies b.py only
        (repo / "b.py").write_text(
            "def model_fn():\n    return 'patched'\n", encoding="utf-8"
        )

        assert mgr.restore(before, applied_files=["b.py"]) is True
        assert (repo / "a.py").read_text(encoding="utf-8") == (
            "def user_fn():\n    return 'user-edit'\n"
        )
        assert (repo / "b.py").read_text(encoding="utf-8") == (
            "def model_fn():\n    return 'orig'\n"
        )
        assert _stash_list(repo) == []
        mgr.cleanup(before)

    def test_patch_created_file_is_deleted(self, tmp_path: Path) -> None:
        """A file the patch created (untracked) is deleted on restore."""
        repo = tmp_path / "repo"
        _init_repo(repo, {"app.py": "def greet():\n    return 'hi'\n"})

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "clean"

        # Patch creates a new file
        (repo / "new.py").write_text("def fresh():\n    return 1\n", encoding="utf-8")

        assert mgr.restore(before, applied_files=["new.py"]) is True
        assert not (repo / "new.py").exists()
        assert (repo / "app.py").exists()
        mgr.cleanup(before)

    def test_patch_deleted_file_is_restored(self, tmp_path: Path) -> None:
        """A tracked file the patch deleted comes back from HEAD."""
        repo = tmp_path / "repo"
        _init_repo(repo, {"app.py": "def greet():\n    return 'hi'\n"})

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "clean"

        # Patch deletes app.py
        (repo / "app.py").unlink()

        assert mgr.restore(before, applied_files=["app.py"]) is True
        assert (repo / "app.py").read_text(encoding="utf-8") == (
            "def greet():\n    return 'hi'\n"
        )
        mgr.cleanup(before)

    def test_same_file_user_edit_and_patch_succeeds(self, tmp_path: Path) -> None:
        """Patch touches the same file the user stashed — revert-first
        ordering makes this a success, not a conflict: the user's edit
        returns intact, the patch is gone."""
        repo = tmp_path / "repo"
        _init_repo(repo, {"a.py": "def shared():\n    return 'orig'\n"})

        (repo / "a.py").write_text(
            "def shared():\n    return 'user-edit'\n", encoding="utf-8"
        )

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "stashed"

        # Patch edits the same file
        (repo / "a.py").write_text(
            "def shared():\n    return 'model-patch'\n", encoding="utf-8"
        )

        assert mgr.restore(before, applied_files=["a.py"]) is True
        # User edit restored; patch gone; stash consumed without conflict
        assert (repo / "a.py").read_text(encoding="utf-8") == (
            "def shared():\n    return 'user-edit'\n"
        )
        assert _stash_list(repo) == []
        mgr.cleanup(before)

    def test_revert_failure_is_loud_and_preserves_stash(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failing revert must surface loudly (error, False) and leave
        the stash untouched — never a silent partial restore."""
        import logging

        repo = tmp_path / "repo"
        _init_repo(repo, {"a.py": "def user_fn():\n    return 'orig'\n"})

        (repo / "a.py").write_text(
            "def user_fn():\n    return 'user-edit'\n", encoding="utf-8"
        )

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "stashed"

        # Simulate a genuine revert failure (e.g. applied_files stale —
        # git cannot check out the path and git says it is tracked).
        monkeypatch.setattr(mgr, "_git_checkout_head", lambda rel: False)
        monkeypatch.setattr(mgr, "_git_is_untracked", lambda rel: False)

        with caplog.at_level(logging.ERROR, logger="nowreck.scanner.snapshot_manager"):
            ok = mgr.restore(before, applied_files=["a.py"])

        assert ok is False
        assert "Revert failed" in caplog.text
        # The stash still holds the user's work — nothing was popped.
        assert len(_stash_list(repo)) == 1
        mgr.cleanup(before)

    def test_restore_after_false_keeps_patch_but_pops_stash(
        self, tmp_path: Path
    ) -> None:
        """restore_after=False skips the revert but still pops a pushed
        stash — the stash holds the user's uncommitted work."""
        repo = tmp_path / "repo"
        _init_repo(
            repo,
            {
                "a.py": "def user_fn():\n    return 'orig'\n",
                "b.py": "def model_fn():\n    return 'orig'\n",
            },
        )

        (repo / "a.py").write_text(
            "def user_fn():\n    return 'user-edit'\n", encoding="utf-8"
        )

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "stashed"

        (repo / "b.py").write_text(
            "def model_fn():\n    return 'patched'\n", encoding="utf-8"
        )

        assert mgr.restore(before, applied_files=["b.py"], revert_files=False) is True
        # Patch stays…
        assert (repo / "b.py").read_text(encoding="utf-8") == (
            "def model_fn():\n    return 'patched'\n"
        )
        # …but the user's edit returns and the stash is consumed.
        assert (repo / "a.py").read_text(encoding="utf-8") == (
            "def user_fn():\n    return 'user-edit'\n"
        )
        assert _stash_list(repo) == []
        mgr.cleanup(before)

    def test_clean_tree_restore_after_false_keeps_patch(self, tmp_path: Path) -> None:
        """Clean-tree + restore_after=False: no revert, no pop — the
        patch stays exactly as applied."""
        repo = tmp_path / "repo"
        _init_repo(repo, {"app.py": "def greet():\n    return 'hi'\n"})

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.restore_mode == "clean"

        (repo / "app.py").write_text(
            "def greet():\n    return 'hello'\n", encoding="utf-8"
        )

        assert mgr.restore(before, applied_files=["app.py"], revert_files=False) is True
        assert (repo / "app.py").read_text(encoding="utf-8") == (
            "def greet():\n    return 'hello'\n"
        )
        assert _stash_list(repo) == []
        mgr.cleanup(before)


# ---------------------------------------------------------------------------
# P3: cache CWD-only policy
# ---------------------------------------------------------------------------


class TestCachePolicy:
    """The persistent cache only writes into the scanned root when that
    root is the current working directory (Part B P3)."""

    def test_cwd_scan_creates_cache_and_restore_removes_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prompt mode scans the CWD → `.nowreck/cache/` is created, and
        restore removes it (it did not pre-exist)."""
        repo = tmp_path / "repo"
        _init_repo(repo, {"app.py": "def greet():\n    return 'hi'\n"})
        monkeypatch.chdir(repo)

        mgr = SnapshotManager(repo)
        before = mgr.save_before()

        cache_dir = repo / ".nowreck" / "cache"
        assert cache_dir.is_dir(), "CWD scan should create .nowreck/cache"
        assert before.cache_pre_existed is False
        # `.nowreck` never enters symbol output.
        for sym in before.symbol_index.all_symbols:
            assert not sym.file_path.parts[0].startswith(".nowreck")

        assert mgr.restore(before, applied_files=[]) is True
        assert not (repo / ".nowreck").exists()
        mgr.cleanup(before)

    def test_pre_existing_cache_is_left_alone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pre-existing `.nowreck/cache/` survives the run untouched."""
        repo = tmp_path / "repo"
        _init_repo(repo, {"app.py": "def greet():\n    return 'hi'\n"})
        cache_dir = repo / ".nowreck" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "scan_cache.json").write_text('{"keep": true}\n', encoding="utf-8")
        monkeypatch.chdir(repo)

        mgr = SnapshotManager(repo)
        before = mgr.save_before()
        assert before.cache_pre_existed is True

        assert mgr.restore(before, applied_files=[]) is True
        assert cache_dir.is_dir()
        assert (cache_dir / "scan_cache.json").exists()
        mgr.cleanup(before)

    def test_external_dir_scan_creates_no_cache(self, tmp_path: Path) -> None:
        """Scanning an external snapshot dir never writes `.nowreck/`."""
        repo = tmp_path / "external"
        _init_repo(repo, {"app.py": "def greet():\n    return 'hi'\n"})
        # NOTE: repo is deliberately NOT the CWD.

        mgr = SnapshotManager(repo)
        before = mgr.save_before()

        # Git strategy is fine (the fixture repo is git-initialised) —
        # the cache policy is what matters: no `.nowreck/` is written
        # into an external dir.
        assert before.restore_mode in ("clean", "stashed")
        assert not (repo / ".nowreck").exists()
        assert _stash_list(repo) == []
        mgr.cleanup(before)

    def test_external_dir_prompt_snapshots_use_no_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Manual snapshot mode (`--pre A --post B`) scans external dirs
        — neither side gets a cache, even when the CWD is nearby."""
        monkeypatch.chdir(tmp_path)  # CWD is tmp_path itself
        pre = tmp_path / "pre"
        post = tmp_path / "post"
        pre.mkdir()
        post.mkdir()
        (pre / "app.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
        (post / "app.py").write_text(
            "def greet():\n    return 'hello'\n", encoding="utf-8"
        )

        pre_mgr = SnapshotManager(pre)
        post_mgr = SnapshotManager(post)
        pre_mgr.capture()
        post_mgr.capture()

        assert not (pre / ".nowreck").exists()
        assert not (post / ".nowreck").exists()
