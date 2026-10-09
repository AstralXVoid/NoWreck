#!/usr/bin/env python3
"""Comprehensive symbol + call suite for the C++ scanner.

Covers every call shape the scanner claims to support (E1/E2/E4/E12), every
caller attribution rule (free functions, methods, out-of-line definitions,
named lambdas), and the negatives that must stay negative.  Every
expectation was verified against scanner output before being written down.

Mirrors test_php_samples/test_php_comprehensive.py.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.cpp_scanner import (  # noqa: E402
    scan_cpp_calls,
    scan_cpp_file,
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
        for c in scan_cpp_calls(path)
    }


def called_names(path: Path) -> set[str]:
    return {c.called_name for c in scan_cpp_calls(path)}


def symbol_tuples(path: Path) -> set[tuple[str, str, str | None]]:
    return {(s.name, s.symbol_type.name, s.parent_class) for s in scan_cpp_file(path)}


# =========================================================================
# SECTION 1: Call shapes (edge_calls.cpp — probes E1/E2/E4)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Call shapes (edge_calls.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_calls.cpp")
exercise = {called for caller, called, _ in calls if caller == "exercise"}

expected = {
    "send",  # request.send(...) and request->send(...)
    "payload",  # a nested call argument
    "retry",  # request.retry()
    "flush",  # Service::flush() — qualified, final segment
    "boot",  # ::boot() — leading scope operator
    "enqueue",  # queue[0].enqueue() — subscript receiver
    "notify",  # (*pointer).notify() — parenthesised receiver
    "next",  # chain.next().last() — the receiver of a call
    "direct",  # a bare call
    "take",  # take(...)
    "move",  # std::move(value)
    "identity",  # identity<int>(3) — templated call
    "assert",  # a macro the grammar parses as a call_expression
}
check(
    "exercise() captures exactly the documented call set",
    exercise == expected,
    f"missing={sorted(expected - exercise)} extra={sorted(exercise - expected)}",
)
check(
    "every exercise() call has no class attribution",
    all(parent is None for caller, _, parent in calls if caller == "exercise"),
)
check(
    "call receiver excluded (`chain.next().last()` keeps only `next`)",
    "last" not in exercise,
)
check(
    "constructor invocation excluded (`new Request()`, `Request local(1)`)",
    "Request" not in exercise,
)
check(
    "a declaration's own declarator is not a call (`Request local(1)`)",
    "local" not in exercise and "made" not in exercise,
)

symbols = symbol_tuples(test_dir / "edge_calls.cpp")
check(
    "Request is a class and its declaration-only methods are symbols",
    {("Request", "CLASS", None), ("send", "METHOD", "Request")} <= symbols,
)
check(
    "a declaration-only member owns no calls",
    all(caller not in {"send", "retry"} for caller, _, _ in calls),
)


# =========================================================================
# SECTION 2: Methods and out-of-line definitions (edge_classes.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Classes and members (edge_classes.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_classes.cpp")
check(
    "class calls attribute exactly",
    calls
    == {
        ("length", "compute", "Coord"),
        ("drive", "start", None),
        ("drive", "stop", None),
        ("drive", "gauge", None),
        ("drive", "reset", None),
    },
    f"calls={sorted(calls)}",
)
check(
    "an inline method's calls carry the class as parent",
    ("length", "compute", "Coord") in calls,
)
check(
    "declaration-only members own nothing",
    all(
        caller not in {"start", "stop", "reset", "instances"} for caller, _, _ in calls
    ),
)
check(
    "`Engine engine;` is an initialiser, not a call",
    all(called != "Engine" for _, called, _ in calls),
)


# =========================================================================
# SECTION 3: Templated calls (edge_templates.cpp — probes E2/E4/E5)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Templated calls (edge_templates.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_templates.cpp")
check(
    "template calls attribute exactly",
    calls
    == {
        ("maximum", "compare", None),
        ("forwarding", "maximum", None),  # maximum<T>(...) — the head identifier
        ("forwarding", "clone", None),
        ("read", "fallback", "Buffer<char, 0>"),
    },
    f"calls={sorted(calls)}",
)
check(
    "a templated call is captured under its final name",
    ("forwarding", "maximum", None) in calls,
)
check(
    "specification-method calls attribute to the specialisation name",
    ("read", "fallback", "Buffer<char, 0>") in calls,
)
check(
    "the declaration-only template member owns nothing",
    all(caller != "write" for caller, _, _ in calls),
)


# =========================================================================
# SECTION 4: The header/impl split (edge_split.h / edge_split.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Header/impl split (edge_split.h / edge_split.cpp)")
print(SECTION_SEP)

header_calls = calls_of(test_dir / "edge_split.h")
impl_calls = calls_of(test_dir / "edge_split.cpp")
check("a declarations-only header owns no calls", header_calls == set())
check(
    "the implementation side attributes exactly",
    impl_calls
    == {
        ("Widget", "register_self", "Widget"),
        ("~Widget", "release_self", "Widget"),
        ("draw", "render_frame", "Widget"),
        ("draw", "resize", "Widget"),
        ("resize", "apply", "Widget"),
        ("total_widgets", "count_widgets", None),
    },
    f"calls={sorted(impl_calls)}",
)
check(
    "an out-of-line definition keeps the class as parent (E14)",
    ("draw", "render_frame", "Widget") in impl_calls,
)
check(
    "a method calling another member keeps the class (unqualified target)",
    ("draw", "resize", "Widget") in impl_calls,
)


# =========================================================================
# SECTION 5: Namespaces (edge_namespaces.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Namespaces (edge_namespaces.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_namespaces.cpp")
check(
    "namespace calls attribute exactly",
    calls
    == {
        ("deep", "helper", None),
        ("c_entry", "hidden", None),
        ("dispatch", "helper", None),  # app::helper()
        ("dispatch", "deep", None),  # app::detail::deep()
        ("dispatch", "hidden", None),  # ::hidden()
        ("dispatch", "c_entry", None),
    },
    f"calls={sorted(calls)}",
)
check(
    "a qualified call keeps only its final segment",
    "helper" in called_names(test_dir / "edge_namespaces.cpp")
    and "app" not in called_names(test_dir / "edge_namespaces.cpp"),
)
check(
    "namespace members never claim a class",
    all(parent is None for _, _, parent in calls),
)


# =========================================================================
# SECTION 6: Lambdas (edge_lambdas.cpp — probe E12)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Lambdas (edge_lambdas.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_lambdas.cpp")
check(
    "lambda calls attribute exactly",
    calls
    == {
        ("doubler", "scale", None),  # a module-scope named lambda owns its body
        ("local", "doubler", None),  # a function-local named lambda owns its body
        ("local", "offset", None),
        ("apply_all", "local", None),  # the enclosing function calls it
    },
    f"calls={sorted(calls)}",
)
check(
    "an immediately-invoked unnamed lambda yields no call for its target",
    all(called != "immediate" for _, called, _ in calls),
)
check(
    "an unnamed lambda's calls belong to the nearest named caller",
    ("local", "offset", None) in calls,
)


# =========================================================================
# SECTION 7: Literals and comments invent nothing (edge_strings.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Literals and comments (edge_strings.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_strings.cpp")
check(
    "string/comment calls attribute exactly",
    calls
    == {
        ("render", "format", "Report"),
        ("render", "print_line", "Report"),
        ("render", "comment_only", "Report"),
        ("print_line", "consume", None),
    },
    f"calls={sorted(calls)}",
)
for phantom in ("ghost", "hidden", "phantom", "not_a_call", "ignore", "ignore_too"):
    check(
        f"`{phantom}` never leaks out of a comment or literal",
        phantom not in called_names(test_dir / "edge_strings.cpp"),
    )
check(
    "a raw string's braces do not unbalance the scanner",
    ("print_line", "consume", None) in calls,
)


# =========================================================================
# SECTION 8: Preprocessor regions (edge_preprocessor.cpp — probe E6)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 8: Preprocessor (edge_preprocessor.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_preprocessor.cpp")
check(
    "conditional bodies are scanned as part of the enclosing function",
    calls
    == {
        ("run_pipeline", "trace_value", None),
        ("run_pipeline", "quiet_value", None),
        ("run_pipeline", "sanitize", None),
        ("total", "accumulate", None),
    },
    f"calls={sorted(calls)}",
)
for directive in ("TRACE", "LOG", "LIMIT", "defined", "include", "define"):
    check(
        f"`{directive}` is not a call",
        directive not in called_names(test_dir / "edge_preprocessor.cpp"),
    )


# =========================================================================
# SECTION 9: Negatives (edge_negatives.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 9: Negatives (edge_negatives.cpp)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_negatives.cpp")
check(
    "only the function body owns calls (module/class/enum code owns nothing)",
    calls == {("guarded", "helper", None), ("guarded", "take_pointer", None)},
    f"calls={sorted(calls)}",
)
check(
    "a module-level initialiser call owns nothing (`int counter = seed();`)",
    "seed" not in called_names(test_dir / "edge_negatives.cpp"),
)
check(
    "a class-level initialiser call owns nothing (`int limit_ = threshold();`)",
    "threshold" not in called_names(test_dir / "edge_negatives.cpp"),
)
check(
    "an enumerator initialiser call owns nothing (`First = pick()`)",
    "pick" not in called_names(test_dir / "edge_negatives.cpp"),
)
check(
    "`sizeof`/`static_cast` are never calls",
    "sizeof" not in called_names(test_dir / "edge_negatives.cpp")
    and "static_cast" not in called_names(test_dir / "edge_negatives.cpp"),
)
check(
    "a function pointer passed as an argument is an argument, not a callee",
    ("guarded", "take_pointer", None) in calls,
)


# =========================================================================
# SECTION 10: Real-world patterns (edge_realworld.cpp)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 10: Real-world patterns (edge_realworld.cpp)")
print(SECTION_SEP)

rw_calls = calls_of(test_dir / "edge_realworld.cpp")
rw_symbols = symbol_tuples(test_dir / "edge_realworld.cpp")
check(
    "tokenizer calls attribute exactly",
    rw_calls
    == {
        ("done", "size", "Scanner"),
        ("next_token", "skip_whitespace", "Scanner"),
        ("next_token", "read_word", "Scanner"),
        ("skip_whitespace", "done", "Scanner"),
        ("skip_whitespace", "peek", "Scanner"),
        ("skip_whitespace", "advance", "Scanner"),
        ("read_word", "done", "Scanner"),
        ("read_word", "peek", "Scanner"),
        ("read_word", "push_back", "Scanner"),
        ("read_word", "advance", "Scanner"),
        ("normalise", "next_token", None),
        ("tokenize", "normalise", None),
    },
    f"calls={sorted(rw_calls)}",
)
check(
    "the class and its members are indexed",
    {
        ("Scanner", "CLASS", None),
        ("next_token", "METHOD", "Scanner"),
        ("read_word", "METHOD", "Scanner"),
        ("normalise", "FUNCTION", None),
        ("tokenize", "FUNCTION", None),
    }
    <= rw_symbols,
)
check(
    "constructing a Scanner is not a call",
    all(called != "Scanner" for _, called, _ in rw_calls),
)
check(
    "namespace-qualified flow is captured under its final segment",
    ("tokenize", "normalise", None) in rw_calls,
)
check(
    "no call is attributed to an empty caller",
    all(caller.strip() for caller, _, _ in rw_calls),
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
