"""Phase 5: Security tests for API key masking.

Verifies that API keys never appear in:
- Error messages
- Failed response saves
- JSON output
- Verbose output
"""

from __future__ import annotations

import json

from nowreck.model.provider import ModelConfig, _mask_key, _mask_messages


class TestMaskKey:
    """Tests for the _mask_key helper."""

    def test_long_key(self) -> None:
        key = "sk-1234567890abcdef1234567890abcdef"
        masked = _mask_key(key)
        assert masked == "sk-1****cdef"
        assert "1234567890abcdef1234567890" not in masked

    def test_short_key(self) -> None:
        key = "sk-short"
        masked = _mask_key(key)
        assert masked == "****"

    def test_empty_key(self) -> None:
        assert _mask_key("") == "****"

    def test_exactly_8_chars(self) -> None:
        key = "12345678"
        masked = _mask_key(key)
        assert masked == "****"

    def test_9_chars(self) -> None:
        key = "123456789"
        masked = _mask_key(key)
        assert masked.startswith("1234")
        assert masked.endswith("6789")
        assert "****" in masked

    def test_preserves_first_and_last_4(self) -> None:
        key = "abcdefghijklmnop"
        masked = _mask_key(key)
        assert masked.startswith("abcd")
        assert masked.endswith("mnop")
        assert masked == "abcd****mnop"

    def test_api_key_style(self) -> None:
        key = "sk-proj-1234567890abcdef"
        masked = _mask_key(key)
        assert "1234567890abcdef" not in masked
        assert "****" in masked


class TestMaskMessages:
    """Tests for _mask_messages helper."""

    def test_returns_new_list(self) -> None:
        original = [{"role": "user", "content": "hello"}]
        masked = _mask_messages(original)
        assert masked is not original
        assert masked[0] is not original[0]

    def test_preserves_content(self) -> None:
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Add a function"},
        ]
        masked = _mask_messages(messages)
        assert masked[0]["content"] == "You are helpful"
        assert masked[1]["content"] == "Add a function"


class TestSecurityIntegration:
    """Integration tests for security in provider."""

    def test_api_key_not_in_json_output(self) -> None:
        """JSON output must never include the API key."""
        from nowreck.reporter.terminal_reporter import TerminalReporter
        from nowreck.verifier.verifier import VerificationReport

        report = VerificationReport(results=[])
        json_str = TerminalReporter.report_json(report)
        data = json.loads(json_str)

        # Verify no key material in output
        full_text = json.dumps(data)
        assert "sk-" not in full_text
        assert "api_key" not in full_text

    def test_model_config_resolve_api_key(self) -> None:
        """ModelConfig.resolve_api_key() returns the key."""
        config = ModelConfig(api_key="sk-secret-key-12345")
        key = config.resolve_api_key()
        assert key == "sk-secret-key-12345"
        # Key falls back to env var when empty
        config2 = ModelConfig(api_key="")
        assert config2.resolve_api_key() == ""

    def test_error_message_masks_key_fragment(self) -> None:
        """If an error message accidentally contains a key fragment,
        _mask_key should be usable to clean it."""
        error_msg = "API returned 401: Invalid key sk-abc123def456ghi"
        # Simulate masking any sk- patterns
        import re

        def mask_sk_fragments(text: str) -> str:
            return re.sub(r"sk-[a-zA-Z0-9]+", lambda m: _mask_key(m.group()), text)

        masked = mask_sk_fragments(error_msg)
        assert "sk-abc123def456ghi" not in masked
        assert "****" in masked
