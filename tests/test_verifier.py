from __future__ import annotations

from pathlib import Path

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange
from nowreck.verifier.verifier import (
    ClaimVerifier,
    Verdict,
    VerificationReport,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claim(
    claim_type: ClaimType,
    file_path: str = "app.py",
    symbol_name: str | None = None,
    parent_class: str | None = None,
    caller_name: str | None = None,
    called_name: str | None = None,
) -> Claim:
    """Factory for quickly building a Claim with defaulted fields."""
    kwargs: dict = {
        "type": claim_type,
        "file_path": file_path,
    }
    if symbol_name is not None:
        kwargs["symbol_name"] = symbol_name
    if parent_class is not None:
        kwargs["parent_class"] = parent_class
    if caller_name is not None:
        kwargs["caller_name"] = caller_name
    if called_name is not None:
        kwargs["called_name"] = called_name
    return Claim(**kwargs)


def _make_change(
    change_type: ChangeType,
    file_path: str = "app.py",
    symbol_name: str | None = None,
    parent_class: str | None = None,
    caller_name: str | None = None,
    called_name: str | None = None,
) -> DetectedChange:
    """Factory for quickly building a DetectedChange."""
    return DetectedChange(
        change_type=change_type,
        file_path=Path(file_path),
        symbol_name=symbol_name,
        parent_class=parent_class,
        caller_name=caller_name,
        called_name=called_name,
    )


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


class TestVerdict:
    def test_has_all_three_outcomes(self) -> None:
        assert Verdict.CONFIRMED
        assert Verdict.CONTRADICTED
        assert Verdict.UNVERIFIABLE

    def test_values_are_distinct(self) -> None:
        values = {v.value for v in Verdict}
        assert len(values) == 3


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------


class TestVerificationResult:
    def test_minimal(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED)
        r = VerificationResult(claim=c, verdict=Verdict.CONFIRMED)
        assert r.claim is c
        assert r.verdict is Verdict.CONFIRMED
        assert r.matched_change is None

    def test_with_matched_change(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED)
        dc = _make_change(ChangeType.FILE_CREATED)
        r = VerificationResult(claim=c, verdict=Verdict.CONFIRMED, matched_change=dc)
        assert r.matched_change is dc


# ---------------------------------------------------------------------------
# VerificationReport
# ---------------------------------------------------------------------------


class TestVerificationReport:
    def test_empty_report(self) -> None:
        report = VerificationReport()
        assert report.total_claims == 0
        assert report.confirmed == 0
        assert report.contradicted == 0
        assert report.unverifiable == 0
        assert report.unexplained_count == 0
        assert report.success is True

    def test_count_properties(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED)
        results = [
            VerificationResult(claim=c, verdict=Verdict.CONFIRMED),
            VerificationResult(claim=c, verdict=Verdict.CONTRADICTED),
            VerificationResult(claim=c, verdict=Verdict.UNVERIFIABLE),
        ]
        report = VerificationReport(results=results)
        assert report.total_claims == 3
        assert report.confirmed == 1
        assert report.contradicted == 1
        assert report.unverifiable == 1

    def test_success_requires_no_issues(self) -> None:
        c = _make_claim(ClaimType.FILE_CREATED)
        clean = VerificationReport(
            results=[VerificationResult(claim=c, verdict=Verdict.CONFIRMED)],
        )
        assert clean.success is True

        has_unverified = VerificationReport(
            results=[VerificationResult(claim=c, verdict=Verdict.UNVERIFIABLE)],
        )
        assert has_unverified.success is False

        has_contradicted = VerificationReport(
            results=[VerificationResult(claim=c, verdict=Verdict.CONTRADICTED)],
        )
        assert has_contradicted.success is False

        has_unexplained = VerificationReport(
            results=[],
            unexplained_changes=[_make_change(ChangeType.FILE_CREATED)],
        )
        assert has_unexplained.success is False


# ---------------------------------------------------------------------------
# ClaimVerifier — CONFIRMED (happy path)
# ---------------------------------------------------------------------------


class TestClaimVerifierConfirmed:
    def test_file_created_confirmed(self) -> None:
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        changes = [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED
        assert report.confirmed == 1
        assert report.unexplained_count == 0

    def test_file_deleted_confirmed(self) -> None:
        claim = _make_claim(ClaimType.FILE_DELETED, file_path="old.py")
        changes = [_make_change(ChangeType.FILE_DELETED, file_path="old.py")]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_add_function_confirmed(self) -> None:
        claim = _make_claim(
            ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="greet"
        )
        changes = [
            _make_change(
                ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="greet"
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_remove_function_confirmed(self) -> None:
        claim = _make_claim(
            ClaimType.REMOVE_FUNCTION, file_path="app.py", symbol_name="old_fn"
        )
        changes = [
            _make_change(
                ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="old_fn"
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_add_class_confirmed(self) -> None:
        claim = _make_claim(
            ClaimType.ADD_CLASS, file_path="app.py", symbol_name="MyClass"
        )
        changes = [
            _make_change(
                ChangeType.ADD_CLASS, file_path="app.py", symbol_name="MyClass"
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_remove_class_confirmed(self) -> None:
        claim = _make_claim(
            ClaimType.REMOVE_CLASS, file_path="app.py", symbol_name="OldClass"
        )
        changes = [
            _make_change(
                ChangeType.REMOVE_CLASS, file_path="app.py", symbol_name="OldClass"
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_calls_function_confirmed(self) -> None:
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            file_path="app.py",
            symbol_name="run",
            caller_name="main",
            called_name="run",
        )
        changes = [
            _make_change(
                ChangeType.CALL_DETECTED,
                file_path="app.py",
                caller_name="main",
                called_name="run",
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_method_add_confirmed_with_parent_class(self) -> None:
        claim = _make_claim(
            ClaimType.ADD_FUNCTION,
            file_path="widget.py",
            symbol_name="render",
            parent_class="Widget",
        )
        changes = [
            _make_change(
                ChangeType.ADD_FUNCTION,
                file_path="widget.py",
                symbol_name="render",
                parent_class="Widget",
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONFIRMED

    def test_multiple_claims_all_confirmed(self) -> None:
        claims = [
            _make_claim(ClaimType.FILE_CREATED, file_path="new.py"),
            _make_claim(ClaimType.ADD_FUNCTION, file_path="new.py", symbol_name="util"),
        ]
        changes = [
            _make_change(ChangeType.FILE_CREATED, file_path="new.py"),
            _make_change(
                ChangeType.ADD_FUNCTION, file_path="new.py", symbol_name="util"
            ),
        ]
        report = ClaimVerifier.verify(claims, changes)
        assert report.confirmed == 2
        assert report.contradicted == 0
        assert report.unverifiable == 0
        assert report.unexplained_count == 0
        assert report.success is True


# ---------------------------------------------------------------------------
# ClaimVerifier — CONTRADICTED
# ---------------------------------------------------------------------------


class TestClaimVerifierContradicted:
    def test_add_function_contradicted_by_remove(self) -> None:
        claim = _make_claim(
            ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        changes = [
            _make_change(
                ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONTRADICTED

    def test_remove_function_contradicted_by_add(self) -> None:
        claim = _make_claim(
            ClaimType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        changes = [
            _make_change(ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="foo")
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONTRADICTED

    def test_add_class_contradicted_by_remove(self) -> None:
        claim = _make_claim(ClaimType.ADD_CLASS, file_path="app.py", symbol_name="Foo")
        changes = [
            _make_change(ChangeType.REMOVE_CLASS, file_path="app.py", symbol_name="Foo")
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONTRADICTED

    def test_remove_class_contradicted_by_add(self) -> None:
        claim = _make_claim(
            ClaimType.REMOVE_CLASS, file_path="app.py", symbol_name="Foo"
        )
        changes = [
            _make_change(ChangeType.ADD_CLASS, file_path="app.py", symbol_name="Foo")
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONTRADICTED

    def test_file_created_contradicted_by_delete(self) -> None:
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        changes = [_make_change(ChangeType.FILE_DELETED, file_path="new.py")]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONTRADICTED

    def test_file_deleted_contradicted_by_create(self) -> None:
        claim = _make_claim(ClaimType.FILE_DELETED, file_path="old.py")
        changes = [_make_change(ChangeType.FILE_CREATED, file_path="old.py")]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONTRADICTED


# ---------------------------------------------------------------------------
# ClaimVerifier — UNVERIFIABLE
# ---------------------------------------------------------------------------


class TestClaimVerifierUnverifiable:
    def test_no_changes_at_all(self) -> None:
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        report = ClaimVerifier.verify([claim], [])
        assert report.results[0].verdict is Verdict.UNVERIFIABLE

    def test_wrong_file_path(self) -> None:
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        changes = [_make_change(ChangeType.FILE_CREATED, file_path="other.py")]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.UNVERIFIABLE

    def test_wrong_symbol_name(self) -> None:
        claim = _make_claim(
            ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        changes = [
            _make_change(ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="bar")
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.UNVERIFIABLE

    def test_wrong_parent_class(self) -> None:
        claim = _make_claim(
            ClaimType.ADD_FUNCTION,
            file_path="widget.py",
            symbol_name="render",
            parent_class="Widget",
        )
        changes = [
            _make_change(
                ChangeType.ADD_FUNCTION,
                file_path="widget.py",
                symbol_name="render",
                parent_class="Button",
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.UNVERIFIABLE

    def test_calls_function_wrong_caller(self) -> None:
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            file_path="app.py",
            symbol_name="run",
            caller_name="main",
            called_name="run",
        )
        changes = [
            _make_change(
                ChangeType.CALL_DETECTED,
                file_path="app.py",
                caller_name="setup",
                called_name="run",
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.UNVERIFIABLE

    def test_calls_function_wrong_called(self) -> None:
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            file_path="app.py",
            symbol_name="run",
            caller_name="main",
            called_name="run",
        )
        changes = [
            _make_change(
                ChangeType.CALL_DETECTED,
                file_path="app.py",
                caller_name="main",
                called_name="print",
            )
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.UNVERIFIABLE

    def test_calls_function_no_opposite(self) -> None:
        """CALLS_FUNCTION claim with caller that doesn't exist in
        changes → unverifiable."""
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            file_path="app.py",
            symbol_name="run",
            caller_name="main",
            called_name="run",
        )
        # Same file, but a different change type — no match, and
        # caller "main" doesn't exist as ADD_FUNCTION either.
        changes = [_make_change(ChangeType.FILE_CREATED, file_path="app.py")]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.UNVERIFIABLE

    def test_calls_function_contradicted_by_caller_exists(self) -> None:
        """CALLS_FUNCTION claim where the caller function exists as
        ADD_FUNCTION but no matching CALL_DETECTED → CONTRADICTED.
        This catches hallucinated call claims in prompt mode."""
        claim = _make_claim(
            ClaimType.CALLS_FUNCTION,
            file_path="app.py",
            caller_name="validate_email",
            called_name="sanitize_input",
        )
        changes = [
            _make_change(
                ChangeType.ADD_FUNCTION,
                file_path="app.py",
                symbol_name="validate_email",
            ),
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.results[0].verdict is Verdict.CONTRADICTED
        assert report.contradicted == 1


# ---------------------------------------------------------------------------
# ClaimVerifier — unexplained changes
# ---------------------------------------------------------------------------


class TestClaimVerifierUnexplained:
    def test_no_claims_all_changes_unexplained(self) -> None:
        changes = [
            _make_change(ChangeType.FILE_CREATED, file_path="new.py"),
            _make_change(
                ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="foo"
            ),
        ]
        report = ClaimVerifier.verify([], changes)
        assert report.unexplained_count == 2
        assert report.results == []

    def test_some_changes_unexplained(self) -> None:
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        changes = [
            _make_change(ChangeType.FILE_CREATED, file_path="new.py"),
            _make_change(
                ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="foo"
            ),
        ]
        report = ClaimVerifier.verify([claim], changes)
        assert report.confirmed == 1
        assert report.unexplained_count == 1
        assert report.unexplained_changes[0].symbol_name == "foo"

    def test_change_matched_only_once(self) -> None:
        """Two identical claims should not consume the same change
        twice — the second claim should be unverifiable."""
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        changes = [_make_change(ChangeType.FILE_CREATED, file_path="new.py")]
        report = ClaimVerifier.verify([claim, claim], changes)
        assert report.confirmed == 1
        assert report.unverifiable == 1
        assert report.unexplained_count == 0


# ---------------------------------------------------------------------------
# ClaimVerifier — deterministic behaviour
# ---------------------------------------------------------------------------


class TestClaimVerifierDeterministic:
    def test_same_input_same_output(self) -> None:
        claims = [
            _make_claim(ClaimType.FILE_CREATED, file_path="new.py"),
            _make_claim(ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="foo"),
        ]
        changes = [
            _make_change(ChangeType.FILE_CREATED, file_path="new.py"),
            _make_change(
                ChangeType.ADD_FUNCTION, file_path="app.py", symbol_name="foo"
            ),
        ]

        r1 = ClaimVerifier.verify(claims, changes)
        r2 = ClaimVerifier.verify(claims, changes)

        assert r1.success == r2.success
        assert r1.results == r2.results
        assert r1.unexplained_changes == r2.unexplained_changes
        assert r1.confirmed == r2.confirmed
        assert r1.unexplained_count == r2.unexplained_count


# ---------------------------------------------------------------------------
# ClaimVerifier — edge cases
# ---------------------------------------------------------------------------


class TestClaimVerifierEdgeCases:
    def test_empty_claims_no_changes(self) -> None:
        report = ClaimVerifier.verify([], [])
        assert report.total_claims == 0
        assert report.unexplained_count == 0
        assert report.success is True

    def test_only_call_changes_with_no_claims(self) -> None:
        changes = [
            _make_change(
                ChangeType.CALL_DETECTED,
                file_path="app.py",
                caller_name="main",
                called_name="print",
            ),
        ]
        report = ClaimVerifier.verify([], changes)
        assert report.unexplained_count == 1

    def test_matched_change_is_stored_in_result(self) -> None:
        claim = _make_claim(ClaimType.FILE_CREATED, file_path="new.py")
        change = _make_change(ChangeType.FILE_CREATED, file_path="new.py")
        report = ClaimVerifier.verify([claim], [change])
        result = report.results[0]
        assert result.matched_change is not None
        assert result.matched_change is change

    def test_contradicted_change_is_stored_in_result(self) -> None:
        claim = _make_claim(
            ClaimType.ADD_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        change = _make_change(
            ChangeType.REMOVE_FUNCTION, file_path="app.py", symbol_name="foo"
        )
        report = ClaimVerifier.verify([claim], [change])
        result = report.results[0]
        assert result.verdict is Verdict.CONTRADICTED
        assert result.matched_change is change
