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
