from __future__ import annotations

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange, change_sort_key

# ---------------------------------------------------------------------------
# System prompt — describes the task and required JSON format.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are Nowreck, an AI assistant that explains structural changes in Python \
code repositories.

You will receive a list of detected changes between two versions of a \
codebase. Your job is to produce a structured explanation of WHY each \
change was made and provide enough context for a reviewer to understand \
the intent.

Rules:
1. Explain each change with a clear natural-language explanation.
2. Every claim must include a confidence score (0.0 to 1.0) reflecting \
your certainty in the explanation.
3. Only make claims about the changes you can see — do not invent changes.
4. Respond ONLY with valid JSON in the format specified below.

Valid claim types:
- ADD_FUNCTION     — A function was added to a file.
- REMOVE_FUNCTION  — A function was removed from a file.
- ADD_CLASS        — A class was added to a file.
- REMOVE_CLASS     — A class was removed from a file.
- FILE_CREATED     — An entirely new file was created.
- FILE_DELETED     — An entire file was deleted.
- CALLS_FUNCTION   — A function now calls another function.

Required JSON format:
{
  "claims": [
    {
      "type": "ADD_FUNCTION",
      "symbol_name": "function_name",
      "file_path": "path/to/file.py",
      "parent_class": null,
      "caller_name": null,
      "called_name": null,
      "confidence": 0.95,
      "explanation": "Natural language explanation of why this change was made."
    }
  ]
}

Field notes:
- symbol_name: Required for function/class claims; omit (null) for file-level claims.
- file_path: Required for all claims. Relative to repository root.
- parent_class: Required when the symbol is a method inside a class.
- caller_name / called_name: Required for CALLS_FUNCTION claims.
- confidence: 0.0 (guess) to 1.0 (certain).\
"""


# ---------------------------------------------------------------------------
# Prompt system prompt — describes the task for single-prompt mode.
# ---------------------------------------------------------------------------

PROMPT_SYSTEM_PROMPT = """\
You are Nowreck, an AI assistant that analyzes descriptions of code changes.

You will receive a natural-language description of changes made to a Python \
code repository. Your task is to produce a structured list of claims that \
capture EXACTLY what the description says changed.

Rules:
1. Only make claims about changes the description explicitly mentions.
2. Every claim must include a confidence score (0.0 to 1.0) reflecting how \
certain you are that this change matches the description.
3. Do NOT invent changes that are not described.
4. Respond ONLY with valid JSON in the format specified below.

Valid claim types:
- ADD_FUNCTION     — A function was added to a file.
- REMOVE_FUNCTION  — A function was removed from a file.
- ADD_CLASS        — A class was added to a file.
- REMOVE_CLASS     — A class was removed from a file.
- FILE_CREATED     — An entirely new file was created.
- FILE_DELETED     — An entire file was deleted.
- CALLS_FUNCTION   — A function now calls another function.

Required JSON format:
{
  "claims": [
    {
      "type": "ADD_FUNCTION",
      "symbol_name": "function_name",
      "file_path": "path/to/file.py",
      "parent_class": null,
      "caller_name": null,
      "called_name": null,
      "confidence": 0.95,
      "explanation": "Natural language explanation of why this change was made."
    }
  ]
}

Field notes:
- symbol_name: Required for function/class claims; omit (null) for file-level claims.
- file_path: Required for all claims. Relative to repository root.
- parent_class: Required when the symbol is a method inside a class.
- caller_name / called_name: Required for CALLS_FUNCTION claims.
- confidence: 0.0 (guess) to 1.0 (certain).\
"""


class PromptBuilder:
    """Builds the system and user messages for the model conversation.

    The builder takes a list of detected changes and formats them into a
    structured user prompt.
    """

    @staticmethod
    def build(changes: list[DetectedChange]) -> list[dict[str, str]]:
        """Build a message list suitable for the Chat Completions API
        when the model should **explain** already-detected changes.

        Args:
            changes: The detected structural changes to explain.

        Returns:
            A list of ``{"role": ..., "content": ...}`` dicts.
        """
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": PromptBuilder._format_changes(changes)},
        ]

    @staticmethod
    def for_prompt(prompt: str) -> list[dict[str, str]]:
        """Build a message list for the single-prompt workflow where the
        model generates both the diff and its explanation from scratch.

        Args:
            prompt: A natural-language description of code changes.

        Returns:
            A list of ``{"role": ..., "content": ...}`` dicts.
        """
        return [
            {"role": "system", "content": PROMPT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Describe the following code changes as a structured "
                    "list of claims in the required JSON format:\n\n"
                    f"{prompt}\n\n"
                    "Explain each change in the required JSON format. "
                    "Include an 'explanation' field for each claim."
                ),
            },
        ]

    # ------------------------------------------------------------------
    # Claim → DetectedChange conversion
    # ------------------------------------------------------------------

    @staticmethod
    def claims_to_changes(claims: list[Claim]) -> list[DetectedChange]:
        """Convert a list of :class:`Claim` objects into a corresponding
        list of :class:`DetectedChange` objects.

        This enables the single-prompt workflow: the model generates
        claims describing the changes, and those claims are converted to
        a ``DetectedChange`` list that the verifier can match against.

        Args:
            claims: Parsed claims (e.g. from the model response).

        Returns:
            A sorted list of ``DetectedChange`` objects derived from
            the claims.
        """
        changes: list[DetectedChange] = []

        for claim in claims:
            change_type = _CLAIM_TO_CHANGE_TYPE.get(claim.type)
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

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_changes(changes: list[DetectedChange]) -> str:
        """Turn the change list into a human-readable numbered list."""
        if not changes:
            return "No changes were detected."

        lines: list[str] = [
            "Please explain the following structural changes detected in "
            "the repository:",
            "",
        ]

        for i, change in enumerate(changes, start=1):
            label = _CHANGE_LABELS.get(change.change_type, change.change_type.name)
            detail = PromptBuilder._change_detail(change)
            lines.append(f"{i}. {label}: {detail}")

        lines.append("")
        lines.append(
            "Explain each change in the required JSON format. Include an "
            "'explanation' field for each claim."
        )
        return "\n".join(lines)

    @staticmethod
    def _change_detail(change: DetectedChange) -> str:
        """Return a one-line detail string for a single change."""
        parts: list[str] = []

        if change.change_type is ChangeType.CALL_DETECTED:
            if change.caller_name and change.called_name:
                parts.append(f"{change.caller_name}() now calls {change.called_name}()")
            parts.append(f"in {change.file_path}")
        else:
            if change.symbol_name is not None:
                if change.parent_class is not None:
                    parts.append(f"{change.parent_class}.{change.symbol_name}()")
                elif change.change_type in (
                    ChangeType.ADD_FUNCTION,
                    ChangeType.REMOVE_FUNCTION,
                ):
                    parts.append(f"{change.symbol_name}()")
                else:
                    parts.append(change.symbol_name)

            parts.append(f"({change.file_path})")

            if change.line_number is not None:
                parts.append(f"line {change.line_number}")

        return " ".join(parts)


# ---------------------------------------------------------------------------
# Human-readable labels for each change type.
# ---------------------------------------------------------------------------

_CHANGE_LABELS: dict[ChangeType, str] = {
    ChangeType.ADD_FUNCTION: "Function added",
    ChangeType.REMOVE_FUNCTION: "Function removed",
    ChangeType.ADD_CLASS: "Class added",
    ChangeType.REMOVE_CLASS: "Class removed",
    ChangeType.FILE_CREATED: "File created",
    ChangeType.FILE_DELETED: "File deleted",
    ChangeType.CALL_DETECTED: "Call detected",
}

# Mapping from ClaimType to ChangeType for the claims→changes conversion.
# NOTE: CALLS_FUNCTION is intentionally omitted.  Call relationships
# describe links between other changes — they are verified by checking
# whether matching CALL_DETECTED changes exist (from the real scanner)
# or whether the caller function itself exists among the derived changes
# (in prompt mode).  Converting them to standalone changes would create
# a self-consistent loop where hallucinated calls can never be caught.
_CLAIM_TO_CHANGE_TYPE: dict[ClaimType, ChangeType] = {
    ClaimType.ADD_FUNCTION: ChangeType.ADD_FUNCTION,
    ClaimType.REMOVE_FUNCTION: ChangeType.REMOVE_FUNCTION,
    ClaimType.ADD_CLASS: ChangeType.ADD_CLASS,
    ClaimType.REMOVE_CLASS: ChangeType.REMOVE_CLASS,
    ClaimType.FILE_CREATED: ChangeType.FILE_CREATED,
    ClaimType.FILE_DELETED: ChangeType.FILE_DELETED,
}
