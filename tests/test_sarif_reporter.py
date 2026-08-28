"""Tests for the SARIF v2.1.0 reporter."""

from __future__ import annotations

import json
from pathlib import Path

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange
from nowreck.reporter.sarif_reporter import (
    _CLAIM_TYPE_TO_RULE,
    _RULE_INDEX,
    _SARIF_RULES,
    SarifReporter,
    _change_to_locations,
    _describe_change,
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
    parent_class: str | None = None,
) -> Claim:
    return Claim(
        type=claim_type,
        symbol_name=symbol_name,
        file_path=file_path,
        parent_class=parent_class,
        caller_name=caller_name,
        called_name=called_name,
    )


def _make_change(
    change_type: ChangeType = ChangeType.ADD_FUNCTION,
    symbol_name: str | None = "my_func",
    file_path: str = "app.py",
    line_number: int | None = 10,
    caller_name: str | None = None,
    called_name: str | None = None,
) -> DetectedChange:
    return DetectedChange(
        change_type=change_type,
        symbol_name=symbol_name,
        file_path=Path(file_path),
        line_number=line_number,
        caller_name=caller_name,
        called_name=called_name,
    )


# ---------------------------------------------------------------------------
# SARIF rule definitions
# ---------------------------------------------------------------------------


class TestSarifRules:
    """Verify SARIF rule definitions are correct."""

    def test_rule_count(self) -> None:
        """Should have exactly 15 rules."""
        assert len(_SARIF_RULES) == 15

    def test_rule_ids_are_unique(self) -> None:
        """All rule IDs should be unique."""
        ids = [r["id"] for r in _SARIF_RULES]
        assert len(ids) == len(set(ids))

    def test_rule_indices_match(self) -> None:
        """Rule index lookup should match position in rules list."""
        for i, rule in enumerate(_SARIF_RULES):
            assert _RULE_INDEX[rule["id"]] == i

    def test_nw001_nw013_are_error(self) -> None:
        """Rules NW001-NW013 should have level 'error'."""
        for rule in _SARIF_RULES:
            if rule["id"] in [f"NW{i:03d}" for i in range(1, 14)]:
                assert rule["defaultConfiguration"]["level"] == "error"

    def test_nw014_is_warning(self) -> None:
        """Rule NW014 (UnverifiedClaim) should have level 'warning'."""
        nw014 = next(r for r in _SARIF_RULES if r["id"] == "NW014")
        assert nw014["defaultConfiguration"]["level"] == "warning"

    def test_nw015_is_note(self) -> None:
        """Rule NW015 (UnexplainedChange) should have level 'note'."""
        nw015 = next(r for r in _SARIF_RULES if r["id"] == "NW015")
        assert nw015["defaultConfiguration"]["level"] == "note"


class TestClaimTypeToRule:
    """Verify claim type to rule mapping."""

    def test_all_claim_types_mapped(self) -> None:
        """All 13 claim types should map to a rule."""
        expected_types = {
            "ADD_FUNCTION",
            "REMOVE_FUNCTION",
            "ADD_CLASS",
            "REMOVE_CLASS",
            "ADD_INTERFACE",
            "REMOVE_INTERFACE",
            "ADD_ENUM",
            "REMOVE_ENUM",
            "ADD_TYPE_ALIAS",
            "REMOVE_TYPE_ALIAS",
            "FILE_CREATED",
            "FILE_DELETED",
            "CALLS_FUNCTION",
        }
        assert set(_CLAIM_TYPE_TO_RULE.keys()) == expected_types

    def test_mapping_values_are_valid_rule_ids(self) -> None:
        """All mapped rule IDs should exist in the rules list."""
        valid_ids = {r["id"] for r in _SARIF_RULES}
        for rule_id in _CLAIM_TYPE_TO_RULE.values():
            assert rule_id in valid_ids


# ---------------------------------------------------------------------------
# SarifReporter
# ---------------------------------------------------------------------------


class TestSarifReporter:
    """Test the SarifReporter class."""

    def test_basic_output_structure(self) -> None:
        """Should produce valid SARIF structure."""
        reporter = SarifReporter()
        report = VerificationReport(results=[], unexplained_changes=[])
        output = reporter.report(report)
        data = json.loads(output)

        assert data["version"] == "2.1.0"
        assert "$schema" in data
        assert len(data["runs"]) == 1
        assert data["runs"][0]["tool"]["driver"]["name"] == "nowreck"
        assert data["runs"][0]["results"] == []

    def test_confirmed_excluded_by_default(self) -> None:
        """CONFIRMED results should be excluded by default."""
        reporter = SarifReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        change = _make_change(ChangeType.ADD_FUNCTION)
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONFIRMED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        data = json.loads(output)
        results = data["runs"][0]["results"]

        assert len(results) == 0

    def test_confirmed_included_when_flag_set(self) -> None:
        """CONFIRMED results should be included when flag is set."""
        reporter = SarifReporter(include_confirmed=True)
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        change = _make_change(ChangeType.ADD_FUNCTION)
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONFIRMED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        data = json.loads(output)
        results = data["runs"][0]["results"]

        assert len(results) == 1
        assert results[0]["ruleId"] == "NW001"
        assert results[0]["level"] == "none"

    def test_contradicted_included(self) -> None:
        """CONTRADICTED results should be included."""
        reporter = SarifReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        change = _make_change(ChangeType.REMOVE_FUNCTION)
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONTRADICTED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        data = json.loads(output)
        results = data["runs"][0]["results"]

        assert len(results) == 1
        assert results[0]["ruleId"] == "NW001"
        assert results[0]["level"] == "error"
        assert "ruleIndex" in results[0]

    def test_unverifiable_included(self) -> None:
        """UNVERIFIABLE results should be included."""
        reporter = SarifReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        result = VerificationResult(claim=claim, verdict=Verdict.UNVERIFIABLE)
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        data = json.loads(output)
        results = data["runs"][0]["results"]

        assert len(results) == 1
        assert results[0]["ruleId"] == "NW014"
        assert results[0]["level"] == "warning"

    def test_unexplained_change_included(self) -> None:
        """Unexplained changes should be included."""
        reporter = SarifReporter()
        change = _make_change(ChangeType.ADD_FUNCTION)
        report = VerificationReport(results=[], unexplained_changes=[change])

        output = reporter.report(report)
        data = json.loads(output)
        results = data["runs"][0]["results"]

        assert len(results) == 1
        assert results[0]["ruleId"] == "NW015"
        assert results[0]["level"] == "note"

    def test_calls_function_contradicted(self) -> None:
        """CALLS_FUNCTION CONTRADICTED should use NW013."""
        reporter = SarifReporter()
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            caller_name="foo",
            called_name="bar",
        )
        change = _make_change(
            ChangeType.CALL_DETECTED,
            caller_name="foo",
            called_name="bar",
        )
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONTRADICTED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        data = json.loads(output)
        results = data["runs"][0]["results"]

        assert results[0]["ruleId"] == "NW013"
        assert "calls" in results[0]["message"]["text"].lower()

    def test_location_includes_file_path(self) -> None:
        """Locations should include the file path."""
        reporter = SarifReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION, file_path="src/app.py")
        change = _make_change(ChangeType.ADD_FUNCTION, file_path="src/app.py")
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONTRADICTED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        data = json.loads(output)
        locations = data["runs"][0]["results"][0]["locations"]

        assert len(locations) == 1
        uri = locations[0]["physicalLocation"]["artifactLocation"]["uri"]
        assert uri == "src/app.py"

    def test_location_includes_line_number(self) -> None:
        """Locations should include line number when available."""
        reporter = SarifReporter()
        claim = _make_claim(ClaimType.ADD_FUNCTION)
        change = _make_change(ChangeType.ADD_FUNCTION, line_number=42)
        result = VerificationResult(
            claim=claim, verdict=Verdict.CONTRADICTED, matched_change=change
        )
        report = VerificationReport(results=[result])

        output = reporter.report(report)
        data = json.loads(output)
        location = data["runs"][0]["results"][0]["locations"][0]
        region = location["physicalLocation"]["region"]

        assert region["startLine"] == 42

    def test_report_dict_returns_dict(self) -> None:
        """report_dict should return a dict, not a string."""
        reporter = SarifReporter()
        report = VerificationReport(results=[])
        result = reporter.report_dict(report)

        assert isinstance(result, dict)
        assert result["version"] == "2.1.0"

    def test_rules_list_in_output(self) -> None:
        """Output should include the full rules list."""
        reporter = SarifReporter()
        report = VerificationReport(results=[])
        output = reporter.report(report)
        data = json.loads(output)
        rules = data["runs"][0]["tool"]["driver"]["rules"]

        assert len(rules) == 15
        assert rules[0]["id"] == "NW001"
        assert rules[-1]["id"] == "NW015"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestDescribeChange:
    """Test the _describe_change helper."""

    def test_function_change(self) -> None:
        change = _make_change(ChangeType.ADD_FUNCTION, symbol_name="my_func")
        desc = _describe_change(change)
        assert "ADD_FUNCTION" in desc
        assert "my_func" in desc

    def test_file_change(self) -> None:
        change = _make_change(ChangeType.FILE_CREATED, symbol_name=None)
        desc = _describe_change(change)
        assert "FILE_CREATED" in desc

    def test_call_change(self) -> None:
        change = _make_change(
            ChangeType.CALL_DETECTED,
            symbol_name=None,
            caller_name="foo",
            called_name="bar",
        )
        desc = _describe_change(change)
        assert "foo" in desc
        assert "bar" in desc


class TestChangeToLocations:
    """Test the _change_to_locations helper."""

    def test_basic_location(self) -> None:
        change = _make_change(ChangeType.ADD_FUNCTION, file_path="app.py")
        locations = _change_to_locations(change)
        assert len(locations) == 1
        assert locations[0]["physicalLocation"]["artifactLocation"]["uri"] == "app.py"

    def test_with_line_number(self) -> None:
        change = _make_change(ChangeType.ADD_FUNCTION, line_number=10)
        locations = _change_to_locations(change)
        assert locations[0]["physicalLocation"]["region"]["startLine"] == 10

    def test_without_line_number(self) -> None:
        change = _make_change(ChangeType.ADD_FUNCTION, line_number=None)
        locations = _change_to_locations(change)
        assert "region" not in locations[0]["physicalLocation"]
