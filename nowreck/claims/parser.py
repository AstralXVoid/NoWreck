from __future__ import annotations

import json
import re
from typing import Any, cast

from nowreck.claims.models import CLAIM_TYPE_NAMES, Claim, ParseResult

# Public mapping re-exported for reuse (not prefixed with _).  The single
# source of truth lives in claims/models.py — no local copy here, so new
# claim types flow through automatically.


class ClaimParser:
    """Parses the AI model's structured JSON output into validated claims.

    The parser performs a single parse attempt (one shot).  Retry logic
    is the responsibility of the orchestrator that drives the model
    conversation.
    """

    @staticmethod
    def parse(json_str: str) -> ParseResult:
        """Parse a JSON string into a ``ParseResult``.

        The expected JSON format is::

            {
              "claims": [
                {
                  "type": "ADD_FUNCTION",
                  "symbol_name": "greet",
                  "file_path": "src/hello.py"
                }
              ]
            }

        Args:
            json_str: The raw JSON string produced by the AI model.

        Returns:
            A ``ParseResult`` containing validated claims and/or error
            messages.
        """
        errors: list[str] = []
        claims: list[Claim] = []

        # --- Step 0: strip markdown code block fences before parsing ---
        # Some models wrap JSON in ```json ... ``` or ``` ... ``` blocks.
        cleaned = ClaimParser._strip_markdown_fence(json_str)

        # --- Step 1: parse the top-level JSON structure ---
        try:
            parsed: Any = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return ParseResult(
                errors=[f"Invalid JSON: {exc}"],
                raw_json=json_str,
            )

        if not isinstance(parsed, dict):
            return ParseResult(
                errors=[f"Expected a JSON object, got {type(parsed).__name__}"],
                raw_json=json_str,
            )

        data: dict[str, Any] = cast("dict[str, Any]", parsed)
        raw_claims: Any = data.get("claims")
        if raw_claims is None:
            return ParseResult(
                errors=['Missing required key "claims"'],
                raw_json=json_str,
            )

        if not isinstance(raw_claims, list):
            return ParseResult(
                errors=[f'"claims" must be a list, got {type(raw_claims).__name__}'],
                raw_json=json_str,
            )

        claim_list: list[Any] = cast("list[Any]", raw_claims)
        if len(claim_list) == 0:
            return ParseResult(
                errors=['"claims" list is empty — at least one claim expected'],
                raw_json=json_str,
            )

        # --- Step 2: validate each claim ---
        for i, raw in enumerate(claim_list):
            claim_errors = ClaimParser._validate_single(raw, index=i)
            if claim_errors:
                errors.extend(claim_errors)
                continue

            # Build and validate via Pydantic
            try:
                assert isinstance(raw, dict)
                raw_dict: dict[str, Any] = cast("dict[str, Any]", raw)
                normalized = ClaimParser._normalize_claim(raw_dict)
                claim = Claim.model_validate(normalized)
                claims.append(claim)
            except Exception as exc:
                errors.append(f"Claim #{i}: validation error: {exc}")

        # --- Step 3: extract optional patch field (v10) ---
        patch: str | None = None
        raw_patch: Any = data.get("patch")
        if isinstance(raw_patch, str) and raw_patch.strip():
            patch = raw_patch

        return ParseResult(
            claims=claims,
            errors=errors,
            raw_json=json_str,
            patch=patch,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_single(raw: Any, index: int) -> list[str]:
        """Run pre-Pydantic structural checks on a single claim dict."""
        errs: list[str] = []

        if not isinstance(raw, dict):
            errs.append(f"Claim #{index}: expected an object, got {type(raw).__name__}")
            return errs

        raw_dict: dict[str, Any] = cast("dict[str, Any]", raw)
        raw_type: Any = raw_dict.get("type")
        if raw_type is None:
            errs.append(f"Claim #{index}: missing required field 'type'")
            return errs

        if not isinstance(raw_type, str):
            errs.append(
                f"Claim #{index}: 'type' must be a string, got "
                f"{type(raw_type).__name__}"
            )
            return errs

        if raw_type not in CLAIM_TYPE_NAMES:
            valid = ", ".join(sorted(CLAIM_TYPE_NAMES))
            errs.append(
                f"Claim #{index}: unknown claim type '{raw_type}'. Valid types: {valid}"
            )
            return errs

        file_path: Any = raw_dict.get("file_path")
        if file_path is None:
            errs.append(f"Claim #{index}: missing required field 'file_path'")
        elif not isinstance(file_path, str) or not file_path.strip():
            errs.append(f"Claim #{index}: 'file_path' must be a non-empty string")

        return errs

    @staticmethod
    def _strip_markdown_fence(raw: str) -> str:
        """Strip markdown code-block fences (`` ```json ... ``` `` or
        `` ``` ... ``` ``) from a model response.

        Many open-source models wrap their JSON output in markdown
        code blocks.  This method extracts the JSON payload from
        inside the block when fences are detected.

        Returns the original string unchanged if no fences are found.
        """
        # Search for the first ``` ... ``` block anywhere in the string
        # (handles both clean blocks and blocks with leading/trailing text).
        pattern = r"```[a-z]*\s*\n?(.*?)```"
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            return match.group(1).strip()
        return raw

    @staticmethod
    def _normalize_claim(raw: dict[str, Any]) -> dict[str, Any]:
        """Convert raw JSON fields into a shape Pydantic can validate.

        Handles the string-to-enum mapping for the ``type`` field and
        provides defaults for missing optional fields.
        """
        normalized: dict[str, Any] = dict(raw)
        raw_type: str = str(raw.get("type", ""))
        normalized["type"] = CLAIM_TYPE_NAMES.get(raw_type, raw.get("type"))
        return normalized
