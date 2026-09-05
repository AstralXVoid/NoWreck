"""Unit tests for CallEvidence (v0.16.0 Phase 1).

CallEvidence replaces the bare ``(Path, str, str)`` call tuples across
all five language extractors.  It carries the caller's enclosing class so
the verifier can distinguish same-named methods in different classes and
gives method calls (``self.foo()``, ``obj.bar()``) a first-class identity.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nowreck.scanner.call_evidence import CallEvidence


class TestCallEvidence:
    """The CallEvidence value object contract."""

    def test_top_level_call(self) -> None:
        """A call from a top-level function has no parent class."""
        ev = CallEvidence(
            file_path=Path("app.py"),
            caller_name="main",
            called_name="helper",
        )
        assert ev.file_path == Path("app.py")
        assert ev.caller_name == "main"
        assert ev.called_name == "helper"
        assert ev.caller_parent_class is None

    def test_method_call_carries_parent_class(self) -> None:
        """A call from inside a method records the enclosing class."""
        ev = CallEvidence(
            file_path=Path("app.py"),
            caller_name="render",
            called_name="sanitize",
            caller_parent_class="Widget",
        )
        assert ev.caller_parent_class == "Widget"

    def test_frozen_cannot_be_mutated(self) -> None:
        """CallEvidence is immutable."""
        ev = CallEvidence(
            file_path=Path("app.py"),
            caller_name="main",
            called_name="helper",
        )
        with pytest.raises(AttributeError):
            ev.called_name = "other"  # type: ignore[misc]

    def test_called_name_is_required(self) -> None:
        """Every call has a target — omitting it is a construction bug
        (Accepted Edges #5)."""
        with pytest.raises(TypeError):
            CallEvidence(  # type: ignore[call-arg]
                file_path=Path("app.py"),
                caller_name="main",
            )

    def test_equality_ignores_receiver_chain(self) -> None:
        """``self.foo()`` and ``obj.foo()`` share an identity: the
        receiver chain is deliberately not part of the evidence."""
        from_self = CallEvidence(
            file_path=Path("app.py"),
            caller_name="render",
            called_name="foo",
            caller_parent_class="Widget",
        )
        from_obj = CallEvidence(
            file_path=Path("app.py"),
            caller_name="render",
            called_name="foo",
            caller_parent_class="Widget",
        )
        assert from_self == from_obj
        assert hash(from_self) == hash(from_obj)

    def test_equality_distinguishes_callers_and_classes(self) -> None:
        """Same called name from different callers or classes differs."""
        base = CallEvidence(
            file_path=Path("app.py"),
            caller_name="render",
            called_name="foo",
            caller_parent_class="Widget",
        )
        other_caller = CallEvidence(
            file_path=Path("app.py"),
            caller_name="setup",
            called_name="foo",
            caller_parent_class="Widget",
        )
        other_class = CallEvidence(
            file_path=Path("app.py"),
            caller_name="render",
            called_name="foo",
            caller_parent_class="Window",
        )
        assert base != other_caller
        assert base != other_class

    def test_usable_in_sets(self) -> None:
        """Frozen dataclass hashing supports set-diff detection."""
        pre = {
            CallEvidence(Path("a.py"), "main", "helper"),
            CallEvidence(Path("a.py"), "render", "foo", "Widget"),
        }
        post = {
            CallEvidence(Path("a.py"), "render", "foo", "Widget"),
        }
        assert pre - post == {CallEvidence(Path("a.py"), "main", "helper")}
