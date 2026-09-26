#!/usr/bin/env python3
"""Type-level sample suite for the Kotlin scanner.

Formal assertions for class / interface / enum / object / companion /
typealias collection across the dedicated samples.  Every line number was
hand-verified against the source and re-verified against scanner output.

Mirrors test_java_samples/test_java_types.py.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.kotlin_scanner import scan_kotlin_file  # noqa: E402

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
    """Return symbols grouped by name (a name may be defined more than once)."""
    result: dict[str, list] = {}
    for s in scan_kotlin_file(path):
        result.setdefault(s.name, []).append(s)
    return result


def check_symbol(
    syms: dict[str, list],
    name: str,
    expected_type: str,
    expected_line: int,
    parent: str | None = None,
) -> None:
    """Assert a symbol of *expected_type* exists at *expected_line*.

    *parent* disambiguates a name that is legitimately defined more than
    once, e.g. an interface member and the member that implements it.
    """
    found = [s for s in syms.get(name, []) if s.symbol_type.name == expected_type]
    if parent is not None:
        found = [s for s in found if s.parent_class == parent]
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


def check_no_empty_names(path: Path) -> None:
    """The scanner must never emit a nameless symbol (D5 invariant)."""
    names = [s.name for s in scan_kotlin_file(path)]
    check(
        f"{path.name}: no empty symbol names",
        all(name.strip() for name in names),
        f"names={names}",
    )


# =========================================================================
# SECTION 1: Basic declarations (basic.kt)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Basic declarations (basic.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "basic.kt")

check_symbol(syms, "Handler", "TYPE_ALIAS", 3)
check_symbol(syms, "Greeter", "INTERFACE", 5)
check_symbol(syms, "greet", "METHOD", 6)
check_symbol(syms, "Person", "CLASS", 9)
check_symbol(syms, "birthday", "METHOD", 10)
check_symbol(syms, "Color", "ENUM", 15)
check_symbol(syms, "topLevel", "FUNCTION", 21)
check("interface method parent_class", syms["greet"][0].parent_class == "Greeter")
check("top-level fun has no parent_class", syms["topLevel"][0].parent_class is None)
# A typealias has no hash (no CHANGED_TYPE_ALIAS claim exists) and an
# interface carries none either (no CHANGED_INTERFACE), while CLASS/ENUM
# carry a shell hash.
check("typealias carries no hash", syms["Handler"][0].body_hash is None)
check("interface carries no hash", syms["Greeter"][0].body_hash is None)
check("class carries a shell hash", bool(syms["Person"][0].body_hash))
check("enum carries a shell hash", bool(syms["Color"][0].body_hash))
check("enum constants are not symbols", "RED" not in syms)
check_no_empty_names(test_dir / "basic.kt")


# =========================================================================
# SECTION 2: Interfaces (edge_interfaces.kt)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Interfaces (edge_interfaces.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_interfaces.kt")

check_symbol(syms, "Plain", "INTERFACE", 3)
check_symbol(syms, "Sam", "INTERFACE", 7)  # fun interface → INTERFACE
check_symbol(syms, "Shape", "INTERFACE", 11)  # sealed interface → INTERFACE
check_symbol(syms, "WithDefaults", "INTERFACE", 15)
check_symbol(syms, "Impl", "CLASS", 23)
check_symbol(syms, "required", "METHOD", 4, parent="Plain")
check_symbol(syms, "required", "METHOD", 24, parent="Impl")
check_symbol(syms, "only", "METHOD", 8)
check_symbol(syms, "area", "METHOD", 12)
check_symbol(syms, "provided", "METHOD", 16)
check_symbol(syms, "alsoProvided", "METHOD", 20)
plain_required = [s for s in syms["required"] if s.parent_class == "Plain"][0]
impl_required = [s for s in syms["required"] if s.parent_class == "Impl"][0]
check(
    "abstract interface method still carries a body hash",
    bool(plain_required.body_hash),
)
check(
    "an override hashes differently from the declaration it implements",
    plain_required.body_hash != impl_required.body_hash,
)
check_no_empty_names(test_dir / "edge_interfaces.kt")


# =========================================================================
# SECTION 3: Enums, entry bodies and nested enums (edge_enums.kt)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Enums (edge_enums.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_enums.kt")

check_symbol(syms, "Status", "ENUM", 3)
check_symbol(syms, "Level", "ENUM", 8)
check_symbol(syms, "Kind", "ENUM", 21)
check_symbol(syms, "Container", "CLASS", 32)
check_symbol(syms, "Nested", "ENUM", 33)
check_symbol(syms, "describe", "METHOD", 12)
check_symbol(syms, "fromWeight", "METHOD", 15)
check_symbol(syms, "useNested", "METHOD", 38)

check(
    "companion method attributes to the *enum* (not to a companion symbol)",
    all(s.parent_class == "Level" for s in syms["fromWeight"]),
)
check(
    "nested enum parent_class is the outer class",
    syms["Nested"][0].parent_class == "Container",
)
check(
    "enum-entry body method is not a symbol (probe K11)",
    len(syms["name"]) == 1,
    f"count={len(syms['name'])}",
)
check(
    "enum-entry body method keeps the enum as parent",
    syms["name"][0].parent_class == "Kind",
)
check("enum constants are not symbols", "ACTIVE" not in syms and "LOW" not in syms)
check_no_empty_names(test_dir / "edge_enums.kt")


# =========================================================================
# SECTION 4: Objects, companions, anonymous objects (edge_objects.kt)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Objects (edge_objects.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_objects.kt")

check_symbol(syms, "Registry", "CLASS", 3)  # object → CLASS
check_symbol(syms, "Singleton", "CLASS", 9)  # data object → CLASS
check_symbol(syms, "Service", "CLASS", 11)
check_symbol(syms, "Named", "CLASS", 26)
check_symbol(syms, "Holder", "CLASS", 32)
check_symbol(syms, "Helpers", "CLASS", 33)  # nested object is its own class
check_symbol(syms, "lookup", "METHOD", 4)
check_symbol(syms, "create", "METHOD", 13)
check_symbol(syms, "run", "METHOD", 20)
check_symbol(syms, "make", "METHOD", 28)
check_symbol(syms, "help", "METHOD", 34)

check(
    "object member parent_class is the object",
    syms["lookup"][0].parent_class == "Registry",
)
check(
    "unnamed companion method attributes to the *outer* class (probe K3)",
    syms["create"][0].parent_class == "Service",
)
check(
    "named companion method attributes to the *outer* class (probe K3)",
    syms["make"][0].parent_class == "Named",
)
check(
    "companion constant is not a symbol",
    "NAME" not in syms,
)
check(
    "nested object method parent_class is the nested object",
    syms["help"][0].parent_class == "Helpers",
)
check(
    "anonymous-object method is not a symbol (probe K11)",
    all(
        s.symbol_type.name != "METHOD" or s.parent_class is not None
        for s in syms["run"]
    ),
)
check_no_empty_names(test_dir / "edge_objects.kt")


# =========================================================================
# SECTION 5: Class members (edge_members.kt)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Class members (edge_members.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_members.kt")

check_symbol(syms, "Full", "CLASS", 3)
check_symbol(syms, "Generic", "CLASS", 29)
check_symbol(syms, "Base", "CLASS", 35)
check_symbol(syms, "derivedValue", "METHOD", 20)
check_symbol(syms, "helper", "METHOD", 22)
check_symbol(syms, "openMethod", "METHOD", 24)
check_symbol(syms, "internalMethod", "METHOD", 26)
check_symbol(syms, "largest", "METHOD", 30)
check_symbol(syms, "required", "METHOD", 36)
check_symbol(syms, "optional", "METHOD", 38)

full_methods = [s for s in syms["Full"] if s.symbol_type.name == "METHOD"]
check(
    "secondary constructor is a METHOD named after its class",
    len(full_methods) == 1 and full_methods[0].parent_class == "Full",
    f"methods={[(s.name, s.line_number) for s in full_methods]}",
)
check("secondary constructor line", full_methods[0].line_number == 16)
check("constructor parameter properties are not symbols", "value" not in syms)
check(
    "plain properties are not symbols", "computed" not in syms and "mutable" not in syms
)
check("getter/setter bodies are not symbols", "field" not in syms and "set" not in syms)
check("generic class method parent_class", syms["largest"][0].parent_class == "Generic")
check(
    "every METHOD carries a parent_class",
    all(
        s.parent_class is not None
        for s in scan_kotlin_file(test_dir / "edge_members.kt")
        if s.symbol_type.name == "METHOD"
    ),
)
check_no_empty_names(test_dir / "edge_members.kt")


# =========================================================================
# SECTION 6: Annotations, attached and detached (edge_annotations.kt)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Annotations (edge_annotations.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_annotations.kt")

check_symbol(syms, "annotatedLast", "FUNCTION", 3)  # attached (last in file)
check_symbol(syms, "AnnotatedClass", "CLASS", 8)
check_symbol(syms, "MultiAnnotated", "CLASS", 22)
check_symbol(syms, "method", "METHOD", 13)
check_symbol(syms, "multi", "METHOD", 23)
check_symbol(syms, "Marker", "INTERFACE", 30)  # annotation class → INTERFACE
check_symbol(syms, "AnnotatedObject", "CLASS", 34)
check_symbol(syms, "inside", "METHOD", 36)

check(
    "annotated declaration reports the annotation's line (K8)",
    syms["annotatedLast"][0].line_number == 3,
)
check(
    "detached annotation keeps the declaration's line (D4)",
    syms["MultiAnnotated"][0].line_number == 22,
)
check("annotated property is not a symbol", "field" not in syms)
check("use-site-targeted property is not a symbol", "aliased" not in syms)
check_no_empty_names(test_dir / "edge_annotations.kt")


# =========================================================================
# SECTION 7: Grammar-defect recovery (edge_recovery.kt)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Grammar-defect recovery (edge_recovery.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_recovery.kt")

check_symbol(syms, "SingleEntry", "ENUM", 3)  # D2: destroyed by the annotation
check_symbol(syms, "AnnotatedAnnotation", "INTERFACE", 12)  # D3
check_symbol(syms, "MultiEntry", "ENUM", 24)
check_symbol(syms, "AnnotatedObject", "CLASS", 29)
check_symbol(syms, "OneLine", "CLASS", 36)  # D1: accepted edge
check_symbol(syms, "describe", "METHOD", 7)
check_symbol(syms, "followed", "FUNCTION", 15)
check_symbol(syms, "afterFollowed", "FUNCTION", 20)
check_symbol(syms, "work", "METHOD", 31)
check_symbol(syms, "oneLiner", "METHOD", 36)

check("recovered enum keeps its shell hash", bool(syms["SingleEntry"][0].body_hash))
check(
    "recovered annotation class carries no hash",
    syms["AnnotatedAnnotation"][0].body_hash is None,
)
check(
    "recovered enum's member is attributed to it",
    syms["describe"][0].parent_class == "SingleEntry",
)
check(
    "the declaration after a detached annotation is intact",
    syms["afterFollowed"][0].parent_class is None,
)
check(
    "one-line class body still yields its class and member (D1)",
    syms["oneLiner"][0].parent_class == "OneLine",
)
check_no_empty_names(test_dir / "edge_recovery.kt")


# =========================================================================
# SECTION 8: D5 — soft-keyword names are recovered, never emitted nameless
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 8: Soft-keyword names (edge_calls.kt)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_calls.kt")

check(
    "type-body 'fun dynamic()' is recovered as a METHOD",
    len(syms.get("dynamic", [])) == 1,
    f"found={[(s.name, s.line_number) for s in syms.get('dynamic', [])]}",
)
if syms.get("dynamic"):
    check(
        "recovered name has the right kind",
        syms["dynamic"][0].symbol_type.name == "METHOD",
    )
    check(
        "recovered name has the right parent",
        syms["dynamic"][0].parent_class == "CallShapes",
    )
    check("recovered name has the right line", syms["dynamic"][0].line_number == 37)
    check("recovered name carries a hash", bool(syms["dynamic"][0].body_hash))


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
