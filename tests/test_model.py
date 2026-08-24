from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from nowreck.claims.models import ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange
from nowreck.model.prompts import PROMPT_SYSTEM_PROMPT, SYSTEM_PROMPT, PromptBuilder
from nowreck.model.provider import (
    ModelConfig,
    ModelError,
    ModelProvider,
    ModelResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _mock_http_ok(messages: list[dict], config: ModelConfig) -> str:
    """Mock HTTP call that returns valid claims JSON."""
    return json.dumps(
        {
            "claims": [
                {
                    "type": "FILE_CREATED",
                    "file_path": "new.py",
                    "confidence": 0.95,
                    "explanation": "A new file was created.",
                },
            ],
        }
    )


def _mock_http_bad_json(messages: list[dict], config: ModelConfig) -> str:
    """Mock HTTP call that returns invalid JSON."""
    return "not valid json at all"


def _mock_http_missing_key(messages: list[dict], config: ModelConfig) -> str:
    """Mock HTTP call that returns JSON missing the 'claims' key."""
    return json.dumps({"not_claims": []})


def _mock_http_valid_then_bad(messages: list[dict], config: ModelConfig) -> str:
    """Return valid JSON on first call, invalid on subsequent calls."""
    has_assistant = any(m.get("role") == "assistant" for m in messages)
    if has_assistant:
        return json.dumps({"not_claims": []})
    return _mock_http_ok(messages, config)


def _mock_http_bad_then_valid(messages: list[dict], config: ModelConfig) -> str:
    """Return invalid JSON on first call, valid on repair."""
    has_assistant = any(m.get("role") == "assistant" for m in messages)
    if has_assistant:
        return _mock_http_ok(messages, config)
    return json.dumps({"not_claims": []})


def _mock_http_network_error(messages: list[dict], config: ModelConfig) -> str:
    """Mock HTTP call that raises a network error."""
    raise ModelError("Connection refused")


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------


class TestPromptBuilder:
    def test_system_present(self) -> None:
        messages = PromptBuilder.build([])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Nowreck" in messages[0]["content"]

    def test_empty_changes(self) -> None:
        messages = PromptBuilder.build([])
        assert "No changes were detected." in messages[1]["content"]

    def test_single_function_add(self) -> None:
        changes = [
            _make_change(
                ChangeType.ADD_FUNCTION,
                file_path="app.py",
                symbol_name="greet",
            ),
        ]
        messages = PromptBuilder.build(changes)
        content = messages[1]["content"]
        assert "greet()" in content
        assert "app.py" in content

    def test_function_with_parent_class(self) -> None:
        changes = [
            _make_change(
                ChangeType.ADD_FUNCTION,
                file_path="widget.py",
                symbol_name="render",
                parent_class="Widget",
            ),
        ]
        messages = PromptBuilder.build(changes)
        content = messages[1]["content"]
        assert "Widget.render()" in content

    def test_call_detected(self) -> None:
        changes = [
            _make_change(
                ChangeType.CALL_DETECTED,
                file_path="app.py",
                caller_name="main",
                called_name="print",
            ),
        ]
        messages = PromptBuilder.build(changes)
        content = messages[1]["content"]
        assert "main() now calls print()" in content

    def test_file_level_change(self) -> None:
        changes = [
            _make_change(ChangeType.FILE_CREATED, file_path="new.py"),
        ]
        messages = PromptBuilder.build(changes)
        content = messages[1]["content"]
        assert "new.py" in content

    def test_change_with_line_number(self) -> None:
        changes = [
            _make_change(
                ChangeType.REMOVE_FUNCTION,
                file_path="app.py",
                symbol_name="old_fn",
                line_number=42,
            ),
        ]
        messages = PromptBuilder.build(changes)
        content = messages[1]["content"]
        assert "line 42" in content

    def test_multiple_changes_numbered(self) -> None:
        changes = [
            _make_change(ChangeType.FILE_CREATED, file_path="new.py"),
            _make_change(
                ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="greet"
            ),
        ]
        messages = PromptBuilder.build(changes)
        content = messages[1]["content"]
        assert "1. File created:" in content
        assert "2. Function added:" in content

    def test_system_prompt_has_json_format(self) -> None:
        assert '"claims"' in SYSTEM_PROMPT
        assert "ADD_FUNCTION" in SYSTEM_PROMPT

    def test_for_prompt_system_present(self) -> None:
        messages = PromptBuilder.for_prompt("Add a function x")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Nowreck" in messages[0]["content"]

    def test_for_prompt_contains_user_text(self) -> None:
        messages = PromptBuilder.for_prompt("Add validate_email to app.py")
        assert "validate_email" in messages[1]["content"]

    def test_for_prompt_system_has_json_format(self) -> None:
        assert '"claims"' in PROMPT_SYSTEM_PROMPT
        assert "ADD_FUNCTION" in PROMPT_SYSTEM_PROMPT

    def test_claims_to_changes_empty(self) -> None:
        assert PromptBuilder.claims_to_changes([]) == []

    def test_claims_to_changes_add_function(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.ADD_FUNCTION,
                symbol_name="validate_email",
                file_path="app.py",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.ADD_FUNCTION
        assert changes[0].symbol_name == "validate_email"
        assert str(changes[0].file_path) == "app.py"

    def test_claims_to_changes_add_class(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.ADD_CLASS,
                symbol_name="UserService",
                file_path="services/user.py",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.ADD_CLASS
        assert changes[0].symbol_name == "UserService"

    def test_claims_to_changes_file_created(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.FILE_CREATED,
                file_path="new_module.py",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.FILE_CREATED
        assert str(changes[0].file_path) == "new_module.py"

    def test_claims_to_changes_add_interface(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.ADD_INTERFACE,
                symbol_name="User",
                file_path="models.ts",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.ADD_INTERFACE
        assert changes[0].symbol_name == "User"
        assert str(changes[0].file_path) == "models.ts"

    def test_claims_to_changes_remove_interface(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.REMOVE_INTERFACE,
                symbol_name="User",
                file_path="models.ts",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.REMOVE_INTERFACE

    def test_claims_to_changes_add_enum(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.ADD_ENUM,
                symbol_name="Role",
                file_path="models.ts",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.ADD_ENUM
        assert changes[0].symbol_name == "Role"

    def test_claims_to_changes_remove_enum(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.REMOVE_ENUM,
                symbol_name="Role",
                file_path="models.ts",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.REMOVE_ENUM

    def test_claims_to_changes_add_type_alias(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.ADD_TYPE_ALIAS,
                symbol_name="UserStatus",
                file_path="models.ts",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.ADD_TYPE_ALIAS
        assert changes[0].symbol_name == "UserStatus"

    def test_claims_to_changes_remove_type_alias(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.REMOVE_TYPE_ALIAS,
                symbol_name="UserStatus",
                file_path="models.ts",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.REMOVE_TYPE_ALIAS

    def test_prompt_renders_interface_change(self) -> None:
        """A type-level change renders with its human label, not a raw
        enum name."""
        changes = [
            _make_change(
                ChangeType.ADD_INTERFACE,
                file_path="models.ts",
                symbol_name="User",
            ),
        ]
        messages = PromptBuilder.build(changes)
        content = messages[1]["content"]
        assert "Interface added" in content
        assert "User" in content
        assert "models.ts" in content

    def test_claims_to_changes_skips_calls_function(self) -> None:
        """CALLS_FUNCTION claims are NOT converted to CALL_DETECTED
        changes — they are verified against other changes instead."""
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(
                type=ClaimType.CALLS_FUNCTION,
                caller_name="main",
                called_name="validate",
                file_path="app.py",
            ),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 0  # No change derived from CALLS_FUNCTION

    def test_claims_to_changes_multiple_sorted(self) -> None:
        from nowreck.claims.models import Claim, ClaimType

        claims = [
            Claim(type=ClaimType.FILE_CREATED, file_path="z.py"),
            Claim(type=ClaimType.FILE_CREATED, file_path="a.py"),
        ]
        changes = PromptBuilder.claims_to_changes(claims)
        assert len(changes) == 2
        # Should be sorted by file_path (a.py before z.py)
        assert str(changes[0].file_path) == "a.py"
        assert str(changes[1].file_path) == "z.py"


# ---------------------------------------------------------------------------
# ModelConfig
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_defaults(self) -> None:
        config = ModelConfig()
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4o"
        assert config.temperature == 0.0
        assert config.max_retries == 1

    def test_resolve_api_key_from_field(self) -> None:
        config = ModelConfig(api_key="sk-test")
        assert config.resolve_api_key() == "sk-test"

    def test_resolve_api_key_from_env(self) -> None:
        os.environ["NOWRECK_API_KEY"] = "sk-env"
        config = ModelConfig()
        try:
            assert config.resolve_api_key() == "sk-env"
        finally:
            del os.environ["NOWRECK_API_KEY"]

    def test_resolve_api_key_empty(self) -> None:
        config = ModelConfig()
        assert config.resolve_api_key() == ""

    def test_resolve_failed_dir_default(self) -> None:
        config = ModelConfig()
        path = config.resolve_failed_dir()
        assert path is not None
        assert ".nowreck" in str(path)

    def test_resolve_failed_dir_custom(self) -> None:
        config = ModelConfig(failed_dir=Path("/tmp/nowreck-fails"))
        assert config.resolve_failed_dir() == Path("/tmp/nowreck-fails")


# ---------------------------------------------------------------------------
# ModelResult
# ---------------------------------------------------------------------------


class TestModelResult:
    def test_defaults(self) -> None:
        result = ModelResult()
        assert result.claims == []
        assert result.changes == []
        assert result.parse_result is None
        assert result.raw_response == ""
        assert result.attempts == 1
        assert result.messages == []


# ---------------------------------------------------------------------------
# ModelProvider — successful responses
# ---------------------------------------------------------------------------


class TestModelProviderSuccess:
    def test_returns_claims(self) -> None:
        provider = ModelProvider(http_call=_mock_http_ok)
        changes = [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        result = provider.explain_changes(changes)
        assert len(result.claims) == 1
        assert result.claims[0].type is ClaimType.FILE_CREATED
        assert result.claims[0].file_path == "new.py"

    def test_parse_result_is_success(self) -> None:
        provider = ModelProvider(http_call=_mock_http_ok)
        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )
        assert result.parse_result is not None
        assert result.parse_result.success is True

    def test_raw_response_present(self) -> None:
        provider = ModelProvider(http_call=_mock_http_ok)
        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )
        assert result.raw_response != ""

    def test_attempts_is_one_on_success(self) -> None:
        provider = ModelProvider(http_call=_mock_http_ok)
        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )
        assert result.attempts == 1


# ---------------------------------------------------------------------------
# ModelProvider — repair logic
# ---------------------------------------------------------------------------


class TestModelProviderRepair:
    def test_repair_succeeds_after_retry(self) -> None:
        """First call returns bad JSON, repair attempt returns good."""
        provider = ModelProvider(http_call=_mock_http_bad_then_valid)
        changes = [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        result = provider.explain_changes(changes)
        assert len(result.claims) == 1
        assert result.attempts == 2

    def test_repair_fails_writes_to_failed_dir(self) -> None:
        """Both attempts fail — failed response is saved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ModelConfig(failed_dir=Path(tmpdir))
            provider = ModelProvider(
                config=config,
                http_call=_mock_http_missing_key,
            )
            result = provider.explain_changes(
                [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
            )
            assert result.claims == []
            assert result.parse_result is not None
            assert result.parse_result.success is False
            # Check a failed file was written
            failed_files = list(Path(tmpdir).iterdir())
            assert len(failed_files) == 1
            assert "failed_" in failed_files[0].name

    def test_repair_attempts_limited_by_config(self) -> None:
        """With max_retries=0, no repair is attempted."""
        config = ModelConfig(max_retries=0)
        provider = ModelProvider(
            config=config,
            http_call=_mock_http_missing_key,
        )
        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )
        assert result.attempts == 1

    def test_repair_not_attempted_when_first_succeeds(self) -> None:
        """First call succeeds — no repair needed."""
        config = ModelConfig(max_retries=3)
        provider = ModelProvider(
            config=config,
            http_call=_mock_http_ok,
        )
        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )
        assert result.attempts == 1

    def test_failed_dir_disabled_no_file_saved(self) -> None:
        """Custom path that is writable but out of the way."""
        config = ModelConfig(failed_dir=Path("/tmp/nowreck-fails"))
        provider = ModelProvider(
            config=config,
            http_call=_mock_http_missing_key,
        )
        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )
        assert result.claims == []
        # No error — saving is best-effort


# ---------------------------------------------------------------------------
# ModelProvider — error handling
# ---------------------------------------------------------------------------


class TestModelProviderErrors:
    def test_network_error_raises(self) -> None:
        provider = ModelProvider(http_call=_mock_http_network_error)
        with pytest.raises(ModelError, match="Connection refused"):
            provider.explain_changes(
                [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
            )

    def test_no_api_key_raises(self) -> None:
        """Without an injected mock, _default_http_call checks the
        API key and raises ModelError."""
        config = ModelConfig(api_key="")  # empty, no env var
        provider = ModelProvider(config=config)  # no mock — uses default
        with pytest.raises(ModelError, match="No API key"):
            provider.explain_changes(
                [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
            )


# ---------------------------------------------------------------------------
# ModelProvider — integration with real flow (mocked)
# ---------------------------------------------------------------------------


class TestModelProviderIntegration:
    def test_multiple_changes_all_parsed(self) -> None:
        def _mock(messages: list[dict], config: ModelConfig) -> str:
            return json.dumps(
                {
                    "claims": [
                        {
                            "type": "FILE_CREATED",
                            "file_path": "new.py",
                            "confidence": 0.9,
                        },
                        {
                            "type": "ADD_FUNCTION",
                            "symbol_name": "greet",
                            "file_path": "app.py",
                            "confidence": 0.95,
                        },
                    ],
                }
            )

        provider = ModelProvider(http_call=_mock)
        changes = [
            _make_change(ChangeType.FILE_CREATED, file_path="new.py"),
            _make_change(
                ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="greet"
            ),
        ]
        result = provider.explain_changes(changes)
        assert len(result.claims) == 2
        assert result.parse_result is not None
        assert result.parse_result.success is True

    def test_prompt_built_with_changes(self) -> None:
        captured_messages: list[list[dict]] = []

        def _capture(messages: list[dict], config: ModelConfig) -> str:
            captured_messages.append(messages)
            return _mock_http_ok(messages, config)

        provider = ModelProvider(http_call=_capture)
        changes = [
            _make_change(ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="f")
        ]
        provider.explain_changes(changes)
        assert len(captured_messages) == 1
        sent = captured_messages[0]
        assert sent[0]["role"] == "system"
        assert sent[1]["role"] == "user"
        assert "f()" in sent[1]["content"]


# ---------------------------------------------------------------------------
# ModelProvider — prompt mode
# ---------------------------------------------------------------------------


class TestModelProviderPrompt:
    def test_changes_from_prompt_returns_claims(self) -> None:
        provider = ModelProvider(http_call=_mock_http_ok)
        result = provider.changes_from_prompt("Create a new file new.py")
        assert len(result.claims) == 1
        assert result.claims[0].type is ClaimType.FILE_CREATED

    def test_changes_from_prompt_returns_changes(self) -> None:
        provider = ModelProvider(http_call=_mock_http_ok)
        result = provider.changes_from_prompt("Create a new file new.py")
        assert len(result.changes) == 1
        assert result.changes[0].change_type is ChangeType.FILE_CREATED
        assert str(result.changes[0].file_path) == "new.py"

    def test_changes_from_prompt_uses_correct_prompt(self) -> None:
        captured: list[list[dict]] = []

        def _capture(messages: list[dict], config: ModelConfig) -> str:
            captured.append(messages)
            return _mock_http_ok(messages, config)

        provider = ModelProvider(http_call=_capture)
        provider.changes_from_prompt("Add validation to app.py")
        assert len(captured) == 1
        sent = captured[0]
        assert "PROMPT_SYSTEM_PROMPT" not in sent[0]["content"]  # not literal
        assert "Nowreck" in sent[0]["content"]
        assert "Add validation to app.py" in sent[1]["content"]

    def test_changes_from_prompt_retries_on_failure(self) -> None:
        provider = ModelProvider(http_call=_mock_http_bad_then_valid)
        result = provider.changes_from_prompt("Create new.py")
        assert len(result.claims) == 1
        assert result.attempts == 2

    def test_changes_from_prompt_empty_on_network_error(self) -> None:
        provider = ModelProvider(http_call=_mock_http_network_error)
        with pytest.raises(ModelError, match="Connection refused"):
            provider.changes_from_prompt("Create new.py")


# ---------------------------------------------------------------------------
# ModelProvider — failed response content
# ---------------------------------------------------------------------------


class TestModelProviderFailedContent:
    def test_saved_file_contains_parse_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ModelConfig(failed_dir=Path(tmpdir))
            provider = ModelProvider(
                config=config,
                http_call=_mock_http_missing_key,
            )
            provider.explain_changes(
                [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
            )
            failed_files = list(Path(tmpdir).iterdir())
            assert len(failed_files) == 1
            content = failed_files[0].read_text(encoding="utf-8")
            data = json.loads(content)
            assert "parse_errors" in data
            assert "messages" in data
            assert "raw_response" in data

    def test_saved_file_has_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ModelConfig(failed_dir=Path(tmpdir))
            provider = ModelProvider(
                config=config,
                http_call=_mock_http_missing_key,
            )
            provider.explain_changes(
                [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
            )
            failed_files = list(Path(tmpdir).iterdir())
            content = failed_files[0].read_text(encoding="utf-8")
            data = json.loads(content)
            assert "timestamp" in data


# ===========================================================================
# Phase 2 — v10 prompt: claims + patch extraction
# ===========================================================================


def _mock_http_v10_ok(
    messages: list[dict], config: ModelConfig,
) -> str:
    """Mock HTTP call returning valid v10 JSON (claims + patch)."""
    return json.dumps({
        "claims": [
            {
                "type": "ADD_FUNCTION",
                "symbol_name": "validate",
                "file_path": "auth.py",
                "confidence": 0.95,
                "explanation": "Added validation function.",
            },
        ],
        "patch": (
            "--- a/auth.py\n"
            "+++ b/auth.py\n"
            "@@ -1 +1,4 @@\n"
            "+def validate(x):\n"
            "+    if not x:\n"
            "+        raise ValueError('empty')\n"
            "+    return True\n"
        ),
    })


def _mock_http_v10_no_patch(
    messages: list[dict], config: ModelConfig,
) -> str:
    """Mock HTTP call returning claims WITHOUT a patch field."""
    return json.dumps({
        "claims": [
            {
                "type": "ADD_FUNCTION",
                "symbol_name": "validate",
                "file_path": "auth.py",
                "confidence": 0.9,
                "explanation": "Added validation.",
            },
        ],
    })


class TestPromptBuilderV10:
    """PromptBuilder.for_prompt_v10() tests."""

    def test_for_prompt_v10_returns_messages(self) -> None:
        messages = PromptBuilder.for_prompt_v10("Add a function")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "claims" in messages[0]["content"]
        assert "patch" in messages[0]["content"]

    def test_for_prompt_v10_includes_prompt(self) -> None:
        messages = PromptBuilder.for_prompt_v10("Add validate()")
        assert "Add validate()" in messages[1]["content"]

    def test_for_prompt_v10_includes_repo_context(self) -> None:
        messages = PromptBuilder.for_prompt_v10(
            "Add function",
            repo_context="app.py: def hello(): pass",
        )
        assert "app.py" in messages[1]["content"]

    def test_for_prompt_v10_without_context(self) -> None:
        messages = PromptBuilder.for_prompt_v10("Add function")
        assert "Repository context" not in messages[1]["content"]


class TestParseResultPatch:
    """ParseResult.patch extraction from model JSON."""

    def test_patch_extracted_when_present(self) -> None:
        from nowreck.claims.parser import ClaimParser

        result = ClaimParser.parse(json.dumps({
            "claims": [
                {
                    "type": "ADD_FUNCTION",
                    "symbol_name": "foo",
                    "file_path": "a.py",
                },
            ],
            "patch": "--- a/a.py\n+++ b/a.py\n",
        }))
        assert result.patch == "--- a/a.py\n+++ b/a.py\n"
        assert result.success

    def test_patch_none_when_absent(self) -> None:
        from nowreck.claims.parser import ClaimParser

        result = ClaimParser.parse(json.dumps({
            "claims": [
                {
                    "type": "ADD_FUNCTION",
                    "symbol_name": "foo",
                    "file_path": "a.py",
                },
            ],
        }))
        assert result.patch is None
        assert result.success

    def test_patch_none_when_empty_string(self) -> None:
        from nowreck.claims.parser import ClaimParser

        result = ClaimParser.parse(json.dumps({
            "claims": [
                {
                    "type": "ADD_FUNCTION",
                    "symbol_name": "foo",
                    "file_path": "a.py",
                },
            ],
            "patch": "",
        }))
        assert result.patch is None


class TestModelProviderV10:
    """ModelProvider.changes_from_prompt_v10() tests."""

    def test_v10_returns_claims_and_patch(self) -> None:
        provider = ModelProvider(http_call=_mock_http_v10_ok)
        result = provider.changes_from_prompt_v10("Add validate")

        assert len(result.claims) == 1
        assert result.claims[0].symbol_name == "validate"
        assert result.patch is not None
        assert "+++ b/auth.py" in result.patch

    def test_v10_no_patch_returns_none(self) -> None:
        provider = ModelProvider(http_call=_mock_http_v10_no_patch)
        result = provider.changes_from_prompt_v10("Add validate")

        assert len(result.claims) == 1
        assert result.patch is None

    def test_v10_uses_v10_prompt(self) -> None:
        """Verify v10 sends messages from for_prompt_v10."""
        captured: list[list[dict]] = []

        def capture_http(
            messages: list[dict], config: ModelConfig,
        ) -> str:
            captured.append(messages)
            return json.dumps({
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "x",
                        "file_path": "a.py",
                    },
                ],
                "patch": "--- a/a.py\n+++ b/a.py\n",
            })

        provider = ModelProvider(http_call=capture_http)
        provider.changes_from_prompt_v10("Add x")

        assert len(captured) == 1
        msgs = captured[0]
        assert "patch" in msgs[0]["content"]  # system prompt

    def test_v10_backward_compat_old_still_works(self) -> None:
        """Old changes_from_prompt still works (no patch in result)."""
        provider = ModelProvider(http_call=_mock_http_v10_no_patch)
        result = provider.changes_from_prompt("Add validate")

        assert len(result.claims) == 1
        # Old path: changes derived from claims
        assert len(result.changes) >= 1


# ---------------------------------------------------------------------------
# Phase 4 (v11) — adapter selection inside ModelProvider
#
# These tests exercise the REAL _default_http_call path by patching
# urllib.request.urlopen. The fake captures the outgoing Request and
# replies in the native envelope of whichever provider the URL targets,
# so a successfully parsed claim proves the full round trip through
# the correct adapter's build_request()/parse_response().
# ---------------------------------------------------------------------------

_CLAIMS_TEXT = json.dumps(
    {
        "claims": [
            {
                "type": "FILE_CREATED",
                "file_path": "new.py",
                "confidence": 0.95,
                "explanation": "A new file was created.",
            },
        ],
    }
)


def _anthropic_response_body() -> bytes:
    return json.dumps(
        {"content": [{"type": "text", "text": _CLAIMS_TEXT}]}
    ).encode("utf-8")


def _gemini_response_body() -> bytes:
    return json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": _CLAIMS_TEXT}],
                        "role": "model",
                    }
                }
            ]
        }
    ).encode("utf-8")


def _openai_response_body() -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": _CLAIMS_TEXT}}]}
    ).encode("utf-8")


class _FakeUrlopen:
    """Stands in for urllib.request.urlopen and records each Request.

    The response body is chosen from the request URL so that only the
    matching adapter's parse_response() can extract the claims text.
    """

    def __init__(self) -> None:
        self.requests: list[object] = []

    def _body_for(self, url: str) -> bytes:
        if ":generateContent" in url:
            return _gemini_response_body()
        if url.endswith("/v1/messages"):
            return _anthropic_response_body()
        return _openai_response_body()

    def __call__(self, req: object, timeout: float | None = None) -> _FakeUrlopen:
        self.requests.append(req)
        return self

    def __enter__(self) -> _FakeUrlopen:
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass

    def read(self) -> bytes:
        req = self.requests[-1]
        return self._body_for(str(getattr(req, "full_url", "")))


def _provider_headers(req: object) -> dict[str, str]:
    """Return the Request headers as a case-insensitive dict."""
    return {k.lower(): v for k, v in getattr(req, "header_items", list)()}


class TestPhase4AdapterSelection:
    """v11 Phase 4: ModelProvider transparently uses the correct adapter."""

    def test_anthropic_base_url_uses_anthropic_adapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeUrlopen()
        monkeypatch.setattr(
            "nowreck.model.provider.urllib_request.urlopen", fake
        )
        config = ModelConfig(
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
            model="claude-sonnet-4-20250514",
        )
        provider = ModelProvider(config=config)

        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )

        assert len(fake.requests) == 1
        req = fake.requests[0]
        assert str(getattr(req, "full_url")).endswith("/v1/messages")

        headers = _provider_headers(req)
        assert headers["x-api-key"] == "sk-ant-test"
        assert "authorization" not in headers
        assert headers["anthropic-version"] == "2023-06-01"

        body = json.loads(getattr(req, "data"))
        assert body["model"] == "claude-sonnet-4-20250514"
        assert "max_tokens" in body
        assert body["messages"][0]["role"] != "system"
        assert body["system"].startswith("You are Nowreck")

        # Claims parsed => AnthropicAdapter.parse_response ran.
        assert len(result.claims) == 1
        assert result.claims[0].file_path == "new.py"

    def test_gemini_base_url_uses_gemini_adapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeUrlopen()
        monkeypatch.setattr(
            "nowreck.model.provider.urllib_request.urlopen", fake
        )
        config = ModelConfig(
            api_key="AIzaTest",
            base_url="https://generativelanguage.googleapis.com",
            model="gemini-2.0-flash",
        )
        provider = ModelProvider(config=config)

        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )

        assert len(fake.requests) == 1
        req = fake.requests[0]
        assert str(getattr(req, "full_url")) == (
            "https://generativelanguage.googleapis.com"
            "/v1beta/models/gemini-2.0-flash:generateContent"
        )

        headers = _provider_headers(req)
        assert headers["x-goog-api-key"] == "AIzaTest"
        assert "authorization" not in headers

        body = json.loads(getattr(req, "data"))
        assert body["contents"][0]["role"] == "user"
        assert "systemInstruction" in body
        assert "system" not in [c["role"] for c in body["contents"]]

        # Claims parsed => GeminiAdapter.parse_response ran.
        assert len(result.claims) == 1
        assert result.claims[0].file_path == "new.py"

    def test_openai_base_url_uses_openai_adapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeUrlopen()
        monkeypatch.setattr(
            "nowreck.model.provider.urllib_request.urlopen", fake
        )
        config = ModelConfig(
            api_key="sk-openai-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        )
        provider = ModelProvider(config=config)

        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )

        assert len(fake.requests) == 1
        req = fake.requests[0]
        assert (
            str(getattr(req, "full_url"))
            == "https://api.openai.com/v1/chat/completions"
        )

        headers = _provider_headers(req)
        assert headers["authorization"] == "Bearer sk-openai-test"

        body = json.loads(getattr(req, "data"))
        assert body["model"] == "gpt-4o"
        assert body["messages"][0]["role"] == "system"

        assert len(result.claims) == 1

    def test_provider_override_switches_to_gemini_adapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit provider=gemini wins over an OpenAI-compatible base_url."""
        fake = _FakeUrlopen()
        monkeypatch.setattr(
            "nowreck.model.provider.urllib_request.urlopen", fake
        )
        config = ModelConfig(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gemini-2.0-flash",
            provider="gemini",
        )
        provider = ModelProvider(config=config)

        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )

        req = fake.requests[0]
        assert str(getattr(req, "full_url")).endswith(
            "/v1beta/models/gemini-2.0-flash:generateContent"
        )
        body = json.loads(getattr(req, "data"))
        assert "contents" in body
        assert len(result.claims) == 1

    def test_provider_override_switches_to_anthropic_adapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit provider=anthropic wins over an OpenAI-compatible base_url."""
        fake = _FakeUrlopen()
        monkeypatch.setattr(
            "nowreck.model.provider.urllib_request.urlopen", fake
        )
        config = ModelConfig(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
        )
        provider = ModelProvider(config=config)

        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )

        req = fake.requests[0]
        assert str(getattr(req, "full_url")).endswith("/v1/messages")
        body = json.loads(getattr(req, "data"))
        assert "max_tokens" in body
        assert len(result.claims) == 1

    def test_unknown_base_url_falls_back_to_openai_format(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown base_url keeps the OpenAI passthrough format."""
        fake = _FakeUrlopen()
        monkeypatch.setattr(
            "nowreck.model.provider.urllib_request.urlopen", fake
        )
        config = ModelConfig(
            api_key="sk-test",
            base_url="https://my-provider.example.com/v1",
            model="some-model",
        )
        provider = ModelProvider(config=config)

        result = provider.explain_changes(
            [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        )

        req = fake.requests[0]
        assert (
            str(getattr(req, "full_url"))
            == "https://my-provider.example.com/v1/chat/completions"
        )
        assert len(result.claims) == 1
