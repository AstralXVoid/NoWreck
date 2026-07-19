from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nowreck.claims.models import (
    Claim,
    ClaimType,
    ParseResult,
)
from nowreck.claims.parser import CLAIM_TYPE_NAMES, ClaimParser

# ---------------------------------------------------------------------------
# ClaimType
# ---------------------------------------------------------------------------


class TestClaimType:
    def test_has_all_mvp_types(self) -> None:
        assert ClaimType.ADD_FUNCTION
        assert ClaimType.REMOVE_FUNCTION
        assert ClaimType.ADD_CLASS
        assert ClaimType.REMOVE_CLASS
        assert ClaimType.FILE_CREATED
        assert ClaimType.FILE_DELETED
        assert ClaimType.CALLS_FUNCTION

    def test_values_are_distinct(self) -> None:
        values = {m.value for m in ClaimType}
        assert len(values) == 7

    def test_all_types_in_name_map(self) -> None:
        for member in ClaimType:
            assert member.name in CLAIM_TYPE_NAMES
            assert CLAIM_TYPE_NAMES[member.name] is member


# ---------------------------------------------------------------------------
# Claim Pydantic model
# ---------------------------------------------------------------------------


class TestClaim:
    def test_minimal_valid(self) -> None:
        c = Claim(type=ClaimType.FILE_CREATED, file_path="new.py")
        assert c.type is ClaimType.FILE_CREATED
        assert c.file_path == "new.py"
        assert c.symbol_name is None
        assert c.confidence == 1.0

    def test_full_function_add(self) -> None:
        c = Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="greet",
            file_path="src/hello.py",
            line_number=5,
            confidence=0.95,
        )
        assert c.symbol_name == "greet"
        assert c.file_path == "src/hello.py"
        assert c.line_number == 5
        assert c.confidence == 0.95

    def test_calls_function(self) -> None:
        c = Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="run",
            file_path="app.py",
            caller_name="main",
            called_name="run",
        )
        assert c.caller_name == "main"
        assert c.called_name == "run"

    def test_confidence_clamped(self) -> None:
        with pytest.raises(ValidationError):
            Claim(type=ClaimType.FILE_CREATED, file_path="x.py", confidence=1.5)
        with pytest.raises(ValidationError):
            Claim(type=ClaimType.FILE_CREATED, file_path="x.py", confidence=-0.1)

    def test_file_path_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            Claim(type=ClaimType.FILE_CREATED, file_path="")
        with pytest.raises(ValidationError):
            Claim(type=ClaimType.FILE_CREATED, file_path="   ")

    def test_to_detected_change_path(self) -> None:
        c = Claim(type=ClaimType.ADD_FUNCTION, symbol_name="f", file_path="src/util.py")
        assert c.to_detected_change_path() == Path("src/util.py")


# ---------------------------------------------------------------------------
# ParseResult
# ---------------------------------------------------------------------------


class TestParseResult:
    def test_success_property(self) -> None:
        r = ParseResult(claims=[], errors=[], raw_json="{}")
        assert r.success is True
        r2 = ParseResult(claims=[], errors=["bad"], raw_json="{}")
        assert r2.success is False

    def test_empty_is_success(self) -> None:
        """An empty ParseResult with no errors is considered a success
        (no claims but no errors either)."""
        r = ParseResult()
        assert r.success is True


# ---------------------------------------------------------------------------
# ClaimParser — valid JSON
# ---------------------------------------------------------------------------


class TestClaimParserValid:
    def test_single_claim(self) -> None:
        payload = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "greet",
                        "file_path": "app.py",
                    },
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.success is True
        assert len(result.claims) == 1
        assert result.claims[0].type is ClaimType.ADD_FUNCTION
        assert result.claims[0].symbol_name == "greet"
        assert result.claims[0].file_path == "app.py"

    def test_multiple_claims(self) -> None:
        payload = json.dumps(
            {
                "claims": [
                    {"type": "FILE_CREATED", "file_path": "new.py"},
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "util",
                        "file_path": "new.py",
                    },
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.success is True
        assert len(result.claims) == 2

    def test_all_claim_types(self) -> None:
        for ct in ClaimType:
            claim_dict = {"type": ct.name, "file_path": "f.py"}
            if ct in (ClaimType.ADD_FUNCTION, ClaimType.REMOVE_FUNCTION):
                claim_dict["symbol_name"] = "fn"
            elif ct in (ClaimType.ADD_CLASS, ClaimType.REMOVE_CLASS):
                claim_dict["symbol_name"] = "Cls"
            elif ct is ClaimType.CALLS_FUNCTION:
                claim_dict.update(
                    {"symbol_name": "fn", "caller_name": "main", "called_name": "fn"}
                )
            payload = json.dumps({"claims": [claim_dict]})
            result = ClaimParser.parse(payload)
            assert result.success is True, f"Failed for {ct.name}: {result.errors}"
            assert len(result.claims) == 1
            assert result.claims[0].type is ct

    def test_optional_line_number(self) -> None:
        payload = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "greet",
                        "file_path": "app.py",
                        "line_number": 42,
                    },
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.success is True
        assert result.claims[0].line_number == 42

    def test_custom_confidence(self) -> None:
        payload = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "f",
                        "file_path": "f.py",
                        "confidence": 0.75,
                    },
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.success is True
        assert result.claims[0].confidence == 0.75

    def test_extra_fields_are_ignored(self) -> None:
        """Pydantic ignores extra fields by default."""
        payload = json.dumps(
            {
                "claims": [
                    {
                        "type": "FILE_CREATED",
                        "file_path": "f.py",
                        "extra_field": "should be ignored",
                    },
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.success is True
        assert len(result.claims) == 1


# ---------------------------------------------------------------------------
# ClaimParser — invalid JSON
# ---------------------------------------------------------------------------


class TestClaimParserInvalidJson:
    def test_not_json(self) -> None:
        result = ClaimParser.parse("not valid json{{}")
        assert result.success is False
        assert "Invalid JSON" in result.errors[0]
        assert result.claims == []

    def test_not_an_object(self) -> None:
        result = ClaimParser.parse('"just a string"')
        assert result.success is False
        assert len(result.errors) == 1

    def test_missing_claims_key(self) -> None:
        result = ClaimParser.parse('{"something": 1}')
        assert result.success is False
        assert any("claims" in e for e in result.errors)

    def test_claims_not_a_list(self) -> None:
        result = ClaimParser.parse('{"claims": "not a list"}')
        assert result.success is False
        assert "must be a list" in result.errors[0]

    def test_empty_claims_list(self) -> None:
        result = ClaimParser.parse('{"claims": []}')
        assert result.success is False
        assert "empty" in result.errors[0].lower()

    def test_claim_not_an_object(self) -> None:
        payload = json.dumps({"claims": ["string instead of object"]})
        result = ClaimParser.parse(payload)
        assert result.success is False
        assert any("expected an object" in e for e in result.errors)

    def test_missing_type_field(self) -> None:
        payload = json.dumps({"claims": [{"file_path": "f.py"}]})
        result = ClaimParser.parse(payload)
        assert result.success is False
        assert any("type" in e for e in result.errors)

    def test_unknown_claim_type(self) -> None:
        payload = json.dumps({"claims": [{"type": "NONEXISTENT", "file_path": "f.py"}]})
        result = ClaimParser.parse(payload)
        assert result.success is False
        assert any("unknown claim type" in e.lower() for e in result.errors)

    def test_type_not_a_string(self) -> None:
        payload = json.dumps({"claims": [{"type": 123, "file_path": "f.py"}]})
        result = ClaimParser.parse(payload)
        assert result.success is False
        assert any("must be a string" in e for e in result.errors)

    def test_missing_file_path(self) -> None:
        payload = json.dumps({"claims": [{"type": "ADD_FUNCTION", "symbol_name": "f"}]})
        result = ClaimParser.parse(payload)
        assert result.success is False
        assert any("file_path" in e for e in result.errors)

    def test_empty_file_path(self) -> None:
        payload = json.dumps(
            {"claims": [{"type": "ADD_FUNCTION", "symbol_name": "f", "file_path": ""}]}
        )
        result = ClaimParser.parse(payload)
        assert result.success is False

    def test_partial_failure(self) -> None:
        """Two claims, one valid and one invalid — should return the
        valid one plus an error for the invalid one."""
        payload = json.dumps(
            {
                "claims": [
                    {"type": "FILE_CREATED", "file_path": "good.py"},
                    {"type": "INVALID_TYPE", "file_path": "bad.py"},
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.success is False  # at least one error
        assert len(result.claims) == 1  # only the valid one
        assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# ClaimParser — deterministic
# ---------------------------------------------------------------------------


class TestClaimParserDeterministic:
    def test_same_input_same_output(self) -> None:
        payload = json.dumps(
            {
                "claims": [
                    {"type": "ADD_FUNCTION", "symbol_name": "f", "file_path": "f.py"},
                ],
            }
        )
        r1 = ClaimParser.parse(payload)
        r2 = ClaimParser.parse(payload)
        assert r1.success == r2.success
        assert r1.claims == r2.claims
        assert r1.errors == r2.errors
        assert r1.raw_json == r2.raw_json


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestClaimParserEdgeCases:
    def test_claim_overwrites_default_confidence(self) -> None:
        payload = json.dumps(
            {
                "claims": [
                    {"type": "FILE_CREATED", "file_path": "f.py", "confidence": 0.5},
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.claims[0].confidence == 0.5

    def test_parent_class_field(self) -> None:
        payload = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "render",
                        "file_path": "widget.py",
                        "parent_class": "Widget",
                    },
                ],
            }
        )
        result = ClaimParser.parse(payload)
        assert result.success is True
        assert result.claims[0].parent_class == "Widget"
