"""Provider adapters for non-OpenAI API formats.

Each adapter translates between the provider's native request/response
format and the internal OpenAI-compatible format used by ModelProvider.

Adapters are isolated — they do not touch the verifier, scanner,
reporter, or any other component.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import cast

# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------


class ProviderAdapter(ABC):
    """Translates between a provider's native format and OpenAI format.

    The adapter receives OpenAI-format messages and returns a
    provider-specific request body.  It also provides auth headers
    and response parsing.
    """

    @abstractmethod
    def build_request(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
    ) -> tuple[str, dict[str, str], bytes]:
        """Build the HTTP request for this provider.

        Args:
            messages: OpenAI-format message list (``{"role": ..., "content": ...}``).
            model: Model identifier.
            temperature: Sampling temperature.

        Returns:
            ``(url, headers, body)`` — ready for ``urllib.request.urlopen()``.
        """

    @abstractmethod
    def parse_response(self, raw: bytes) -> str:
        """Extract the assistant's content from the provider response.

        Returns the plain text content, equivalent to OpenAI's
        ``choices[0].message.content``.
        """


# ---------------------------------------------------------------------------
# Browser User-Agent (shared across adapters)
# ---------------------------------------------------------------------------

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_COMMON_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "User-Agent": _BROWSER_UA,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# OpenAI-compatible adapter (passthrough)
# ---------------------------------------------------------------------------


class OpenAIAdapter(ProviderAdapter):
    """Passthrough adapter for OpenAI-compatible endpoints.

    Handles: OpenAI, Groq, OpenRouter, Grok (xAI), Kimi (Moonshot),
    Ollama, LM Studio, and any other OpenAI-compatible provider.
    """

    def build_request(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
    ) -> tuple[str, dict[str, str], bytes]:
        import json

        url_suffix = "/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")

        headers = dict(_COMMON_HEADERS)
        # API key is injected by ModelProvider — not the adapter's job.

        return (url_suffix, headers, body)

    def parse_response(self, raw: bytes) -> str:
        import json

        data: dict[str, object] = json.loads(raw)

        raw_choices: object = data.get("choices")
        if not isinstance(raw_choices, list) or not raw_choices:
            raise _AdapterError("API response missing 'choices'")

        choice_list: list[dict[str, object]] = cast(
            "list[dict[str, object]]", raw_choices
        )
        raw_choice: object = choice_list[0]
        if not isinstance(raw_choice, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise _AdapterError("API response choice is not an object")

        choice: dict[str, object] = raw_choice
        raw_message: object = choice.get("message")
        if not isinstance(raw_message, dict):
            raise _AdapterError("API response choice missing 'message'")

        message: dict[str, object] = cast("dict[str, object]", raw_message)
        content = message.get("content")
        if not isinstance(content, str):
            raise _AdapterError("API response message missing 'content'")

        return content


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------


# Default max_tokens — Anthropic requires this field.
_ANTHROPIC_DEFAULT_MAX_TOKENS = 4096


class AnthropicAdapter(ProviderAdapter):
    """Adapter for the Anthropic Messages API (``/v1/messages``).

    Translates OpenAI-format messages into Anthropic's format:

    * System messages are extracted from the ``messages`` list and
      placed in the top-level ``system`` field.
    * ``max_tokens`` is set to a safe default.
    * The response ``content`` array is flattened to a single string.
    """

    def build_request(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
    ) -> tuple[str, dict[str, str], bytes]:
        import json

        url_suffix = "/v1/messages"

        # Separate system messages from conversation messages.
        system_parts: list[str] = []
        conversation: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg["content"])
            else:
                conversation.append(msg)

        body_payload: dict[str, object] = {
            "model": model,
            "max_tokens": _ANTHROPIC_DEFAULT_MAX_TOKENS,
            "messages": conversation,
            "temperature": temperature,
        }
        if system_parts:
            body_payload["system"] = "\n".join(system_parts)

        body = json.dumps(body_payload).encode("utf-8")

        headers = dict(_COMMON_HEADERS)
        # Auth is injected by ModelProvider via _auth_header().
        # Anthropic also requires this version header.
        headers["anthropic-version"] = "2023-06-01"

        return (url_suffix, headers, body)

    def parse_response(self, raw: bytes) -> str:
        import json

        data: dict[str, object] = json.loads(raw)

        # Anthropic wraps the response in a "content" array of blocks.
        raw_content: object = data.get("content")
        if not isinstance(raw_content, list) or not raw_content:
            raise _AdapterError("Anthropic response missing 'content'")

        content_blocks: list[dict[str, object]] = cast(
            "list[dict[str, object]]", raw_content
        )

        # Find the first text block.
        for block in content_blocks:
            if not isinstance(block, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                continue
            block_typed: dict[str, object] = block
            block_type = block_typed.get("type")
            if block_type == "text":
                text = block_typed.get("text")
                if isinstance(text, str):
                    return text

        raise _AdapterError(
            "Anthropic response contains no text content block"
        )


# ---------------------------------------------------------------------------
# Gemini adapter
# ---------------------------------------------------------------------------


class GeminiAdapter(ProviderAdapter):
    """Adapter for the Google Gemini ``generateContent`` API.

    Endpoint: ``POST /v1beta/models/{model}:generateContent``

    Translates OpenAI-format messages into Gemini's format:

    * System messages are placed in the top-level
      ``systemInstruction`` field.
    * Conversation messages become ``contents`` with ``parts``.
    * The response ``candidates[0].content.parts[0].text`` is
      extracted.
    """

    def build_request(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
    ) -> tuple[str, dict[str, str], bytes]:
        import json

        # Gemini uses model-specific URL paths.
        url_suffix = f"/v1beta/models/{model}:generateContent"

        # Separate system messages from conversation.
        system_parts: list[str] = []
        contents: list[dict[str, object]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                # Gemini uses "user" and "model" (not "assistant").
                gemini_role = "model" if role == "assistant" else "user"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": content}],
                })

        body_payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }
        if system_parts:
            body_payload["systemInstruction"] = {
                "parts": [{"text": "\n".join(system_parts)}],
            }

        body = json.dumps(body_payload).encode("utf-8")

        headers = dict(_COMMON_HEADERS)
        # Auth is injected by ModelProvider via _auth_header().

        return (url_suffix, headers, body)

    def parse_response(self, raw: bytes) -> str:
        import json

        data: dict[str, object] = json.loads(raw)

        # Gemini wraps the response in "candidates" -> "content" -> "parts".
        raw_candidates: object = data.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise _AdapterError("Gemini response missing 'candidates'")

        candidates: list[dict[str, object]] = cast(
            "list[dict[str, object]]", raw_candidates
        )
        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise _AdapterError("Gemini candidate is not an object")

        candidate: dict[str, object] = first_candidate
        raw_content: object = candidate.get("content")
        if not isinstance(raw_content, dict):
            raise _AdapterError("Gemini candidate missing 'content'")

        content_obj: dict[str, object] = cast("dict[str, object]", raw_content)
        raw_parts: object = content_obj.get("parts")
        if not isinstance(raw_parts, list) or not raw_parts:
            raise _AdapterError("Gemini content missing 'parts'")

        parts: list[dict[str, object]] = cast(
            "list[dict[str, object]]", raw_parts
        )
        for part in parts:
            if not isinstance(part, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                continue
            text = part.get("text")
            if isinstance(text, str):
                return text

        raise _AdapterError("Gemini response contains no text part")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class _AdapterError(Exception):
    """Raised when an adapter fails to parse a response."""


# ---------------------------------------------------------------------------
# Factory — auto-detect adapter from base_url
# ---------------------------------------------------------------------------


def detect_adapter(
    base_url: str,
    provider_override: str | None = None,
) -> ProviderAdapter:
    """Select the correct adapter based on the base URL or explicit override.

    Args:
        base_url: The configured API base URL.
        provider_override: Optional explicit provider name
            (``"openai"``, ``"anthropic"``, ``"gemini"``).

    Returns:
        A ``ProviderAdapter`` instance.
    """
    if provider_override:
        key = provider_override.lower().strip()
        if key == "anthropic":
            return _make_anthropic()
        if key == "gemini":
            return _make_gemini()
        # Unknown override — fall through to URL detection.
        # (OpenAI-compatible is the default.)

    url_lower = base_url.lower()

    if "api.anthropic.com" in url_lower:
        return _make_anthropic()
    if "generativelanguage.googleapis.com" in url_lower:
        return _make_gemini()

    return OpenAIAdapter()


def _make_anthropic() -> ProviderAdapter:
    """Create the Anthropic adapter."""
    return AnthropicAdapter()


def _make_gemini() -> ProviderAdapter:
    """Create the Gemini adapter."""
    return GeminiAdapter()
