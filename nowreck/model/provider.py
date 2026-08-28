from __future__ import annotations

import datetime
import json
import os
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from nowreck.claims.models import Claim, ClaimType
from nowreck.claims.parser import ClaimParser, ParseResult
from nowreck.detector.change_detector import (
    ChangeType,
    DetectedChange,
    change_sort_key,
)
from nowreck.model.adapters import resolve_provider
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

    def __post_init__(self) -> None:
        """Validate configuration values at construction time.

        Raises:
            ValueError: If ``temperature`` is outside ``[0.0, 5.0]``.
        """
        # NaN fails the chained comparison, so it is rejected here too.
        if not 0.0 <= self.temperature <= 5.0:
            raise ValueError(
                f"temperature must be within [0.0, 5.0], got {self.temperature!r}"
            )
        if self.temperature > 2.0:
            warnings.warn(
                f"temperature {self.temperature} exceeds the OpenAI "
                "maximum (2.0); Anthropic rejects anything above 1.0.",
                UserWarning,
                stacklevel=2,
            )

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


_CLAIM_TYPE_TO_CHANGE: dict[ClaimType, ChangeType] = {
    ClaimType.ADD_FUNCTION: ChangeType.ADD_FUNCTION,
    ClaimType.REMOVE_FUNCTION: ChangeType.REMOVE_FUNCTION,
    ClaimType.ADD_CLASS: ChangeType.ADD_CLASS,
    ClaimType.REMOVE_CLASS: ChangeType.REMOVE_CLASS,
    ClaimType.ADD_INTERFACE: ChangeType.ADD_INTERFACE,
    ClaimType.REMOVE_INTERFACE: ChangeType.REMOVE_INTERFACE,
    ClaimType.ADD_ENUM: ChangeType.ADD_ENUM,
    ClaimType.REMOVE_ENUM: ChangeType.REMOVE_ENUM,
    ClaimType.ADD_TYPE_ALIAS: ChangeType.ADD_TYPE_ALIAS,
    ClaimType.REMOVE_TYPE_ALIAS: ChangeType.REMOVE_TYPE_ALIAS,
    ClaimType.FILE_CREATED: ChangeType.FILE_CREATED,
    ClaimType.FILE_DELETED: ChangeType.FILE_DELETED,
}


def _claims_to_changes(claims: list[Claim]) -> list[DetectedChange]:
    """Convert parsed claims into ``DetectedChange`` records.

    Private relocation of the former (deprecated)
    ``PromptBuilder.claims_to_changes`` — used only by the legacy
    :meth:`ModelProvider.changes_from_prompt` flow.
    """
    changes: list[DetectedChange] = []
    for claim in claims:
        change_type = _CLAIM_TYPE_TO_CHANGE.get(claim.type)
        if change_type is None:
            continue
        changes.append(
            DetectedChange(
                change_type=change_type,
                file_path=claim.to_detected_change_path(),
                symbol_name=claim.symbol_name,
                parent_class=claim.parent_class,
                line_number=claim.line_number,
                caller_name=claim.caller_name,
                called_name=claim.called_name,
            )
        )
    return sorted(changes, key=change_sort_key)


def mask_key(key: str) -> str:
    """Public alias for :func:`_mask_key`.

    Provided for cross-module consumers (CLI config display) that need
    key masking without reaching into private names.
    """
    return _mask_key(key)


def _mask_key(key: str) -> str:
    """Mask an API key for safe display.

    Shows first 4 and last 4 characters with ``****`` in between.
    Short keys (<=8 chars) are fully masked.
    """
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


class ModelError(Exception):
    """Raised when the model API call fails irrecoverably."""


def _auth_header_from_type(api_key: str, auth_type: str) -> dict[str, str]:
    """Return the authorization header for the given auth type.

    This is a simple type-to-header mapping with **no URL inference**.
    All URL matching and provider detection happens in
    :func:`nowreck.model.adapters.resolve_provider`, which returns the
    ``auth_type`` string consumed here.

    Args:
        api_key: The API key to include in the header.
        auth_type: One of ``"bearer"``, ``"x-api-key"``, or
            ``"x-goog-api-key"`` — as returned by
            :func:`~nowreck.model.adapters.resolve_provider`.
    """
    if auth_type == "x-api-key":
        return {"x-api-key": api_key}
    if auth_type == "x-goog-api-key":
        return {"x-goog-api-key": api_key}
    # Default: Bearer token (covers "bearer" and any unknown value).
    return {"Authorization": f"Bearer {api_key}"}


def _join_url(base_url: str, url_suffix: str) -> str:
    """Join a configured base URL with an adapter's versioned suffix.

    Strips a redundant trailing version segment (``/v1`` or
    ``/v1beta``) from the base when the adapter's suffix already
    carries its own — prevents requests like ``/v1/v1/messages``.
    """
    base = base_url.rstrip("/")
    for segment in ("/v1", "/v1beta"):
        if url_suffix.startswith(segment) and base.endswith(segment):
            base = base[: -len(segment)]
            break
    return f"{base}{url_suffix}"


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
        """.. deprecated:: v0.11.1
            Production callers use :meth:`changes_from_prompt_v10` or
            :func:`nowreck.verifier.prompt_verifier.verify_prompt`.
            Kept for backwards compatibility; no longer emits
            deprecation warnings.

        Send a natural-language prompt to the model and return both
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
        messages = PromptBuilder.for_prompt_v10(prompt)
        result = self._call_with_retry(messages)

        # Derive DetectedChanges from the parsed claims.
        changes = _claims_to_changes(result.claims)

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

        provider_info = resolve_provider(config.base_url, config.provider)
        url_suffix, headers, body = provider_info.adapter.build_request(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
        )

        req = urllib_request.Request(
            url=_join_url(config.base_url, url_suffix),
            data=body,
            headers={
                **headers,
                **_auth_header_from_type(api_key, provider_info.auth_type),
            },
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
            return provider_info.adapter.parse_response(raw)
        except (
            json.JSONDecodeError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            # Phase 5 / 3.3: narrow the broad ``except Exception`` to the
            # exception types the adapter is contractually allowed to
            # raise.  ``_AdapterError`` was considered but does not exist
            # in ``nowreck.model.adapters`` — the documented exception
            # surface is the built-ins above plus whatever specific
            # transport errors the underlying ``urlopen`` call already
            # raised and converted to ``ModelError`` above.
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

        masked_messages = messages  # chat payloads carry no headers

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
