#!/usr/bin/env python3
"""Comprehensive symbol + call suite for the Kotlin scanner.

Covers every call shape the scanner claims to support, every caller
attribution rule, and the negatives that must stay negative.  Every
expectation was verified against scanner output before being written down.

Mirrors test_java_samples/test_java_comprehensive.py.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.kotlin_scanner import (  # noqa: E402
    scan_kotlin_calls,
    scan_kotlin_file,
)

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


def calls_of(
    path: Path, repo_root: Path | None = None
) -> set[tuple[str, str, str | None]]:
    """Every call as ``(caller, called, caller_parent_class)`` tuples."""
    return {
        (c.caller_name, c.called_name, c.caller_parent_class)
        for c in scan_kotlin_calls(path, repo_root=repo_root)
    }


def symbol_tuples(path: Path) -> set[tuple[str, str, str | None]]:
    return {
        (s.name, s.symbol_type.name, s.parent_class) for s in scan_kotlin_file(path)
    }


# =========================================================================
# SECTION 1: Call shapes (edge_calls.kt, probes K5)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Call shapes (edge_calls.kt)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_calls.kt")

# Bare call, member call, and every receiver spelling.
check("bare call captured", ("plain", "helper", "CallShapes") in calls)
check("object member call captured", ("member", "compute", "CallShapes") in calls)
check("safe call (`?.`) captured", ("safeCall", "compute", "CallShapes") in calls)
check(
    "not-null assert call (`!!.`) captured",
    ("notNull", "compute", "CallShapes") in calls,
)
check("`this.` call captured", ("onThis", "local", "CallShapes") in calls)
check("`super.` call captured", ("onSuper", "onSuper", "CallShapes") in calls)
check(
    "chained `a.b.c()` resolves to the member", ("chains", "c", "CallShapes") in calls
)
check(
    "indexed receiver (`a[0].b()`) captured",
    ("indexed", "compute", "CallShapes") in calls,
)
check(
    "chained not-null receiver (`a.b!!.c()`) captured",
    ("chainedNotNull", "compute", "CallShapes") in calls,
)
# The one dynamic receiver is excluded, exactly like JS/TS/Java: the member
# belongs to whatever `factory()` returned, not to a name we can resolve.
check(
    "dynamic receiver (`f().bar()`) is not a call",
    all(called != "result" for _, called, _ in calls),
)
# `Foo::bar` is a reference, not a call.
check(
    "callable reference (`::local`) is not a call",
    all(called != "local" or caller != "reference" for caller, called, _ in calls),
)
# A bare `__dunder__()` IS a call; only *member* dunder calls are excluded.
neg_calls = calls_of(test_dir / "edge_negatives.kt")
check("bare dunder call captured", ("bareDunder", "__bare__", "Negatives") in neg_calls)
check(
    "member dunder call excluded",
    all(called != "__secret__" for _, called, _ in neg_calls),
)
check("lambda-body call captured", ("nestedLambda", "inner", "CallShapes") in calls)
check(
    "library call on a lambda receiver captured",
    ("nestedLambda", "map", "CallShapes") in calls,
)


# =========================================================================
# SECTION 2: Caller attribution — local functions and lambdas
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Local functions and lambdas (edge_basic.kt, edge_lambdas.kt)")
print(SECTION_SEP)

basic = calls_of(test_dir / "edge_basic.kt")
check("local function owns its calls", ("localMethod", "localWork", "Local") in basic)
check("local function call from its body owner", ("withLocal", "inner", None) in basic)
check("extension function is a caller", ("shout", "uppercase", None) in basic)
check(
    "generic extension function is a caller",
    ("secondOrNull", "getOrNull", None) in basic,
)
check(
    "constructor call inside a local class is captured",
    ("host", "Local", "Outer") in basic,
)

lambdas = calls_of(test_dir / "edge_lambdas.kt")
check(
    "lambda-valued field is a caller", ("field", "fieldWork", "LambdaHolder") in lambdas
)
check(
    "anonymous-function field is a caller",
    ("anonField", "anonFieldWork", "LambdaHolder") in lambdas,
)
check(
    "local lambda proves the property is a caller",
    ("local", "localWork", "LambdaHolder") in lambdas,
)
check(
    "unnamed trailing lambda belongs to the enclosing function",
    ("trailingLambda", "forEach", None) in lambdas
    and ("trailingLambda", "map", None) in lambdas,
)


# =========================================================================
# SECTION 3: Caller attribution — accessors, constructors, companions
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Accessors, constructors, companions")
print(SECTION_SEP)

members = calls_of(test_dir / "edge_members.kt")
check(
    "getter/setter body is a caller named after its property",
    ("mutable", "trim", "Full") in members,
)
check(
    "property initialiser at class level owns no calls (Java-family rule)",
    all(called != "derive" for _, called, _ in members),
)
check(
    "`init { }` block owns no calls (Java-family rule)",
    all(called != "initialise" for _, called, _ in members),
)
check(
    "secondary constructor is a caller named after the class",
    ("Full", "copied", "Full") in members,
)

objects = calls_of(test_dir / "edge_objects.kt")
check("companion method is a caller", ("create", "Repo", "Service") in objects)
check(
    "companion constructor call captured", ("create", "Service", "Service") in objects
)
check("object method is a caller", ("lookup", "register", "Registry") in objects)
check(
    "anonymous-object method is a caller with no parent class",
    ("run", "anonWork", None) in objects,
)
check("nested object method is a caller", ("help", "assist", "Helpers") in objects)

enums = calls_of(test_dir / "edge_enums.kt")
check("enum method is a caller", ("describe", "label", "Level") in enums)
check("enum companion method is a caller", ("fromWeight", "lookup", "Level") in enums)
check(
    "enum-entry body method is a caller (probe K11)",
    ("name", "entryWork", "Kind") in enums,
)

interfaces = calls_of(test_dir / "edge_interfaces.kt")
check(
    "interface default method is a caller",
    ("provided", "helper", "WithDefaults") in interfaces,
)
check(
    "expression-bodied interface method",
    ("alsoProvided", "format", "WithDefaults") in interfaces,
)
check(
    "abstract interface method owns no calls",
    all(caller != "required" for caller, _, _ in interfaces),
)


# =========================================================================
# SECTION 4: D5 — a soft-keyword name is recovered, calls included
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Soft-keyword function named `dynamic` (edge_calls.kt)")
print(SECTION_SEP)

check(
    "recovered method owns the calls in its body",
    ("dynamic", "factory", "CallShapes") in calls,
)
check(
    "no call is attributed to an empty caller name",
    all(caller.strip() and called.strip() for caller, called, _ in calls),
)


# =========================================================================
# SECTION 5: D2/D3 recovery — damaged declarations keep their members
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Grammar-defect recovery (edge_recovery.kt)")
print(SECTION_SEP)

recovery = calls_of(test_dir / "edge_recovery.kt")
check(
    "recovered enum's member is a caller",
    ("describe", "recoveryWork", "SingleEntry") in recovery,
)
check(
    "object after an attached annotation is a caller",
    ("work", "objectWork", "AnnotatedObject") in recovery,
)
check(
    "detached annotation does not swallow the next call",
    ("followed", "followedWork", None) in recovery,
)

recovery_syms = symbol_tuples(test_dir / "edge_recovery.kt")
check("recovered enum symbol present", ("SingleEntry", "ENUM", None) in recovery_syms)
check(
    "recovered annotation class symbol present",
    ("AnnotatedAnnotation", "INTERFACE", None) in recovery_syms,
)
check(
    "one-line class body still yields its member",
    ("oneLiner", "METHOD", "OneLine") in recovery_syms,
)


# =========================================================================
# SECTION 6: Real-world file
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Real-world patterns (edge_realworld.kt)")
print(SECTION_SEP)

rw = calls_of(test_dir / "edge_realworld.kt", repo_root=test_dir)
check(
    "service method calls its helper",
    ("save", "notifyChanged", "InMemoryRepository") in rw,
)
check("top-level flow calls its functions", ("main", "process", None) in rw)
check("delegating call captured", ("main", "save", None) in rw)
check("string extension call captured", ("initials", "split", None) in rw)
check("stdlib call captured", ("oldestAge", "maxOfOrNull", "InMemoryRepository") in rw)
check("constructor call captured", ("main", "User", None) in rw)


# =========================================================================
# SECTION 7: Every file is clean — naming and hash invariants
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Global invariants across every sample")
print(SECTION_SEP)

kotlin_files = sorted(test_dir.glob("*.kt"))
check(
    "sample corpus is non-trivial",
    len(kotlin_files) >= 13,
    f"files={len(kotlin_files)}",
)

empty_names: list[str] = []
bad_calls: list[str] = []
for path in kotlin_files:
    empty_names.extend(
        f"{path.name}:{s.name!r}" for s in scan_kotlin_file(path) if not s.name.strip()
    )
    bad_calls.extend(
        f"{path.name}:{c.caller_name!r}->{c.called_name!r}"
        for c in scan_kotlin_calls(path)
        if not c.caller_name.strip() or not c.called_name.strip()
    )
check("no symbol has an empty name", not empty_names, str(empty_names[:3]))
check("no call has an empty caller or callee", not bad_calls, str(bad_calls[:3]))

check(
    "every METHOD has a parent_class",
    all(
        not (s.symbol_type.name == "METHOD" and s.parent_class is None)
        for path in kotlin_files
        for s in scan_kotlin_file(path)
    ),
)
check(
    "every FUNCTION has no parent_class",
    all(
        not (s.symbol_type.name == "FUNCTION" and s.parent_class is not None)
        for path in kotlin_files
        for s in scan_kotlin_file(path)
    ),
)
check(
    "every CLASS/ENUM carries a shell hash",
    all(
        bool(s.body_hash)
        for path in kotlin_files
        for s in scan_kotlin_file(path)
        if s.symbol_type.name in ("CLASS", "ENUM")
    ),
)
check(
    "no INTERFACE/TYPE_ALIAS carries a hash",
    all(
        s.body_hash is None
        for path in kotlin_files
        for s in scan_kotlin_file(path)
        if s.symbol_type.name in ("INTERFACE", "TYPE_ALIAS")
    ),
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
