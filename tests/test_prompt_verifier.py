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
from nowreck.scanner.snapshot_manager import Snapshot, SnapshotManager
from nowreck.verifier.prompt_verifier import (
    PatchApplicationResult,
    PatchApplier,
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

    def test_claim_not_used_as_evidence(
        self, repo_dir: Path
    ) -> None:
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

    def test_false_claim_contradicted(
        self, repo_with_changes: Path
    ) -> None:
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

    def test_honest_claim_confirmed(
        self, repo_with_changes: Path
    ) -> None:
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

    def test_multiple_claims_partial_match(
        self, repo_with_changes: Path
    ) -> None:
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

    def test_no_evidence_produces_unverifiable(
        self, repo_dir: Path
    ) -> None:
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

    def test_two_captures_detect_changes(
        self, repo_with_changes: Path
    ) -> None:
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

    def test_identical_captures_no_changes(
        self, repo_dir: Path
    ) -> None:
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
        response = json.dumps({
            "claims": [{
                "type": "ADD_FUNCTION",
                "symbol_name": "greet",
                "file_path": "src/app.py",
            }],
            "patch": patch_str,
        })
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
