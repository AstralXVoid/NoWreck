#!/usr/bin/env python3
"""Type-level sample suite for the C++ scanner.

Formal assertions for class / struct / union / enum / type-alias / function /
method / named-lambda collection across the dedicated samples.  Every line
number was hand-verified against the source and re-verified against scanner
output.

Mirrors test_php_samples/test_php_types.py.
"""

import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.cpp_scanner import scan_cpp_file  # noqa: E402

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
    for s in scan_cpp_file(path):
        result.setdefault(s.name, []).append(s)
    return result


def check_symbol(
    syms: dict[str, list],
    name: str,
    expected_type: str,
    expected_line: int,
    parent: str | None = None,
) -> None:
    """Assert exactly one symbol of *expected_type* exists at *expected_line*."""
    found = [s for s in syms.get(name, []) if s.symbol_type.name == expected_type]
    if parent is not None:
        found = [s for s in found if s.parent_class == parent]
    check(f"{name} captured as {expected_type}", len(found) == 1, f"count={len(found)}")
    if found:
        check(
            f"{name} line {expected_line}",
            found[0].line_number == expected_line,
            f"actual={found[0].line_number}",
        )


def check_multiset(
    syms: dict[str, list],
    name: str,
    expected: set[tuple[str, int]],
    parent: str | None = None,
) -> None:
    """Assert the exact ``{(type, line)}`` set for a (possibly repeated) name."""
    found = syms.get(name, [])
    if parent is not None:
        found = [s for s in found if s.parent_class == parent]
    actual = {(s.symbol_type.name, s.line_number) for s in found}
    check(
        f"{name} declarations are exactly {sorted(expected)}",
        actual == expected,
        f"actual={sorted(actual)}",
    )


def check_no_empty_names(path: Path) -> None:
    """The scanner must never emit a nameless symbol."""
    names = [s.name for s in scan_cpp_file(path)]
    check(
        f"{path.name}: no empty symbol names",
        all(name.strip() for name in names),
        f"names={names}",
    )


def one(syms: dict[str, list], name: str, parent: str | None = None):
    """The first symbol called *name* (optionally filtered by parent)."""
    found = syms.get(name, [])
    if parent is not None:
        found = [s for s in found if s.parent_class == parent]
    return found[0] if found else None


# =========================================================================
# SECTION 1: Basic declarations (basic.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Basic declarations (basic.cpp)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "basic.cpp")

check_symbol(syms, "Greeter", "CLASS", 9)
check_symbol(syms, "Greeter", "METHOD", 12, parent="Greeter")
check_symbol(syms, "greet", "METHOD", 14, parent="Greeter")
check_symbol(syms, "format", "METHOD", 20, parent="Greeter")
check_symbol(syms, "Mode", "ENUM", 26)
check_symbol(syms, "Name", "TYPE_ALIAS", 32)
check_symbol(syms, "run", "FUNCTION", 34)
check_symbol(syms, "free_function", "FUNCTION", 40)

check(
    "a namespace is not a symbol",
    "app" not in syms and "detail" not in syms,
)
check("a global variable is not a symbol", "counter" not in syms)
check("a field is not a symbol", "name_" not in syms)
check("an enum case is not a symbol", "Fast" not in syms and "Slow" not in syms)
check("a parameter is not a symbol", "value" not in syms)

# CLASS/ENUM symbols carry a class-*shell* hash; TYPE_ALIAS symbols carry
# none (no CHANGED_TYPE_ALIAS claim), and a declaration-only member has
# ``body_hash=None`` (E9) so a .cpp body edit can never falsify it.
check("class carries a shell hash", bool(one(syms, "Greeter").body_hash))
check("enum carries a shell hash", bool(one(syms, "Mode").body_hash))
check("type alias carries no hash", one(syms, "Name").body_hash is None)
check(
    "declaration-only method has no hash (E9)",
    one(syms, "format", "Greeter").body_hash is None,
)
check(
    "the defined method has a hash",
    bool(one(syms, "greet", "Greeter").body_hash),
)
check(
    "a method never inherits the class shell hash",
    one(syms, "greet", "Greeter").body_hash != one(syms, "Greeter").body_hash,
)
check(
    "class methods carry the class as parent",
    one(syms, "greet", "Greeter").parent_class == "Greeter",
)
check(
    "a free function has no parent_class",
    one(syms, "run").parent_class is None,
)
check_no_empty_names(test_dir / "basic.cpp")


# =========================================================================
# SECTION 2: Class, struct and union shapes (edge_classes.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Class shapes (edge_classes.cpp)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_classes.cpp")

check_symbol(syms, "Engine", "CLASS", 3)
check_symbol(syms, "Coord", "CLASS", 29)
check_symbol(syms, "Value", "CLASS", 40)  # a union is a class-like type
check_symbol(syms, "drive", "FUNCTION", 46)
# ``Engine()``, ``~Engine()``, ``Engine(const Engine&) = delete`` and
# ``Engine& operator=() = default`` are all METHOD symbols.
check_multiset(
    syms,
    "Engine",
    {("CLASS", 3), ("METHOD", 6), ("METHOD", 9)},
)
check_symbol(syms, "~Engine", "METHOD", 7, parent="Engine")
check_symbol(syms, "operator=", "METHOD", 10, parent="Engine")
check_symbol(syms, "start", "METHOD", 12, parent="Engine")
check_symbol(syms, "stop", "METHOD", 13, parent="Engine")
check_symbol(syms, "gauge", "METHOD", 15, parent="Engine")
check_symbol(syms, "instances", "METHOD", 20, parent="Engine")
check_symbol(syms, "reset", "METHOD", 23, parent="Engine")
check_symbol(syms, "length", "METHOD", 34, parent="Coord")

engine_methods = {
    s.line_number: s for s in syms["Engine"] if s.symbol_type.name == "METHOD"
}
check(
    "a declaration-only constructor has no hash (E9)",
    engine_methods[6].body_hash is None,
)
check(
    "= delete is a definition and is hashed (E13)",
    engine_methods[9].body_hash is not None,
)
check(
    "= default is a definition and is hashed (E13)",
    one(syms, "operator=", "Engine").body_hash is not None,
)
check(
    "an inline method definition carries a hash",
    bool(one(syms, "gauge", "Engine").body_hash),
)
check("a static data member is not a symbol", "level_" not in syms)
check("a union member is not a symbol", "as_int" not in syms)
check("a struct field is not a symbol", "x" not in syms)
check_no_empty_names(test_dir / "edge_classes.cpp")


# =========================================================================
# SECTION 3: Templates (edge_templates.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Templates (edge_templates.cpp)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_templates.cpp")

check_symbol(syms, "maximum", "FUNCTION", 4)
check_symbol(syms, "Buffer", "CLASS", 10)
check_symbol(syms, "read", "METHOD", 13, parent="Buffer")
check_symbol(syms, "write", "METHOD", 18, parent="Buffer")
check_symbol(syms, "Ptr", "TYPE_ALIAS", 35)
check_symbol(syms, "forwarding", "FUNCTION", 38)
# The grammar's ``template_type`` name node carries the arguments, so a
# specialisation is indexed under its full name — distinct from the primary.
check_symbol(syms, "Buffer<char, 0>", "CLASS", 25)
check_symbol(syms, "read", "METHOD", 28, parent="Buffer<char, 0>")

check(
    "the primary template and its specialisation are two symbols",
    len([s for s in syms["Buffer"] if s.symbol_type.name == "CLASS"]) == 1
    and len(syms["Buffer<char, 0>"]) == 1,
)
check(
    "a template-parameter edit is folded into the wrapped hash (E5)",
    bool(one(syms, "maximum").body_hash),
)
check("an unbounded array member is not a symbol", "data_" not in syms)
check_no_empty_names(test_dir / "edge_templates.cpp")


# =========================================================================
# SECTION 4: The header/impl split (edge_split.h / edge_split.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Header/impl split (edge_split.h / edge_split.cpp)")
print(SECTION_SEP)

header = symbols_by_name(test_dir / "edge_split.h")
impl = symbols_by_name(test_dir / "edge_split.cpp")

check_symbol(header, "Widget", "CLASS", 3)
check_symbol(header, "Widget", "METHOD", 6, parent="Widget")
check_symbol(header, "~Widget", "METHOD", 7, parent="Widget")
check_symbol(header, "draw", "METHOD", 9, parent="Widget")
check_symbol(header, "resize", "METHOD", 10, parent="Widget")
check_symbol(header, "update", "METHOD", 12, parent="Widget")
check_symbol(header, "total_widgets", "FUNCTION", 18)

check_symbol(impl, "Widget", "METHOD", 5, parent="Widget")
check_symbol(impl, "~Widget", "METHOD", 10, parent="Widget")
check_symbol(impl, "draw", "METHOD", 15, parent="Widget")
check_symbol(impl, "resize", "METHOD", 21, parent="Widget")
check_symbol(impl, "total_widgets", "FUNCTION", 26)

check(
    "every header-side member is declaration-only (body_hash=None, E9)",
    all(
        s.body_hash is None
        for name in ("Widget", "~Widget", "draw", "resize")
        for s in header[name]
        if s.symbol_type.name == "METHOD"
    ),
)
check(
    "the pure virtual is a declaration-only member too",
    one(header, "update", "Widget").body_hash is None,
)
check(
    "the implementation side carries hashes",
    all(
        one(impl, name, "Widget").body_hash is not None
        for name in ("Widget", "~Widget", "draw", "resize")
    ),
)
check(
    "the split is two independent per-file symbols, not one merged symbol",
    one(header, "draw", "Widget").file_path != one(impl, "draw", "Widget").file_path,
)
check(
    "header and impl bodies hash differently",
    one(header, "total_widgets").body_hash != one(impl, "total_widgets").body_hash,
)
check_no_empty_names(test_dir / "edge_split.h")
check_no_empty_names(test_dir / "edge_split.cpp")


# =========================================================================
# SECTION 5: Namespaces are module scope (edge_namespaces.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Namespaces (edge_namespaces.cpp)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_namespaces.cpp")

check_symbol(syms, "helper", "FUNCTION", 5)
check_symbol(syms, "deep", "FUNCTION", 12)
check_symbol(syms, "hidden", "FUNCTION", 21)
check_symbol(syms, "c_entry", "FUNCTION", 29)
check_symbol(syms, "dispatch", "FUNCTION", 35)

check(
    "namespaces are not symbols (named, nested or anonymous)",
    not ({"app", "detail", "hidden_ns"} & set(syms)),
)
check(
    "every namespace member has no parent_class",
    all(
        s.parent_class is None for s in scan_cpp_file(test_dir / "edge_namespaces.cpp")
    ),
)
check_no_empty_names(test_dir / "edge_namespaces.cpp")


# =========================================================================
# SECTION 6: Lambdas (edge_lambdas.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Lambdas (edge_lambdas.cpp)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_lambdas.cpp")

check_symbol(syms, "doubler", "FUNCTION", 3)
check_symbol(syms, "apply_all", "FUNCTION", 8)
check_symbol(syms, "offset", "FUNCTION", 19)

check(
    "a module-scope named lambda is a FUNCTION (the JS arrow rule, E12)",
    one(syms, "doubler").parent_class is None
    and one(syms, "doubler").body_hash is not None,
)
check(
    "a lambda assigned inside a function body is not a symbol",
    "local" not in syms and "immediate" not in syms,
)
check_no_empty_names(test_dir / "edge_lambdas.cpp")


# =========================================================================
# SECTION 7: Negatives (edge_negatives.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Negatives (edge_negatives.cpp)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_negatives.cpp")

check_symbol(syms, "Callback", "TYPE_ALIAS", 5)
check_symbol(syms, "Holder", "CLASS", 9)
check_symbol(syms, "Holder", "METHOD", 12, parent="Holder")
check_symbol(syms, "Kind", "ENUM", 19)
check_symbol(syms, "guarded", "FUNCTION", 25)

check(
    "a function-pointer declaration is not a symbol (`int (*callback)(int);`)",
    "callback" not in syms,
)
check(
    "a function-pointer *typedef* is a type alias",
    one(syms, "Callback").symbol_type.name == "TYPE_ALIAS",
)
check("a global variable initialiser is not a symbol", "counter" not in syms)
check("a class field is not a symbol", "limit_" not in syms)
check("a static class constant is not a symbol", "kBase" not in syms)
check("an enumerator is not a symbol", "First" not in syms and "Second" not in syms)
check("a local variable is not a symbol", "local" not in syms)
check_no_empty_names(test_dir / "edge_negatives.cpp")


# =========================================================================
# SECTION 8: Loud grammar lag (edge_grammar_lag.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 8: Grammar lag, reported loudly (edge_grammar_lag.cpp)")
print(SECTION_SEP)

records: list[logging.LogRecord] = []


class _Capture(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        records.append(record)


logger = logging.getLogger("nowreck.scanner.cpp_scanner")
handler = _Capture()
logger.addHandler(handler)
try:
    lag_syms = scan_cpp_file(test_dir / "edge_grammar_lag.cpp")
finally:
    logger.removeHandler(handler)

check(
    "a parse error is reported loudly (warning logged)",
    any("Syntax error" in r.getMessage() for r in records),
    f"records={[r.getMessage() for r in records]}",
)
check(
    "partial symbols are still extracted",
    sorted((s.name, s.symbol_type.name, s.line_number) for s in lag_syms)
    == [
        ("Config", "CLASS", 4),
        ("Config", "METHOD", 7),
        ("broken", "FUNCTION", 15),
        ("name", "METHOD", 9),
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
