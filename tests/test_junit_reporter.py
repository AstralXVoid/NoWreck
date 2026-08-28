"""Tests for the JUnit XML reporter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange
from nowreck.reporter.junit_reporter import (
    JUnitReporter,
    _get_evidence_text,
    _get_failure_message,
)
from nowreck.verifier.verifier import (
    Verdict,
    VerificationReport,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_claim(
    claim_type: ClaimType = ClaimType.ADD_FUNCTION,
    symbol_name: str | None = "my_func",
    file_path: str = "app.py",
    caller_name: str | None = None,
    called_name: str | None = None,
) -> Claim:
    return Claim(
        type=claim_type,
        symbol_name=symbol_name,
        file_path=file_path,
        caller_name=caller_name,
        called_name=called_name,
    )


def _make_change(
    change_type: ChangeType = ChangeType.ADD_FUNCTION,
    symbol_name: str | None = "my_func",
    file_path: str = "app.py",
    line_number: int | None = 10,
) -> DetectedChange:
    return DetectedChange(
        change_type=change_type,
        symbol_name=symbol_name,
        file_path=Path(file_path),
        line_number=line_number,
    )


def _parse_xml(xml_str: str) -> ET.Element:
    """Parse XML string, stripping the declaration."""
    # Remove XML declaration if present
    if xml_str.startswith("<?xml"):
        xml_str = xml_str[xml_str.index("?>") + 2 :]
    return ET.fromstring(xml_str.strip())


# ---------------------------------------------------------------------------
# JUnitReporter
# ---------------------------------------------------------------------------


class TestJUnitReporter:
    """Test the JUnitReporter class."""

    def test_basic_output_structure(self) -> None:
        """Should produce valid JUnit structure."""
        reporter = JUnitReporter()
        report = VerificationReport(results=[])
        output = reporter.report(report)
        root = _parse_xml(output)

        assert root.tag == "testsuites"
        assert root.get("name") == "nowreck"
        assert root.get("tests") == "0"
        assert root.get("failures") == "0"

    def test_confirmed_is_pass(self) -> None:
        """CONFIRMED results should have no failure element."""
        reporter = JUnitReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        change = _make_change(ChangeType.ADD_FUNCTION)
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONFIRMED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        root = _parse_xml(output)
        testsuite = root.find("testsuite")
        assert testsuite is not None
        testcase = testsuite.find("testcase")
        assert testcase is not None

        # No failure element
        assert testcase.find("failure") is None
        # Test counts
        assert root.get("tests") == "1"
        assert root.get("failures") == "0"

    def test_contradicted_is_failure(self) -> None:
        """CONTRADICTED results should have a failure element."""
        reporter = JUnitReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        change = _make_change(ChangeType.REMOVE_FUNCTION)
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONTRADICTED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        root = _parse_xml(output)
        testsuite = root.find("testsuite")
        assert testsuite is not None
        testcase = testsuite.find("testcase")
        assert testcase is not None

        failure = testcase.find("failure")
        assert failure is not None
        assert failure.get("type") == "CONTRADICTED"
        assert failure.get("message") is not None
        # Test counts
        assert root.get("tests") == "1"
        assert root.get("failures") == "1"

    def test_unverifiable_is_failure(self) -> None:
        """UNVERIFIABLE results should have a failure element."""
        reporter = JUnitReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        result = VerificationResult(claim=claim, verdict=Verdict.UNVERIFIABLE)
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        root = _parse_xml(output)
        testsuite = root.find("testsuite")
        assert testsuite is not None
        testcase = testsuite.find("testcase")
        assert testcase is not None

        failure = testcase.find("failure")
        assert failure is not None
        assert failure.get("type") == "UNVERIFIABLE"

    def test_testcase_name_format(self) -> None:
        """Testcase name should be 'CLAIM_TYPE symbol_name'."""
        reporter = JUnitReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION, symbol_name="validate_email")
        result = VerificationResult(claim=claim, verdict=Verdict.CONFIRMED)
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        root = _parse_xml(output)
        testcase = root.find("testsuite/testcase")
        assert testcase is not None
        assert testcase.get("name") == "ADD_FUNCTION validate_email"

    def test_testcase_classname_is_file_path(self) -> None:
        """Testcase classname should be the full file path."""
        reporter = JUnitReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION, file_path="src/auth.py")
        result = VerificationResult(claim=claim, verdict=Verdict.CONFIRMED)
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        root = _parse_xml(output)
        testcase = root.find("testsuite/testcase")
        assert testcase is not None
        assert testcase.get("classname") == "src/auth.py"

    def test_multiple_results(self) -> None:
        """Should handle multiple results correctly."""
        reporter = JUnitReporter()
        results = [
            VerificationResult(
                claim=_make_claim(ClaimType.ADD_FUNCTION),
                verdict=Verdict.CONFIRMED,
            ),
            VerificationResult(
                claim=_make_claim(ClaimType.ADD_CLASS),
                verdict=Verdict.CONTRADICTED,
            ),
            VerificationResult(
                claim=_make_claim(ClaimType.FILE_CREATED),
                verdict=Verdict.UNVERIFIABLE,
            ),
        ]
        report = VerificationReport(results=results)

        output = reporter.report(report)
        root = _parse_xml(output)

        assert root.get("tests") == "3"
        assert root.get("failures") == "2"  # CONTRADICTED + UNVERIFIABLE

    def test_calls_function_failure_message(self) -> None:
        """CALLS_FUNCTION failure should mention caller and called."""
        reporter = JUnitReporter()
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            caller_name="foo",
            called_name="bar",
        )
        result = VerificationResult(claim=claim, verdict=Verdict.CONTRADICTED)
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        root = _parse_xml(output)
        failure = root.find("testsuite/testcase/failure")
        assert failure is not None
        message = failure.get("message", "")
        assert "foo" in message
        assert "bar" in message

    def test_report_dict_returns_dict(self) -> None:
        """report_dict should return a dict."""
        reporter = JUnitReporter()
        report = VerificationReport(results=[])
        result = reporter.report_dict(report)

        assert isinstance(result, dict)
        assert "testsuites" in result
        assert result["testsuites"]["name"] == "nowreck"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestGetFailureMessage:
    """Test the _get_failure_message helper."""

    def test_basic_claim(self) -> None:
        claim = _make_claim(ClaimType.ADD_FUNCTION, symbol_name="my_func")
        result = VerificationResult(claim=claim, verdict=Verdict.CONTRADICTED)
        msg = _get_failure_message(result)
        assert "ADD_FUNCTION" in msg
        assert "my_func" in msg

    def test_calls_function_claim(self) -> None:
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            caller_name="foo",
            called_name="bar",
        )
        result = VerificationResult(claim=claim, verdict=Verdict.CONTRADICTED)
        msg = _get_failure_message(result)
        assert "foo" in msg
        assert "bar" in msg


class TestGetEvidenceText:
    """Test the _get_evidence_text helper."""

    def test_with_matched_change(self) -> None:
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        change = _make_change(ChangeType.ADD_FUNCTION)
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONTRADICTED, matched_change=change
        )
        text = _get_evidence_text(result)
        assert "Matched change" in text

    def test_without_matched_change(self) -> None:
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        result = VerificationResult(claim=claim, verdict=Verdict.UNVERIFIABLE)
        text = _get_evidence_text(result)
        assert "No matching" in text
