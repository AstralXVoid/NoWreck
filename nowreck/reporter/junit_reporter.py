"""JUnit XML output reporter for NoWreck verification results.

Produces JUnit XML format compatible with Jenkins, GitLab CI,
and Azure Pipelines test reports.

Verdict mapping:
- CONFIRMED → pass (no element)
- CONTRADICTED → <failure>
- UNVERIFIABLE → <failure type="UNVERIFIABLE">
- UNEXPLAINED → excluded (not a claim)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from nowreck.verifier.verifier import Verdict, VerificationReport, VerificationResult


class JUnitReporter:
    """Produces JUnit XML output from a VerificationReport.

    Verdict → JUnit status:
    - CONFIRMED → pass (no element)
    - CONTRADICTED → <failure>
    - UNVERIFIABLE → <failure type="UNVERIFIABLE">
    - UNEXPLAINED → excluded (not a claim)
    """

    def report(self, verification_report: VerificationReport) -> str:
        """Render the verification report as JUnit XML.

        Args:
            verification_report: The verification report to render.

        Returns:
            An XML string in JUnit format.
        """
        testsuites = self._build_testsuites(verification_report)
        return ET.tostring(testsuites, encoding="unicode", xml_declaration=True)

    def report_dict(self, verification_report: VerificationReport) -> dict[str, Any]:
        """Render the verification report as a JUnit-like dict.

        Useful for testing and debugging without XML serialization.

        Args:
            verification_report: The verification report to render.

        Returns:
            A dict with testsuites/testsuite/testcase structure.
        """
        failures = sum(
            1
            for r in verification_report.results
            if r.verdict in (Verdict.CONTRADICTED, Verdict.UNVERIFIABLE)
        )
        tests = len(verification_report.results)

        testcases: list[dict[str, Any]] = []
        for result in verification_report.results:
            testcases.append(self._result_to_dict(result))

        return {
            "testsuites": {
                "name": "nowreck",
                "tests": tests,
                "failures": failures,
                "errors": 0,
                "testsuite": {
                    "name": "verification",
                    "tests": tests,
                    "failures": failures,
                    "testcases": testcases,
                },
            }
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_testsuites(self, report: VerificationReport) -> ET.Element:
        """Build the complete JUnit XML structure."""
        tests = len(report.results)
        failures = sum(
            1
            for r in report.results
            if r.verdict in (Verdict.CONTRADICTED, Verdict.UNVERIFIABLE)
        )
        errors = 0

        testsuites = ET.Element("testsuites")
        testsuites.set("name", "nowreck")
        testsuites.set("tests", str(tests))
        testsuites.set("failures", str(failures))
        testsuites.set("errors", str(errors))

        testsuite = ET.SubElement(testsuites, "testsuite")
        testsuite.set("name", "verification")
        testsuite.set("tests", str(tests))
        testsuite.set("failures", str(failures))

        for result in report.results:
            testcase = self._build_testcase(result)
            testsuite.append(testcase)

        return testsuites

    def _build_testcase(self, result: VerificationResult) -> ET.Element:
        """Build a single JUnit testcase element."""
        # Build testcase name: "CLAIM_TYPE symbol_name"
        name_parts = [result.claim.type.name]
        if result.claim.symbol_name:
            name_parts.append(result.claim.symbol_name)
        name = " ".join(name_parts)

        testcase = ET.Element("testcase")
        testcase.set("name", name)
        testcase.set("classname", result.claim.file_path)

        if result.verdict is Verdict.CONTRADICTED:
            failure = ET.SubElement(testcase, "failure")
            failure.set("type", "CONTRADICTED")
            failure.set("message", f"Contradicted: {_get_failure_message(result)}")
            failure.text = _get_evidence_text(result)

        elif result.verdict is Verdict.UNVERIFIABLE:
            failure = ET.SubElement(testcase, "failure")
            failure.set("type", "UNVERIFIABLE")
            failure.set("message", f"Unverifiable: {_get_failure_message(result)}")
            failure.text = _get_evidence_text(result)

        # CONFIRMED → no element (pass)

        return testcase

    @staticmethod
    def _result_to_dict(result: VerificationResult) -> dict[str, Any]:
        """Convert a VerificationResult to a dict."""
        name_parts = [result.claim.type.name]
        if result.claim.symbol_name:
            name_parts.append(result.claim.symbol_name)
        name = " ".join(name_parts)

        testcase: dict[str, Any] = {
            "name": name,
            "classname": result.claim.file_path,
        }

        if result.verdict is Verdict.CONTRADICTED:
            testcase["failure"] = {
                "type": "CONTRADICTED",
                "message": f"Contradicted: {_get_failure_message(result)}",
                "text": _get_evidence_text(result),
            }
        elif result.verdict is Verdict.UNVERIFIABLE:
            testcase["failure"] = {
                "type": "UNVERIFIABLE",
                "message": f"Unverifiable: {_get_failure_message(result)}",
                "text": _get_evidence_text(result),
            }

        return testcase


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_failure_message(result: VerificationResult) -> str:
    """Get a human-readable failure message."""
    claim = result.claim
    if claim.type.name == "CALLS_FUNCTION":
        return (
            f"AI claimed '{claim.caller_name}' calls "
            f"'{claim.called_name}' but no such call exists "
            f"in {claim.file_path}"
        )
    return (
        f"AI claimed {claim.type.name} for "
        f"'{claim.symbol_name}' but no matching structural "
        f"evidence found in {claim.file_path}"
    )


def _get_evidence_text(result: VerificationResult) -> str:
    """Get the evidence text for a failure."""
    if result.matched_change is not None:
        return f"Matched change: {result.matched_change}"
    return "No matching structural evidence found"
