#!/usr/bin/env python3
"""Comprehensive scanner-level tests for Java symbol and call extraction.

Mirrors the structure and depth of test_rust_samples/test_rust_comprehensive.py
but for the Java scanner (tree-sitter-java grammar).

Covers the whole Phase 2 matrix at the scanner layer: the call-capture
rules resolved by probes J1–J12, the symbol model, hash normalisation,
and the documented exclusions.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.java_scanner import (  # noqa: E402
    scan_java_calls,
    scan_java_file,
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


SECTION_SEP = "=" * 70


def calls_of(path: Path) -> set[tuple[str, str, str | None]]:
    return {
        (c.caller_name, c.called_name, c.caller_parent_class)
        for c in scan_java_calls(path)
    }


def called_names(path: Path) -> set[str]:
    return {c.called_name for c in scan_java_calls(path)}


def symbols_of(path: Path) -> list:
    return scan_java_file(path)


def hash_of(source: str, name: str, kind: str) -> str | None:
    """Scan *source* from a temp file and return the named symbol's hash."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Sample.java"
        path.write_text(source)
        for s in scan_java_file(path):
            if s.name == name and s.symbol_type.name == kind:
                return s.body_hash
    raise AssertionError(f"no {kind} symbol named {name}")


# =========================================================================
# SECTION 1: Call capture matrix (edge_calls.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Call capture matrix (edge_calls.java)")
print(SECTION_SEP)

calls = calls_of(test_dir / "edge_calls.java")
names = {c[1] for c in calls}

check("plain call captured", ("plainCall", "helper", "CallShapes") in calls)
check("this.member call captured", ("memberCall", "helper", "CallShapes") in calls)
check("super.member call captured", ("helper", "helper", "CallShapes") in calls)
check(
    "qualified A.B.m() captured",
    ("qualifiedCall", "staticHelper", "CallShapes") in calls,
)
check("index-receiver chain captured", "get" in names)
check("dynamic receiver's own call captured", "factory" in names)
check("bare dunder call captured", "__plain__" in names)

# ``items.get(0).trim()`` — the receiver of ``trim`` is a call, so only
# ``get`` is captured.  (``trim`` does appear elsewhere — from
# ``consume``, whose ``value.trim()`` has an identifier receiver.)
index_calls = {c for c in calls if c[0] == "indexReceiver"}
check(
    "receiver-is-a-call target excluded",
    index_calls == {("indexReceiver", "get", "CallShapes")},
    f"got {index_calls}",
)
check("dunder member call excluded", "__magic__" not in names)
check(
    "lambda body call attributed to the method",
    ("lambda", "consume", "CallShapes") in calls,
)
check("lambda's own invocation captured", ("lambda", "forEach", "CallShapes") in calls)
check(
    "nested lambda body call attributed to the method",
    ("nestedLambda", "consume", "CallShapes") in calls,
)

# ``f().helper()`` — only ``factory`` is captured, never ``helper``.
dynamic = {c for c in calls if c[0] == "dynamicReceiver"}
check(
    "only the inner call of f().bar() is captured",
    dynamic == {("dynamicReceiver", "factory", "CallShapes")},
    f"got {dynamic}",
)

# ``new Foo()`` and ``Foo::bar`` must never appear.
check("no constructor invocation captured", "CallShapes" not in names)
check("no method-reference target captured", "toString" not in names)


# =========================================================================
# SECTION 2: Symbol model (edge_basic.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Symbol model (edge_basic.java)")
print(SECTION_SEP)

syms = symbols_of(test_dir / "edge_basic.java")
by_name: dict[str, list] = {}
for s in syms:
    by_name.setdefault(s.name, []).append(s)

check("class captured", by_name["Greeter"][0].symbol_type.name == "CLASS")
check(
    "constructor is a METHOD named after the class",
    any(s.symbol_type.name == "METHOD" for s in by_name["Greeter"]),
)
check("interface captured", by_name["Drawable"][0].symbol_type.name == "INTERFACE")
check("enum captured", by_name["Direction"][0].symbol_type.name == "ENUM")
check("record maps to CLASS", by_name["UserId"][0].symbol_type.name == "CLASS")
check(
    "methods carry parent_class",
    all(s.parent_class == "Greeter" for s in by_name["greet"] + by_name["getUses"]),
)
check(
    "no FUNCTION symbol exists (Java has no top-level functions)",
    all(s.symbol_type.name != "FUNCTION" for s in syms),
)
check("class shell is hashed", by_name["Greeter"][0].body_hash is not None)
check("enum shell is hashed", by_name["Direction"][0].body_hash is not None)
check(
    "interface has no hash (no CHANGED_INTERFACE claim type)",
    by_name["Drawable"][0].body_hash is None,
)


# =========================================================================
# SECTION 3: Negatives (edge_negatives.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Negatives (edge_negatives.java)")
print(SECTION_SEP)

neg_names = {s.name for s in symbols_of(test_dir / "edge_negatives.java")}
check(
    "fields are not symbols", "CONSTANT" not in neg_names and "field" not in neg_names
)
check("locals are not symbols", "local" not in neg_names and "lambda" not in neg_names)
check("local class is not a symbol", "LocalClass" not in neg_names)
check("anonymous class is not a symbol", "anon" not in neg_names)
check("enum constants are not symbols", "A" not in neg_names and "B" not in neg_names)
check("annotation elements are not symbols", "value" not in neg_names)
check("record components are not symbols", "x" not in neg_names)


# =========================================================================
# SECTION 4: Nested / local / anonymous callers (edge_nested.java)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Caller attribution (edge_nested.java)")
print(SECTION_SEP)

nested = calls_of(test_dir / "edge_nested.java")
check(
    "nested-class method caller carries the nested class",
    ("staticMethod", "innerHelper", "StaticNested") in nested,
)
check(
    "inner-class method caller carries the inner class",
    ("innerMethod", "outerMethod", "Inner") in nested,
)
check(
    "local-class method is a caller attributed to the local class",
    ("localMethod", "localHelper", "Local") in nested,
)
check(
    "anonymous-class method is a caller with no class",
    ("run", "anonymousHelper", None) in nested,
)
check(
    "enclosing method still owns its own calls",
    ("withLocalAndAnonymous", "run", "Outer") in nested,
)


# =========================================================================
# SECTION 5: Hash normalisation
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Hash normalisation")
print(SECTION_SEP)

# Reformatting and comments never change a hash.
compact = hash_of("class A { void m() { int x = 1; foo(x); } }", "m", "METHOD")
padded = hash_of(
    "class A {\n"
    "    // a comment\n"
    "    /* another */\n"
    "    void m() {\n"
    "        int x = 1;\n"
    "        foo(x);\n"
    "    }\n"
    "}\n",
    "m",
    "METHOD",
)
check("reformat + comments do not change the hash", compact == padded)

# A logic edit always changes it.
edited = hash_of("class A { void m() { int x = 2; foo(x); } }", "m", "METHOD")
check("logic edit changes the hash", compact != edited)

# Quote style is not content: "x" and a text block holding x collide.
quoted = hash_of('class A { void m() { use("x"); } }', "m", "METHOD")
text_block = hash_of('class A { void m() { use("""x"""); } }', "m", "METHOD")
check('quote style is normalised ("x" vs text block)', quoted == text_block)

# Text-block content edits are real changes.
block_a = hash_of('class A { void m() { use("""aa"""); } }', "m", "METHOD")
block_b = hash_of('class A { void m() { use("""bb"""); } }', "m", "METHOD")
check("text-block content edit is a change", block_a != block_b)

# Semicolons are required syntax → hashed as content (not ASI-excluded).
with_semi = hash_of("class A { void m() { int x = 1; } }", "m", "METHOD")
check("semicolon-bearing body hashes deterministically", with_semi is not None)

# Disjoint facts: a method edit never changes the class shell hash.
shell_before = hash_of("class A { int f = 1; void m() { int x = 1; } }", "A", "CLASS")
shell_after = hash_of("class A { int f = 1; void m() { int x = 999; } }", "A", "CLASS")
check("method edit does not change the class shell hash", shell_before == shell_after)

field_before = hash_of("class A { int f = 1; void m() {} }", "A", "CLASS")
field_after = hash_of("class A { int f = 2; void m() {} }", "A", "CLASS")
check("field edit changes the class shell hash", field_before != field_after)

# Enum constants are shell content: a constant edit fires CHANGED_CLASS.
enum_before = hash_of("enum E { A, B; void m() {} }", "E", "ENUM")
enum_after = hash_of("enum E { A, C; void m() {} }", "E", "ENUM")
check("enum constant edit changes the enum shell hash", enum_before != enum_after)

# Record components are shell content.
rec_before = hash_of("record R(int x) {} ", "R", "CLASS")
rec_after = hash_of("record R(int y) {} ", "R", "CLASS")
check("record component edit changes the record shell hash", rec_before != rec_after)

# Constructor edit changes the constructor hash but not the class shell.
ctor_before = hash_of("class A { A(int x) { this.x = x; } int x; }", "A", "CLASS")
ctor_after = hash_of("class A { A(int x) { this.x = x + 1; } int x; }", "A", "CLASS")
check(
    "constructor edit does not change the class shell hash", ctor_before == ctor_after
)


# =========================================================================
# SECTION 6: Multi-line signatures and formatting variety
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Formatting variety")
print(SECTION_SEP)

multi = symbols_of(test_dir / "edge_methods.java")
check(
    "multi-line signature method captured",
    any(s.name == "multiLine" for s in multi),
)
check(
    "annotated method captured",
    any(
        s.name == "multiAnnotated"
        for s in symbols_of(test_dir / "edge_annotations.java")
    ),
)

# Annotation is inside the declaration → annotation edit changes the method hash.
with_ann = hash_of("class A { @Deprecated void m() { } }", "m", "METHOD")
no_ann = hash_of("class A { void m() { } }", "m", "METHOD")
check("method annotation edit changes the method hash", with_ann != no_ann)

# ... and the class-level annotation changes the class shell.
class_ann = hash_of("@Deprecated class A { void m() { } }", "A", "CLASS")
class_no_ann = hash_of("class A { void m() { } }", "A", "CLASS")
check("class annotation edit changes the class shell hash", class_ann != class_no_ann)


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
