"""Tests for the v10 PromptModeVerifier.

These tests prove the circularity fix:
- Claims and evidence must come from independent sources.
- Model claims must never generate verification evidence.
- Missing evidence must produce UNVERIFIABLE.
- Contradictory evidence must produce CONTRADICTED.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from nowreck.claims.models import Claim, ClaimType
from nowreck.claims.parser import ClaimParser
from nowreck.detector.change_detector import (
    ChangeType,
    detect_changes,
)
from nowreck.model.provider import ModelConfig, ModelResult
from nowreck.scanner.snapshot_manager import Snapshot, SnapshotManager
from nowreck.verifier.prompt_verifier import (
    PatchApplicationResult,
    PatchApplier,
    PromptModeVerifier,
    PromptVerificationResult,
)
from nowreck.verifier.verifier import ClaimVerifier, Verdict

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    """Create a minimal repo with one Python file."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        textwrap.dedent("""\
            def greet(name):
                return f"Hello, {name}!"

            def add(a, b):
                return a + b
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def repo_with_changes(repo_dir: Path) -> Path:
    """Repo that has been modified (add a new function)."""
    (repo_dir / "src" / "utils.py").write_text(
        textwrap.dedent("""\
            def multiply(a, b):
                return a * b
        """),
        encoding="utf-8",
    )
    return repo_dir


# ---------------------------------------------------------------------------
# PatchApplier tests
# ---------------------------------------------------------------------------


class TestPatchApplier:
    """Tests for the PatchApplier class."""

    def test_apply_empty_patch(self, repo_dir: Path) -> None:
        result = PatchApplier.apply("", repo_dir)
        assert result.success is False
        assert "Empty patch" in result.errors[0]

    def test_apply_simple_addition(self, repo_dir: Path) -> None:
        patch = textwrap.dedent("""\
            --- a/src/utils.py
            +++ b/src/utils.py
            @@ -0,0 +1,2 @@
            +def multiply(a, b):
            +    return a * b
        """)
        result = PatchApplier.apply(patch, repo_dir)
        assert result.success is True
        assert "src/utils.py" in result.applied_files
        assert (repo_dir / "src" / "utils.py").exists()

    def test_extract_files_from_patch(self) -> None:
        patch = textwrap.dedent("""\
            --- a/src/app.py
            +++ b/src/app.py
            @@ -1 +1 @@
            -def old():
            +def new():
        """)
        files = PatchApplier._extract_files_from_patch(patch)
        assert "src/app.py" in files

    def test_extract_multiple_files(self) -> None:
        patch = textwrap.dedent("""\
            --- a/src/app.py
            +++ b/src/app.py
            @@ -1 +1 @@
            -def old():
            +def new():
            --- a/src/utils.py
            +++ b/src/utils.py
            @@ -0,0 +1 @@
            +def helper():
        """)
        files = PatchApplier._extract_files_from_patch(patch)
        assert "src/app.py" in files
        assert "src/utils.py" in files


# ---------------------------------------------------------------------------
# Circularity tests — THE CRITICAL TESTS
# ---------------------------------------------------------------------------


class TestCircularityPrevention:
    """Proves that the verifier cannot obtain evidence from the claim itself.

    These tests create scenarios where:
    1. Claims say X happened
    2. But the repo state shows X did NOT happen
    3. The verifier must report CONTRADICTED, not CONFIRMED
    """

    def test_claim_not_used_as_evidence(self, repo_dir: Path) -> None:
        """If model claims ADD_FUNCTION but no file was added,
        result must be UNVERIFIABLE (no evidence), not CONFIRMED."""
        # Claims say we added a function
        claims = [
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="deleted_func",
                file_path="src/deleted.py",
            )
        ]

        # But the repo hasn't changed at all
        before = SnapshotManager(repo_dir).capture()
        after = SnapshotManager(repo_dir).capture()

        observed = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        report = ClaimVerifier.verify(claims, observed)

        # Must be UNVERIFIABLE — no evidence exists
        assert report.results[0].verdict is Verdict.UNVERIFIABLE
        # Must NOT be CONFIRMED — that would mean the claim fabricated evidence
        assert report.results[0].verdict is not Verdict.CONFIRMED

    def test_false_claim_contradicted(self, repo_with_changes: Path) -> None:
        """If model claims ADD_FUNCTION for a function that was REMOVED,
        result must be CONTRADICTED."""
        # Capture BEFORE state (repo has greet + add)
        before = SnapshotManager(repo_with_changes).capture()

        # Now remove a function
        (repo_with_changes / "src" / "app.py").write_text(
            textwrap.dedent("""\
                def add(a, b):
                    return a + b
            """),
            encoding="utf-8",
        )

        after = SnapshotManager(repo_with_changes).capture()

        observed = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        # Model claims greet was ADDED (it was actually REMOVED)
        claims = [
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="greet",
                file_path="src/app.py",
            )
        ]

        report = ClaimVerifier.verify(claims, observed)

        # greet was removed, claim says added → CONTRADICTED
        assert report.results[0].verdict is Verdict.CONTRADICTED

    def test_honest_claim_confirmed(self, repo_with_changes: Path) -> None:
        """If model claims ADD_FUNCTION for a function that WAS added,
        result must be CONFIRMED."""
        before = SnapshotManager(repo_with_changes).capture()

        # Add a new function
        (repo_with_changes / "src" / "math.py").write_text(
            textwrap.dedent("""\
                def multiply(a, b):
                    return a * b
            """),
            encoding="utf-8",
        )

        after = SnapshotManager(repo_with_changes).capture()

        observed = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        claims = [
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="multiply",
                file_path="src/math.py",
            )
        ]

        report = ClaimVerifier.verify(claims, observed)

        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_multiple_claims_partial_match(self, repo_with_changes: Path) -> None:
        """Multiple claims — some verified, some contradicted,
        some unverifiable — each evaluated independently."""
        before = SnapshotManager(repo_with_changes).capture()

        # Add a new file
        (repo_with_changes / "src" / "math.py").write_text(
            textwrap.dedent("""\
                def multiply(a, b):
                    return a * b
            """),
            encoding="utf-8",
        )

        after = SnapshotManager(repo_with_changes).capture()

        observed = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        claims = [
            # TRUE: multiply was added
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="multiply",
                file_path="src/math.py",
            ),
            # FALSE: greet was not added (it already existed)
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="greet",
                file_path="src/app.py",
            ),
            # FALSE: nonexistent function
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="nonexistent",
                file_path="src/fake.py",
            ),
        ]

        report = ClaimVerifier.verify(claims, observed)

        verdicts = [r.verdict for r in report.results]
        assert Verdict.CONFIRMED in verdicts  # multiply
        assert Verdict.UNVERIFIABLE in verdicts  # nonexistent or greet

    def test_no_evidence_produces_unverifiable(self, repo_dir: Path) -> None:
        """When there's no before/after transition, all claims must be
        UNVERIFIABLE — never CONFIRMED."""
        claims = [
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="any_func",
                file_path="src/any.py",
            )
        ]

        # Same state before and after
        before = SnapshotManager(repo_dir).capture()
        after = SnapshotManager(repo_dir).capture()

        observed = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        report = ClaimVerifier.verify(claims, observed)

        assert report.results[0].verdict is Verdict.UNVERIFIABLE
        assert report.confirmed == 0
        assert report.contradicted == 0


# ---------------------------------------------------------------------------
# SnapshotManager integration tests
# ---------------------------------------------------------------------------


class TestSnapshotManagerIntegration:
    """Tests for SnapshotManager used by PromptModeVerifier."""

    def test_capture_returns_snapshot(self, repo_dir: Path) -> None:
        mgr = SnapshotManager(repo_dir)
        snap = mgr.capture()
        assert isinstance(snap, Snapshot)
        # ScanResult has modules, js_files, ts_files, etc.
        total_files = (
            len(snap.scan_result.modules)
            + len(snap.scan_result.js_files)
            + len(snap.scan_result.ts_files)
            + len(snap.scan_result.rust_files)
            + len(snap.scan_result.go_files)
        )
        assert total_files > 0
        assert len(snap.symbol_index.all_symbols) > 0

    def test_two_captures_detect_changes(self, repo_with_changes: Path) -> None:
        mgr = SnapshotManager(repo_with_changes)
        before = mgr.capture()

        # Modify
        (repo_with_changes / "src" / "new.py").write_text(
            "def new_func(): pass\n",
            encoding="utf-8",
        )

        after = mgr.capture()

        changes = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        assert len(changes) > 0
        assert ChangeType.ADD_FUNCTION in {c.change_type for c in changes}

    def test_identical_captures_no_changes(self, repo_dir: Path) -> None:
        mgr = SnapshotManager(repo_dir)
        before = mgr.capture()
        after = mgr.capture()

        changes = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        assert len(changes) == 0


# ---------------------------------------------------------------------------
# PatchApplicationResult tests
# ---------------------------------------------------------------------------


class TestPatchApplicationResult:
    """Tests for the PatchApplicationResult dataclass."""

    def test_success_result(self) -> None:
        result = PatchApplicationResult(
            success=True,
            applied_files=["src/app.py"],
        )
        assert result.success is True
        assert result.applied_files == ["src/app.py"]
        assert result.errors == []

    def test_failure_result(self) -> None:
        result = PatchApplicationResult(
            success=False,
            errors=["File not found"],
        )
        assert result.success is False
        assert "File not found" in result.errors


# ---------------------------------------------------------------------------
# PromptVerificationResult tests
# ---------------------------------------------------------------------------


class TestPromptVerificationResult:
    """Tests for the PromptVerificationResult dataclass."""

    def test_has_independent_evidence(self) -> None:
        from nowreck.verifier.verifier import VerificationReport

        report = VerificationReport(results=[])
        result = PromptVerificationResult(
            report=report,
            patch_applied=True,
            has_independent_evidence=True,
        )
        assert result.has_independent_evidence is True

    def test_no_independent_evidence(self) -> None:
        from nowreck.verifier.verifier import VerificationReport

        report = VerificationReport(results=[])
        result = PromptVerificationResult(
            report=report,
            patch_applied=False,
            has_independent_evidence=False,
        )
        assert result.has_independent_evidence is False


# ---------------------------------------------------------------------------
# Claim parser patch extraction tests
# ---------------------------------------------------------------------------


class TestClaimParserPatchExtraction:
    """Tests for the patch field in ClaimParser.parse()."""

    def test_parse_with_patch(self) -> None:
        import json

        patch_str = "--- a/src/app.py\n+++ b/src/app.py"
        patch_str += "\n@@ -0,0 +1,2 @@\n+def greet():\n+    pass"
        response = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "greet",
                        "file_path": "src/app.py",
                    }
                ],
                "patch": patch_str,
            }
        )
        result = ClaimParser.parse(response)
        assert result.success
        assert result.patch is not None
        assert "--- a/src/app.py" in result.patch

    def test_parse_without_patch(self) -> None:
        response = textwrap.dedent("""\
            {
              "claims": [
                {
                  "type": "ADD_FUNCTION",
                  "symbol_name": "greet",
                  "file_path": "src/app.py"
                }
              ]
            }
        """)
        result = ClaimParser.parse(response)
        assert result.success
        assert result.patch is None

    def test_parse_with_empty_patch(self) -> None:
        response = textwrap.dedent("""\
            {
              "claims": [
                {
                  "type": "ADD_FUNCTION",
                  "symbol_name": "greet",
                  "file_path": "src/app.py"
                }
              ],
              "patch": ""
            }
        """)
        result = ClaimParser.parse(response)
        assert result.success
        assert result.patch is None


# ---------------------------------------------------------------------------
# Restore-after-patch tests (P0-01)
#
# Before the fix, _restore_from_patch() was a no-op stub: Prompt Mode
# left the model's patch permanently in the user's working tree, and a
# mid-flow exception (or a git-stash snapshot with no patch) silently
# skipped cleanup entirely.
# ---------------------------------------------------------------------------

_PATCH = "fake unified diff — applied by the stubbed PatchApplier"


class _StubModelProvider:
    """Stands in for ModelProvider inside PromptModeVerifier."""

    def __init__(self, result: ModelResult) -> None:
        self._result = result

    def changes_from_prompt_v10(
        self, prompt: str, repo_context: str = ""
    ) -> ModelResult:
        return self._result


def _patched_file_result() -> ModelResult:
    return ModelResult(claims=[], patch=_PATCH)


def _stub_patch_apply(monkeypatch: pytest.MonkeyPatch, repo_dir: Path) -> None:
    """Replace PatchApplier.apply with a deterministic file creation."""

    def fake_apply(patch: str, repo: Path) -> PatchApplicationResult:
        target = Path(repo) / "src" / "new.py"
        target.write_text("def fresh():\n    return 1\n", encoding="utf-8")
        return PatchApplicationResult(success=True, applied_files=["src/new.py"])

    monkeypatch.setattr(
        "nowreck.verifier.prompt_verifier.PatchApplier.apply", fake_apply
    )


def _make_verifier(repo_dir: Path, result: ModelResult) -> PromptModeVerifier:
    verifier = PromptModeVerifier(repo_dir, ModelConfig(api_key="sk-test"))
    verifier._model_provider = _StubModelProvider(result)
    return verifier


class TestRestoreAfterPatch:
    """Prove that verify() settles the working tree in every path."""

    def test_restore_removes_patched_file(
        self, repo_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A patch that creates src/new.py is undone after verify()."""
        _stub_patch_apply(monkeypatch, repo_dir)
        verifier = _make_verifier(repo_dir, _patched_file_result())

        result = verifier.verify("add fresh function")

        assert not (repo_dir / "src" / "new.py").exists()
        assert result.patch_applied is True

    def test_no_restore_leaves_patch_when_disabled(
        self, repo_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With restore_after=False the patch stays in the tree."""
        _stub_patch_apply(monkeypatch, repo_dir)
        verifier = _make_verifier(repo_dir, _patched_file_result())

        verifier.verify("add fresh function", restore_after=False)

        assert (repo_dir / "src" / "new.py").exists()

    def test_restored_repo_scannable(
        self, repo_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After restore, the repo scans cleanly at its original size."""
        from nowreck.scanner.repository_scanner import RepositoryScanner

        baseline = len(RepositoryScanner(repo_dir).scan().modules)
        _stub_patch_apply(monkeypatch, repo_dir)
        verifier = _make_verifier(repo_dir, _patched_file_result())

        verifier.verify("add fresh function")

        modules = RepositoryScanner(repo_dir).scan().modules
        assert len(modules) == baseline

    def test_no_patch_skips_restore_but_cleans_up(
        self, repo_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No patch → no restore attempt, but snapshot cleanup still runs."""
        cleaned: list[Snapshot] = []
        monkeypatch.setattr(
            SnapshotManager,
            "cleanup",
            lambda self, snap: cleaned.append(snap),
        )
        verifier = _make_verifier(repo_dir, ModelResult(claims=[]))

        result = verifier.verify("do nothing")

        assert result.patch_applied is False
        assert not (repo_dir / "src" / "new.py").exists()
        assert len(cleaned) == 1
        # save_before() always produces a temp snapshot dir here
        # (repo_dir is not a git repo), so cleanup had real work.
        assert cleaned[0].snapshot_dir is not None

    def test_exception_midflow_still_restores(
        self, repo_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An exception between patch application and verification must
        still restore the tree (finally-block guarantee)."""
        _stub_patch_apply(monkeypatch, repo_dir)
        verifier = _make_verifier(repo_dir, _patched_file_result())

        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("mid-flow explosion")

        monkeypatch.setattr("nowreck.verifier.prompt_verifier.detect_changes", boom)

        with pytest.raises(RuntimeError, match="mid-flow explosion"):
            verifier.verify("add fresh function")

        assert not (repo_dir / "src" / "new.py").exists()

    def test_stash_snapshot_popped_even_without_patch(
        self, repo_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Git-stash snapshots are popped even when no patch was applied —
        the stash holds the user's uncommitted changes."""
        real_capture = SnapshotManager.capture
        sentinel = Path(repo_dir) / ".stash_sentinel"
        sentinel.mkdir()
        (sentinel / ".git_stash").touch()

        restore_calls: list[Snapshot] = []

        def fake_save_before(self: SnapshotManager) -> Snapshot:
            snap = real_capture(self)
            return Snapshot(
                scan_result=snap.scan_result,
                symbol_index=snap.symbol_index,
                snapshot_dir=sentinel,
            )

        def fake_restore(self: SnapshotManager, snap: Snapshot) -> bool:
            restore_calls.append(snap)
            return True

        monkeypatch.setattr(SnapshotManager, "save_before", fake_save_before)
        monkeypatch.setattr(SnapshotManager, "restore", fake_restore)

        verifier = _make_verifier(repo_dir, ModelResult(claims=[]))
        result = verifier.verify("do nothing")

        assert result.patch_applied is False
        # THE critical assertion: stash-mode snapshots are popped even
        # though no patch was applied.
        assert len(restore_calls) == 1
        assert not sentinel.exists()  # cleanup removed the sentinel dir


class TestManualApplyHunks:
    """P1-03: the no-git fallback applies hunks positionally, correctly."""

    BASE = "one\ntwo\nthree\nfour\nfive\nsix\nseven\n"

    def _write_base(self, repo_dir: Path) -> Path:
        target = repo_dir / "src" / "mod.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.BASE, encoding="utf-8")
        return target

    def test_multi_hunk_modification(self, repo_dir: Path) -> None:
        target = self._write_base(repo_dir)
        patch = (
            "--- a/src/mod.py\n"
            "+++ b/src/mod.py\n"
            "@@ -1,3 +1,3 @@\n"
            " one\n"
            "-two\n"
            "+TWO\n"
            " three\n"
            "@@ -6,2 +6,3 @@\n"
            " six\n"
            "+SIX_HALF\n"
            " seven\n"
        )
        result = PatchApplier.apply(patch, repo_dir)

        assert result.success, result.errors
        text = target.read_text(encoding="utf-8")
        assert text == "one\nTWO\nthree\nfour\nfive\nsix\nSIX_HALF\nseven\n"

    def test_insertion_keeps_tail_intact(self, repo_dir: Path) -> None:
        target = self._write_base(repo_dir)
        patch = (
            "--- a/src/mod.py\n"
            "+++ b/src/mod.py\n"
            "@@ -3,2 +3,4 @@\n"
            " three\n"
            "+inserted_a\n"
            "+inserted_b\n"
            " four\n"
        )
        result = PatchApplier.apply(patch, repo_dir)

        assert result.success, result.errors
        assert target.read_text(encoding="utf-8") == (
            "one\ntwo\nthree\ninserted_a\ninserted_b\nfour\nfive\nsix\nseven\n"
        )

    def test_removal_deletes_lines(self, repo_dir: Path) -> None:
        target = self._write_base(repo_dir)
        patch = (
            "--- a/src/mod.py\n"
            "+++ b/src/mod.py\n"
            "@@ -1,5 +1,3 @@\n"
            " one\n"
            "-two\n"
            "-three\n"
            " four\n"
            " five\n"
        )
        result = PatchApplier.apply(patch, repo_dir)

        assert result.success, result.errors
        assert target.read_text(encoding="utf-8") == (
            "one\nfour\nfive\nsix\nseven\n"
        )

    def test_context_mismatch_fails_without_corruption(
        self, repo_dir: Path
    ) -> None:
        target = self._write_base(repo_dir)
        patch = (
            "--- a/src/mod.py\n"
            "+++ b/src/mod.py\n"
            "@@ -1,3 +1,3 @@\n"
            " NOT_THE_ACTUAL_LINE\n"
            "-two\n"
            "+TWO\n"
            " three\n"
        )
        result = PatchApplier.apply(patch, repo_dir)

        assert not result.success
        assert any("context mismatch" in e for e in result.errors)
        # Original content untouched.
        assert target.read_text(encoding="utf-8") == self.BASE

    def test_new_file_creation(self, repo_dir: Path) -> None:
        patch = (
            "--- /dev/null\n"
            "+++ b/src/created.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def fresh():\n"
            "+    return 1\n"
        )
        result = PatchApplier.apply(patch, repo_dir)

        assert result.success, result.errors
        created = repo_dir / "src" / "created.py"
        assert created.read_text(encoding="utf-8") == (
            "def fresh():\n    return 1\n"
        )

    def test_file_deletion(self, repo_dir: Path) -> None:
        target = self._write_base(repo_dir)
        patch = (
            "--- a/src/mod.py\n"
            "+++ /dev/null\n"
            "@@ -1,7 +0,0 @@\n"
            "-one\n"
            "-two\n"
            "-three\n"
            "-four\n"
            "-five\n"
            "-six\n"
            "-seven\n"
        )
        result = PatchApplier.apply(patch, repo_dir)

        assert result.success, result.errors
        assert not target.exists()
