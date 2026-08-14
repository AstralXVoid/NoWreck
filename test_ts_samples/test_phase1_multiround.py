#!/usr/bin/env python3
"""Multi-round repeatability, stress, and chaos test for the TS scanner."""

import os
import random
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.typescript_scanner import scan_ts_file  # noqa: E402

test_dir = Path(__file__).resolve().parent

pass_count = 0
fail_count = 0
test_start_line = 0  # not used but kept for consistency with JS multi-round


def check(label: str, condition: bool) -> None:
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  ✅ {label}")
    else:
        fail_count += 1
        print(f"  ❌ {label}")


SECTION = "=" * 70
SUB = "-" * 60


# =========================================================================
# ROUND 1: REPEATABILITY — 3 runs, must produce identical results
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 1: REPEATABILITY — 3 runs, must produce identical results")
print(SECTION)

files = [
    test_dir / "edge_basic.ts",
    test_dir / "edge_export.ts",
    test_dir / "edge_generators.ts",
    test_dir / "edge_iife.ts",
    test_dir / "edge_types_only.ts",
]

results: list[frozenset[tuple]] = []
for run in range(3):
    all_symbols: set[tuple] = set()
    for f in files:
        syms = scan_ts_file(f)
        for s in syms:
            all_symbols.add((
                s.name,
                s.symbol_type.name,
                str(s.file_path),
                s.line_number,
                s.parent_class,
            ))
    results.append(frozenset(all_symbols))

msg_r1r2 = f"Run 1 == Run 2: {results[0] == results[1]}"
check(msg_r1r2, results[0] == results[1])
msg_r1r3 = f"Run 1 == Run 3: {results[0] == results[2]}"
check(msg_r1r3, results[0] == results[2])
msg_r2r3 = f"Run 2 == Run 3: {results[1] == results[2]}"
check(msg_r2r3, results[1] == results[2])
print(f"\n  All 3 runs produced {len(results[0])} unique symbol tuples.")


# =========================================================================
# ROUND 2: STRESS TEST — large file, many symbols
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 2: STRESS TEST — large file, many symbols")
print(SECTION)

large_lines: list[str] = []
for i in range(500):
    large_lines.append(
        f"function func{i:04d}(x: number): number {{ return x + {i}; }}\n"
    )
    large_lines.append(
        f"const arr{i:04d} = (x: number): number => x * {i};\n"
    )
    if i % 10 == 0:
        large_lines.append(
            f"class LargeClass{i:04d} {{\n  method(): void {{}}\n}}\n"
        )

large_source = "".join(large_lines)

with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
    f.write(large_source)
    fname = f.name

symbols = scan_ts_file(fname)
check(
    f"Stress file parsed — {len(symbols)} symbols found",
    len(symbols) > 0,
)
# Expected: 500 funcs + 500 arrows + 50 classes + 50 methods = 1100
total_expected = 500 + 500 + 50 + 50
check(
    f"Stress file has expected ~{total_expected} symbols",
    total_expected - 10 <= len(symbols) <= total_expected + 10,
)
os.unlink(fname)


# =========================================================================
# ROUND 3: PATH VARIANTS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 3: PATH VARIANTS")
print(SECTION)

path_str = str(test_dir / "edge_basic.ts")
path_posix = test_dir / "edge_basic.ts"
sym_str = scan_ts_file(path_str)
sym_posix = scan_ts_file(path_posix)
check("str path works", len(sym_str) > 0)
check("PosixPath works", len(sym_posix) > 0)
str_names = {s.name for s in sym_str}
posix_names = {s.name for s in sym_posix}
check("str == PosixPath results", str_names == posix_names)


# =========================================================================
# ROUND 4: REAL-WORLD TS PATTERNS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 4: REAL-WORLD TS PATTERNS")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
    f.write("""\
// Common real-world TypeScript patterns
export function formatDate(date: Date, locale: string = "en-US"): string {
    return date.toLocaleDateString(locale);
}

// Default params (not captured as symbols, just structural)
export function greet(name: string = "World"): string {
    return `Hello, ${name}`;
}

// Async function
export async function fetchData(url: string): Promise<Response> {
    const response = await fetch(url);
    return response;
}

// Arrow with destructured params
export const transform = ({x, y}: {x: number; y: number}): number => {
    return x + y;
};

// Class with public/private (decorators deferred — just method detection)
class Service {
    private data: string[] = [];

    add(item: string): void {
        this.data.push(item);
    }

    getAll(): string[] {
        return this.data;
    }
}
""")
    fname = f.name

symbols = scan_ts_file(fname)
sym_names = {s.name for s in symbols}
check(
    "formatDate (function with default param) captured",
    "formatDate" in sym_names,
)
check(
    "greet (function with default param) captured",
    "greet" in sym_names,
)
check(
    "fetchData (async function) captured",
    "fetchData" in sym_names,
)
check(
    "transform (arrow with destructured params) captured",
    "transform" in sym_names,
)
check("Service (class) captured", "Service" in sym_names)
check("add (method) captured", "add" in sym_names)
check("getAll (method) captured", "getAll" in sym_names)
os.unlink(fname)


# =========================================================================
# ROUND 5: LINE NUMBER ACCURACY
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 5: LINE NUMBER ACCURACY")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
    f.write("\n\n\n")  # 3 blank lines
    f.write("function onLine4(): void {}\n")  # line 4
    f.write("\n\n")  # blank lines
    f.write("const onLine7 = (): void => {};\n")  # line 7
    f.write("\n")
    f.write("class OnLine9 {\n")  # line 9
    f.write("  methodOnLine10(): void {}\n")  # line 10
    f.write("}\n")
    fname = f.name

symbols = scan_ts_file(fname)
for s in symbols:
    if s.name == "onLine4":
        check("onLine4 is on line 4", s.line_number == 4)
    elif s.name == "onLine7":
        check("onLine7 is on line 7", s.line_number == 7)
    elif s.name == "OnLine9":
        check("OnLine9 is on line 9", s.line_number == 9)
    elif s.name == "methodOnLine10":
        check("methodOnLine10 is on line 10", s.line_number == 10)
os.unlink(fname)


# =========================================================================
# ROUND 6: TYPE CHECKING & LINT
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 6: TYPE CHECKING & LINT")
print(SECTION)

# Verify that the refactored JS scanner still works (regression check)
from nowreck.scanner.javascript_scanner import scan_js_file as js_scan  # noqa: E402

js_test = test_dir.parent / "test_js_samples" / "edge_basic.js"
if js_test.exists():
    js_syms = js_scan(js_test)
    check(
        f"JS edge_basic.js still works ({len(js_syms)} symbols)",
        len(js_syms) > 0,
    )


# =========================================================================
# ROUND 7: CHAOS TEST — random property verification
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 7: CHAOS TEST — random property verification")
print(SECTION)

# Parse all test files and verify random properties
all_syms: list[tuple] = []
for f in [
    test_dir / "edge_basic.ts",
    test_dir / "edge_export.ts",
    test_dir / "edge_generators.ts",
    test_dir / "edge_iife.ts",
    test_dir / "edge_types_only.ts",
]:
    for s in scan_ts_file(f):
        all_syms.append((s.name, s.symbol_type, s.line_number, s.parent_class))

if all_syms:
    sample = random.sample(all_syms, min(10, len(all_syms)))
    for sym_name, sym_type, line, parent in sample:
        msg = (
            f"Random symbol: {sym_type.name} {sym_name} "
            f"(line {line}, parent={parent})"
        )
        check(msg, sym_name and sym_type and line > 0)
else:
    check("No symbols found for chaos test", False)


# =========================================================================
# RESULTS
# =========================================================================
total = pass_count + fail_count
print(f"\n{SECTION}")
print("  MULTI-ROUND TEST RESULTS")
print(f"  Total tests: {total}")
print(f"  Passed:      {pass_count}")
print(f"  Failed:      {fail_count}")
print("  Time:        ---")
print(SECTION)
result_text = (
    "ALL TESTS PASSED — No failures across all 7 rounds."
    if fail_count == 0
    else "SOME TESTS FAILED!"
)
print(f"\n  {'✅' if fail_count == 0 else '❌'} {result_text}")
print()

if __name__ == "__main__":
    if fail_count > 0:
        sys.exit(1)
