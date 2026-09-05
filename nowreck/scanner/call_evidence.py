"""Call-evidence type shared by all five language scanners.

v0.16.0 replaces the bare ``(Path, str, str)`` tuples returned by the
Python, JS/TS, Rust, and Go call extractors with a single frozen
dataclass.  Carrying the caller's enclosing class lets the verifier
distinguish ``Widget.render`` from ``Window.render`` and gives method
calls (``self.foo()``, ``obj.bar()``) a first-class identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CallEvidence:
    """A single call site: some caller invokes *called_name*.

    Attributes:
        file_path: Path relative to the repository root.
        caller_name: Name of the calling function or method.
        called_name: Final method/function name being called.  Required
            — every call has one; the receiver chain is deliberately not
            part of identity (``self.foo()`` and ``obj.foo()`` both
            yield ``called_name="foo"``).
        caller_parent_class: Enclosing class of the caller, ``None`` for
            top-level functions.
    """

    file_path: Path
    caller_name: str
    called_name: str
    caller_parent_class: str | None = None
