"""Tests for SnapshotManager (v10 Phase 1)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from nowreck.scanner.snapshot_manager import Snapshot, SnapshotManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_repo(path: Path, files: dict[str, str]) -> None:
    """Write files to a directory."""
    for rel, content in files.items():
        full = path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(textwrap.dedent(content), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests: capture()
# ---------------------------------------------------------------------------


class TestCapture:
    """SnapshotManager.capture() — scan without copy."""

    def test_capture_returns_snapshot(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        assert isinstance(snap, Snapshot)
        assert snap.snapshot_dir is None
        assert snap.scan_result is not None
        assert snap.symbol_index is not None

    def test_capture_finds_functions(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {
            "app.py": "def hello(): pass\ndef world(): pass\n",
        })
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        funcs = snap.symbol_index.functions
        names = {s.name for s in funcs}
        assert "hello" in names
        assert "world" in names

    def test_capture_empty_dir(self, tmp_path: Path) -> None:
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        assert len(snap.symbol_index.all_symbols) == 0

    def test_capture_finds_js(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {
            "index.js": "function greet() { return 'hi'; }\n",
        })
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        funcs = snap.symbol_index.functions
        names = {s.name for s in funcs}
        assert "greet" in names

    def test_capture_finds_ts(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {
            "app.ts": "function greet(name: string): string { return name; }\n",
        })
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        funcs = snap.symbol_index.functions
        names = {s.name for s in funcs}
        assert "greet" in names

    def test_capture_finds_rust(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {
            "main.rs": "fn greet() -> &'static str { \"hi\" }\n",
        })
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        funcs = snap.symbol_index.functions
        names = {s.name for s in funcs}
        assert "greet" in names

    def test_capture_finds_go(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {
            "main.go": "package main\n\nfunc greet() string { return \"hi\" }\n",
        })
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        funcs = snap.symbol_index.functions
        names = {s.name for s in funcs }
        assert "greet" in names

    def test_capture_deterministic(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        snap1 = mgr.capture()
        snap2 = mgr.capture()

        names1 = {s.name for s in snap1.symbol_index.all_symbols}
        names2 = {s.name for s in snap2.symbol_index.all_symbols}
        assert names1 == names2


# ---------------------------------------------------------------------------
# Tests: save_before() and capture after modification
# ---------------------------------------------------------------------------


class TestSaveBeforeAndCapture:
    """save_before + capture detects real changes."""

    def test_detects_added_function(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        before = mgr.save_before()

        # Model adds a function
        (tmp_path / "app.py").write_text(
            "def hello(): pass\n\ndef world(): pass\n",
            encoding="utf-8",
        )

        after = mgr.capture()

        before_names = {s.name for s in before.symbol_index.all_symbols}
        after_names = {s.name for s in after.symbol_index.all_symbols}

        assert "world" in after_names
        assert "world" not in before_names

        mgr.cleanup(before)

    def test_detects_removed_function(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {
            "app.py": "def hello(): pass\ndef world(): pass\n",
        })
        mgr = SnapshotManager(tmp_path)

        before = mgr.save_before()

        # Model removes a function
        (tmp_path / "app.py").write_text(
            "def hello(): pass\n",
            encoding="utf-8",
        )

        after = mgr.capture()

        before_names = {s.name for s in before.symbol_index.all_symbols}
        after_names = {s.name for s in after.symbol_index.all_symbols}

        assert "world" in before_names
        assert "world" not in after_names

        mgr.cleanup(before)

    def test_detects_added_file(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        before = mgr.save_before()

        # Model creates a new file
        (tmp_path / "utils.py").write_text(
            "def helper(): pass\n",
            encoding="utf-8",
        )

        after = mgr.capture()

        before_files = set(before.scan_result.modules.keys())
        after_files = set(after.scan_result.modules.keys())

        assert Path("utils.py") in after_files
        assert Path("utils.py") not in before_files

        mgr.cleanup(before)

    def test_no_changes_detected(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        before = mgr.save_before()
        after = mgr.capture()

        before_names = {s.name for s in before.symbol_index.all_symbols}
        after_names = {s.name for s in after.symbol_index.all_symbols}
        assert before_names == after_names

        mgr.cleanup(before)


# ---------------------------------------------------------------------------
# Tests: restore()
# ---------------------------------------------------------------------------


class TestRestore:
    """save_before + restore returns repo to original state."""

    def test_restore_recovers_original_files(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        before = mgr.save_before()

        # Model modifies file
        (tmp_path / "app.py").write_text(
            "def modified(): pass\n",
            encoding="utf-8",
        )

        # Restore
        restored = mgr.restore(before)
        assert restored is True

        content = (tmp_path / "app.py").read_text(encoding="utf-8")
        assert "def hello():" in content
        assert "def modified():" not in content

        mgr.cleanup(before)

    def test_restore_removes_added_files(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        before = mgr.save_before()

        # Model adds a file
        (tmp_path / "new.py").write_text("x = 1\n", encoding="utf-8")
        assert (tmp_path / "new.py").exists()

        # Restore
        mgr.restore(before)
        assert not (tmp_path / "new.py").exists()

        mgr.cleanup(before)


# ---------------------------------------------------------------------------
# Tests: cleanup()
# ---------------------------------------------------------------------------


class TestCleanup:
    """cleanup removes temporary snapshot directories."""

    def test_cleanup_removes_temp_dir(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        before = mgr.save_before()
        snap_dir = before.snapshot_dir
        assert snap_dir is not None
        assert snap_dir.is_dir()

        mgr.cleanup(before)
        assert not snap_dir.is_dir()

    def test_cleanup_no_snapshot_dir(self, tmp_path: Path) -> None:
        """cleanup on a capture() snapshot (no temp dir) is a no-op."""
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        mgr = SnapshotManager(tmp_path)

        snap = mgr.capture()
        assert snap.snapshot_dir is None
        mgr.cleanup(snap)  # should not raise


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_nonexistent_repo(self, tmp_path: Path) -> None:
        mgr = SnapshotManager(tmp_path / "nonexistent")
        snap = mgr.capture()
        assert len(snap.symbol_index.all_symbols) == 0

    def test_save_before_on_clean_repo(self, tmp_path: Path) -> None:
        """save_before on a clean git repo should still work."""
        _write_repo(tmp_path, {"app.py": "def hello(): pass\n"})
        # Initialize git repo
        import subprocess
        subprocess.run(
            ["git", "init"],
            cwd=tmp_path, capture_output=True, timeout=5,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_path, capture_output=True, timeout=5,
        )
        subprocess.run(
            ["git", "commit", "-m", "init", "--allow-empty"],
            cwd=tmp_path, capture_output=True, timeout=5,
        )

        mgr = SnapshotManager(tmp_path)
        before = mgr.save_before()
        assert before.snapshot_dir is not None

        mgr.cleanup(before)

    def test_mixed_languages(self, tmp_path: Path) -> None:
        """capture finds symbols across all languages."""
        _write_repo(tmp_path, {
            "app.py": "def hello_py(): pass\n",
            "index.js": "function hello_js() {}\n",
            "app.ts": "function hello_ts(): string { return ''; }\n",
            "main.rs": "fn hello_rs() -> i32 { 0 }\n",
            "main.go": "package main\n\nfunc hello_go() string { return \"\" }\n",
        })
        mgr = SnapshotManager(tmp_path)
        snap = mgr.capture()

        names = {s.name for s in snap.symbol_index.all_symbols}
        assert "hello_py" in names
        assert "hello_js" in names
        assert "hello_ts" in names
        assert "hello_rs" in names
        assert "hello_go" in names
