from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, auto
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class ClaimType(IntEnum):
    """The seven structural claim types supported in the MVP.

    Each corresponds one-to-one with the claim taxonomy in the frozen
    specification.  No additional claim types are defined.
    """

    ADD_FUNCTION = auto()
    REMOVE_FUNCTION = auto()
    ADD_CLASS = auto()
    REMOVE_CLASS = auto()
    FILE_CREATED = auto()
    FILE_DELETED = auto()
    CALLS_FUNCTION = auto()


# Mapping from JSON string to ClaimType enum — used for case-insensitive
# parsing of model output.
CLAIM_TYPE_NAMES: dict[str, ClaimType] = {
    "ADD_FUNCTION": ClaimType.ADD_FUNCTION,
    "REMOVE_FUNCTION": ClaimType.REMOVE_FUNCTION,
    "ADD_CLASS": ClaimType.ADD_CLASS,
    "REMOVE_CLASS": ClaimType.REMOVE_CLASS,
    "FILE_CREATED": ClaimType.FILE_CREATED,
    "FILE_DELETED": ClaimType.FILE_DELETED,
    "CALLS_FUNCTION": ClaimType.CALLS_FUNCTION,
}


class Claim(BaseModel):
    """A single structured claim produced by the AI model.

    Attributes:
        type: The kind of structural claim.
        symbol_name: Name of the affected function, class, or method.
            Required for ADD/REMOVE FUNCTION/CLASS and CALLS_FUNCTION.
        file_path: Path relative to the repository root.  Required for
            all claim types.
        parent_class: For methods, the enclosing class name.  ``None``
            for top-level symbols and file claims.
        line_number: 1-based line number where the definition starts.
            Optional — used as contextual hint.
        caller_name: For ``CALLS_FUNCTION``, the function or method
            that contains the call.  ``None`` for other claim types.
        called_name: For ``CALLS_FUNCTION``, the name of the function
            being called.  ``None`` for other claim types.
        confidence: The model's confidence in this claim, from 0.0 to
            1.0.  Defaults to 1.0.
    """

    type: ClaimType
    symbol_name: str | None = None
    file_path: str
    parent_class: str | None = None
    line_number: int | None = None
    caller_name: str | None = None
    called_name: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("file_path")
    @classmethod
    def _file_path_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("file_path must not be empty")
        return v

    def to_detected_change_path(self) -> Path:
        """Convert the string file_path to a ``Path`` as used by the
        change detector."""
        return Path(self.file_path)


@dataclass(frozen=True)
class ParseResult:
    """The outcome of a single claim-parsing attempt.

    Attributes:
        claims: Validated claims.  Empty when parsing fails.
        errors: Human-readable error messages describing what went
            wrong.  Empty when parsing succeeds.
        raw_json: The original JSON string that was parsed (or attempted).
    """

    claims: list[Claim] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_json: str = ""

    @property
    def success(self) -> bool:
        """``True`` when no errors occurred during parsing."""
        return len(self.errors) == 0
