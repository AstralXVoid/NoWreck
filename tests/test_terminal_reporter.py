from __future__ import annotations

import json
import re
from pathlib import Path

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.verifier.verifier import (
    Verdict,
    VerificationReport,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claim(
    claim_type: ClaimType,
    file_path: str = "app.py",
    symbol_name: str | None = None,
    parent_class: str | None = None,
    caller_name: str | None = None,
    called_name: str | None = None,
    confidence: float = 1.0,
) -> Claim:
    """Factory for quickly building a Claim."""
    kwargs: dict = {
        "type": claim_type,
        "file_path": file_path,
        "confidence": confidence,
    }
    if symbol_name is not None:
        kwargs["symbol_name"] = symbol_name
    if parent_class is not None:
        kwargs["parent_class"] = parent_class
    if caller_name is not None:
        kwargs["caller_name"] = caller_name
    if called_name is not None:
        kwargs["called_name"] = called_name
    return Claim(**kwargs)


def _make_change(
    change_type: ChangeType,
    file_path: str = "app.py",
    symbol_name: str | None = None,
    parent_class: str | None = None,
    caller_name: str | None = None,
    called_name: str | None = None,
    line_number: int | None = None,
) -> DetectedChange:
    """Factory for quickly building a DetectedChange."""
    return DetectedChange(
        change_type=change_type,
        file_path=Path(file_path),
        symbol_name=symbol_name,
        parent_class=parent_class,
        caller_name=caller_name,
        called_name=called_name,
        line_number=line_number,
    )


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for assertion readability."""
    return re.sub(r"\033\[[0-9;]*m", "", text)


# ---------------------------------------------------------------------------
# TerminalReporter — basic output structure
# ---------------------------------------------------------------------------


class TestReporterBasicStructure:
    def test_empty_report(self) -> None:
        report = VerificationReport()
        reporter = TerminalReporter(colour=False)
        output = reporter.report(report)
        assert "Nowreck Verification Report" in output
        assert "Summary" in output
        assert "0 claims total" in output
        assert "0 confirmed" in output

    def test_header_present(self) -> None:
        report = VerificationReport()
        reporter = TerminalReporter(colour=False)
        output = reporter.report(report)
        assert "═══════════════════════════════════════════════════" in output
        assert "Nowreck Verification Report" in output

    def test_summary_line(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(
            results=[vr],
        )
        reporter = TerminalReporter(colour=False)
        output = reporter.report(vreport)
        assert "1 claim total" in output
        assert "1 confirmed" in output

    def test_summary_with_contradicted(self) -> None:
        c = _make_claim(ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="foo")
        dc = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        vr = VerificationResult(
            claim=c, verdict=Verdict.CONTRADICTED, matched_change=dc
        )
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = reporter.report(vreport)
        assert "1 contradicted" in output

    def test_summary_with_unverifiable(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        vr = VerificationResult(claim=c, verdict=Verdict.UNVERIFIABLE)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = reporter.report(vreport)
        assert "1 unverifiable" in output

    def test_summary_with_unexplained(self) -> None:
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        vreport = VerificationReport(unexplained_changes=[dc])
        reporter = TerminalReporter(colour=False)
        output = reporter.report(vreport)
        assert "1 unexplained change" in output


# ---------------------------------------------------------------------------
# TerminalReporter — CONFIRMED section
# ---------------------------------------------------------------------------


class TestReporterConfirmed:
    def test_file_created_confirmed_line(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "CONFIRMED" in output
        assert "FILE_CREATED" in output

    def test_add_function_evidence(self) -> None:
        c = _make_claim(
            ClaimType.ADD_FUNCTION,
            file_path="app.py",
            symbol_name="greet",
            confidence=0.95,
        )
        dc = _make_change(
            ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="greet"
        )
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "Evidence:" in output
        assert "Function 'greet' was added" in output
        assert "app.py" in output
        # Deterministic structural findings show 100% confidence
        assert "100%" in output

    def test_file_created_evidence(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "File 'new.py' was created" in output

    def test_add_class_evidence(self) -> None:
        c = _make_claim(ClaimType.ADD_CLASS, file_path="models.py", symbol_name="User")
        dc = _make_change(
            ChangeType.ADD_CLASS, file_path="models.py", symbol_name="User"
        )
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "Class 'User' was added" in output

    def test_calls_function_evidence(self) -> None:
        c = _make_claim(
            ClaimType.CALLS_FUNCTION,
            file_path="app.py",
            symbol_name="run",
            caller_name="main",
            called_name="run",
        )
        dc = _make_change(
            ChangeType.CALL_DETECTED,
            file_path="app.py",
            caller_name="main",
            called_name="run",
        )
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "main" in output
        assert "run" in output


# ---------------------------------------------------------------------------
# TerminalReporter — CONTRADICTED section
# ---------------------------------------------------------------------------


class TestReporterContradicted:
    def test_contradicted_section_present(self) -> None:
        c = _make_claim(ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="foo")
        dc = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        vr = VerificationResult(
            claim=c, verdict=Verdict.CONTRADICTED, matched_change=dc
        )
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "CONTRADICTED" in output
        assert "was removed" in output


# ---------------------------------------------------------------------------
# TerminalReporter — UNVERIFIABLE section
# ---------------------------------------------------------------------------


class TestReporterUnverifiable:
    def test_unverifiable_section_present(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        vr = VerificationResult(claim=c, verdict=Verdict.UNVERIFIABLE)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "UNVERIFIABLE" in output
        assert "No matching change detected" in output


# ---------------------------------------------------------------------------
# TerminalReporter — UNEXPLAINED CHANGES section
# ---------------------------------------------------------------------------


class TestReporterUnexplained:
    def test_unexplained_section_present(self) -> None:
        dc = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="old_fn"
        )
        vreport = VerificationReport(unexplained_changes=[dc])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "UNEXPLAINED CHANGES" in output
        assert "REMOVE_FUNCTION" in output
        assert "old_fn" in output

    def test_unexplained_call_change(self) -> None:
        dc = _make_change(
            ChangeType.CALL_DETECTED,
            file_path="app.py",
            caller_name="main",
            called_name="print",
        )
        vreport = VerificationReport(unexplained_changes=[dc])
        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(vreport))
        assert "main → print" in output


# ---------------------------------------------------------------------------
# TerminalReporter — colour mode
# ---------------------------------------------------------------------------


class TestReporterColour:
    def test_colour_on_contains_ansi(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=True)
        output = reporter.report(vreport)
        assert "\033[" in output

    def test_colour_off_contains_no_ansi(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        vr = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        vreport = VerificationReport(results=[vr])
        reporter = TerminalReporter(colour=False)
        output = reporter.report(vreport)
        assert "\033[" not in output


# ---------------------------------------------------------------------------
# TerminalReporter — confidence formatting
# ---------------------------------------------------------------------------


class TestReporterConfidence:
    def test_confidence_formats_percent(self) -> None:
        assert TerminalReporter._format_confidence(1.0) == "100%"
        assert TerminalReporter._format_confidence(0.5) == " 50%"
        assert TerminalReporter._format_confidence(0.0) == "  0%"
        assert TerminalReporter._format_confidence(0.75) == " 75%"
        assert TerminalReporter._format_confidence(0.999) == "100%"


# ---------------------------------------------------------------------------
# TerminalReporter — claim description
# ---------------------------------------------------------------------------


class TestReporterClaimDescription:
    def test_file_created_description(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        desc = TerminalReporter._describe_claim(c)
        assert "FILE_CREATED" in desc
        assert "new.py" in desc

    def test_add_function_no_parent_class(self) -> None:
        c = _make_claim(ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="greet")
        desc = TerminalReporter._describe_claim(c)
        assert "ADD_FUNCTION greet → app.py" in desc

    def test_add_function_with_line_number(self) -> None:
        c = Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="greet",
            file_path="app.py",
            line_number=10,
        )
        desc = TerminalReporter._describe_claim(c)
        assert "app.py:10" in desc

    def test_calls_function_description(self) -> None:
        c = _make_claim(
            ClaimType.CALLS_FUNCTION,
            file_path="app.py",
            symbol_name="run",
            caller_name="main",
            called_name="run",
        )
        desc = TerminalReporter._describe_claim(c)
        assert "CALLS_FUNCTION" in desc
        assert "app.py" in desc


# ---------------------------------------------------------------------------
# TerminalReporter — evidence description
# ---------------------------------------------------------------------------


class TestReporterEvidence:
    def test_remove_function_evidence(self) -> None:
        dc = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="old_fn"
        )
        evidence = TerminalReporter._describe_evidence(dc)
        assert "removed" in evidence
        assert "old_fn" in evidence

    def test_remove_class_evidence(self) -> None:
        dc = _make_change(
            ChangeType.REMOVE_CLASS, file_path="models.py", symbol_name="OldModel"
        )
        evidence = TerminalReporter._describe_evidence(dc)
        assert "removed" in evidence
        assert "OldModel" in evidence

    def test_file_deleted_evidence(self) -> None:
        dc = _make_change(ChangeType.FILE_DELETED, file_path="old.py")
        evidence = TerminalReporter._describe_evidence(dc)
        assert "deleted" in evidence

    def test_add_function_with_parent_class_evidence(self) -> None:
        dc = _make_change(
            ChangeType.ADD_FUNCTION,
            file_path="widget.py",
            symbol_name="render",
            parent_class="Widget",
        )
        evidence = TerminalReporter._describe_evidence(dc)
        assert "added" in evidence
        assert "Widget" in evidence

    def test_contradicted_evidence(self) -> None:
        """Contradicted evidence still describes the actual change."""
        dc = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        evidence = TerminalReporter._describe_evidence(dc)
        assert "removed" in evidence


# ---------------------------------------------------------------------------
# TerminalReporter — full integration scenario
# ---------------------------------------------------------------------------


class TestReporterIntegration:
    def test_mixed_report(self) -> None:
        """A report with all four outcome types produces all sections."""
        confirmed_claim = _make_claim(
            ClaimType.ADD_FUNCTION,
            file_path="app.py",
            symbol_name="greet",
            confidence=0.95,
        )
        confirmed_change = _make_change(
            ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="greet"
        )
        contradicted_claim = _make_claim(
            ClaimType.ADD_FUNCTION,
            file_path="app.py",
            symbol_name="foo",
            confidence=0.80,
        )
        contradicted_change = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        unverifiable_claim = _make_claim(
            ClaimType.FILE_CREATED, file_path="missing.py", confidence=0.60
        )
        unexplained = _make_change(ChangeType.FILE_CREATED, file_path="unexpected.py")

        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=confirmed_claim,
                    verdict=Verdict.CONFIRMED,
                    matched_change=confirmed_change,
                ),
                VerificationResult(
                    claim=contradicted_claim,
                    verdict=Verdict.CONTRADICTED,
                    matched_change=contradicted_change,
                ),
                VerificationResult(
                    claim=unverifiable_claim,
                    verdict=Verdict.UNVERIFIABLE,
                ),
            ],
            unexplained_changes=[unexplained],
        )

        reporter = TerminalReporter(colour=False)
        output = _strip_ansi(reporter.report(report))

        # All sections present
        assert "CONFIRMED" in output
        assert "CONTRADICTED" in output
        assert "UNVERIFIABLE" in output
        assert "UNEXPLAINED CHANGES" in output

        # Summary counts
        assert "3 claims total" in output
        assert "1 confirmed" in output
        assert "1 contradicted" in output
        assert "1 unverifiable" in output
        assert "1 unexplained change" in output

        # Evidence — deterministic CONFIRMED shows 100%
        assert "Evidence:" in output
        assert "100%" in output

    def test_deterministic_output(self) -> None:
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        change = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=claim, verdict=Verdict.CONFIRMED, matched_change=change
                )
            ],
        )
        reporter = TerminalReporter(colour=False)
        r1 = reporter.report(report)
        r2 = reporter.report(report)
        assert r1 == r2


# ---------------------------------------------------------------------------
# TerminalReporter — JSON output
# ---------------------------------------------------------------------------


class TestReporterJson:
    def test_json_empty_report(self) -> None:
        report = VerificationReport()
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        assert data["success"] is True
        assert data["summary"]["total_claims"] == 0
        assert data["results"] == []
        assert data["unexplained_changes"] == []

    def test_json_summary_counts(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=c, verdict=Verdict.CONFIRMED, matched_change=dc
                ),
                VerificationResult(
                    claim=c, verdict=Verdict.CONTRADICTED, matched_change=dc
                ),
                VerificationResult(claim=c, verdict=Verdict.UNVERIFIABLE),
            ],
            unexplained_changes=[dc],
        )
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        assert data["summary"]["total_claims"] == 3
        assert data["summary"]["confirmed"] == 1
        assert data["summary"]["contradicted"] == 1
        assert data["summary"]["unverifiable"] == 1
        assert data["summary"]["unexplained_count"] == 1

    def test_json_result_verdicts(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=c, verdict=Verdict.CONFIRMED, matched_change=dc
                ),
            ],
        )
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        assert data["results"][0]["verdict"] == "CONFIRMED"

    def test_json_claim_fields(self) -> None:
        c = Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="greet",
            file_path="app.py",
            parent_class=None,
            line_number=10,
            confidence=0.95,
        )
        dc = _make_change(
            ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="greet"
        )
        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=c, verdict=Verdict.CONFIRMED, matched_change=dc
                ),
            ],
        )
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        result = data["results"][0]
        claim = result["claim"]
        assert claim["type"] == "ADD_FUNCTION"
        assert claim["symbol_name"] == "greet"
        assert claim["file_path"] == "app.py"
        assert claim["line_number"] == 10
        # Raw model confidence preserved in claim dict
        assert claim["confidence"] == 0.95
        # Verifier confidence overrides for deterministic findings
        assert result["verifier_confidence"] == 1.0

    def test_json_unexplained_change_fields(self) -> None:
        dc = _make_change(
            ChangeType.ADD_FUNCTION,
            file_path="app.py",
            symbol_name="foo",
            parent_class=None,
            line_number=5,
        )
        report = VerificationReport(unexplained_changes=[dc])
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        change = data["unexplained_changes"][0]
        assert change["change_type"] == "ADD_FUNCTION"
        assert change["file_path"] == "app.py"
        assert change["symbol_name"] == "foo"
        assert change["line_number"] == 5

    def test_json_matched_change_included(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=c, verdict=Verdict.CONFIRMED, matched_change=dc
                ),
            ],
        )
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        assert "matched_change" in data["results"][0]
        assert data["results"][0]["matched_change"]["change_type"] == "FILE_CREATED"

    def test_json_success_propagation(self) -> None:
        clean = VerificationReport(
            results=[
                VerificationResult(
                    claim=_make_claim(ClaimType.FILE_CREATED, file_path="new.py"),
                    verdict=Verdict.CONFIRMED,
                ),
            ],
        )
        data_clean = json.loads(TerminalReporter.report_json(clean))
        assert data_clean["success"] is True

        dirty = VerificationReport(
            results=[
                VerificationResult(
                    claim=_make_claim(ClaimType.FILE_CREATED, file_path="new.py"),
                    verdict=Verdict.UNVERIFIABLE,
                ),
            ],
        )
        data_dirty = json.loads(TerminalReporter.report_json(dirty))
        assert data_dirty["success"] is False

    def test_json_serialization_safe(self) -> None:
        """JSON output should be valid JSON without any custom
        serializers (Path → str conversion built in)."""
        dc = _make_change(ChangeType.FILE_CREATED, file_path="some/path.py")
        report = VerificationReport(unexplained_changes=[dc])
        output = TerminalReporter.report_json(report)
        # Should be parseable without error
        data = json.loads(output)
        assert data["unexplained_changes"][0]["file_path"] == "some/path.py"

    def test_deterministic_json_output(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        dc = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=c, verdict=Verdict.CONFIRMED, matched_change=dc
                ),
            ],
        )
        r1 = TerminalReporter.report_json(report)
        r2 = TerminalReporter.report_json(report)
        assert r1 == r2

    def test_json_verifier_confidence_contradicted(self) -> None:
        """CONTRADICTED results should have verifier_confidence: 1.0."""
        c = _make_claim(
            ClaimType.ADD_FUNCTION,
            file_path="app.py",
            symbol_name="foo",
            confidence=0.3,
        )
        dc = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        report = VerificationReport(
            results=[
                VerificationResult(
                    claim=c, verdict=Verdict.CONTRADICTED, matched_change=dc
                ),
            ],
        )
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        result = data["results"][0]
        assert result["verdict"] == "CONTRADICTED"
        # Raw model confidence preserved
        assert result["claim"]["confidence"] == 0.3
        # Verifier confidence is 100% for deterministic findings
        assert result["verifier_confidence"] == 1.0

    def test_json_verifier_confidence_unverifiable(self) -> None:
        """UNVERIFIABLE results should preserve the model's original
        confidence in verifier_confidence."""
        c = _make_claim(
            ClaimType.FILE_CREATED,
            file_path="missing.py",
            confidence=0.6,
        )
        report = VerificationReport(
            results=[
                VerificationResult(claim=c, verdict=Verdict.UNVERIFIABLE),
            ],
        )
        output = TerminalReporter.report_json(report)
        data = json.loads(output)
        result = data["results"][0]
        assert result["verdict"] == "UNVERIFIABLE"
        # Model confidence preserved in both fields for UNVERIFIABLE
        assert result["claim"]["confidence"] == 0.6
        assert result["verifier_confidence"] == 0.6
