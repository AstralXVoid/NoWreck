#!/usr/bin/env python3
"""Type-level sample suite for the PHP scanner.

Formal assertions for class / interface / enum / trait / function /
closure collection across the dedicated samples.  Every line number was
hand-verified against the source and re-verified against scanner output.

Mirrors test_kotlin_samples/test_kotlin_types.py.
"""

import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.php_scanner import scan_php_file  # noqa: E402

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
    for s in scan_php_file(path):
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
    once, e.g. an interface method and the method that implements it.
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
    """The scanner must never emit a nameless symbol."""
    names = [s.name for s in scan_php_file(path)]
    check(
        f"{path.name}: no empty symbol names",
        all(name.strip() for name in names),
        f"names={names}",
    )


def one(syms: dict[str, list], name: str, parent: str | None = None):
    """The single symbol called *name* (optionally filtered by parent)."""
    found = syms.get(name, [])
    if parent is not None:
        found = [s for s in found if s.parent_class == parent]
    return found[0] if found else None


# =========================================================================
# SECTION 1: Basic declarations (basic.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Basic declarations (basic.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "basic.php")

check_symbol(syms, "Greeter", "INTERFACE", 3)
check_symbol(syms, "greet", "METHOD", 5, parent="Greeter")
check_symbol(syms, "Person", "CLASS", 8)
check_symbol(syms, "__construct", "METHOD", 12, parent="Person")
check_symbol(syms, "greet", "METHOD", 17, parent="Person")
check_symbol(syms, "Color", "ENUM", 23)
check_symbol(syms, "Loggable", "CLASS", 29)
check_symbol(syms, "log", "METHOD", 31, parent="Loggable")
check_symbol(syms, "topLevel", "FUNCTION", 37)
check_symbol(syms, "double", "FUNCTION", 42)

check(
    "interface method parent_class",
    one(syms, "greet", "Greeter").parent_class == "Greeter",
)
check(
    "class method parent_class", one(syms, "greet", "Person").parent_class == "Person"
)
check(
    "top-level function has no parent_class",
    one(syms, "topLevel").parent_class is None,
)
# PH6: a closure assignment is indexed as a FUNCTION named without the $.
check(
    "closure assignment has no parent_class",
    one(syms, "double").parent_class is None,
)
# INTERFACE symbols carry no hash (no CHANGED_INTERFACE claim); CLASS/ENUM
# carry a shell hash; a declaration-only method has body_hash=None (PH9).
check("interface carries no hash", one(syms, "Greeter").body_hash is None)
check("class carries a shell hash", bool(one(syms, "Person").body_hash))
check("enum carries a shell hash", bool(one(syms, "Color").body_hash))
check("trait carries a shell hash", bool(one(syms, "Loggable").body_hash))
check(
    "declaration-only interface method has no hash (PH9)",
    one(syms, "greet", "Greeter").body_hash is None,
)
check(
    "the implementing method has a hash",
    bool(one(syms, "greet", "Person").body_hash),
)
check(
    "a method never inherits the class shell hash",
    one(syms, "greet", "Person").body_hash != one(syms, "Person").body_hash,
)
check("enum cases are not symbols", "Red" not in syms and "Blue" not in syms)
check("a property is not a symbol", "name" not in syms)
check_no_empty_names(test_dir / "basic.php")


# =========================================================================
# SECTION 2: Interfaces (edge_interfaces.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Interfaces (edge_interfaces.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_interfaces.php")

check_symbol(syms, "Plain", "INTERFACE", 3)
check_symbol(syms, "required", "METHOD", 5, parent="Plain")
check_symbol(syms, "WithDefaults", "INTERFACE", 8)
check_symbol(syms, "provided", "METHOD", 10, parent="WithDefaults")
check_symbol(syms, "alsoProvided", "METHOD", 15, parent="WithDefaults")
check_symbol(syms, "Impl", "CLASS", 18)
check_symbol(syms, "required", "METHOD", 20, parent="Impl")
check_symbol(syms, "provided", "METHOD", 25, parent="Impl")

plain_required = one(syms, "required", "Plain")
impl_required = one(syms, "required", "Impl")
check(
    "declaration-only interface method has no hash (PH9)",
    plain_required.body_hash is None,
)
check(
    "the implementation carries a hash the declaration cannot",
    bool(impl_required.body_hash),
)
check(
    "an interface default method *with* a body carries a hash",
    bool(one(syms, "provided", "WithDefaults").body_hash),
)
check(
    "a second declaration-only member has no hash either",
    one(syms, "alsoProvided").body_hash is None,
)
check("interfaces carry no hash", one(syms, "Plain").body_hash is None)
check_no_empty_names(test_dir / "edge_interfaces.php")


# =========================================================================
# SECTION 3: Enums (edge_enums.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Enums (edge_enums.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_enums.php")

check_symbol(syms, "Status", "ENUM", 3)
check_symbol(syms, "label", "METHOD", 8, parent="Status")
check_symbol(syms, "Priority", "ENUM", 14)
check_symbol(syms, "rank", "METHOD", 19, parent="Priority")
check_symbol(syms, "HasRank", "INTERFACE", 25)
check_symbol(syms, "rank", "METHOD", 27, parent="HasRank")
check_symbol(syms, "Container", "CLASS", 30)
check_symbol(syms, "useStatus", "METHOD", 32, parent="Container")

check("enum carries a shell hash", bool(one(syms, "Status").body_hash))
check(
    "enum method parent_class is the enum",
    one(syms, "label", "Status").parent_class == "Status",
)
check(
    "the interface's declaration-only method has no hash (PH9)",
    one(syms, "rank", "HasRank").body_hash is None,
)
check(
    "the enum's implementation of the same name does",
    bool(one(syms, "rank", "Priority").body_hash),
)
check(
    "enum cases are not symbols",
    "Draft" not in syms and "Low" not in syms,
)
check_no_empty_names(test_dir / "edge_enums.php")


# =========================================================================
# SECTION 4: Class members and property hooks (edge_members.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Class members (edge_members.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_members.php")

check_symbol(syms, "Full", "CLASS", 3)
check_symbol(syms, "__construct", "METHOD", 10, parent="Full")
check_symbol(syms, "compose", "METHOD", 24, parent="Full")
check_symbol(syms, "assign", "METHOD", 29, parent="Full")
check_symbol(syms, "Derived", "CLASS", 35)
check_symbol(syms, "extra", "METHOD", 37, parent="Derived")

check("constant is not a symbol", "LIMIT" not in syms)
check("static property is not a symbol", "instances" not in syms)
check("plain properties are not symbols", "first" not in syms)
check("promoted parameters are not symbols", "last" not in syms and "code" not in syms)
check("a property is not a symbol", "full_name" not in syms)
check("property hooks are not symbols", "get" not in syms and "set" not in syms)
check(
    "every METHOD carries a parent_class",
    all(
        s.parent_class is not None
        for s in scan_php_file(test_dir / "edge_members.php")
        if s.symbol_type.name == "METHOD"
    ),
)
check_no_empty_names(test_dir / "edge_members.php")


# =========================================================================
# SECTION 5: Traits (edge_traits.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Traits (edge_traits.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_traits.php")

check_symbol(syms, "HasUuid", "CLASS", 3)  # PH8: no TRAIT claim type
check_symbol(syms, "uuid", "METHOD", 7, parent="HasUuid")
check_symbol(syms, "generate", "METHOD", 16, parent="HasUuid")
check_symbol(syms, "Timestamps", "CLASS", 22)
check_symbol(syms, "touch", "METHOD", 26, parent="Timestamps")
check_symbol(syms, "Record", "CLASS", 32)
check_symbol(syms, "describe", "METHOD", 37, parent="Record")

check("trait carries a shell hash", bool(one(syms, "HasUuid").body_hash))
check(
    "trait method parent_class is the trait",
    one(syms, "uuid", "HasUuid").parent_class == "HasUuid",
)
check(
    "a trait-use does not copy symbols into the using class",
    all(
        s.parent_class != "Record"
        for s in scan_php_file(test_dir / "edge_traits.php")
        if s.name == "uuid"
    ),
)
check("a trait property is not a symbol", "updated_at" not in syms)
check(
    "the uuid *property* adds no extra symbol",
    len(syms.get("uuid", [])) == 1,
    f"count={len(syms.get('uuid', []))}",
)
check_no_empty_names(test_dir / "edge_traits.php")


# =========================================================================
# SECTION 6: Anonymous classes (edge_objects.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Anonymous classes (edge_objects.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_objects.php")

check_symbol(syms, "Renderer", "INTERFACE", 3)
check_symbol(syms, "render", "METHOD", 5, parent="Renderer")
check_symbol(syms, "make", "FUNCTION", 8)
check_symbol(syms, "pipeline", "FUNCTION", 27)

check(
    "an anonymous class yields no symbol (PH5)",
    "__construct" not in syms,
)
check(
    "an anonymous class's method is not a symbol (PH5)",
    all(s.parent_class is not None for s in syms.get("render", [])),
    f"render={[(s.name, s.parent_class) for s in syms.get('render', [])]}",
)
check(
    "the containing function still is",
    one(syms, "make").parent_class is None,
)
check_no_empty_names(test_dir / "edge_objects.php")


# =========================================================================
# SECTION 7: Namespaces as module scope (edge_namespace.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Namespaces (edge_namespace.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_namespace.php")

check_symbol(syms, "flat_helper", "FUNCTION", 9)
check_symbol(syms, "FlatService", "CLASS", 14)
check_symbol(syms, "run", "METHOD", 16, parent="FlatService")
check_symbol(syms, "alpha_helper", "FUNCTION", 23)
check_symbol(syms, "AlphaService", "CLASS", 28)
check_symbol(syms, "run", "METHOD", 30, parent="AlphaService")
check_symbol(syms, "beta_helper", "FUNCTION", 38)

check(
    "a namespace is not a symbol",
    "App" not in syms and "App\\Flat" not in syms,
)
check(
    "use imports are not symbols",
    "Formatter" not in syms,
)
check(
    "declare(strict_types=1) is not a symbol",
    "strict_types" not in syms,
)
check_no_empty_names(test_dir / "edge_namespace.php")


# =========================================================================
# SECTION 8: Attributes report their own line (edge_attributes.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 8: Attributes (edge_attributes.php)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_attributes.php")

# The grammar begins a declaration at its attribute, so an attributed
# declaration reports the attribute's line; an unattributed one reports
# its own.  Both spellings must be stable.
check_symbol(syms, "home", "FUNCTION", 5)
check_symbol(syms, "PageController", "CLASS", 11)
check_symbol(syms, "index", "METHOD", 18, parent="PageController")
check_symbol(syms, "layout", "METHOD", 25, parent="PageController")

check(
    "attributes belong to the declaration, not to a sibling",
    one(syms, "index").line_number == 18
    and (test_dir / "edge_attributes.php")
    .read_text()
    .splitlines()[19]
    .strip()
    .startswith("public function index"),
)
check("a parameter attribute hides no symbol", "logger" not in syms)
check_no_empty_names(test_dir / "edge_attributes.php")


# =========================================================================
# SECTION 9: Loud grammar lag (edge_grammar_lag.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 9: Grammar lag, reported loudly (edge_grammar_lag.php)")
print(SECTION_SEP)

records: list[logging.LogRecord] = []


class _Capture(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        records.append(record)


logger = logging.getLogger("nowreck.scanner.php_scanner")
handler = _Capture()
logger.addHandler(handler)
try:
    lag_syms = scan_php_file(test_dir / "edge_grammar_lag.php")
finally:
    logger.removeHandler(handler)

check(
    "a parse error is reported loudly (warning logged)",
    any("Syntax error" in r.getMessage() for r in records),
    f"records={[r.getMessage() for r in records]}",
)
check(
    "partial symbols are still extracted",
    sorted((s.name, s.symbol_type.name) for s in lag_syms)
    == [
        ("Config", "CLASS"),
        ("__construct", "METHOD"),
        ("name", "METHOD"),
    ],
    f"symbols={[(s.name, s.symbol_type.name) for s in lag_syms]}",
)
check(
    "the unaffected method still has a hash",
    next(s for s in lag_syms if s.name == "name").body_hash is not None,
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
