from __future__ import annotations

import datetime
import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from urllib import error as urllib_error
from urllib import request as urllib_request

from nowreck.claims.models import Claim
from nowreck.claims.parser import ClaimParser, ParseResult
from nowreck.detector.change_detector import DetectedChange
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
        base_url: Base URL of the OpenAI-compatible API.  Defaults to
            the OpenAI API.
        model: Model identifier (e.g. ``gpt-4o``, ``claude-3-opus``).
        temperature: Sampling temperature (0.0 = deterministic).
        max_retries: Number of repair attempts after a failed parse.
            0 means no retry.
        failed_dir: Directory where failed responses are saved.
            ``None`` means save to ``.nowreck/failed/`` relative to
            the current working directory.  Set to an empty ``Path``
            to disable saving.
    """

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    temperature: float = 0.0
    max_retries: int = 1
    failed_dir: Path | None = None

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
    """

    claims: list[Claim] = field(default_factory=list)
    changes: list[DetectedChange] = field(default_factory=list)
    parse_result: ParseResult | None = None
    raw_response: str = ""
    attempts: int = 1
    messages: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ModelError(Exception):
    """Raised when the model API call fails irrecoverably."""


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
        )

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
        )

    # ------------------------------------------------------------------
    # HTTP call — default implementation
    # ------------------------------------------------------------------

    @staticmethod
    def _default_http_call(
        messages: list[dict[str, str]],
        config: ModelConfig,
    ) -> str:
        """Make a synchronous HTTP POST to the Chat Completions API.

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

        body = json.dumps(
            {
                "model": config.model,
                "messages": messages,
                "temperature": config.temperature,
            }
        ).encode("utf-8")

        # Use a realistic browser User-Agent to avoid Cloudflare 1010
        # blocks that some providers (e.g. Groq) enforce on bare
        # urllib requests.
        browser_ua = (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

        req = urllib_request.Request(
            url=f"{config.base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": browser_ua,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=120) as resp:
                data: dict[str, object] = json.loads(resp.read())
        except urllib_error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ModelError(f"API returned {exc.code}: {error_body}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelError(f"Request failed: {exc}") from exc

        raw_choices: object = data.get("choices")
        if not isinstance(raw_choices, list) or not raw_choices:
            raise ModelError("API response missing 'choices'")

        raw_choice: object = cast("object", raw_choices[0])
        if not isinstance(raw_choice, dict):
            raise ModelError("API response choice is not an object")

        choice: dict[str, object] = cast("dict[str, object]", raw_choice)
        raw_message: object = choice.get("message")
        if not isinstance(raw_message, dict):
            raise ModelError("API response choice missing 'message'")

        message: dict[str, object] = cast("dict[str, object]", raw_message)
        content: object = message.get("content")
        if not isinstance(content, str):
            raise ModelError("API response message missing 'content'")

        return content

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

        payload = {
            "timestamp": timestamp,
            "messages": messages,
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
