"""Comprehensive scanner-level tests for Go symbol extraction.

Mirrors the structure and depth of test_ts_samples/test_phase1_comprehensive.py
but for the Go scanner (tree-sitter-go grammar).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.go_scanner import scan_go_calls, scan_go_file  # noqa: E402

test_dir = Path(__file__).resolve().parent

pass_count = 0
fail_count = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global pass_count, fail_count  # noqa: PLW0603
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

# --- edge_basic.go ---
path = test_dir / "edge_basic.go"
symbols = scan_go_file(path)
sym_names = {s.name for s in symbols}

check("greet (function) captured", "greet" in sym_names)
check("add (function) captured", "add" in sym_names)
check("User (struct) captured", "User" in sym_names)
check("NewUser (constructor) captured", "NewUser" in sym_names)
check("Display (method) captured", "Display" in sym_names)
check("UpdateAge (method) captured", "UpdateAge" in sym_names)
check("Shape (interface) captured", "Shape" in sym_names)
check("UserID (type alias) captured", "UserID" in sym_names)

# Type checks
greet_syms = [s for s in symbols if s.name == "greet"]
check("greet is type FUNCTION",
      all(s.symbol_type.name == "FUNCTION" for s in greet_syms))
user_syms = [s for s in symbols if s.name == "User"]
check("User is type CLASS",
      all(s.symbol_type.name == "CLASS" for s in user_syms))
display_syms = [s for s in symbols if s.name == "Display"]
check("Display is type METHOD with parent_class=User",
      all(s.symbol_type.name == "METHOD" and s.parent_class == "User"
          for s in display_syms))
shape_syms = [s for s in symbols if s.name == "Shape"]
check("Shape is type INTERFACE",
      all(s.symbol_type.name == "INTERFACE" for s in shape_syms))
uid_syms = [s for s in symbols if s.name == "UserID"]
check("UserID is type TYPE_ALIAS",
      all(s.symbol_type.name == "TYPE_ALIAS" for s in uid_syms))

# --- edge_export.go ---
path = test_dir / "edge_export.go"
symbols = scan_go_file(path)
sym_names = {s.name for s in symbols}

check("ExportedFunc captured", "ExportedFunc" in sym_names)
check("unexportedFunc captured", "unexportedFunc" in sym_names)
check("ExportedStruct captured", "ExportedStruct" in sym_names)
check("unexportedStruct captured", "unexportedStruct" in sym_names)
check("ExportedInterface captured", "ExportedInterface" in sym_names)
check("unexportedInterface captured", "unexportedInterface" in sym_names)
check("Status captured", "Status" in sym_names)
check("internalID captured", "internalID" in sym_names)

# --- edge_interfaces.go ---
path = test_dir / "edge_interfaces.go"
symbols = scan_go_file(path)
sym_names = {s.name for s in symbols}

check("Reader (interface) captured", "Reader" in sym_names)
check("Writer (interface) captured", "Writer" in sym_names)
check("ReadWriter (composed interface) captured", "ReadWriter" in sym_names)
check("Buffer (struct) captured", "Buffer" in sym_names)
check("Read (method on Buffer) captured", "Read" in sym_names)
check("Write (method on Buffer) captured", "Write" in sym_names)
check("Any (empty interface) captured", "Any" in sym_names)
check("Stringer (interface) captured", "Stringer" in sym_names)
check("Logger (interface) captured", "Logger" in sym_names)
check("ConsoleLogger (struct) captured", "ConsoleLogger" in sym_names)
check("FileLogger (struct) captured", "FileLogger" in sym_names)

# Interface types
reader_syms = [s for s in symbols if s.name == "Reader"]
check("Reader is type INTERFACE",
      all(s.symbol_type.name == "INTERFACE" for s in reader_syms))
buffer_syms = [s for s in symbols if s.name == "Buffer"]
check("Buffer is type CLASS (struct)",
      all(s.symbol_type.name == "CLASS" for s in buffer_syms))

# --- edge_methods.go ---
path = test_dir / "edge_methods.go"
symbols = scan_go_file(path)
sym_names = {s.name for s in symbols}

check("Counter (struct) captured", "Counter" in sym_names)
check("Value (value receiver) captured", "Value" in sym_names)
check("Increment (pointer receiver) captured", "Increment" in sym_names)
check("Reset (pointer receiver) captured", "Reset" in sym_names)
check("String (pointer receiver) captured", "String" in sym_names)
check("Calculator (struct) captured", "Calculator" in sym_names)
check("Add (method) captured", "Add" in sym_names)
check("Subtract (method) captured", "Subtract" in sym_names)
check("Result (method) captured", "Result" in sym_names)
check("MyInt (type alias) captured", "MyInt" in sym_names)
check("IsPositive (method on MyInt) captured", "IsPositive" in sym_names)

# Method parent classes
value_syms = [s for s in symbols if s.name == "Value"]
check("Value has parent_class=Counter",
      all(s.parent_class == "Counter" for s in value_syms))
add_syms = [s for s in symbols if s.name == "Add"]
check("Add has parent_class=Calculator",
      all(s.parent_class == "Calculator" for s in add_syms))

# --- edge_structs.go ---
path = test_dir / "edge_structs.go"
symbols = scan_go_file(path)
sym_names = {s.name for s in symbols}

check("Base (struct) captured", "Base" in sym_names)
check("Extended (struct) captured", "Extended" in sym_names)
check("FullName (method on Extended) captured", "FullName" in sym_names)
check("Address (struct) captured", "Address" in sym_names)
check("Person (struct) captured", "Person" in sym_names)
check("Location (method on Person) captured", "Location" in sym_names)
check("Config (struct) captured", "Config" in sym_names)
check("DefaultConfig (function) captured", "DefaultConfig" in sym_names)
check("Handler (struct) captured", "Handler" in sym_names)
check("Process (method on Handler) captured", "Process" in sym_names)

# --- edge_init.go ---
path = test_dir / "edge_init.go"
symbols = scan_go_file(path)
sym_names = {s.name for s in symbols}

check("init (init func) captured", "init" in sym_names)
check("makeCounter captured", "makeCounter" in sym_names)
check("validateInput captured", "validateInput" in sym_names)
check("runAsync captured", "runAsync" in sym_names)
check("createChannel captured", "createChannel" in sym_names)

# --- edge_generics.go ---
path = test_dir / "edge_generics.go"
symbols = scan_go_file(path)
sym_names = {s.name for s in symbols}

check("First (generic fn) captured", "First" in sym_names)
check("Contains (generic fn) captured", "Contains" in sym_names)
check("Number (interface) captured", "Number" in sym_names)
check("Sum (generic fn) captured", "Sum" in sym_names)
check("Pair (generic struct) captured", "Pair" in sym_names)
check("NewPair (generic constructor) captured", "NewPair" in sym_names)
check("Map (generic fn) captured", "Map" in sym_names)
check("Stack (generic struct) captured", "Stack" in sym_names)
check("Push (generic method) captured", "Push" in sym_names)
check("Pop (generic method) captured", "Pop" in sym_names)

# Generic method parent classes
push_syms = [s for s in symbols if s.name == "Push"]
check("Push has parent_class containing Stack",
      all("Stack" in (s.parent_class or "") for s in push_syms))


# =========================================================================
# SECTION 2: Error handling
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Error handling")
print(SECTION_SEP)

# Non-existent file
try:
    scan_go_file("/nonexistent/file.go")
    check("Non-existent file raises FileNotFoundError", False)
except FileNotFoundError:
    check("Non-existent file raises FileNotFoundError", True)

# Empty file
with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
    fname = f.name
symbols = scan_go_file(fname)
check("Empty .go file returns empty list", len(symbols) == 0)
os.unlink(fname)

# File with only comments
with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
    f.write("// just a comment\n// another comment\n")
    fname = f.name
symbols = scan_go_file(fname)
check("Comments-only file returns empty list", len(symbols) == 0)
os.unlink(fname)

# Verify repo_root relativisation
with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
    f.write("package main\n\nfunc foo() {}\n")
    fname = Path(f.name)
repo_root = fname.parent
symbols = scan_go_file(fname, repo_root=repo_root)
check("repo_root makes file_path relative", len(symbols) > 0)
if symbols:
    check("file_path is relative when repo_root given",
          not symbols[0].file_path.is_absolute())


# =========================================================================
# SECTION 3: Call detection
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Call detection")
print(SECTION_SEP)

# Simple identifier calls
path = test_dir / "edge_interfaces.go"
raw_calls = scan_go_calls(path)
calls = {(caller, called) for _, caller, called in raw_calls}
check("Read calls copy (stdlib)", ("Read", "copy") in calls)
# len() is called inside Read in basic.go but not edge_interfaces.go
# Verify Read calls copy (which IS detected)
check("Read calls copy (stdlib)", ("Read", "copy") in calls)
check("Write calls append (stdlib)", ("Write", "append") in calls)

# Method calls on receivers are excluded (by design)
path = test_dir / "edge_basic.go"
raw_calls = scan_go_calls(path)
calls = {(caller, called) for _, caller, called in raw_calls}
check("greet does NOT call Display (no simple calls in greet)",
      ("greet", "Display") not in calls)


# =========================================================================
# SECTION 4: Determinism
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Determinism")
print(SECTION_SEP)

path = test_dir / "edge_basic.go"
syms1 = scan_go_file(path)
syms2 = scan_go_file(path)
check("Two scans produce identical results",
      [(s.name, s.symbol_type, s.line_number) for s in syms1]
      == [(s.name, s.symbol_type, s.line_number) for s in syms2])


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
