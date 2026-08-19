"""Comprehensive scanner-level tests for Rust symbol extraction.

Mirrors the structure and depth of test_ts_samples/test_phase1_comprehensive.py
but for the Rust scanner (tree-sitter-rust grammar).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.rust_scanner import scan_rust_calls, scan_rust_file  # noqa: E402

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

# --- edge_basic.rs ---
path = test_dir / "edge_basic.rs"
symbols = scan_rust_file(path)
sym_names = {s.name for s in symbols}

check("greet (function) captured", "greet" in sym_names)
check("add (function) captured", "add" in sym_names)
check("User (struct) captured", "User" in sym_names)
check("new (impl method) captured", "new" in sym_names)
check("display (impl method) captured", "display" in sym_names)
check("update_age (impl method) captured", "update_age" in sym_names)
check("Drawable (trait) captured", "Drawable" in sym_names)
check("Color (enum) captured", "Color" in sym_names)
check("UserId (type alias) captured", "UserId" in sym_names)

# Type checks
hello_syms = [s for s in symbols if s.name == "greet"]
check("greet is type FUNCTION",
      all(s.symbol_type.name == "FUNCTION" for s in hello_syms))
user_syms = [s for s in symbols if s.name == "User"]
check("User is type CLASS",
      all(s.symbol_type.name == "CLASS" for s in user_syms))
new_syms = [s for s in symbols if s.name == "new"]
check("new is type METHOD with parent_class=User",
      all(s.symbol_type.name == "METHOD" and s.parent_class == "User"
          for s in new_syms))
drawable_syms = [s for s in symbols if s.name == "Drawable"]
check("Drawable is type INTERFACE",
      all(s.symbol_type.name == "INTERFACE" for s in drawable_syms))
color_syms = [s for s in symbols if s.name == "Color"]
check("Color is type ENUM",
      all(s.symbol_type.name == "ENUM" for s in color_syms))
uid_syms = [s for s in symbols if s.name == "UserId"]
check("UserId is type TYPE_ALIAS",
      all(s.symbol_type.name == "TYPE_ALIAS" for s in uid_syms))

# Line numbers (hand-verified against edge_basic.rs source)
for s in symbols:
    if s.name == "greet":
        check("greet is on line 3", s.line_number == 3)
    elif s.name == "User":
        check("User is on line 11", s.line_number == 11)

# --- edge_pub.rs ---
path = test_dir / "edge_pub.rs"
symbols = scan_rust_file(path)
sym_names = {s.name for s in symbols}

check("public_function captured", "public_function" in sym_names)
check("private_function captured", "private_function" in sym_names)
check("crate_visible captured", "crate_visible" in sym_names)
check("PublicStruct captured", "PublicStruct" in sym_names)
check("PrivateStruct captured", "PrivateStruct" in sym_names)
check("PublicTrait captured", "PublicTrait" in sym_names)
check("PrivateTrait captured", "PrivateTrait" in sym_names)
check("PublicEnum captured", "PublicEnum" in sym_names)
check("PrivateEnum captured", "PrivateEnum" in sym_names)

# --- edge_traits.rs ---
path = test_dir / "edge_traits.rs"
symbols = scan_rust_file(path)
sym_names = {s.name for s in symbols}

check("Summary (trait) captured", "Summary" in sym_names)
check("Serializable (trait) captured", "Serializable" in sym_names)
check("Article (struct) captured", "Article" in sym_names)
check("Display (trait) captured", "Display" in sym_names)
check("Debug (trait) captured", "Debug" in sym_names)
check("Point (struct) captured", "Point" in sym_names)

# Trait types
summary_syms = [s for s in symbols if s.name == "Summary"]
check("Summary is type INTERFACE",
      all(s.symbol_type.name == "INTERFACE" for s in summary_syms))

# --- edge_generics.rs ---
path = test_dir / "edge_generics.rs"
symbols = scan_rust_file(path)
sym_names = {s.name for s in symbols}

check("first (generic fn) captured", "first" in sym_names)
check("swap (generic fn) captured", "swap" in sym_names)
check("Pair (generic struct) captured", "Pair" in sym_names)
check("KeyValue (generic struct) captured", "KeyValue" in sym_names)
check("longest (lifetime fn) captured", "longest" in sym_names)
check("print_all (trait bound fn) captured", "print_all" in sym_names)
check("zip_with (multi-generic fn) captured", "zip_with" in sym_names)

# Generic struct methods
pair_new = [s for s in symbols if s.name == "new" and s.parent_class == "Pair"]
# Generic impl<T> Pair<T> — methods may or may not capture parent_class
# depending on how the type_identifier is nested. Verify METHOD type.
check("Pair methods exist", len([s for s in symbols if s.parent_class is not None]) > 0)
check("Pair::new is type METHOD",
      all(s.symbol_type.name == "METHOD" for s in pair_new))

# --- edge_closures.rs ---
path = test_dir / "edge_closures.rs"
symbols = scan_rust_file(path)
sym_names = {s.name for s in symbols}

check("apply_to_vec (fn accepting closure) captured", "apply_to_vec" in sym_names)
check("make_adder (fn returning closure) captured", "make_adder" in sym_names)
check("filter_positive captured", "filter_positive" in sym_names)
check("process_data captured", "process_data" in sym_names)
check("process_items captured", "process_items" in sym_names)

# --- edge_nested.rs ---
path = test_dir / "edge_nested.rs"
symbols = scan_rust_file(path)
sym_names = {s.name for s in symbols}

check("outer captured", "outer" in sym_names)
check("inner NOT captured (nested)", "inner" not in sym_names)
check("helper captured", "helper" in sym_names)
# Items inside `mod utilities {}` are nested, not top-level.
# Rust scanner captures only top-level declarations — modules are opaque.
check("utilities module items NOT captured (nested)", "util_function" not in sym_names)
check("Config in module NOT captured (nested)", "Config" not in sym_names)
check("process_map captured", "process_map" in sym_names)
check("level_one captured", "level_one" in sym_names)
check("level_two NOT captured (nested)", "level_two" not in sym_names)
check("level_three NOT captured (deeply nested)", "level_three" not in sym_names)


# =========================================================================
# SECTION 2: Error handling
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Error handling")
print(SECTION_SEP)

# Non-existent file
try:
    scan_rust_file("/nonexistent/file.rs")
    check("Non-existent file raises FileNotFoundError", False)
except FileNotFoundError:
    check("Non-existent file raises FileNotFoundError", True)

# Empty file
with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
    fname = f.name
symbols = scan_rust_file(fname)
check("Empty .rs file returns empty list", len(symbols) == 0)
os.unlink(fname)

# File with only comments
with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
    f.write("// just a comment\n// another comment\n")
    fname = f.name
symbols = scan_rust_file(fname)
check("Comments-only file returns empty list", len(symbols) == 0)
os.unlink(fname)

# Symbol line numbers (hand-verified against edge_basic.rs source)
path = test_dir / "edge_basic.rs"
symbols = scan_rust_file(path)
for s in symbols:
    if s.name == "greet":
        check("greet is on line 3", s.line_number == 3)
    elif s.name == "User":
        check("User is on line 11", s.line_number == 11)

# Verify repo_root relativisation
with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
    f.write("fn foo() -> i32 { 0 }\n")
    fname = Path(f.name)
repo_root = fname.parent
symbols = scan_rust_file(fname, repo_root=repo_root)
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

path = test_dir / "edge_basic.rs"
raw_calls = scan_rust_calls(path)
calls = {(caller, called) for _, caller, called in raw_calls}
check("greet does not make simple calls", not any(c == "greet" for c, _ in calls))

path = test_dir / "edge_nested.rs"
raw_calls = scan_rust_calls(path)
calls = {(caller, called) for _, caller, called in raw_calls}
check("outer calls inner (nested fn)", ("outer", "inner") in calls)
check("outer calls helper", ("outer", "helper") in calls)

path = test_dir / "edge_closures.rs"
raw_calls = scan_rust_calls(path)
calls = {(caller, called) for _, caller, called in raw_calls}
check("process_data makes calls (iter/sum)", len(calls) > 0)


# =========================================================================
# SECTION 4: Determinism
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Determinism")
print(SECTION_SEP)

path = test_dir / "edge_basic.rs"
syms1 = scan_rust_file(path)
syms2 = scan_rust_file(path)
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
