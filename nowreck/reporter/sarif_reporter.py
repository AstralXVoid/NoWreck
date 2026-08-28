"""SARIF v2.1.0 output reporter for NoWreck verification results.

Produces Static Analysis Results Interchange Format (SARIF) output
compatible with GitHub Code Scanning, SonarQube, and CodeQL.

CONFIRMED results are excluded by default — SARIF is designed for
reporting problems, not successes.
"""

from __future__ import annotations

import json
from typing import Any

from nowreck import __version__
from nowreck.detector.change_detector import DetectedChange
from nowreck.verifier.verifier import Verdict, VerificationReport, VerificationResult

# ---------------------------------------------------------------------------
# SARIF rule definitions — one per claim type (CONTRADICTED) plus
# UNVERIFIABLE and UNEXPLAINED.
# ---------------------------------------------------------------------------

_SARIF_RULES: list[dict[str, Any]] = [
    {
        "id": "NW001",
        "name": "HallucinatedFunction",
        "shortDescription": {
            "text": "AI claimed a function was added but it doesn't exist"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW002",
        "name": "HallucinatedRemoveFunction",
        "shortDescription": {
            "text": "AI claimed a function was removed but it still exists"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW003",
        "name": "HallucinatedClass",
        "shortDescription": {
            "text": "AI claimed a class was added but it doesn't exist"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW004",
        "name": "HallucinatedRemoveClass",
        "shortDescription": {
            "text": "AI claimed a class was removed but it still exists"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW005",
        "name": "HallucinatedInterface",
        "shortDescription": {
            "text": "AI claimed an interface was added but it doesn't exist"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW006",
        "name": "HallucinatedRemoveInterface",
        "shortDescription": {
            "text": "AI claimed an interface was removed but it still exists"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW007",
        "name": "HallucinatedEnum",
        "shortDescription": {
            "text": "AI claimed an enum was added but it doesn't exist"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW008",
        "name": "HallucinatedRemoveEnum",
        "shortDescription": {
            "text": "AI claimed an enum was removed but it still exists"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW009",
        "name": "HallucinatedTypeAlias",
        "shortDescription": {
            "text": "AI claimed a type alias was added but it doesn't exist"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW010",
        "name": "HallucinatedRemoveTypeAlias",
        "shortDescription": {
            "text": "AI claimed a type alias was removed but it still exists"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW011",
        "name": "HallucinatedFileCreated",
        "shortDescription": {
            "text": "AI claimed a file was created but it doesn't exist"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW012",
        "name": "HallucinatedFileDeleted",
        "shortDescription": {
            "text": "AI claimed a file was deleted but it still exists"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW013",
        "name": "FakeApiCall",
        "shortDescription": {
            "text": "AI claimed a function calls another but no call exists"
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "NW014",
        "name": "UnverifiedClaim",
        "shortDescription": {
            "text": "AI claim could not be verified against structural evidence"
        },
        "defaultConfiguration": {"level": "warning"},
    },
    {
        "id": "NW015",
        "name": "UnexplainedChange",
        "shortDescription": {
            "text": "Structural change detected with no matching claim"
        },
        "defaultConfiguration": {"level": "note"},
    },
]

# Build lookup: rule index by rule ID
_RULE_INDEX: dict[str, int] = {r["id"]: i for i, r in enumerate(_SARIF_RULES)}

# Build lookup: rule ID by claim type name (for CONTRADICTED claims)
_CLAIM_TYPE_TO_RULE: dict[str, str] = {
    "ADD_FUNCTION": "NW001",
    "REMOVE_FUNCTION": "NW002",
    "ADD_CLASS": "NW003",
    "REMOVE_CLASS": "NW004",
    "ADD_INTERFACE": "NW005",
    "REMOVE_INTERFACE": "NW006",
    "ADD_ENUM": "NW007",
    "REMOVE_ENUM": "NW008",
    "ADD_TYPE_ALIAS": "NW009",
    "REMOVE_TYPE_ALIAS": "NW010",
    "FILE_CREATED": "NW011",
    "FILE_DELETED": "NW012",
    "CALLS_FUNCTION": "NW013",
}


class SarifReporter:
    """Produces SARIF v2.1.0 output from a VerificationReport.

    CONFIRMED results are excluded by default — SARIF is designed for
    reporting problems, not successes.
    """

    def __init__(self, include_confirmed: bool = False) -> None:
        """Initialize the SARIF reporter.

        Args:
            include_confirmed: If True, include CONFIRMED results in output.
                Default False — SARIF is for problems, not successes.
        """
        self._include_confirmed = include_confirmed

    def report(self, verification_report: VerificationReport) -> str:
        """Render the verification report as a SARIF JSON string.

        Args:
            verification_report: The verification report to render.

        Returns:
            A JSON string in SARIF v2.1.0 format.
        """
        sarif = self._build_sarif(verification_report)
        return json.dumps(sarif, indent=2, default=str)

    def report_dict(self, verification_report: VerificationReport) -> dict[str, Any]:
        """Render the verification report as a SARIF dict.

        Args:
            verification_report: The verification report to render.

        Returns:
            A dict in SARIF v2.1.0 format.
        """
        return self._build_sarif(verification_report)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_sarif(self, report: VerificationReport) -> dict[str, Any]:
        """Build the complete SARIF structure."""
        results = self._build_results(report)
        run: dict[str, Any] = {
            "tool": self._build_tool(),
            "results": results,
        }
        return {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [run],
        }

    @staticmethod
    def _build_tool() -> dict[str, Any]:
        """Build the SARIF tool section."""
        return {
            "driver": {
                "name": "nowreck",
                "version": __version__,
                "informationUri": "https://github.com/AstralXVoid/NoWreck",
                "rules": list(_SARIF_RULES),
            }
        }

    def _build_results(self, report: VerificationReport) -> list[dict[str, Any]]:
        """Build the SARIF results array."""
        results: list[dict[str, Any]] = []

        # Process claim verification results
        for result in report.results:
            sarif_result = self._result_to_sarif(result)
            if sarif_result is not None:
                results.append(sarif_result)

        # Process unexplained changes
        for change in report.unexplained_changes:
            results.append(self._unexplained_to_sarif(change))

        return results

    def _result_to_sarif(self, result: VerificationResult) -> dict[str, Any] | None:
        """Convert a VerificationResult to a SARIF result.

        Returns None for CONFIRMED results (excluded by default).
        """
        if result.verdict is Verdict.CONFIRMED and not self._include_confirmed:
            return None

        rule_id = self._get_rule_id(result)
        level = self._get_level(result)
        message = self._get_message(result)
        locations = self._get_locations(result)

        sarif_result: dict[str, Any] = {
            "ruleId": rule_id,
            "ruleIndex": _RULE_INDEX[rule_id],
            "level": level,
            "message": {"text": message},
        }

        if locations:
            sarif_result["locations"] = locations

        return sarif_result

    @staticmethod
    def _unexplained_to_sarif(change: DetectedChange) -> dict[str, Any]:
        """Convert an unexplained DetectedChange to a SARIF result."""
        rule_id = "NW015"
        message = _describe_change(change)
        locations = _change_to_locations(change)

        return {
            "ruleId": rule_id,
            "ruleIndex": _RULE_INDEX[rule_id],
            "level": "note",
            "message": {"text": message},
            "locations": locations if locations else [],
        }

    @staticmethod
    def _get_rule_id(result: VerificationResult) -> str:
        """Get the SARIF rule ID for a verification result."""
        if result.verdict is Verdict.UNVERIFIABLE:
            return "NW014"

        # CONTRADICTED — map claim type to specific rule
        return _CLAIM_TYPE_TO_RULE.get(result.claim.type.name, "NW014")

    @staticmethod
    def _get_level(result: VerificationResult) -> str:
        """Get the SARIF level for a verification result."""
        if result.verdict is Verdict.CONTRADICTED:
            return "error"
        if result.verdict is Verdict.UNVERIFIABLE:
            return "warning"
        return "none"

    @staticmethod
    def _get_message(result: VerificationResult) -> str:
        """Get the human-readable message for a verification result."""
        if result.verdict is Verdict.UNVERIFIABLE:
            return (
                f"AI claimed {result.claim.type.name} for "
                f"'{result.claim.symbol_name or result.claim.file_path}' "
                f"but this could not be verified against structural evidence"
            )

        # CONTRADICTED
        if result.claim.type.name == "CALLS_FUNCTION":
            return (
                f"AI claimed '{result.claim.caller_name}' calls "
                f"'{result.claim.called_name}' but no such call exists "
                f"in {result.claim.file_path}"
            )
        return (
            f"AI claimed {result.claim.type.name} for "
            f"'{result.claim.symbol_name}' but it doesn't match "
            f"structural evidence in {result.claim.file_path}"
        )

    @staticmethod
    def _get_locations(result: VerificationResult) -> list[dict[str, Any]]:
        """Get the SARIF locations for a verification result."""
        if result.matched_change is not None:
            return _change_to_locations(result.matched_change)

        # For UNVERIFIABLE, point to the claimed file
        return [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": result.claim.file_path,
                    },
                }
            }
        ]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _change_to_locations(change: DetectedChange) -> list[dict[str, Any]]:
    """Convert a DetectedChange to SARIF locations."""
    location: dict[str, Any] = {
        "physicalLocation": {
            "artifactLocation": {
                "uri": str(change.file_path),
            },
        }
    }

    if change.line_number is not None:
        location["physicalLocation"]["region"] = {
            "startLine": change.line_number,
        }

    return [location]


def _describe_change(change: DetectedChange) -> str:
    """Describe an unexplained change for the SARIF message."""
    change_type = change.change_type.name

    if change.symbol_name:
        return (
            f"Structural change detected: {change_type} "
            f"'{change.symbol_name}' in {change.file_path}"
        )
    if change.caller_name and change.called_name:
        return (
            f"Structural change detected: {change_type} "
            f"'{change.caller_name}' -> '{change.called_name}' "
            f"in {change.file_path}"
        )
    return f"Structural change detected: {change_type} in {change.file_path}"
