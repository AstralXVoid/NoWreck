#!/usr/bin/env python3
"""Comprehensive test suite for the TypeScript scanner (Phase 1, v0.5.0)."""

import os
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.typescript_scanner import scan_ts_file  # noqa: E402

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


# =========================================================================
# SECTION 1: Core positive detection
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Core positive detection")
print(SECTION_SEP)

# --- edge_basic.ts ---
path = test_dir / "edge_basic.ts"
symbols = scan_ts_file(path)
sym_names = {s.name for s in symbols}

check("hello (function declaration) captured", "hello" in sym_names)
check("world (arrow function) captured", "world" in sym_names)
check("MyClass (class) captured", "MyClass" in sym_names)
check("greet (method) captured", "greet" in sym_names)

# Verify types
hello_syms = [s for s in symbols if s.name == "hello"]
check("hello is type FUNCTION",
      all(s.symbol_type.name == "FUNCTION" for s in hello_syms))

myclass_syms = [s for s in symbols if s.name == "MyClass"]
check("MyClass is type CLASS",
      all(s.symbol_type.name == "CLASS" for s in myclass_syms))

greet_syms = [s for s in symbols if s.name == "greet"]
check("greet is type METHOD with parent_class=MyClass",
      all(s.symbol_type.name == "METHOD"
          and s.parent_class == "MyClass" for s in greet_syms))

# --- edge_export.ts ---
path = test_dir / "edge_export.ts"
symbols = scan_ts_file(path)
sym_names = {s.name for s in symbols}

check("exportedFunc (export function) captured", "exportedFunc" in sym_names)
check("ExportedClass (export class) captured", "ExportedClass" in sym_names)
check("arrowExport (export const arrow) captured", "arrowExport" in sym_names)
check("defaultFunc (export default function) captured", "defaultFunc" in sym_names)
check("DefaultClass (export default class) captured", "DefaultClass" in sym_names)
check("method (inside ExportedClass) captured", "method" in sym_names)
check("doStuff (inside DefaultClass) captured", "doStuff" in sym_names)

# --- edge_generators.ts ---
path = test_dir / "edge_generators.ts"
symbols = scan_ts_file(path)
sym_names = {s.name for s in symbols}

check("generatorDecl (function* decl) captured", "generatorDecl" in sym_names)
check("generatorExpr (const function*) captured", "generatorExpr" in sym_names)
check("asyncGen (async function*) captured", "asyncGen" in sym_names)
check("exportedGen (export function*) captured", "exportedGen" in sym_names)
check("defaultGen (export default function*) captured", "defaultGen" in sym_names)
check("normalFunc (positive control) captured", "normalFunc" in sym_names)
check("normalArrow (positive control) captured", "normalArrow" in sym_names)
check("notAGen (non-generator function expression) NOT captured",
      "notAGen" not in sym_names)

# --- edge_iife.ts ---
path = test_dir / "edge_iife.ts"
symbols = scan_ts_file(path)
sym_names = {s.name for s in symbols}

check("config IIFE assigned to const NOT captured", "config" not in sym_names)
check("theme arrow IIFE NOT captured", "theme" not in sym_names)
check("oldStyle var IIFE NOT captured", "oldStyle" not in sym_names)
check("normalArrow (positive control) captured", "normalArrow" in sym_names)
check("normalFunc (positive control) captured", "normalFunc" in sym_names)

# --- edge_types_only.ts (type-level constructs — captured since v0.8.0) ---
path = test_dir / "edge_types_only.ts"
symbols = scan_ts_file(path)
sym_names = {s.name for s in symbols}

check("interface User captured", "User" in sym_names)
check("type alias Status captured", "Status" in sym_names)
check("enum Color captured", "Color" in sym_names)
check("workingFunction (positive control) captured", "workingFunction" in sym_names)
check("WorkingClass (positive control) captured", "WorkingClass" in sym_names)
check("method (inside WorkingClass) captured", "method" in sym_names)
check("workingArrow (positive control) captured", "workingArrow" in sym_names)

# Type + line-number checks for the type-level symbols
user_syms = [s for s in symbols if s.name == "User"]
check("User is type INTERFACE",
      all(s.symbol_type.name == "INTERFACE" for s in user_syms))
status_syms = [s for s in symbols if s.name == "Status"]
check("Status is type TYPE_ALIAS",
      all(s.symbol_type.name == "TYPE_ALIAS" for s in status_syms))
color_syms = [s for s in symbols if s.name == "Color"]
check("Color is type ENUM",
      all(s.symbol_type.name == "ENUM" for s in color_syms))
for s in symbols:
    if s.name == "User":
        check("User line 5 (interface declaration line)",
              s.line_number == 5)
    elif s.name == "Status":
        check("Status line 10 (type alias line)",
              s.line_number == 10)
    elif s.name == "Color":
        check("Color line 12 (enum declaration line)",
              s.line_number == 12)


# =========================================================================
# SECTION 2: Error handling
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Error handling")
print(SECTION_SEP)

# Non-existent file
try:
    scan_ts_file("/nonexistent/file.ts")
    check("Non-existent file raises FileNotFoundError", False)
except FileNotFoundError:
    check("Non-existent file raises FileNotFoundError", True)

# Empty file
with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
    fname = f.name
symbols = scan_ts_file(fname)
check("Empty .ts file returns empty list", len(symbols) == 0)
os.unlink(fname)

# File with only comments
with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
    f.write("// just a comment\n// another comment\n")
    fname = f.name
symbols = scan_ts_file(fname)
check("Comments-only file returns empty list", len(symbols) == 0)
os.unlink(fname)

# Symbol line numbers
path = test_dir / "edge_basic.ts"
symbols = scan_ts_file(path)
for s in symbols:
    if s.name == "hello":
        check("hello line number is 2 (function declaration line)",
              s.line_number == 2)
    elif s.name == "world":
        check("world line number is 6 (const assignment line)",
              s.line_number == 6)
    elif s.name == "MyClass":
        check("MyClass line number is 10 (class declaration line)",
              s.line_number == 10)

# Verify repo_root relativisation
with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
    f.write("function foo(): void {}\n")
    fname = Path(f.name)
# Create a fake repo root that contains the file
repo_root = fname.parent
symbols = scan_ts_file(fname, repo_root=repo_root)
check("repo_root makes file_path relative", len(symbols) > 0)
if symbols:
    check("file_path is relative when repo_root given",
          not symbols[0].file_path.is_absolute())


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
