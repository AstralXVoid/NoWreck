#!/usr/bin/env python3
"""Type-level sample suite (Phase 3, v0.8.0).

Formal assertions for ``interface`` / ``enum`` / ``type`` alias collection
across the dedicated samples:

- ``edge_types_exports.{ts,tsx}``  — exported + default-exported declarations
- ``edge_types_generics.{ts,tsx}`` — generic declarations + class positive control
- ``edge_types_only.ts``          — base positive sample (negatives here too)

Every line number below was hand-verified against the sample source.
"""

import sys
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


def symbols_by_name(path: Path) -> dict[str, list]:
    """Return symbol names grouped by name for easy assertion."""
    result: dict[str, list] = {}
    for s in scan_ts_file(path):
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
# SECTION 1: Exported type-level declarations (.ts)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Exported type-level declarations (.ts)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_types_exports.ts")

check_symbol(syms, "User", "INTERFACE", 2)
check_symbol(syms, "Color", "ENUM", 7)
check_symbol(syms, "Status", "TYPE_ALIAS", 12)
check_symbol(syms, "Config", "INTERFACE", 14)  # export default interface

# =========================================================================
# SECTION 2: Exported type-level declarations (.tsx)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Exported type-level declarations (.tsx)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_types_exports.tsx")

check_symbol(syms, "ButtonProps", "INTERFACE", 2)
check_symbol(syms, "Variant", "ENUM", 6)
check_symbol(syms, "Size", "TYPE_ALIAS", 11)

# =========================================================================
# SECTION 3: Generic type-level declarations (.ts)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Generic type-level declarations (.ts)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_types_generics.ts")

check_symbol(syms, "Box", "INTERFACE", 2)
check_symbol(syms, "Pair", "TYPE_ALIAS", 6)
check_symbol(syms, "Level", "ENUM", 8)
# Positive control: a generic class still lands as CLASS
check_symbol(syms, "Holder", "CLASS", 13)

# =========================================================================
# SECTION 4: Generic type-level declarations (.tsx)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Generic type-level declarations (.tsx)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_types_generics.tsx")

check_symbol(syms, "ListItem", "INTERFACE", 2)
check_symbol(syms, "Result", "TYPE_ALIAS", 6)

# =========================================================================
# SECTION 5: Negatives — members and type parameters are NOT captured
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Negatives — members and type parameters are NOT captured")
print(SECTION_SEP)

# edge_types_only.ts: interface property names, enum member names
syms = symbols_by_name(test_dir / "edge_types_only.ts")
check("interface property 'name' NOT captured", "name" not in syms)
check("interface property 'age' NOT captured", "age" not in syms)
check("enum member 'Red' NOT captured", "Red" not in syms)
check("enum member 'Green' NOT captured", "Green" not in syms)
check("enum member 'Blue' NOT captured", "Blue" not in syms)

# edge_types_exports.ts: property names + enum member names
syms = symbols_by_name(test_dir / "edge_types_exports.ts")
check("exported interface property 'id' NOT captured", "id" not in syms)
check("exported interface property 'name' NOT captured", "name" not in syms)
check("exported enum member 'Red' NOT captured", "Red" not in syms)
check("exported enum member 'Green' NOT captured", "Green" not in syms)
check("default interface property 'debug' NOT captured", "debug" not in syms)

# edge_types_generics.ts: generic type parameters are not symbols
syms = symbols_by_name(test_dir / "edge_types_generics.ts")
check("generic param 'T' NOT captured", "T" not in syms)
check("generic param 'A' NOT captured", "A" not in syms)
check("generic param 'B' NOT captured", "B" not in syms)
check("interface member 'value' NOT captured", "value" not in syms)

# =========================================================================
# SECTION 6: .ts / .tsx parity — same constructs captured in both
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: .ts / .tsx parity")
print(SECTION_SEP)

ts_syms = symbols_by_name(test_dir / "edge_types_exports.ts")
tsx_syms = symbols_by_name(test_dir / "edge_types_exports.tsx")

check(
    "exports .ts captures interface+enum+type alias",
    "User" in ts_syms and "Color" in ts_syms and "Status" in ts_syms,
)
check(
    "exports .tsx captures interface+enum+type alias",
    "ButtonProps" in tsx_syms
    and "Variant" in tsx_syms
    and "Size" in tsx_syms,
)

ts_gen = symbols_by_name(test_dir / "edge_types_generics.ts")
tsx_gen = symbols_by_name(test_dir / "edge_types_generics.tsx")
check(
    "generics .ts captures interface+type alias",
    "Box" in ts_gen and "Pair" in ts_gen,
)
check(
    "generics .tsx captures interface+type alias",
    "ListItem" in tsx_gen and "Result" in tsx_gen,
)


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
