from __future__ import annotations

import json
import tempfile
from pathlib import Path

from nowreck.claims.parser import ClaimParser
from nowreck.detector.change_detector import ChangeDetector, ChangeType, DetectedChange
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.scanner.repository_scanner import RepositoryScanner
from nowreck.scanner.symbol_index import build_symbol_index
from nowreck.verifier.verifier import ClaimVerifier, Verdict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tree(root: Path, files: dict[str, str]) -> None:
    """Write a dict of relative path → content into *root*."""
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _run_pipeline(
    pre_files: dict[str, str],
    post_files: dict[str, str],
    claims_json: str,
) -> tuple[list[DetectedChange], object, object]:
    """Run the full scan → detect → parse → verify pipeline.

    Args:
        pre_files: File tree for the *before* state.
        post_files: File tree for the *after* state.
        claims_json: A JSON string representing the AI model's claims.

    Returns:
        A tuple ``(detected_changes, parse_result, verification_report)``.
    """
    with tempfile.TemporaryDirectory(prefix="nowreck_val_") as tmpdir:
        pre_root = Path(tmpdir) / "pre"
        post_root = Path(tmpdir) / "post"
        pre_root.mkdir()
        post_root.mkdir()

        _write_tree(pre_root, pre_files)
        _write_tree(post_root, post_files)

        # Scan both states
        pre_scan = RepositoryScanner(pre_root).scan()
        post_scan = RepositoryScanner(post_root).scan()

        # Build symbol indices
        pre_symbols = build_symbol_index(pre_scan)
        post_symbols = build_symbol_index(post_scan)

        # Detect changes
        changes = ChangeDetector.detect(pre_scan, post_scan, pre_symbols, post_symbols)

        # Parse claims
        parse_result = ClaimParser.parse(claims_json)

        # Verify
        report = ClaimVerifier.verify(parse_result.claims, changes)

    return changes, parse_result, report


# ---------------------------------------------------------------------------
# 1. Valid change — all claims match detected changes
# ---------------------------------------------------------------------------


class TestValidChange:
    def test_function_added_is_confirmed(self) -> None:
        pre = {"app.py": "def welcome(): pass\n"}
        post = {"app.py": "def welcome(): pass\n\ndef greet(): pass\n"}
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "greet",
                        "file_path": "app.py",
                        "confidence": 0.95,
                        "explanation": "Added a greeting function.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert len(parse_result.claims) == 1
        assert report.confirmed == 1
        assert report.contradicted == 0
        assert report.unverifiable == 0
        assert report.unexplained_count == 0
        assert report.success is True

    def test_file_created_is_confirmed(self) -> None:
        pre = {"existing.py": "x = 1\n"}
        post = {"existing.py": "x = 1\n", "new.py": "y = 2\n"}
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "FILE_CREATED",
                        "file_path": "new.py",
                        "confidence": 1.0,
                        "explanation": "Created new file.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.confirmed == 1
        assert report.unexplained_count == 0

    def test_multiple_changes_all_confirmed(self) -> None:
        pre = {"app.py": "def old(): pass\n"}
        post = {
            "app.py": "def old(): pass\n\ndef added(): pass\n",
            "helper.py": "def util(): pass\n",
        }
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "added",
                        "file_path": "app.py",
                        "confidence": 0.9,
                    },
                    {
                        "type": "FILE_CREATED",
                        "file_path": "helper.py",
                        "confidence": 1.0,
                    },
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "util",
                        "file_path": "helper.py",
                        "confidence": 0.95,
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert report.confirmed == 3
        assert report.contradicted == 0
        assert report.unverifiable == 0
        assert report.unexplained_count == 0
        assert report.success is True


# ---------------------------------------------------------------------------
# 2. Hallucinated function — claim says ADD_FUNCTION but no change happened
# ---------------------------------------------------------------------------


class TestHallucinatedFunction:
    def test_hallucinated_add_function_is_unverifiable(self) -> None:
        """AI claims a function was added, but nothing changed."""
        pre = {"app.py": "def welcome(): pass\n"}
        post = {"app.py": "def welcome(): pass\n"}  # no changes
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "greet",
                        "file_path": "app.py",
                        "confidence": 0.8,
                        "explanation": "Added a greet function.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.confirmed == 0
        assert report.contradicted == 0
        assert report.unverifiable == 1
        assert report.unexplained_count == 0

    def test_hallucinated_add_function_with_real_change(self) -> None:
        """AI claims a function was added that wasn't, while also
        missing the actual change."""
        pre = {"app.py": "def old(): pass\n"}
        post = {"app.py": "def old(): pass\n\ndef actual(): pass\n"}
        # AI says greet was added, but actual was really added
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "greet",
                        "file_path": "app.py",
                        "confidence": 0.8,
                    },
                ],
            }
        )

        changes, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.confirmed == 0
        assert report.unverifiable == 1
        # The actual change (ADD_FUNCTION actual) is unexplained
        assert report.unexplained_count == 1
        assert report.unexplained_changes[0].symbol_name == "actual"


# ---------------------------------------------------------------------------
# 3. Hallucinated file — claim says FILE_CREATED but no file was created
# ---------------------------------------------------------------------------


class TestHallucinatedFile:
    def test_hallucinated_file_creation_is_unverifiable(self) -> None:
        """AI claims a file was created, but nothing changed."""
        pre = {}
        post = {}  # no changes
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "FILE_CREATED",
                        "file_path": "new.py",
                        "confidence": 0.9,
                        "explanation": "Created a new file.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.confirmed == 0
        assert report.unverifiable == 1
        assert report.unexplained_count == 0

    def test_hallucinated_file_missed_real_file(self) -> None:
        """AI hallucinates a file while missing the real one."""
        pre = {}
        post = {"real.py": "x = 1\n"}
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "FILE_CREATED",
                        "file_path": "imaginary.py",
                        "confidence": 0.9,
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.confirmed == 0
        assert report.unverifiable == 1
        assert report.unexplained_count == 1
        assert report.unexplained_changes[0].file_path == Path("real.py")


# ---------------------------------------------------------------------------
# 4. Wrong explanation — claim type contradicts detected change
# ---------------------------------------------------------------------------


class TestWrongExplanation:
    def test_add_function_claim_but_actually_removed(self) -> None:
        """AI says ADD_FUNCTION, but the function was actually removed."""
        pre = {"app.py": "def old_fn(): pass\n"}
        post = {"app.py": ""}  # old_fn removed
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "old_fn",
                        "file_path": "app.py",
                        "confidence": 0.7,
                        "explanation": "Added old_fn for compatibility.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.confirmed == 0
        assert report.contradicted == 1
        assert report.unverifiable == 0
        assert report.unexplained_count == 0
        # The matched change should be REMOVE_FUNCTION
        assert report.results[0].verdict is Verdict.CONTRADICTED
        assert report.results[0].matched_change is not None
        assert (
            report.results[0].matched_change.change_type is ChangeType.REMOVE_FUNCTION
        )

    def test_file_created_claim_but_actually_deleted(self) -> None:
        """AI says FILE_CREATED, but the file was actually deleted."""
        pre = {"temp.py": "x = 1\n"}
        post = {}
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "FILE_CREATED",
                        "file_path": "temp.py",
                        "confidence": 0.6,
                        "explanation": "Created temp file.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.contradicted == 1
        assert report.results[0].matched_change is not None
        assert report.results[0].matched_change.change_type is ChangeType.FILE_DELETED


# ---------------------------------------------------------------------------
# 5. Missing explanation — AI fails to mention detected changes
# ---------------------------------------------------------------------------


class TestMissingExplanation:
    def test_one_change_missing(self) -> None:
        """Two changes happened, AI only mentions one."""
        pre = {"app.py": "def old(): pass\n"}
        post = {
            "app.py": "def old(): pass\n\ndef a(): pass\n\ndef b(): pass\n",
        }
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "a",
                        "file_path": "app.py",
                        "confidence": 0.95,
                    },
                    # AI forgot to mention 'b'
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success
        assert report.confirmed == 1
        assert report.unverifiable == 0
        assert report.unexplained_count == 1
        assert report.unexplained_changes[0].symbol_name == "b"

    def test_all_changes_missing(self) -> None:
        """Changes happened but AI claims nothing."""
        pre = {"old.py": "x = 1\n"}
        post = {"old.py": "x = 1\n", "new.py": "y = 2\n"}
        claims = json.dumps({"claims": []})  # empty claims

        _, parse_result, report = _run_pipeline(pre, post, claims)
        # Empty claims should fail to parse
        assert parse_result.success is False
        # No claims, so nothing to verify
        assert report.total_claims == 0
        # But changes were detected
        assert report.unexplained_count >= 1


# ---------------------------------------------------------------------------
# 6. Mixed scenario — realistic combination
# ---------------------------------------------------------------------------


class TestMixedScenario:
    def test_mixed_confirmed_unverifiable_unexplained(self) -> None:
        """A realistic mix: some claims correct, some wrong, some missed."""
        pre = {"app.py": "def stable(): pass\n"}
        post = {
            "app.py": "def stable(): pass\n\ndef added(): pass\n",  # added
            "new_file.py": "def helper(): pass\n",  # new file
        }
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "added",
                        "file_path": "app.py",
                        "confidence": 0.95,
                        "explanation": "Added the function.",
                    },
                    {
                        "type": "FILE_CREATED",
                        "file_path": "new_file.py",
                        "confidence": 1.0,
                        "explanation": "Created new file.",
                    },
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "nonexistent",
                        "file_path": "app.py",
                        "confidence": 0.3,
                        "explanation": "Hallucinated function.",
                    },
                    {
                        "type": "REMOVE_FUNCTION",
                        "symbol_name": "stable",
                        "file_path": "app.py",
                        "confidence": 0.5,
                        "explanation": "Says stable was removed, but it wasn't.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        assert parse_result.success

        # added() was really added → CONFIRMED
        # new_file.py was really created → CONFIRMED
        # nonexistent() was not added → UNVERIFIABLE
        # stable() was not removed (no REMOVE_FUNCTION change) → UNVERIFIABLE
        # helper() in new_file.py was added but not claimed → unexplained

        assert report.confirmed == 2
        assert report.unverifiable == 2
        assert report.contradicted == 0
        assert report.unexplained_count >= 1
        # Not all good since there are unverified claims and unexplained
        assert report.success is False


# ---------------------------------------------------------------------------
# 7. Terminal reporter integration — verify it prints without error
# ---------------------------------------------------------------------------


class TestTerminalReporterIntegration:
    def test_reporter_renders_validation_output(self) -> None:
        """Run the full pipeline and verify the terminal reporter
        produces output without errors."""
        pre = {"app.py": "def welcome(): pass\n"}
        post = {"app.py": "def welcome(): pass\n\ndef greet(): pass\n"}
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "greet",
                        "file_path": "app.py",
                        "confidence": 0.95,
                        "explanation": "Greeting function.",
                    },
                ],
            }
        )

        _, parse_result, report = _run_pipeline(pre, post, claims)
        reporter = TerminalReporter(colour=False)
        output = reporter.report(report)
        assert "Nowreck Verification Report" in output
        assert "CONFIRMED" in output
        assert "100%" in output


# ---------------------------------------------------------------------------
# Determinism — same inputs produce same outputs
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_deterministic_pipeline(self) -> None:
        """Running the same pipeline twice produces identical
        results."""
        pre = {"app.py": "def old(): pass\n"}
        post = {"app.py": "def old(): pass\n\ndef new(): pass\n"}
        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "new",
                        "file_path": "app.py",
                        "confidence": 0.9,
                    },
                ],
            }
        )

        _, _, report1 = _run_pipeline(pre, post, claims)
        _, _, report2 = _run_pipeline(pre, post, claims)

        assert report1.results == report2.results
        assert report1.unexplained_changes == report2.unexplained_changes
        assert report1.confirmed == report2.confirmed
        assert report1.unexplained_count == report2.unexplained_count
        assert report1.success == report2.success
