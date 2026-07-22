from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, auto
from pathlib import Path

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange, change_sort_key


class Verdict(IntEnum):
    """The outcome of verifying a single claim against all detected changes."""

    CONFIRMED = auto()
    CONTRADICTED = auto()
    UNVERIFIABLE = auto()


# Mapping from a ClaimType to its corresponding ChangeType for
# same-type (confirmed) matching.
_SAME_CHANGE: dict[ClaimType, ChangeType] = {
    ClaimType.ADD_FUNCTION: ChangeType.ADD_FUNCTION,
    ClaimType.REMOVE_FUNCTION: ChangeType.REMOVE_FUNCTION,
    ClaimType.ADD_CLASS: ChangeType.ADD_CLASS,
    ClaimType.REMOVE_CLASS: ChangeType.REMOVE_CLASS,
    ClaimType.FILE_CREATED: ChangeType.FILE_CREATED,
    ClaimType.FILE_DELETED: ChangeType.FILE_DELETED,
    ClaimType.CALLS_FUNCTION: ChangeType.CALL_DETECTED,
}

# Mapping from a ClaimType to its *opposite* ChangeType for
# contradicted matching.
_OPPOSITE_CHANGE: dict[ClaimType, ChangeType] = {
    ClaimType.ADD_FUNCTION: ChangeType.REMOVE_FUNCTION,
    ClaimType.REMOVE_FUNCTION: ChangeType.ADD_FUNCTION,
    ClaimType.ADD_CLASS: ChangeType.REMOVE_CLASS,
    ClaimType.REMOVE_CLASS: ChangeType.ADD_CLASS,
    ClaimType.FILE_CREATED: ChangeType.FILE_DELETED,
    ClaimType.FILE_DELETED: ChangeType.FILE_CREATED,
    # CALLS_FUNCTION has no semantic opposite.
}


@dataclass(frozen=True)
class VerificationResult:
    """The outcome of verifying a single claim.

    Attributes:
        claim: The claim that was verified.
        verdict: The verdict assigned to the claim.
        matched_change: The ``DetectedChange`` that supports
            ``CONFIRMED`` or ``CONTRADICTED``.  ``None`` for
            ``UNVERIFIABLE``.
    """

    claim: Claim
    verdict: Verdict
    matched_change: DetectedChange | None = None


@dataclass(frozen=True)
class VerificationReport:
    """Complete report from verifying all claims against all changes.

    Attributes:
        results: One ``VerificationResult`` per input claim.
        unexplained_changes: ``DetectedChange`` objects for which **no**
            claim was found.  Sorted for deterministic output.
        total_claims: Number of input claims.
        confirmed: Number of ``CONFIRMED`` results.
        contradicted: Number of ``CONTRADICTED`` results.
        unverifiable: Number of ``UNVERIFIABLE`` results.
        unexplained_count: Number of unexplained changes.
    """

    results: list[VerificationResult] = field(default_factory=list)
    unexplained_changes: list[DetectedChange] = field(default_factory=list)

    @property
    def total_claims(self) -> int:
        return len(self.results)

    @property
    def confirmed(self) -> int:
        return sum(1 for r in self.results if r.verdict is Verdict.CONFIRMED)

    @property
    def contradicted(self) -> int:
        return sum(1 for r in self.results if r.verdict is Verdict.CONTRADICTED)

    @property
    def unverifiable(self) -> int:
        return sum(1 for r in self.results if r.verdict is Verdict.UNVERIFIABLE)

    @property
    def unexplained_count(self) -> int:
        return len(self.unexplained_changes)

    @property
    def success(self) -> bool:
        """``True`` when all claims are confirmed and nothing is
        unexplained."""
        return (
            self.unverifiable == 0
            and self.contradicted == 0
            and self.unexplained_count == 0
        )


class ClaimVerifier:
    """Deterministically matches claims against detected changes.

    The verifier operates **exclusively** on ``DetectedChange`` objects
    — it never inspects ASTs, looks up symbols, or applies AI judgment.
    Every outcome is purely field-based matching.

    Rules:

    * **CONFIRMED** — A ``DetectedChange`` with the same type and
      matching identity fields exists.
    * **CONTRADICTED** — A ``DetectedChange`` with the *opposite* type
      and matching identity fields exists (e.g. claim says
      ``ADD_FUNCTION`` but the detector found ``REMOVE_FUNCTION``).
    * **UNVERIFIABLE** — No relevant ``DetectedChange`` exists at all.
    * **Unexplained changes** — ``DetectedChange`` objects that no claim
      matched against.
    """

    @staticmethod
    def verify(
        claims: list[Claim],
        detected_changes: list[DetectedChange],
    ) -> VerificationReport:
        """Verify a list of claims against all detected changes.

        Args:
            claims: Claims produced by the AI model (parsed and
                validated).
            detected_changes: The single source of truth produced by the
                change detector.

        Returns:
            A ``VerificationReport`` containing per-claim results and
            any unexplained changes.
        """
        results: list[VerificationResult] = []
        # Track which DetectedChanges have been matched.
        matched_indices: set[int] = set()

        for claim in claims:
            result = ClaimVerifier._verify_single(
                claim,
                detected_changes,
                matched_indices,
            )
            results.append(result)

        # Any DetectedChange that was never matched is unexplained.
        unexplained = [
            dc for i, dc in enumerate(detected_changes) if i not in matched_indices
        ]

        return VerificationReport(
            results=results,
            unexplained_changes=sorted(unexplained, key=change_sort_key),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _verify_single(
        claim: Claim,
        changes: list[DetectedChange],
        matched_indices: set[int],
    ) -> VerificationResult:
        """Verify one claim against the list of changes.

        *matched_indices* is mutated in-place to record which changes
        were consumed.
        """
        claim_path: Path = claim.to_detected_change_path()

        # 1. Try same-type (confirmed) match first.
        target_type = _SAME_CHANGE.get(claim.type)
        if target_type is not None:
            for i, change in enumerate(changes):
                if i in matched_indices:
                    continue
                if change.change_type is target_type and ClaimVerifier._fields_match(
                    claim, change, claim_path
                ):
                    matched_indices.add(i)
                    return VerificationResult(
                        claim=claim,
                        verdict=Verdict.CONFIRMED,
                        matched_change=change,
                    )

        # 2. Special case: CALLS_FUNCTION — check if the caller function
        #    exists among the changes.  If the caller exists but the
        #    claimed call was not part of the diff, the claim is
        #    CONTRADICTED (the model hallucinated a call that doesn't
        #    exist in the actual changes).
        #
        #    NOTE: We scan ALL changes here, including already-matched
        #    ones.  The caller function may have been consumed by another
        #    claim (e.g. ADD_FUNCTION) — that doesn't mean we can't use
        #    its existence as evidence that a call claim is hallucinated.
        if claim.type is ClaimType.CALLS_FUNCTION:
            if claim.caller_name is not None:
                for i, change in enumerate(changes):
                    # Look for the CALLER function itself (not a call),
                    # regardless of whether it was already matched.
                    if (
                        change.change_type is ChangeType.ADD_FUNCTION
                        and change.file_path == claim_path
                        and change.symbol_name == claim.caller_name
                        and change.parent_class == claim.parent_class
                    ):
                        # Do NOT add to matched_indices — the caller
                        # function change was already consumed by the
                        # ADD_FUNCTION claim that matched it.
                        return VerificationResult(
                            claim=claim,
                            verdict=Verdict.CONTRADICTED,
                            matched_change=change,
                        )

        # 3. Try opposite-type (contradicted) match.
        opposite_type = _OPPOSITE_CHANGE.get(claim.type)
        if opposite_type is not None:
            for i, change in enumerate(changes):
                if i in matched_indices:
                    continue
                if change.change_type is opposite_type and ClaimVerifier._fields_match(
                    claim, change, claim_path
                ):
                    matched_indices.add(i)
                    return VerificationResult(
                        claim=claim,
                        verdict=Verdict.CONTRADICTED,
                        matched_change=change,
                    )

        # 4. Nothing found — unverifiable.
        return VerificationResult(
            claim=claim,
            verdict=Verdict.UNVERIFIABLE,
        )

    @staticmethod
    def _fields_match(
        claim: Claim,
        change: DetectedChange,
        claim_path: Path,
    ) -> bool:
        """Check if the identifying fields of a claim match a detected
        change.

        Only the fields that carry structural identity are compared:

        * ``file_path`` — always compared.
        * ``symbol_name`` — compared when the claim specifies one
          (``None`` on a claim means the claim is about the file, so
          the check is skipped).
        * ``parent_class`` — compared when the change carries one.
        * For ``CALLS_FUNCTION`` / ``CALL_DETECTED`` — also compares
          ``caller_name`` and ``called_name``.
        """
        if claim_path != change.file_path:
            return False

        # Symbol-bearing claims: match symbol_name.
        # CALLS_FUNCTION claims carry symbol_name, but CALL_DETECTED
        # changes do not — identity is via caller_name/called_name.
        if claim.symbol_name is not None and claim.type is not ClaimType.CALLS_FUNCTION:
            if claim.symbol_name != change.symbol_name:
                return False

        # parent_class must match symmetrically.
        if claim.parent_class != change.parent_class:
            return False

        # CALLS_FUNCTION: also verify caller / called identity.
        if claim.type is ClaimType.CALLS_FUNCTION:
            if claim.caller_name != change.caller_name:
                return False
            if claim.called_name != change.called_name:
                return False

        return True
