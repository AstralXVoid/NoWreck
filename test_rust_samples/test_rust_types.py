#!/usr/bin/env python3
"""Type-level sample suite for Rust scanner.

Formal assertions for trait / enum / type alias collection across the
dedicated samples.  Every line number was hand-verified against the source.

Mirrors test_ts_samples/test_phase1_types.py structure.
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.rust_scanner import scan_rust_file  # noqa: E402

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


def symbols_by_name(path: Path) -> dict[str, list]:
    """Return symbol names grouped by name for easy assertion."""
    result: dict[str, list] = {}
    for s in scan_rust_file(path):
        result.setdefault(s.name, []).append(s)
    return result


def check_symbol(
    syms: dict[str, list],
    name: str,
    expected_type: str,
    expected_line: int,
) -> None:
    """Assert a symbol exists with the right type and line number."""
    found = syms.get(name, [])
    check(f"{name} captured", len(found) == 1, f"count={len(found)}")
    if found:
        check(
            f"{name} is type {expected_type}",
            found[0].symbol_type.name == expected_type,
            f"actual={found[0].symbol_type.name}",
        )
        check(
            f"{name} line {expected_line}",
            found[0].line_number == expected_line,
            f"actual={found[0].line_number}",
        )


# =========================================================================
# SECTION 1: Basic type-level declarations (edge_basic.rs)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Basic type-level declarations (edge_basic.rs)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_basic.rs")

check_symbol(syms, "Drawable", "INTERFACE", 33)
check_symbol(syms, "Color", "ENUM", 37)
check_symbol(syms, "UserId", "TYPE_ALIAS", 43)

# Positive control: functions and structs still captured
check_symbol(syms, "greet", "FUNCTION", 3)
check_symbol(syms, "User", "CLASS", 11)


# =========================================================================
# SECTION 2: Trait and impl patterns (edge_traits.rs)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Trait and impl patterns (edge_traits.rs)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_traits.rs")

check_symbol(syms, "Summary", "INTERFACE", 3)
check_symbol(syms, "Serializable", "INTERFACE", 17)
check_symbol(syms, "Display", "INTERFACE", 47)
check_symbol(syms, "Debug", "INTERFACE", 51)

# Structs with trait impls
check_symbol(syms, "Article", "CLASS", 22)
check_symbol(syms, "Point", "CLASS", 55)

# Methods from impl blocks
check_symbol(syms, "summarize", "METHOD", 28)
check_symbol(syms, "to_json", "METHOD", 34)
check_symbol(syms, "from_json", "METHOD", 38)
check_symbol(syms, "fmt", "METHOD", 61)
check_symbol(syms, "debug", "METHOD", 67)

# Verify parent_class for methods
summarize = syms.get("summarize", [])
if summarize:
    check(
        "summarize parent_class is Article",
        summarize[0].parent_class == "Article",
        f"actual={summarize[0].parent_class}",
    )


# =========================================================================
# SECTION 3: Generic impl patterns (edge_generics.rs)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Generic impl patterns (edge_generics.rs)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_generics.rs")

check_symbol(syms, "Pair", "CLASS", 11)
check_symbol(syms, "KeyValue", "CLASS", 26)

# Generic impl methods
pair_new = [s for s in syms.get("new", []) if s.parent_class == "Pair"]
check("Pair::new captured", len(pair_new) == 1, f"count={len(pair_new)}")
if pair_new:
    check(
        "Pair::new is type METHOD",
        pair_new[0].symbol_type.name == "METHOD",
    )
    check(
        "Pair::new parent_class is Pair",
        pair_new[0].parent_class == "Pair",
    )

pair_first = [s for s in syms.get("first", []) if s.parent_class == "Pair"]
check("Pair::first captured", len(pair_first) == 1, f"count={len(pair_first)}")

kv_new = [s for s in syms.get("new", []) if s.parent_class == "KeyValue"]
check("KeyValue::new captured", len(kv_new) == 1, f"count={len(kv_new)}")

# Positive control: generic functions
# Note: "first" appears as both a free function (line 3) and a method
# on Pair (line 21), so we check for the FUNCTION variant specifically.
first_fns = [s for s in syms.get("first", []) if s.symbol_type.name == "FUNCTION"]
check("first (generic fn) captured as FUNCTION", len(first_fns) == 1)
if first_fns:
    check("first is FUNCTION at line 3", first_fns[0].line_number == 3)
check_symbol(syms, "longest", "FUNCTION", 38)
check_symbol(syms, "zip_with", "FUNCTION", 50)


# =========================================================================
# SECTION 4: Derive and attribute patterns (edge_derive.rs)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Derive and attribute patterns (edge_derive.rs)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_derive.rs")

# Derive macros don't affect symbol detection
check_symbol(syms, "Config", "CLASS", 6)
check_symbol(syms, "Point", "CLASS", 12)
check_symbol(syms, "Buffer", "CLASS", 18)
check_symbol(syms, "Repository", "INTERFACE", 31)
check_symbol(syms, "Direction", "ENUM", 37)
check_symbol(syms, "Unused", "TYPE_ALIAS", 46)
check_symbol(syms, "SerdeItem", "CLASS", 50)

# Function with attributes
check_symbol(syms, "platform_specific", "FUNCTION", 25)


# =========================================================================
# SECTION 5: Real-world patterns (edge_realworld.rs)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Real-world patterns (edge_realworld.rs)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_realworld.rs")

check_symbol(syms, "fetch_data", "FUNCTION", 7)
check_symbol(syms, "parse_config", "FUNCTION", 12)
check_symbol(syms, "find_user", "FUNCTION", 20)
check_symbol(syms, "classify", "FUNCTION", 25)
check_symbol(syms, "Config", "CLASS", 34)
check_symbol(syms, "User", "CLASS", 47)
check_symbol(syms, "Describable", "INTERFACE", 59)
check_symbol(syms, "Status", "ENUM", 69)
check_symbol(syms, "Result", "TYPE_ALIAS", 82)
check_symbol(syms, "log_and_return", "FUNCTION", 85)

# Impl methods
check_symbol(syms, "new", "METHOD", 40)
check_symbol(syms, "greet", "METHOD", 53)
check_symbol(syms, "is_active", "METHOD", 76)


# =========================================================================
# SECTION 6: Negatives — members and nested items NOT captured
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Negatives — members and nested items NOT captured")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_negatives.rs")

# Trait method signatures are NOT captured
check("trait method 'find' NOT captured", "find" not in syms)
check("trait method 'save' NOT captured", "save" not in syms)
check("trait method 'delete' NOT captured", "delete" not in syms)

# Struct fields are NOT captured
check("struct field 'title' NOT captured", "title" not in syms)
check("struct field 'content' NOT captured", "content" not in syms)
check("struct field 'views' NOT captured", "views" not in syms)

# Enum variants are NOT captured
check("enum variant 'Red' NOT captured", "Red" not in syms)
check("enum variant 'Green' NOT captured", "Green" not in syms)
check("enum variant 'Blue' NOT captured", "Blue" not in syms)

# Nested function inside fn body is NOT captured
check("nested fn 'helper' NOT captured", "helper" not in syms)

# Items inside mod blocks are NOT captured
check("mod item 'secret' NOT captured", "secret" not in syms)
check("mod item 'Hidden' NOT captured", "Hidden" not in syms)

# But top-level items ARE captured
check("top-level 'Repository' captured", "Repository" in syms)
check("top-level 'Article' captured", "Article" in syms)
check("top-level 'Color' captured", "Color" in syms)
check("top-level 'outer' captured", "outer" in syms)
check("method 'summary' captured", "summary" in syms)


# =========================================================================
# SECTION 7: Method parent_class accuracy
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Method parent_class accuracy")
print(SECTION_SEP)

# edge_basic.rs
syms = symbols_by_name(test_dir / "edge_basic.rs")
new_methods = syms.get("new", [])
check("User::new parent_class is User",
      any(m.parent_class == "User" for m in new_methods),
      f"actual={[m.parent_class for m in new_methods]}")

display_methods = syms.get("display", [])
check("User::display parent_class is User",
      any(m.parent_class == "User" for m in display_methods),
      f"actual={[m.parent_class for m in display_methods]}")

update_methods = syms.get("update_age", [])
check("User::update_age parent_class is User",
      any(m.parent_class == "User" for m in update_methods),
      f"actual={[m.parent_class for m in update_methods]}")


# =========================================================================
# SECTION 8: Edge cases — macro invocations, pub use
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 8: Edge cases — macro invocations, pub use")
print(SECTION_SEP)

# edge_realworld.rs: macro invocations should NOT be symbols
realworld_syms = scan_rust_file(test_dir / "edge_realworld.rs")
realworld_names = {s.name for s in realworld_syms}
check("println! NOT captured as symbol", "println" not in realworld_names)
check("dbg! NOT captured as symbol", "dbg" not in realworld_names)


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
