from __future__ import annotations

import datetime
import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from nowreck.claims.models import Claim
from nowreck.claims.parser import ClaimParser, ParseResult
from nowreck.detector.change_detector import DetectedChange
from nowreck.model.adapters import detect_adapter
from nowreck.model.prompts import PromptBuilder

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for the OpenAI-compatible model provider.

    Attributes:
        api_key: API key for authentication.  Falls back to the
            ``NOWRECK_API_KEY`` environment variable when empty.
        base_url: Base URL of the API.  Defaults to the OpenAI API.
            The adapter is auto-detected from this URL.
        model: Model identifier (e.g. ``gpt-4o``, ``claude-sonnet-4-20250514``).
        temperature: Sampling temperature (0.0 = deterministic).
        max_retries: Number of repair attempts after a failed parse.
            0 means no retry.
        failed_dir: Directory where failed responses are saved.
            ``None`` means save to ``.nowreck/failed/`` relative to
            the current working directory.  Set to an empty ``Path``
            to disable saving.
        provider: Optional explicit provider override (``"openai"``,
            ``"anthropic"``, ``"gemini"``).  When ``None``, the adapter
            is auto-detected from ``base_url``.
    """

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    temperature: float = 0.0
    max_retries: int = 1
    failed_dir: Path | None = None
    provider: str | None = None

    def resolve_api_key(self) -> str:
        """Return the API key, falling back to the environment
        variable."""
        if self.api_key:
            return self.api_key
        env_key = os.environ.get("NOWRECK_API_KEY")
        if env_key:
            return env_key
        return ""

    def resolve_failed_dir(self) -> Path:
        """Return the directory for failed responses.

        Defaults to ``.nowreck/failed/`` relative to the current
        working directory.  Saving is best-effort — failures are
        silently ignored.
        """
        if self.failed_dir is None:
            return Path.cwd() / ".nowreck" / "failed"
        return self.failed_dir


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelResult:
    """The outcome of a model interaction.

    Attributes:
        claims: Successfully parsed claims.  Empty when parsing fails
            after all retries.
        changes: ``DetectedChange`` objects derived from *claims*.
            Populated by :meth:`ModelProvider.changes_from_prompt`;
            empty in the ``explain_changes`` flow.
        parse_result: The ``ParseResult`` from the **last** parse
            attempt.
        raw_response: The raw text returned by the model (the last
            attempt if multiple).
        attempts: Number of model calls made (1 or 1 + retries).
        messages: The messages list that was sent (useful for debugging).
        patch: An optional unified diff patch extracted from the model
            response.  ``None`` when the response does not include a
            patch (pre-v10 format).
    """

    claims: list[Claim] = field(default_factory=list)
    changes: list[DetectedChange] = field(default_factory=list)
    parse_result: ParseResult | None = None
    raw_response: str = ""
    attempts: int = 1
    messages: list[dict[str, str]] = field(default_factory=list)
    patch: str | None = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _mask_key(key: str) -> str:
    """Mask an API key for safe display.

    Shows first 4 and last 4 characters with ``****`` in between.
    Short keys (<=8 chars) are fully masked.
    """
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def _mask_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Mask Authorization headers in a messages list.

    Returns a new list — the original is not mutated.
    """
    masked: list[dict[str, str]] = []
    for msg in messages:
        new_msg = dict(msg)
        # No headers to mask in standard chat messages
        masked.append(new_msg)
    return masked


class ModelError(Exception):
    """Raised when the model API call fails irrecoverably."""


def _auth_header(api_key: str, base_url: str) -> dict[str, str]:
    """Return the correct authorization header for the provider.

    Anthropic uses ``x-api-key``, Gemini uses ``x-goog-api-key``,
    and everything else uses ``Authorization: Bearer``.
    """
    url_lower = base_url.lower()
    if "api.anthropic.com" in url_lower:
        return {"x-api-key": api_key}
    if "generativelanguage.googleapis.com" in url_lower:
        return {"x-goog-api-key": api_key}
    return {"Authorization": f"Bearer {api_key}"}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ModelProvider:
    """OpenAI-compatible model provider for Nowreck.

    Handles prompt construction, API calls, structured JSON response
    parsing, repair retries, and saving failed responses.

    The actual HTTP call is delegated to a callable so tests can inject
    a mock without hitting the network.
    """

    def __init__(
        self,
        config: ModelConfig | None = None,
        *,
        http_call: Callable[..., str] | None = None,
    ) -> None:
        self._config = config or ModelConfig()
        # Allow test injection of a fake HTTP callable.
        self._http_call = http_call or self._default_http_call

    # ------------------------------------------------------------------
    # Public API — pre/post mode
    # ------------------------------------------------------------------

    def explain_changes(
        self,
        changes: list[DetectedChange],
    ) -> ModelResult:
        """Send detected changes to the model and return parsed claims.

        This is the **pre/post** flow: the change detector has already
        found structural differences, and the model explains them.

        Args:
            changes: The structural changes detected by the change
                detector.

        Returns:
            A ``ModelResult`` with parsed claims (may be empty on
            failure).

        Raises:
            ModelError: If the API call fails irrecoverably (network
                error, bad auth, etc.).
        """
        messages = PromptBuilder.build(changes)
        return self._call_with_retry(messages)

    # ------------------------------------------------------------------
    # Public API — prompt mode
    # ------------------------------------------------------------------

    def changes_from_prompt(
        self,
        prompt: str,
    ) -> ModelResult:
        """Send a natural-language prompt to the model and return both
        the parsed claims and the ``DetectedChange`` objects derived from
        them.

        This is the **single-prompt** flow: the model generates the
        diff (as claims) from a description, and the claims are
        converted to ``DetectedChange`` objects so the verifier can
        match them.

        Args:
            prompt: A natural-language description of code changes.

        Returns:
            A ``ModelResult`` with *claims* (parsed from the model)
            and *changes* (derived from the claims).

        Raises:
            ModelError: If the API call fails irrecoverably (network
                error, bad auth, etc.).
        """
        messages = PromptBuilder.for_prompt(prompt)
        result = self._call_with_retry(messages)

        # Derive DetectedChanges from the parsed claims.
        changes = PromptBuilder.claims_to_changes(result.claims)

        return ModelResult(
            claims=result.claims,
            changes=changes,
            parse_result=result.parse_result,
            raw_response=result.raw_response,
            attempts=result.attempts,
            messages=result.messages,
            patch=result.patch,
        )

    def changes_from_prompt_v10(
        self,
        prompt: str,
        repo_context: str = "",
    ) -> ModelResult:
        """Send a prompt to the model and return claims + patch.

        This is the **v10 independent verification** flow: the model
        returns both structured claims AND a unified diff patch.  The
        caller applies the patch, scans the resulting state, and
        verifies claims against independently observed changes.

        Args:
            prompt: A natural-language description of code changes.
            repo_context: Optional context about the repository.

        Returns:
            A ``ModelResult`` with *claims* and *patch*.

        Raises:
            ModelError: If the API call fails irrecoverably.
        """
        messages = PromptBuilder.for_prompt_v10(prompt, repo_context)
        return self._call_with_retry(messages)

    # ------------------------------------------------------------------
    # Shared retry logic
    # ------------------------------------------------------------------

    def _call_with_retry(
        self,
        messages: list[dict[str, str]],
    ) -> ModelResult:
        """Call the model with *messages*, parse the response, and retry
        on parse failure up to ``max_retries`` times.

        Each retry attempt sends a fresh conversation consisting of the
        original messages plus the failed response and a repair request.
        """
        raw_response = self._http_call(
            messages=messages,
            config=self._config,
        )
        parse_result = ClaimParser.parse(raw_response)
        attempts = 1

        # Repair loop — at most max_retries additional attempts.
        # Each retry rebuilds from the original messages so the model
        # sees a focused repair prompt rather than a growing history.
        for _ in range(self._config.max_retries):
            if parse_result.success:
                break

            retry_msgs: list[dict[str, str]] = list(messages)
            retry_msgs.append(
                {
                    "role": "assistant",
                    "content": raw_response,
                }
            )
            retry_msgs.append(
                {
                    "role": "user",
                    "content": (
                        "The response above has the following errors:\n"
                        + "\n".join(parse_result.errors)
                        + "\n\nPlease fix the response. Ensure it is "
                        "valid JSON matching the required format."
                    ),
                }
            )

            raw_response = self._http_call(
                messages=retry_msgs,
                config=self._config,
            )
            parse_result = ClaimParser.parse(raw_response)
            attempts += 1

        # Save failed responses for debugging.
        if not parse_result.success:
            self._save_failure(messages, raw_response, parse_result)

        return ModelResult(
            claims=parse_result.claims,
            parse_result=parse_result,
            raw_response=raw_response,
            attempts=attempts,
            messages=messages,
            patch=parse_result.patch,
        )

    # ------------------------------------------------------------------
    # HTTP call — default implementation
    # ------------------------------------------------------------------

    @staticmethod
    def _default_http_call(
        messages: list[dict[str, str]],
        config: ModelConfig,
    ) -> str:
        """Make a synchronous HTTP POST to the model API.

        Uses a ``ProviderAdapter`` to build the request and parse the
        response.  The adapter is auto-detected from ``config.base_url``
        (or overridden by ``config.provider``).

        Raises:
            ModelError: On network failure, bad status code, or
                missing response content.
        """
        api_key = config.resolve_api_key()
        if not api_key:
            raise ModelError(
                "No API key provided. Set NOWRECK_API_KEY environment "
                "variable or pass api_key to ModelConfig."
            )

        adapter = detect_adapter(config.base_url, config.provider)
        url_suffix, headers, body = adapter.build_request(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
        )

        req = urllib_request.Request(
            url=f"{config.base_url.rstrip('/')}{url_suffix}",
            data=body,
            headers={**headers, **_auth_header(api_key, config.base_url)},
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=120) as resp:
                raw: bytes = resp.read()
        except urllib_error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            masked_body = _mask_key(error_body)
            raise ModelError(f"API returned {exc.code}: {masked_body}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelError(f"Request failed: {exc}") from exc

        try:
            return adapter.parse_response(raw)
        except Exception as exc:
            raise ModelError(f"Failed to parse provider response: {exc}") from exc

    # ------------------------------------------------------------------
    # Failure persistence
    # ------------------------------------------------------------------

    def _save_failure(
        self,
        messages: list[dict[str, str]],
        raw_response: str,
        parse_result: ParseResult,
    ) -> None:
        """Write a failed model interaction to disk for debugging."""
        failed_dir = self._config.resolve_failed_dir()

        try:
            failed_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return  # Best-effort saving.

        timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%dT%H%M%S")
        suffix = uuid.uuid4().hex[:8]
        filename = f"failed_{timestamp}_{suffix}.json"

        # Mask API keys in saved messages
        masked_messages = _mask_messages(messages)

        payload = {
            "timestamp": timestamp,
            "messages": masked_messages,
            "raw_response": raw_response,
            "parse_errors": parse_result.errors,
        }

        try:
            (failed_dir / filename).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
