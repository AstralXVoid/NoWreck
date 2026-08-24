"""Tests for the provider adapter system (v11 Phase 1).

Covers:
- ProviderAdapter ABC contract
- OpenAIAdapter request building and response parsing
- detect_adapter factory (auto-detection and override)
- _auth_header helper (provider-specific auth)
"""

from __future__ import annotations

import json

import pytest

from nowreck.model.adapters import (
    AnthropicAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    ProviderAdapter,
    _AdapterError,
    detect_adapter,
)
from nowreck.model.provider import (
    ModelConfig,
    ModelProvider,
    _auth_header,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MESSAGES: list[dict[str, str]] = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Say hello"},
]

_VALID_OPENAI_RESPONSE: bytes = json.dumps(
    {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"claims": []}',
                }
            }
        ]
    }
).encode("utf-8")


# ---------------------------------------------------------------------------
# ProviderAdapter ABC
# ---------------------------------------------------------------------------


class TestProviderAdapterABC:
    """Verify that ProviderAdapter cannot be instantiated directly."""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            ProviderAdapter()  # type: ignore[abstract]

    def test_openai_adapter_is_subclass(self) -> None:
        assert issubclass(OpenAIAdapter, ProviderAdapter)

    def test_openai_adapter_has_build_request(self) -> None:
        adapter = OpenAIAdapter()
        assert hasattr(adapter, "build_request")
        assert callable(adapter.build_request)

    def test_openai_adapter_has_parse_response(self) -> None:
        adapter = OpenAIAdapter()
        assert hasattr(adapter, "parse_response")
        assert callable(adapter.parse_response)


# ---------------------------------------------------------------------------
# OpenAIAdapter — build_request
# ---------------------------------------------------------------------------


class TestOpenAIBuildRequest:
    def test_returns_tuple_of_three(self) -> None:
        adapter = OpenAIAdapter()
        result = adapter.build_request(_MESSAGES, "gpt-4o", 0.0)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_url_suffix_is_chat_completions(self) -> None:
        adapter = OpenAIAdapter()
        url_suffix, _headers, _body = adapter.build_request(
            _MESSAGES, "gpt-4o", 0.0,
        )
        assert url_suffix == "/chat/completions"

    def test_body_contains_model(self) -> None:
        adapter = OpenAIAdapter()
        _url, _headers, body = adapter.build_request(_MESSAGES, "gpt-4o", 0.0)
        data = json.loads(body)
        assert data["model"] == "gpt-4o"

    def test_body_contains_messages(self) -> None:
        adapter = OpenAIAdapter()
        _url, _headers, body = adapter.build_request(_MESSAGES, "gpt-4o", 0.0)
        data = json.loads(body)
        assert data["messages"] == _MESSAGES

    def test_body_contains_temperature(self) -> None:
        adapter = OpenAIAdapter()
        _url, _headers, body = adapter.build_request(_MESSAGES, "gpt-4o", 0.7)
        data = json.loads(body)
        assert data["temperature"] == 0.7

    def test_headers_contain_content_type(self) -> None:
        adapter = OpenAIAdapter()
        _url, headers, _body = adapter.build_request(_MESSAGES, "gpt-4o", 0.0)
        assert headers["Content-Type"] == "application/json"

    def test_headers_contain_user_agent(self) -> None:
        adapter = OpenAIAdapter()
        _url, headers, _body = adapter.build_request(_MESSAGES, "gpt-4o", 0.0)
        assert "Mozilla" in headers["User-Agent"]
        assert "Chrome" in headers["User-Agent"]

    def test_headers_do_not_contain_auth(self) -> None:
        """Auth is injected by ModelProvider, not the adapter."""
        adapter = OpenAIAdapter()
        _url, headers, _body = adapter.build_request(_MESSAGES, "gpt-4o", 0.0)
        assert "Authorization" not in headers
        assert "x-api-key" not in headers

    def test_body_is_utf8_bytes(self) -> None:
        adapter = OpenAIAdapter()
        _url, _headers, body = adapter.build_request(_MESSAGES, "gpt-4o", 0.0)
        assert isinstance(body, bytes)

    def test_different_models(self) -> None:
        adapter = OpenAIAdapter()
        _url, _headers, body = adapter.build_request(
            _MESSAGES, "claude-3-opus", 0.5,
        )
        data = json.loads(body)
        assert data["model"] == "claude-3-opus"


# ---------------------------------------------------------------------------
# OpenAIAdapter — parse_response
# ---------------------------------------------------------------------------


class TestOpenAIParseResponse:
    def test_valid_response(self) -> None:
        adapter = OpenAIAdapter()
        content = adapter.parse_response(_VALID_OPENAI_RESPONSE)
        assert content == '{"claims": []}'

    def test_missing_choices(self) -> None:
        adapter = OpenAIAdapter()
        raw = json.dumps({"no_choices": []}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'choices'"):
            adapter.parse_response(raw)

    def test_empty_choices(self) -> None:
        adapter = OpenAIAdapter()
        raw = json.dumps({"choices": []}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'choices'"):
            adapter.parse_response(raw)

    def test_choice_not_dict(self) -> None:
        adapter = OpenAIAdapter()
        raw = json.dumps({"choices": ["not_a_dict"]}).encode("utf-8")
        with pytest.raises(_AdapterError, match="not an object"):
            adapter.parse_response(raw)

    def test_missing_message(self) -> None:
        adapter = OpenAIAdapter()
        raw = json.dumps({"choices": [{"no_message": True}]}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'message'"):
            adapter.parse_response(raw)

    def test_missing_content(self) -> None:
        adapter = OpenAIAdapter()
        raw = json.dumps(
            {"choices": [{"message": {"role": "assistant"}}]}
        ).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'content'"):
            adapter.parse_response(raw)

    def test_content_not_string(self) -> None:
        adapter = OpenAIAdapter()
        raw = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": 123}}]}
        ).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'content'"):
            adapter.parse_response(raw)

    def test_message_not_dict(self) -> None:
        adapter = OpenAIAdapter()
        raw = json.dumps({"choices": [{"message": "not_a_dict"}]}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'message'"):
            adapter.parse_response(raw)

    def test_preserves_full_content_string(self) -> None:
        adapter = OpenAIAdapter()
        long_content = "x" * 10_000
        raw = json.dumps(
            {"choices": [{"message": {"content": long_content}}]}
        ).encode("utf-8")
        assert adapter.parse_response(raw) == long_content


# ---------------------------------------------------------------------------
# detect_adapter — factory
# ---------------------------------------------------------------------------


class TestDetectAdapter:
    def test_openai_url_returns_openai_adapter(self) -> None:
        adapter = detect_adapter("https://api.openai.com/v1")
        assert isinstance(adapter, OpenAIAdapter)

    def test_groq_url_returns_openai_adapter(self) -> None:
        adapter = detect_adapter("https://api.groq.com/openai/v1")
        assert isinstance(adapter, OpenAIAdapter)

    def test_openrouter_url_returns_openai_adapter(self) -> None:
        adapter = detect_adapter("https://openrouter.ai/api/v1")
        assert isinstance(adapter, OpenAIAdapter)

    def test_ollama_url_returns_openai_adapter(self) -> None:
        adapter = detect_adapter("http://localhost:11434/v1")
        assert isinstance(adapter, OpenAIAdapter)

    def test_lmstudio_url_returns_openai_adapter(self) -> None:
        adapter = detect_adapter("http://localhost:1234/v1")
        assert isinstance(adapter, OpenAIAdapter)

    def test_unknown_url_returns_openai_adapter(self) -> None:
        adapter = detect_adapter("https://my-custom-provider.example.com/v1")
        assert isinstance(adapter, OpenAIAdapter)

    def test_anthropic_url_returns_anthropic_adapter(self) -> None:
        adapter = detect_adapter("https://api.anthropic.com/v1")
        assert isinstance(adapter, AnthropicAdapter)

    def test_gemini_url_returns_gemini_adapter(self) -> None:
        adapter = detect_adapter(
            "https://generativelanguage.googleapis.com/v1beta"
        )
        assert isinstance(adapter, GeminiAdapter)

    def test_override_anthropic_returns_anthropic_adapter(self) -> None:
        adapter = detect_adapter(
            "https://api.openai.com/v1",
            provider_override="anthropic",
        )
        assert isinstance(adapter, AnthropicAdapter)

    def test_override_gemini_returns_gemini_adapter(self) -> None:
        adapter = detect_adapter(
            "https://api.openai.com/v1", provider_override="gemini"
        )
        assert isinstance(adapter, GeminiAdapter)

    def test_override_openai_returns_openai_adapter(self) -> None:
        adapter = detect_adapter(
            "https://api.openai.com/v1", provider_override="openai"
        )
        assert isinstance(adapter, OpenAIAdapter)

    def test_override_case_insensitive(self) -> None:
        adapter = detect_adapter(
            "https://api.openai.com/v1", provider_override="OpenAI"
        )
        assert isinstance(adapter, OpenAIAdapter)

    def test_override_unknown_falls_back_to_url_detection(self) -> None:
        adapter = detect_adapter(
            "https://api.openai.com/v1", provider_override="unknown"
        )
        assert isinstance(adapter, OpenAIAdapter)


# ---------------------------------------------------------------------------
# _auth_header — provider-specific auth
# ---------------------------------------------------------------------------


class TestAuthHeader:
    def test_openai_uses_bearer(self) -> None:
        headers = _auth_header("sk-test", "https://api.openai.com/v1")
        assert headers == {"Authorization": "Bearer sk-test"}

    def test_groq_uses_bearer(self) -> None:
        headers = _auth_header("gsk-test", "https://api.groq.com/openai/v1")
        assert headers == {"Authorization": "Bearer gsk-test"}

    def test_anthropic_uses_x_api_key(self) -> None:
        headers = _auth_header("sk-ant-test", "https://api.anthropic.com/v1")
        assert headers == {"x-api-key": "sk-ant-test"}

    def test_gemini_uses_x_goog_api_key(self) -> None:
        headers = _auth_header(
            "AIzaSyTest", "https://generativelanguage.googleapis.com/v1beta"
        )
        assert headers == {"x-goog-api-key": "AIzaSyTest"}

    def test_case_insensitive_url(self) -> None:
        headers = _auth_header("sk-ant-test", "https://API.ANTHROPIC.COM/v1")
        assert headers == {"x-api-key": "sk-ant-test"}

    def test_unknown_provider_uses_bearer(self) -> None:
        headers = _auth_header("custom-key", "https://my-provider.com/v1")
        assert headers == {"Authorization": "Bearer custom-key"}


# ---------------------------------------------------------------------------
# Integration — ModelProvider uses adapter transparently
# ---------------------------------------------------------------------------


class TestModelProviderAdapterIntegration:
    """Verify that ModelProvider._default_http_call uses the adapter
    system without changing existing behavior."""

    def test_model_provider_with_mock_still_works(self) -> None:
        """Existing mock-based tests should pass unchanged."""
        import json

        def _mock_http_ok(
            messages: list[dict[str, str]], config: ModelConfig
        ) -> str:
            return json.dumps(
                {
                    "claims": [
                        {
                            "type": "FILE_CREATED",
                            "file_path": "new.py",
                            "confidence": 0.95,
                            "explanation": "A new file was created.",
                        }
                    ]
                }
            )

        provider = ModelProvider(http_call=_mock_http_ok)
        from pathlib import Path

        from nowreck.detector.change_detector import ChangeType, DetectedChange

        changes = [
            DetectedChange(
                change_type=ChangeType.FILE_CREATED,
                file_path=Path("new.py"),
            )
        ]
        result = provider.explain_changes(changes)
        assert len(result.claims) == 1
        assert result.claims[0].file_path == "new.py"

    def test_model_config_provider_field_defaults_to_none(self) -> None:
        config = ModelConfig()
        assert config.provider is None

    def test_model_config_provider_field_settable(self) -> None:
        config = ModelConfig(provider="anthropic")
        assert config.provider == "anthropic"


# ---------------------------------------------------------------------------
# AnthropicAdapter — build_request
# ---------------------------------------------------------------------------

ANTHROPIC_MESSAGES = [
    {"role": "user", "content": "Say hello"},
]

ANTHROPIC_SYSTEM_MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Say hello"},
]


class TestAnthropicBuildRequest:
    def test_returns_tuple_of_three(self) -> None:
        adapter = AnthropicAdapter()
        result = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0
        )
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_url_suffix_is_messages(self) -> None:
        adapter = AnthropicAdapter()
        url_suffix, _headers, _body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        assert url_suffix == "/v1/messages"

    def test_body_contains_model(self) -> None:
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        data = json.loads(body)
        assert data["model"] == "claude-sonnet-4-20250514"

    def test_body_contains_max_tokens(self) -> None:
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        data = json.loads(body)
        assert "max_tokens" in data
        assert isinstance(data["max_tokens"], int)
        assert data["max_tokens"] > 0

    def test_body_contains_messages(self) -> None:
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        data = json.loads(body)
        assert data["messages"] == ANTHROPIC_MESSAGES

    def test_body_contains_temperature(self) -> None:
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.7,
        )
        data = json.loads(body)
        assert data["temperature"] == 0.7

    def test_system_messages_extracted_to_system_field(self) -> None:
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            ANTHROPIC_SYSTEM_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        data = json.loads(body)
        assert data["system"] == "You are a helpful assistant."
        # System message must NOT appear in messages array.
        for msg in data["messages"]:
            assert msg["role"] != "system"

    def test_multiple_system_messages_joined(self) -> None:
        msgs = [
            {"role": "system", "content": "Rule 1."},
            {"role": "system", "content": "Rule 2."},
            {"role": "user", "content": "Hi"},
        ]
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            msgs, "claude-sonnet-4-20250514", 0.0,
        )
        data = json.loads(body)
        assert data["system"] == "Rule 1.\nRule 2."

    def test_no_system_field_when_no_system_messages(self) -> None:
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        data = json.loads(body)
        assert "system" not in data

    def test_headers_contain_anthropic_version(self) -> None:
        adapter = AnthropicAdapter()
        _url, headers, _body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        assert headers["anthropic-version"] == "2023-06-01"

    def test_headers_do_not_contain_auth(self) -> None:
        adapter = AnthropicAdapter()
        _url, headers, _body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        assert "Authorization" not in headers
        assert "x-api-key" not in headers

    def test_body_is_utf8_bytes(self) -> None:
        adapter = AnthropicAdapter()
        _url, _headers, body = adapter.build_request(
            ANTHROPIC_MESSAGES, "claude-sonnet-4-20250514", 0.0,
        )
        assert isinstance(body, bytes)


# ---------------------------------------------------------------------------
# AnthropicAdapter — parse_response
# ---------------------------------------------------------------------------

_ANTHROPIC_VALID_RESPONSE: bytes = json.dumps(
    {
        "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": '{"claims": []}',
            }
        ],
        "model": "claude-sonnet-4-20250514",
        "stop_reason": "end_turn",
    }
).encode("utf-8")


class TestAnthropicParseResponse:
    def test_valid_response(self) -> None:
        adapter = AnthropicAdapter()
        content = adapter.parse_response(_ANTHROPIC_VALID_RESPONSE)
        assert content == '{"claims": []}'

    def test_missing_content(self) -> None:
        adapter = AnthropicAdapter()
        raw = json.dumps({"no_content": True}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'content'"):
            adapter.parse_response(raw)

    def test_empty_content(self) -> None:
        adapter = AnthropicAdapter()
        raw = json.dumps({"content": []}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'content'"):
            adapter.parse_response(raw)

    def test_no_text_block(self) -> None:
        adapter = AnthropicAdapter()
        raw = json.dumps(
            {
                "content": [
                    {"type": "image", "source": {"data": "..."}}
                ]
            }
        ).encode("utf-8")
        with pytest.raises(_AdapterError, match="no text content block"):
            adapter.parse_response(raw)

    def test_multiple_text_blocks_returns_first(self) -> None:
        adapter = AnthropicAdapter()
        raw = json.dumps(
            {
                "content": [
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ]
            }
        ).encode("utf-8")
        assert adapter.parse_response(raw) == "first"

    def test_skips_non_dict_blocks(self) -> None:
        adapter = AnthropicAdapter()
        raw = json.dumps(
            {
                "content": [
                    "not_a_dict",
                    {"type": "text", "text": "real_text"},
                ]
            }
        ).encode("utf-8")
        assert adapter.parse_response(raw) == "real_text"

    def test_preserves_full_content_string(self) -> None:
        adapter = AnthropicAdapter()
        long_content = "x" * 10_000
        raw = json.dumps(
            {"content": [{"type": "text", "text": long_content}]}
        ).encode("utf-8")
        assert adapter.parse_response(raw) == long_content


# ---------------------------------------------------------------------------
# detect_adapter — Anthropic URLs
# ---------------------------------------------------------------------------


class TestDetectAdapterAnthropic:
    def test_anthropic_url_returns_anthropic_adapter(self) -> None:
        adapter = detect_adapter("https://api.anthropic.com/v1")
        assert isinstance(adapter, AnthropicAdapter)

    def test_override_anthropic_returns_anthropic_adapter(self) -> None:
        adapter = detect_adapter(
            "https://api.openai.com/v1",
            provider_override="anthropic",
        )
        assert isinstance(adapter, AnthropicAdapter)

    def test_anthropic_adapter_round_trip(self) -> None:
        """Build request then parse response — full cycle."""
        adapter = AnthropicAdapter()
        msgs = [{"role": "user", "content": "test"}]
        url, headers, body = adapter.build_request(
            msgs, "claude-sonnet-4-20250514", 0.0
        )
        assert url == "/v1/messages"
        assert "anthropic-version" in headers

        response = json.dumps(
            {"content": [{"type": "text", "text": "hello"}]}
        ).encode()
        assert adapter.parse_response(response) == "hello"


# ---------------------------------------------------------------------------
# GeminiAdapter — build_request
# ---------------------------------------------------------------------------

GEMINI_MESSAGES = [
    {"role": "user", "content": "Say hello"},
]

GEMINI_SYSTEM_MESSAGES = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Say hello"},
]


class TestGeminiBuildRequest:
    def test_returns_tuple_of_three(self) -> None:
        adapter = GeminiAdapter()
        result = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.0
        )
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_url_suffix_contains_model_and_generate(self) -> None:
        adapter = GeminiAdapter()
        url_suffix, _headers, _body = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.0,
        )
        assert "/v1beta/models/gemini-2.0-flash:generateContent" == url_suffix

    def test_body_contains_contents(self) -> None:
        adapter = GeminiAdapter()
        _url, _headers, body = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.0,
        )
        data = json.loads(body)
        assert "contents" in data
        assert isinstance(data["contents"], list)
        assert len(data["contents"]) == 1

    def test_body_parts_structure(self) -> None:
        adapter = GeminiAdapter()
        _url, _headers, body = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.0,
        )
        data = json.loads(body)
        content = data["contents"][0]
        assert content["role"] == "user"
        assert content["parts"] == [{"text": "Say hello"}]

    def test_body_contains_temperature(self) -> None:
        adapter = GeminiAdapter()
        _url, _headers, body = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.7,
        )
        data = json.loads(body)
        assert data["generationConfig"]["temperature"] == 0.7

    def test_assistant_role_becomes_model(self) -> None:
        msgs = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Bye"},
        ]
        adapter = GeminiAdapter()
        _url, _headers, body = adapter.build_request(
            msgs, "gemini-2.0-flash", 0.0,
        )
        data = json.loads(body)
        roles = [c["role"] for c in data["contents"]]
        assert roles == ["user", "model", "user"]

    def test_system_messages_to_system_instruction(self) -> None:
        adapter = GeminiAdapter()
        _url, _headers, body = adapter.build_request(
            GEMINI_SYSTEM_MESSAGES, "gemini-2.0-flash", 0.0,
        )
        data = json.loads(body)
        assert data["systemInstruction"] == {
            "parts": [{"text": "You are helpful."}]
        }
        # System message must NOT be in contents.
        for c in data["contents"]:
            assert c.get("role") != "system"

    def test_no_system_instruction_when_no_system(self) -> None:
        adapter = GeminiAdapter()
        _url, _headers, body = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.0,
        )
        data = json.loads(body)
        assert "systemInstruction" not in data

    def test_headers_do_not_contain_auth(self) -> None:
        adapter = GeminiAdapter()
        _url, headers, _body = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.0,
        )
        assert "Authorization" not in headers
        assert "x-goog-api-key" not in headers

    def test_body_is_utf8_bytes(self) -> None:
        adapter = GeminiAdapter()
        _url, _headers, body = adapter.build_request(
            GEMINI_MESSAGES, "gemini-2.0-flash", 0.0,
        )
        assert isinstance(body, bytes)


# ---------------------------------------------------------------------------
# GeminiAdapter — parse_response
# ---------------------------------------------------------------------------

_GEMINI_VALID_RESPONSE: bytes = json.dumps(
    {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": '{"claims": []}'},],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ]
    }
).encode("utf-8")


class TestGeminiParseResponse:
    def test_valid_response(self) -> None:
        adapter = GeminiAdapter()
        content = adapter.parse_response(_GEMINI_VALID_RESPONSE)
        assert content == '{"claims": []}'

    def test_missing_candidates(self) -> None:
        adapter = GeminiAdapter()
        raw = json.dumps({"no_candidates": True}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'candidates'"):
            adapter.parse_response(raw)

    def test_empty_candidates(self) -> None:
        adapter = GeminiAdapter()
        raw = json.dumps({"candidates": []}).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'candidates'"):
            adapter.parse_response(raw)

    def test_candidate_missing_content(self) -> None:
        adapter = GeminiAdapter()
        raw = json.dumps({"candidates": [{"finishReason": "STOP"}]}).encode(
            "utf-8"
        )
        with pytest.raises(_AdapterError, match="missing 'content'"):
            adapter.parse_response(raw)

    def test_content_missing_parts(self) -> None:
        adapter = GeminiAdapter()
        raw = json.dumps(
            {"candidates": [{"content": {"role": "model"}}]}
        ).encode("utf-8")
        with pytest.raises(_AdapterError, match="missing 'parts'"):
            adapter.parse_response(raw)

    def test_no_text_part(self) -> None:
        adapter = GeminiAdapter()
        raw = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"inlineData": {"data": "..."}}],
                            "role": "model",
                        }
                    }
                ]
            }
        ).encode("utf-8")
        with pytest.raises(_AdapterError, match="no text part"):
            adapter.parse_response(raw)

    def test_multiple_parts_returns_first_text(self) -> None:
        adapter = GeminiAdapter()
        raw = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "first"},
                                {"text": "second"},
                            ],
                            "role": "model",
                        }
                    }
                ]
            }
        ).encode("utf-8")
        assert adapter.parse_response(raw) == "first"

    def test_preserves_full_content_string(self) -> None:
        adapter = GeminiAdapter()
        long_content = "x" * 10_000
        raw = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": long_content}],
                            "role": "model",
                        }
                    }
                ]
            }
        ).encode("utf-8")
        assert adapter.parse_response(raw) == long_content


# ---------------------------------------------------------------------------
# detect_adapter — Gemini URLs
# ---------------------------------------------------------------------------


class TestDetectAdapterGemini:
    def test_gemini_url_returns_gemini_adapter(self) -> None:
        adapter = detect_adapter(
            "https://generativelanguage.googleapis.com/v1beta"
        )
        assert isinstance(adapter, GeminiAdapter)

    def test_override_gemini_returns_gemini_adapter(self) -> None:
        adapter = detect_adapter(
            "https://api.openai.com/v1",
            provider_override="gemini",
        )
        assert isinstance(adapter, GeminiAdapter)

    def test_gemini_adapter_round_trip(self) -> None:
        """Build request then parse response — full cycle."""
        adapter = GeminiAdapter()
        msgs = [{"role": "user", "content": "test"}]
        url, headers, body = adapter.build_request(
            msgs, "gemini-2.0-flash", 0.0
        )
        assert "/v1beta/models/gemini-2.0-flash:generateContent" == url

        response = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "hello"}],
                            "role": "model",
                        }
                    }
                ]
            }
        ).encode()
        assert adapter.parse_response(response) == "hello"
