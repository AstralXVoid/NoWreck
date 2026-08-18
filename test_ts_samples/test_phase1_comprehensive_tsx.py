#!/usr/bin/env python3
"""Comprehensive test suite for the TSX scanner (Phase 3, v0.7.0)."""

import os
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.typescript_scanner import (  # noqa: E402
    scan_ts_calls,
    scan_ts_file,
)

test_dir = Path(__file__).resolve().parent

pass_count = 0
fail_count = 0


def check(
    label: str,
    condition: bool,
    detail: str = "",
) -> None:
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  ✅ PASS: {label}")
    else:
        fail_count += 1
        msg = f"  ❌ FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


SECTION_SEP = "-" * 70


def symbols_by_name(path: Path) -> dict[str, list]:
    """Return symbol names grouped by name for easy assertion."""
    result: dict[str, list] = {}
    for s in scan_ts_file(path):
        result.setdefault(s.name, []).append(s)
    return result


def call_tuples(path: Path) -> set[tuple[str, str]]:
    """Return (caller, called) pairs without file paths."""
    return {(caller, called) for (_, caller, called) in scan_ts_calls(path)}


# =========================================================================
# SECTION 1: Component shapes (edge_tsx_components.tsx)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Component shapes")
print(SECTION_SEP)

path = test_dir / "edge_tsx_components.tsx"
syms = symbols_by_name(path)

check("Greeting (function component) captured", "Greeting" in syms)
check(
    "Greeting is type FUNCTION",
    all(s.symbol_type.name == "FUNCTION" for s in syms.get("Greeting", [])),
)
check("Card (arrow component) captured", "Card" in syms)
check(
    "Card is type FUNCTION",
    all(s.symbol_type.name == "FUNCTION" for s in syms.get("Card", [])),
)
check("Profile (class component) captured", "Profile" in syms)
check(
    "Profile is type CLASS",
    all(s.symbol_type.name == "CLASS" for s in syms.get("Profile", [])),
)
check(
    "render (method) captured with parent_class=Profile",
    all(
        s.symbol_type.name == "METHOD" and s.parent_class == "Profile"
        for s in syms.get("render", [])
    ),
)
check("Page (fragment-returning function) captured", "Page" in syms)

# Line numbers must match the actual source
for s in scan_ts_file(path):
    if s.name == "Greeting":
        check("Greeting line 2", s.line_number == 2)
    elif s.name == "Card":
        check("Card line 6", s.line_number == 6)
    elif s.name == "Profile":
        check("Profile line 14", s.line_number == 14)
    elif s.name == "render":
        check("render line 15", s.line_number == 15)
    elif s.name == "Page":
        check("Page line 20", s.line_number == 20)

# JSX usage is NOT a call: <Greeting name="Ada" /> is an element, not a call
calls = call_tuples(path)
check("JSX element usage produces no calls", calls == set())


# =========================================================================
# SECTION 2: Handlers and nested arrows (edge_tsx_handlers.tsx)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Handlers and nested arrows")
print(SECTION_SEP)

path = test_dir / "edge_tsx_handlers.tsx"
syms = symbols_by_name(path)

check("Button captured", "Button" in syms)
check("Form captured", "Form" in syms)
check("Toggle (class) captured", "Toggle" in syms)
check(
    "toggle method captured with parent_class=Toggle",
    all(s.parent_class == "Toggle" for s in syms.get("toggle", [])),
)
check(
    "render method captured with parent_class=Toggle",
    all(s.parent_class == "Toggle" for s in syms.get("render", [])),
)

calls = call_tuples(path)
check(
    "handleClick -> trackEvent (nested arrow assignee)",
    ("handleClick", "trackEvent") in calls,
)
check("submit -> sendForm (nested arrow assignee)", ("submit", "sendForm") in calls)
check("toggle -> flipState (method body call)", ("toggle", "flipState") in calls)
# onClick={onClick} is an identifier, not a call
check(
    "identifier handler (onClick={onClick}) produces no call",
    ("Button", "onClick") not in calls and ("Button", "trackEvent") not in calls,
)
# this.toggle() is a member-expression call, ignored
check(
    "member call this.toggle() NOT captured",
    not any(
        called == "toggle" and caller == "render"
        for called, caller in {(c, r) for (r, c) in calls}
    ),
)


# =========================================================================
# SECTION 3: Exports, generics, interfaces (edge_tsx_exports.tsx)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Exports, generics, interfaces")
print(SECTION_SEP)

path = test_dir / "edge_tsx_exports.tsx"
syms = symbols_by_name(path)

check("App (export default function) captured", "App" in syms)
check("Header (export function) captured", "Header" in syms)
check("Footer (export const arrow) captured", "Footer" in syms)
check("List (generic function component) captured", "List" in syms)
check("AdminPanel (export class) captured", "AdminPanel" in syms)
check(
    "AdminPanel.render captured with parent_class=AdminPanel",
    all(s.parent_class == "AdminPanel" for s in syms.get("render", [])),
)

# Interfaces are captured as INTERFACE symbols (since v0.8.0)
check("ListProps interface captured", "ListProps" in syms)
listprops_syms = syms.get("ListProps", [])
check("ListProps is type INTERFACE",
      all(s.symbol_type.name == "INTERFACE" for s in listprops_syms))

# Line numbers
for s in scan_ts_file(path):
    if s.name == "App":
        check("App line 2", s.line_number == 2)
    elif s.name == "Header":
        check("Header line 6", s.line_number == 6)
    elif s.name == "Footer":
        check("Footer line 10", s.line_number == 10)
    elif s.name == "List":
        check("List line 18", s.line_number == 18)
    elif s.name == "AdminPanel":
        check("AdminPanel line 22", s.line_number == 22)


# =========================================================================
# SECTION 4: Anonymous default export (edge_tsx_anon_default.tsx)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Anonymous default export")
print(SECTION_SEP)

path = test_dir / "edge_tsx_anon_default.tsx"
syms = scan_ts_file(path)
check("anonymous export default () => <div/> NOT captured", len(syms) == 0)
check("anonymous default produces no calls", scan_ts_calls(path) == set())


# =========================================================================
# SECTION 5: Mixed edge cases (edge_tsx_mixed.tsx)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Mixed edge cases")
print(SECTION_SEP)

path = test_dir / "edge_tsx_mixed.tsx"
syms = symbols_by_name(path)

check("useUser captured", "useUser" in syms)
check("Dashboard captured", "Dashboard" in syms)
check("workingArrow captured", "workingArrow" in syms)
check("interface User captured", "User" in syms)
check("type Status captured", "Status" in syms)
check("enum Color captured", "Color" in syms)
check("config IIFE NOT captured", "config" not in syms)

user_syms = syms.get("User", [])
check("User is type INTERFACE",
      all(s.symbol_type.name == "INTERFACE" for s in user_syms))
status_syms = syms.get("Status", [])
check("Status is type TYPE_ALIAS",
      all(s.symbol_type.name == "TYPE_ALIAS" for s in status_syms))
color_syms = syms.get("Color", [])
check("Color is type ENUM",
      all(s.symbol_type.name == "ENUM" for s in color_syms))

calls = call_tuples(path)
check("Dashboard -> useUser (call in JSX-in-body)", ("Dashboard", "useUser") in calls)
check(
    "useUser -> fetchUser (call before return JSX)", ("useUser", "fetchUser") in calls
)


# =========================================================================
# SECTION 6: Error handling and structure
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Error handling and structure")
print(SECTION_SEP)

# Non-existent file
try:
    scan_ts_file("/nonexistent/file.tsx")
    check("Non-existent .tsx raises FileNotFoundError", False)
except FileNotFoundError:
    check("Non-existent .tsx raises FileNotFoundError", True)

# Empty .tsx file
with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
    fname = f.name
syms = scan_ts_file(fname)
check("Empty .tsx file returns empty list", len(syms) == 0)
os.unlink(fname)

# Comments-only .tsx
with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
    f.write("// just a comment\n// another comment\n")
    fname = f.name
syms = scan_ts_file(fname)
check("Comments-only .tsx returns empty list", len(syms) == 0)
os.unlink(fname)

# repo_root relativisation
with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
    f.write("function foo(): JSX.Element { return <div/>; }\n")
    fname = Path(f.name)
repo_root = fname.parent
syms = scan_ts_file(fname, repo_root=repo_root)
check("repo_root makes .tsx file_path relative", len(syms) > 0)
if syms:
    check(
        "file_path is relative when repo_root given",
        not syms[0].file_path.is_absolute(),
    )

# Determinism: same file parsed twice gives identical results
p = test_dir / "edge_tsx_components.tsx"
s1 = scan_ts_file(p)
s2 = scan_ts_file(p)
same = [(x.name, x.symbol_type.name, x.line_number, x.parent_class) for x in s1] == [
    (x.name, x.symbol_type.name, x.line_number, x.parent_class) for x in s2
]
check("TSX symbol extraction deterministic", same)
check("TSX call extraction deterministic", scan_ts_calls(p) == scan_ts_calls(p))


# =========================================================================
# RESULTS
# =========================================================================
total = pass_count + fail_count
print(f"\n{SECTION_SEP}")
print(f"  RESULTS: {pass_count} passed, {fail_count} failed, {total} total")
print(SECTION_SEP)
print(f"\n  {'✅ All tests passed!' if fail_count == 0 else '❌ Some tests failed!'}")


if __name__ == "__main__":
    if fail_count > 0:
        sys.exit(1)
