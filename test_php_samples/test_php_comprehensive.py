#!/usr/bin/env python3
"""Comprehensive symbol + call suite for the PHP scanner.

Covers every call shape the scanner claims to support (PH1/PH2/PH3/PH12),
every caller attribution rule (functions, methods, closures, property
hooks, anonymous-class members), and the negatives that must stay
negative.  Every expectation was verified against scanner output before
being written down.

Mirrors test_kotlin_samples/test_kotlin_comprehensive.py.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.php_scanner import (  # noqa: E402
    scan_php_calls,
    scan_php_file,
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


def calls_of(path: Path) -> set[tuple[str, str, str | None]]:
    """Every call as ``(caller, called, caller_parent_class)`` tuples."""
    return {
        (c.caller_name, c.called_name, c.caller_parent_class)
        for c in scan_php_calls(path)
    }


def symbol_tuples(path: Path) -> set[tuple[str, str, str | None]]:
    return {(s.name, s.symbol_type.name, s.parent_class) for s in scan_php_file(path)}


# =========================================================================
# SECTION 1: Call shapes (edge_calls.php — probes PH1/PH2/PH3/PH12)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Call shapes (edge_calls.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_calls.php")
send = {called for caller, called, parent in calls if caller == "send"}

expected_send = {
    "write",  # $transport->write('payload')
    "helper",  # bare call
    "retry",  # $this->retry()
    "backup",  # self:: / static:: / Client:: all resolve to one name
    "boot",  # parent::boot()
    "flush",  # \App\Util\Logger::flush()
    "normalise",  # \App\util\normalise('a') — final qualified segment
    "maybe",  # $transport?->maybe()  (PH12 nullsafe)
    "after",  # a second object
    "send_all",  # send_all(...$this->items) — spread is a real call
    "first",  # $transport->first()->last() — the receiver of a call
    "cell",  # $rows[0]->cell() — subscript receiver
    "mark",  # (new Marker(1))->mark() — parenthesised receiver
    "rows",  # $this->rows()
    "list",  # $obj->list() — a keyword name is a real method call
}
check(
    "send() captures exactly the captured call set",
    send == expected_send,
    f"missing={sorted(expected_send - send)} extra={sorted(send - expected_send)}",
)
check(
    "every send() call is attributed to Client",
    all(parent == "Client" for caller, _, parent in calls if caller == "send"),
)
check(
    "call receiver excluded (`->last()` after `->first()`)",
    "last" not in send,
)
check(
    "first-class callable excluded (PH1: `strlen(...)`, `trim(...)`)",
    "strlen" not in send and "trim" not in send,
)
check(
    "constructor invocation excluded (`new Marker(2)`)",
    "Marker" not in send,
)
check(
    "magic member excluded (PH12: `$transport->__construct()`)",
    "__construct" not in send,
)
check(
    "scoped magic member excluded (`Client::__toString()` would be)",
    all(called not in {"__construct", "__toString"} for _, called, _ in calls),
)

symbols = symbol_tuples(test_dir / "edge_calls.php")
check(
    "Client and Marker are classes",
    {("Client", "CLASS", None), ("Marker", "CLASS", None)} <= symbols,
)
check(
    "methods carry parent_class",
    {("send", "METHOD", "Client"), ("rows", "METHOD", "Client")} <= symbols,
)


# =========================================================================
# SECTION 2: Caller attribution — closures and arrow functions
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Closures and arrow functions (edge_lambdas.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_lambdas.php")
check(
    "closure calls attribute exactly",
    calls
    == {
        ("static", "strtoupper", None),  # $static = static function …
        ("static", "trim", None),
        ("run", "array_map", None),  # an *unnamed* argument closure
        ("run", "normalise", None),  #   belongs to the enclosing caller
        ("run", "array_filter", None),
        ("arrow", "double_up", None),  # $arrow = fn … owns its own body
    },
    f"calls={sorted(calls)}",
)
check(
    "a named closure owns its body with no class attribution",
    ("arrow", "double_up", None) in calls,
)
check(
    "a closure with no calls contributes nothing",
    all(caller not in {"double", "triple", "counter"} for caller, _, _ in calls),
)
check(
    "closures never claim a parent_class",
    all(parent is None for _, _, parent in calls),
)


# =========================================================================
# SECTION 3: Anonymous-class members are callers, not symbols
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Anonymous classes (edge_objects.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_objects.php")
check(
    "anonymous-class calls attribute exactly",
    calls
    == {
        ("pipeline", "open", None),  # chain start
        ("pipeline", "read", None),  # nullsafe call
        ("render", "strtoupper", None),  # anon-class method, parent None
    },
    f"calls={sorted(calls)}",
)
check(
    "a call receiver excludes the rest of the chain (`->read()->close()`)",
    all(called != "close" for _, called, _ in calls),
)
check(
    "the anonymous-class method is a caller with no class (PH5)",
    ("render", "strtoupper", None) in calls,
)
check(
    "the interface's declaration-only method owns nothing",
    all(caller != "Renderer" for caller, _, _ in calls),
)
check(
    "the containing function contributes nothing on its own",
    all(caller != "make" for caller, _, _ in calls),
)


# =========================================================================
# SECTION 4: Property hooks own their calls (the Kotlin accessor rule)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Property hooks (edge_members.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_members.php")
check(
    "hook calls attribute to the property, with the class as parent",
    calls
    == {
        ("full_name", "compose", "Full"),
        ("full_name", "assign", "Full"),
    },
    f"calls={sorted(calls)}",
)
check(
    "constructors and ordinary methods own their calls too",
    symbol_tuples(test_dir / "edge_members.php")
    >= {("__construct", "METHOD", "Full"), ("compose", "METHOD", "Full")},
)


# =========================================================================
# SECTION 5: Trait methods keep the trait as parent
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Traits (edge_traits.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_traits.php")
check(
    "trait call attribution is exact",
    calls
    == {
        ("uuid", "generate", "HasUuid"),
        ("generate", "bin2hex", "HasUuid"),
        ("generate", "random_bytes", "HasUuid"),
        ("touch", "date", "Timestamps"),
        ("describe", "uuid", "Record"),
    },
    f"calls={sorted(calls)}",
)
check(
    "a trait-use does not re-attribute trait calls to the using class",
    ("describe", "bin2hex", "Record") not in calls,
)


# =========================================================================
# SECTION 6: Negatives — what must never be a call
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Negatives (edge_negatives.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_negatives.php")
callers = {caller for caller, _, _ in calls}
check(
    "only the module-scope function is a caller (module code owns nothing)",
    callers == {"render_head"},
    f"callers={sorted(callers)}",
)
# isset()/empty()/eval()/die() parse as real calls; print_r() is a function.
check(
    "the construct-shaped names the grammar treats as calls are captured",
    {called for _, called, _ in calls}
    == {"die_on_error", "empty", "eval", "isset", "print_r"},
    f"calls={sorted(calls)}",
)
for excluded in (
    "commented_out",
    "fake_in_string",
    "render_body",
    "is_ready",
    "split_pair",
    "array_merge",
    "__get",
    "strlen",
    "clone",
    "match",
    "unset",
    "exit",
    "list",
    "array",
    "print",
    "echo",
    "include",
    "require",
    "render_head",  # called only at module level, where nothing is a caller
):
    check(
        f"`{excluded}` is never reported as a called name",
        all(called != excluded for _, called, _ in calls),
    )


# =========================================================================
# SECTION 7: Enums (edge_enums.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Enums (edge_enums.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_enums.php")
check(
    "enum calls attribute exactly",
    calls
    == {
        ("label", "ucfirst", "Status"),
        ("useStatus", "label", "Container"),
    },
    f"calls={sorted(calls)}",
)
check(
    "`Status::Draft` is a case, not a call",
    all(called != "Draft" for _, called, _ in calls),
)


# =========================================================================
# SECTION 8: Namespaces (edge_namespace.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 8: Namespaces (edge_namespace.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_namespace.php")
check(
    "flat and braced namespace calls attribute exactly",
    calls
    == {
        ("flat_helper", "format", None),
        ("run", "flat_helper", "FlatService"),
        ("alpha_helper", "alpha_inner", None),
        ("run", "alpha_helper", "AlphaService"),
        ("beta_helper", "beta_inner", None),
    },
    f"calls={sorted(calls)}",
)
check(
    "two functions may share one name without mixing callers",
    {
        parent
        for caller, called, parent in calls
        if caller == "run" and called == "flat_helper"
    }
    == {"FlatService"},
)


# =========================================================================
# SECTION 9: Attributes own no calls (edge_attributes.php)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 9: Attributes (edge_attributes.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_attributes.php")
check(
    "attribute arguments are never calls (PH4)",
    all(
        called not in {"Route", "Inject", "Cache", "Deprecated"}
        for _, called, _ in calls
    ),
)
check(
    "declared functions are callers with no class",
    ("home", "render", None) in calls,
)
check(
    "method calls attribute to the class",
    ("index", "layout", "PageController") in calls
    and ("layout", "wrap", "PageController") in calls,
)


# =========================================================================
# SECTION 10: Strings — interpolation holds real calls (PH11)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 10: Strings and interpolation (edge_strings.php)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_strings.php")
check(
    "calls attribute exactly",
    calls
    == {
        ("render", "format", "Report"),
        ("render", "implode", "Report"),
        ("format", "number_format", "Report"),
    },
    f"calls={sorted(calls)}",
)
check(
    "`format` is reached *only* through the `{$…}` interpolation string",
    ("render", "format", "Report") in calls,
)
check(
    "no phantom leaks out of quotes, heredocs or nowdocs",
    all(called not in {"raw", "decoded", "Report", "RAW"} for _, called, _ in calls),
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
