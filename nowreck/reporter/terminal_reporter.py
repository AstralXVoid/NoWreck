from __future__ import annotations

import json

from nowreck import __version__
from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange
from nowreck.verifier.verifier import Verdict, VerificationReport, VerificationResult

# ---------------------------------------------------------------------------
# ANSI escape codes — no external dependency required.
# ---------------------------------------------------------------------------

_ANSI_RESET = "\033[0m"
_ANSI_BOLD = "\033[1m"
_ANSI_DIM = "\033[2m"

_ANSI_GREEN = "\033[92m"
_ANSI_YELLOW = "\033[93m"
_ANSI_RED = "\033[91m"
_ANSI_CYAN = "\033[96m"

_ANSI_WHITE = "\033[97m"

# ---------------------------------------------------------------------------
# Verdict colours
# ---------------------------------------------------------------------------

_VERDICT_COLOUR: dict[Verdict, str] = {
    Verdict.CONFIRMED: _ANSI_GREEN,
    Verdict.CONTRADICTED: _ANSI_YELLOW,
    Verdict.UNVERIFIABLE: _ANSI_YELLOW,
}

_VERDICT_GLYPH: dict[Verdict, str] = {
    Verdict.CONFIRMED: "✓",
    Verdict.CONTRADICTED: "✗",
    Verdict.UNVERIFIABLE: "?",
}


class TerminalReporter:
    """Produces a human-readable terminal report from a
    :class:`VerificationReport`.

    The output is plain text with ANSI colour codes for readability.
    No JSON, CI-mode, or UI output is produced.
    """

    def __init__(self, colour: bool = True) -> None:
        self._colour = colour

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def report(self, report: VerificationReport) -> str:
        """Render the full verification report as a coloured string."""
        lines: list[str] = []

        self._append_header(lines)
        lines.append("")
        self._append_summary(lines, report)
        lines.append("")

        confirmed = [r for r in report.results if r.verdict is Verdict.CONFIRMED]
        contradicted = [r for r in report.results if r.verdict is Verdict.CONTRADICTED]
        unverifiable = [r for r in report.results if r.verdict is Verdict.UNVERIFIABLE]

        self._append_claim_section(lines, confirmed, "CONFIRMED", _ANSI_GREEN)
        self._append_claim_section(lines, contradicted, "CONTRADICTED", _ANSI_YELLOW)
        self._append_unverifiable_section(lines, unverifiable)
        self._append_unexplained_section(lines, report.unexplained_changes)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section rendering helpers
    # ------------------------------------------------------------------

    def _append_claim_section(
        self,
        lines: list[str],
        results: list[VerificationResult],
        title: str,
        colour: str,
    ) -> None:
        """Render a section for CONFIRMED or CONTRADICTED results."""
        if not results:
            return
        self._append_section_header(lines, title, colour)
        for result in results:
            self._append_claim_line(lines, result)
            if result.matched_change is not None:
                self._append_evidence_line(lines, result.matched_change)
        lines.append("")

    def _append_unverifiable_section(
        self,
        lines: list[str],
        results: list[VerificationResult],
    ) -> None:
        """Render a section for UNVERIFIABLE results."""
        if not results:
            return
        self._append_section_header(lines, "UNVERIFIABLE", _ANSI_YELLOW)
        for result in results:
            self._append_claim_line(lines, result)
            self._append_unverifiable_reason(lines, result.claim)
        lines.append("")

    def _append_unexplained_section(
        self,
        lines: list[str],
        changes: list[DetectedChange],
    ) -> None:
        """Render a section for unexplained changes."""
        if not changes:
            return
        self._append_section_header(lines, "UNEXPLAINED CHANGES", _ANSI_RED)
        for change in changes:
            self._append_unexplained_line(lines, change)
        lines.append("")

    # ------------------------------------------------------------------
    # Header / Summary
    # ------------------------------------------------------------------

    def _append_header(self, lines: list[str]) -> None:
        width = 55
        lines.append(self._colourise(_ANSI_CYAN + _ANSI_BOLD, "═" * width))
        lines.append(
            self._colourise(
                _ANSI_CYAN + _ANSI_BOLD,
                "  Nowreck Verification Report",
            )
        )
        lines.append(self._colourise(_ANSI_CYAN + _ANSI_BOLD, "═" * width))

    def _append_summary(self, lines: list[str], report: VerificationReport) -> None:
        lines.append(
            self._colourise(
                _ANSI_BOLD + _ANSI_WHITE,
                "  Summary",
            )
        )
        lines.append(self._colourise(_ANSI_DIM, "  " + "─" * 20))

        def _label(count: int, singular: str, plural: str) -> str:
            return singular if count == 1 else plural

        def _count_line(
            count: int,
            label: str,
            colour: str = _ANSI_WHITE,
        ) -> str:
            glyph = "●"
            return f"  {glyph} {self._colourise(colour, str(count))} {label}"

        lines.append(
            _count_line(
                report.total_claims,
                _label(report.total_claims, "claim total", "claims total"),
            )
        )
        lines.append(
            _count_line(
                report.confirmed,
                _label(report.confirmed, "confirmed", "confirmed"),
                _ANSI_GREEN,
            )
        )
        if report.contradicted:
            lines.append(
                _count_line(
                    report.contradicted,
                    _label(report.contradicted, "contradicted", "contradicted"),
                    _ANSI_YELLOW,
                )
            )
        if report.unverifiable:
            lines.append(
                _count_line(
                    report.unverifiable,
                    _label(report.unverifiable, "unverifiable", "unverifiable"),
                    _ANSI_YELLOW,
                )
            )
        if report.unexplained_count:
            lines.append(
                _count_line(
                    report.unexplained_count,
                    _label(
                        report.unexplained_count,
                        "unexplained change",
                        "unexplained changes",
                    ),
                    _ANSI_RED,
                )
            )

    # ------------------------------------------------------------------
    # Section headers
    # ------------------------------------------------------------------

    def _append_section_header(self, lines: list[str], title: str, colour: str) -> None:
        lines.append(self._colourise(colour + _ANSI_BOLD, f"  {title}"))
        lines.append(self._colourise(colour + _ANSI_DIM, "  " + "─" * len(title)))

    # ------------------------------------------------------------------
    # Claim lines
    # ------------------------------------------------------------------

    def _append_claim_line(self, lines: list[str], result: VerificationResult) -> None:
        colour = _VERDICT_COLOUR.get(result.verdict, _ANSI_WHITE)
        glyph = _VERDICT_GLYPH.get(result.verdict, "?")
        claim_desc = self._describe_claim(result.claim)

        # For deterministic structural findings (CONFIRMED, CONTRADICTED)
        # the verifier's confidence is 100% — the change was either
        # found or not found.  Only UNVERIFIABLE displays the model's
        # original confidence since the verifier couldn't determine
        # anything.
        if result.verdict is Verdict.UNVERIFIABLE:
            conf_str = self._format_confidence(result.claim.confidence)
        else:
            conf_str = self._format_confidence(1.0)

        lines.append(
            self._colourise(
                colour,
                f"  {glyph} {claim_desc}  (conf: {conf_str})",
            )
        )

    def _append_unverifiable_reason(self, lines: list[str], claim: Claim) -> None:
        change_type_str = _CLAIM_TYPE_LABELS.get(claim.type, str(claim.type.name))
        symbol_part = f" '{claim.symbol_name}'" if claim.symbol_name else ""
        file_part = f" in {claim.file_path}"
        msg = (
            f"No matching change detected for"
            f" {change_type_str.lower()}{symbol_part}{file_part}."
        )
        lines.append(
            self._colourise(
                _ANSI_DIM,
                f"    Reason: {msg}",
            )
        )

    # ------------------------------------------------------------------
    # Evidence lines
    # ------------------------------------------------------------------

    def _append_evidence_line(
        self,
        lines: list[str],
        change: DetectedChange,
    ) -> None:
        evidence = self._describe_evidence(change)
        lines.append(
            self._colourise(
                _ANSI_DIM,
                f"    Evidence: {evidence}",
            )
        )

    def _append_unexplained_line(
        self, lines: list[str], change: DetectedChange
    ) -> None:
        desc = self._describe_change(change)
        lines.append(
            self._colourise(
                _ANSI_RED,
                f"  ! {desc}",
            )
        )

    # ------------------------------------------------------------------
    # Descriptors
    # ------------------------------------------------------------------

    @staticmethod
    def _describe_claim(claim: Claim) -> str:
        """Return a human-readable summary of a claim."""
        label = _CLAIM_TYPE_LABELS.get(claim.type, claim.type.name)
        parts: list[str] = [label]

        if claim.symbol_name is not None:
            parts.append(claim.symbol_name)

        if claim.parent_class is not None:
            parts[-1] = f"{claim.parent_class}.{parts[-1]}"

        parts.append(f"→ {claim.file_path}")

        if claim.line_number is not None:
            parts[-1] = f"{parts[-1]}:{claim.line_number}"

        return " ".join(parts)

    @staticmethod
    def _describe_evidence(change: DetectedChange) -> str:
        """Return a human-readable evidence description for a change."""
        if change.change_type is ChangeType.ADD_FUNCTION:
            owner = f" in {change.parent_class}" if change.parent_class else ""
            return (
                f"Function '{change.symbol_name}' was added{owner}"
                f" in {change.file_path}"
            )
        if change.change_type is ChangeType.REMOVE_FUNCTION:
            owner = f" in {change.parent_class}" if change.parent_class else ""
            return (
                f"Function '{change.symbol_name}' was removed{owner}"
                f" from {change.file_path}"
            )
        if change.change_type is ChangeType.ADD_CLASS:
            return f"Class '{change.symbol_name}' was added in {change.file_path}"
        if change.change_type is ChangeType.REMOVE_CLASS:
            return f"Class '{change.symbol_name}' was removed from {change.file_path}"
        if change.change_type is ChangeType.FILE_CREATED:
            return f"File '{change.file_path}' was created"
        if change.change_type is ChangeType.FILE_DELETED:
            return f"File '{change.file_path}' was deleted"
        if change.change_type is ChangeType.CALL_DETECTED:
            return (
                f"Function '{change.caller_name}' calls "
                f"'{change.called_name}' in {change.file_path}"
            )
        return f"Change detected: {change}"

    @staticmethod
    def _describe_change(change: DetectedChange) -> str:
        """Return a human-readable summary of a detected change (for
        unexplained changes section)."""
        label = _CHANGE_TYPE_LABELS.get(change.change_type, change.change_type.name)
        parts: list[str] = [label]

        if change.symbol_name is not None:
            parts.append(change.symbol_name)
            if change.parent_class is not None:
                parts[-1] = f"{change.parent_class}.{parts[-1]}"
        elif change.caller_name is not None and change.called_name is not None:
            parts.append(f"{change.caller_name} → {change.called_name}")

        parts.append(f"({change.file_path})")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _colourise(self, code: str, text: str) -> str:
        if self._colour:
            return f"{code}{text}{_ANSI_RESET}"
        return text

    @staticmethod
    def _format_confidence(value: float) -> str:
        """Format a 0.0–1.0 confidence as a percentage string."""
        return f"{int(round(value * 100)):3d}%"

    # ------------------------------------------------------------------
    # JSON output for CI tools
    # ------------------------------------------------------------------

    @staticmethod
    def report_json(report: VerificationReport) -> str:
        """Render the report as a structured JSON string for CI tools.

        The JSON schema::

            {
              "version": "0.2.0",
              "success": true|false,
              "summary": {
                "total_claims": int,
                "confirmed": int,
                "contradicted": int,
                "unverifiable": int,
                "unexplained_count": int
              },
              "results": [{...}],
              "unexplained_changes": [{...}]
            }
        """
        data: dict[str, object] = {
            "version": __version__,
            "success": report.success,
            "summary": {
                "total_claims": report.total_claims,
                "confirmed": report.confirmed,
                "contradicted": report.contradicted,
                "unverifiable": report.unverifiable,
                "unexplained_count": report.unexplained_count,
            },
            "results": [TerminalReporter._result_to_dict(r) for r in report.results],
            "unexplained_changes": [
                TerminalReporter._change_to_dict(c) for c in report.unexplained_changes
            ],
        }

        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def _result_to_dict(result: VerificationResult) -> dict[str, object]:
        """Serialize a single verification result to a dict.

        For deterministic structural findings (CONFIRMED, CONTRADICTED)
        the verifier's confidence is 100% — the change was either found
        or not found.  Only UNVERIFIABLE preserves the model's original
        confidence since the verifier couldn't determine anything.
        """
        if result.verdict is Verdict.UNVERIFIABLE:
            display_confidence = result.claim.confidence
        else:
            display_confidence = 1.0

        out: dict[str, object] = {
            "claim": TerminalReporter._claim_to_dict(result.claim),
            "verdict": result.verdict.name,
            "verifier_confidence": display_confidence,
        }
        if result.matched_change is not None:
            out["matched_change"] = TerminalReporter._change_to_dict(
                result.matched_change
            )
        return out

    @staticmethod
    def _claim_to_dict(claim: Claim) -> dict[str, object]:
        """Serialize a claim to a plain dict (JSON-safe)."""
        return {
            "type": claim.type.name,
            "symbol_name": claim.symbol_name,
            "file_path": claim.file_path,
            "parent_class": claim.parent_class,
            "line_number": claim.line_number,
            "caller_name": claim.caller_name,
            "called_name": claim.called_name,
            "confidence": claim.confidence,
        }

    @staticmethod
    def _change_to_dict(change: DetectedChange) -> dict[str, object]:
        """Serialize a detected change to a plain dict (JSON-safe).

        Converts ``Path`` to ``str`` for JSON serialization.
        """
        return {
            "change_type": change.change_type.name,
            "file_path": str(change.file_path),
            "symbol_name": change.symbol_name,
            "parent_class": change.parent_class,
            "line_number": change.line_number,
            "caller_name": change.caller_name,
            "called_name": change.called_name,
        }


# ---------------------------------------------------------------------------
# Human-readable labels for each claim type.
# ---------------------------------------------------------------------------

_CLAIM_TYPE_LABELS: dict[ClaimType, str] = {
    ClaimType.ADD_FUNCTION: "ADD_FUNCTION",
    ClaimType.REMOVE_FUNCTION: "REMOVE_FUNCTION",
    ClaimType.ADD_CLASS: "ADD_CLASS",
    ClaimType.REMOVE_CLASS: "REMOVE_CLASS",
    ClaimType.FILE_CREATED: "FILE_CREATED",
    ClaimType.FILE_DELETED: "FILE_DELETED",
    ClaimType.CALLS_FUNCTION: "CALLS_FUNCTION",
}

_CHANGE_TYPE_LABELS: dict[ChangeType, str] = {
    ChangeType.ADD_FUNCTION: "ADD_FUNCTION",
    ChangeType.REMOVE_FUNCTION: "REMOVE_FUNCTION",
    ChangeType.ADD_CLASS: "ADD_CLASS",
    ChangeType.REMOVE_CLASS: "REMOVE_CLASS",
    ChangeType.FILE_CREATED: "FILE_CREATED",
    ChangeType.FILE_DELETED: "FILE_DELETED",
    ChangeType.CALL_DETECTED: "CALL_DETECTED",
}
