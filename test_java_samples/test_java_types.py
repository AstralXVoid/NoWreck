#!/usr/bin/env python3
"""Type-level sample suite for the Java scanner.

Formal assertions for class / interface / enum / record collection across
the dedicated samples.  Every line number was hand-verified against the
source (and re-verified against the scanner output).

Mirrors test_rust_samples/test_rust_types.py structure.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.java_scanner import scan_java_file  # noqa: E402

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
    for s in scan_java_file(path):
        result.setdefault(s.name, []).append(s)
    return result


def check_symbol(
    syms: dict[str, list],
    name: str,
    expected_type: str,
    expected_line: int,
) -> None:
    """Assert a symbol of *expected_type* exists at *expected_line*.

    Filtered by type because a Java type and its constructor share a name
    (``class Point`` and ``Point(...)``) — both are symbols.
    """
    found = [s for s in syms.get(name, []) if s.symbol_type.name == expected_type]
    check(f"{name} captured as {expected_type}", len(found) == 1, f"count={len(found)}")
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
# SECTION 1: Basic type-level declarations (basic.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Basic declarations (basic.java)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "basic.java")

check_symbol(syms, "Basic", "CLASS", 4)
check_symbol(syms, "Shape", "INTERFACE", 20)
check_symbol(syms, "Color", "ENUM", 24)
check_symbol(syms, "Point", "CLASS", 28)
check_symbol(syms, "area", "METHOD", 21)


# =========================================================================
# SECTION 2: Interfaces (edge_interfaces.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Interfaces (edge_interfaces.java)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_interfaces.java")

check_symbol(syms, "Greeter", "INTERFACE", 4)
check_symbol(syms, "Extended", "INTERFACE", 22)
# Abstract, default, static and private interface methods are all METHODS.
check_symbol(syms, "name", "METHOD", 7)
check_symbol(syms, "greet", "METHOD", 9)
check_symbol(syms, "of", "METHOD", 13)
check_symbol(syms, "helper", "METHOD", 17)
check_symbol(syms, "count", "METHOD", 23)

greeter = [s for s in syms["greet"] if s.parent_class == "Greeter"]
check("default method parent_class is the interface", len(greeter) == 1)
check(
    "abstract interface method has a hash",
    bool(syms["name"][0].body_hash),
)


# =========================================================================
# SECTION 3: Enums and annotation types (edge_enums.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Enums and annotation types (edge_enums.java)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_enums.java")

check_symbol(syms, "Planet", "ENUM", 4)
check_symbol(syms, "Status", "ENUM", 25)
check_symbol(syms, "Marker", "INTERFACE", 29)  # @interface → INTERFACE
check_symbol(syms, "surfaceGravity", "METHOD", 16)
check_symbol(syms, "heaviest", "METHOD", 20)

planet_ctor = [s for s in syms["Planet"] if s.symbol_type.name == "METHOD"]
check("enum constructor is a METHOD named after the enum", len(planet_ctor) == 1)
check("enum constructor parent_class", planet_ctor[0].parent_class == "Planet")
check(
    "enum shell has a hash (constants are shell content)",
    bool(syms["Planet"][0].body_hash),
)
# Enum constants and the annotation-type elements must not be symbols.
check("enum constants are not symbols", "MERCURY" not in syms)
check("annotation elements are not symbols", "value" not in syms)
check("annotation type elements are not methods", "priority" not in syms)


# =========================================================================
# SECTION 4: Records and sealed types (edge_records.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Records and sealed types (edge_records.java)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_records.java")

check_symbol(syms, "Point", "CLASS", 4)  # record → CLASS
check_symbol(syms, "Shape", "INTERFACE", 24)
check_symbol(syms, "Circle", "CLASS", 28)
check_symbol(syms, "Square", "CLASS", 34)

point_ctors = [s for s in syms["Point"] if s.symbol_type.name == "METHOD"]
check("record compact + canonical constructors are both METHODS", len(point_ctors) == 2)
check(
    "record constructor parent_class",
    all(s.parent_class == "Point" for s in point_ctors),
)
# Record components are shell content — not symbols.
check("record components are not symbols", "x" not in syms and "y" not in syms)


# =========================================================================
# SECTION 5: Method shapes (edge_methods.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Method shapes (edge_methods.java)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_methods.java")

check_symbol(syms, "MethodShapes", "CLASS", 6)
check_symbol(syms, "abstractMethod", "METHOD", 9)
check_symbol(syms, "nativeMethod", "METHOD", 22)
check_symbol(syms, "multiLine", "METHOD", 47)
check_symbol(syms, "varargs", "METHOD", 24)
check_symbol(syms, "generic", "METHOD", 28)
check("overloads are collected separately", len(syms["overloaded"]) == 2)
shape_ctors = [s for s in syms["MethodShapes"] if s.symbol_type.name == "METHOD"]
check("two constructors collected", len(shape_ctors) == 2)
check(
    "overload body hashes differ",
    syms["overloaded"][0].body_hash != syms["overloaded"][1].body_hash,
)
check(
    "every method symbol carries a parent_class",
    all(
        s.parent_class == "MethodShapes"
        for s in scan_java_file(test_dir / "edge_methods.java")
        if s.symbol_type.name == "METHOD"
    ),
)


# =========================================================================
# SECTION 6: Nested and local classes (edge_nested.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Nested classes (edge_nested.java)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_nested.java")

check_symbol(syms, "Outer", "CLASS", 4)
check_symbol(syms, "StaticNested", "CLASS", 15)
check_symbol(syms, "Inner", "CLASS", 24)
check_symbol(syms, "outerMethod", "METHOD", 7)
check_symbol(syms, "staticMethod", "METHOD", 16)
check_symbol(syms, "innerMethod", "METHOD", 25)
check(
    "nested-class method parent_class is the immediate class",
    syms["innerMethod"][0].parent_class == "Inner",
)
check("local class is not a symbol", "Local" not in syms)
check("local class method is not a symbol", "localMethod" not in syms)
check("anonymous class method is not a symbol", "run" not in syms)


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
