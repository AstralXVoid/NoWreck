#!/usr/bin/env python3
"""Multi-round repeatability, stress, and chaos test for the Java scanner.

Mirrors test_rust_samples/test_rust_multiround.py.  Covers:
repeatability, stress, path variants, real-world patterns, line-number
accuracy, cross-language regression, and a chaos pass.
"""

import random
import sys
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.java_scanner import (  # noqa: E402
    scan_java_calls,
    scan_java_file,
)
from nowreck.scanner.repository_scanner import RepositoryScanner  # noqa: E402

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


SECTION = "=" * 70

JAVA_FILES = sorted(test_dir.glob("edge_*.java")) + [test_dir / "basic.java"]


def all_symbol_tuples(files: list[Path]) -> set[tuple]:
    """Collect every symbol across *files* as comparable tuples."""
    result: set[tuple] = set()
    for f in files:
        for s in scan_java_file(f):
            result.add(
                (
                    s.name,
                    s.symbol_type.name,
                    str(s.file_path),
                    s.line_number,
                    s.parent_class,
                    s.body_hash,
                )
            )
    return result


def all_call_tuples(files: list[Path]) -> set[tuple]:
    result: set[tuple] = set()
    for f in files:
        for c in scan_java_calls(f):
            result.add(
                (
                    c.caller_name,
                    c.called_name,
                    c.caller_parent_class,
                    str(c.file_path),
                )
            )
    return result


# =========================================================================
# ROUND 1: REPEATABILITY — 3 runs must be byte-identical
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 1: REPEATABILITY (3 runs)")
print(SECTION)

runs = [all_symbol_tuples(JAVA_FILES) for _ in range(3)]
check(
    "3 symbol runs identical", runs[0] == runs[1] == runs[2], f"{len(runs[0])} symbols"
)
call_runs = [all_call_tuples(JAVA_FILES) for _ in range(3)]
check("3 call runs identical", call_runs[0] == call_runs[1] == call_runs[2])
check("sample corpus is non-trivial", len(runs[0]) > 80, f"symbols={len(runs[0])}")


# =========================================================================
# ROUND 2: STRESS — a generated large file
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 2: STRESS (generated 20 classes x 50 methods)")
print(SECTION)

lines: list[str] = ["package stress;", ""]
for ci in range(20):
    lines.append(f"class C{ci} {{")
    for mi in range(50):
        lines.append(f"  int m{mi}(int a) {{ return call{mi}(a) + {ci}; }}")
        lines.append(f"  private int call{mi}(int a) {{ return a * {mi}; }}")
    lines.append("}")
large = "\n".join(lines) + "\n"

with tempfile.TemporaryDirectory() as tmp:
    big = Path(tmp) / "Big.java"
    big.write_text(large)
    start = time.perf_counter()
    big_syms = scan_java_file(big)
    big_calls = scan_java_calls(big)
    elapsed = time.perf_counter() - start
    rescan_identical = scan_java_file(big) == big_syms

expected_classes = 20
expected_methods = 20 * 100  # 50 callers + 50 callees each
check(
    "stress symbol count",
    len(big_syms) == expected_classes + expected_methods,
    f"got {len(big_syms)}",
)
check("stress call count", len(big_calls) == 20 * 50, f"got {len(big_calls)}")
# Smoke bound, not a benchmark: generous headroom so the check stays
# stable on a loaded machine while still catching gross perf regressions.
check(
    "stress scan is fast",
    elapsed < 30.0,
    f"took {elapsed:.2f}s for {len(large.splitlines())} lines",
)
check("stress re-scan identical", rescan_identical)


# =========================================================================
# ROUND 3: PATH VARIANTS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 3: PATH VARIANTS")
print(SECTION)

target = test_dir / "edge_basic.java"
with_repo_root = scan_java_file(target, repo_root=test_dir)
without_repo_root = scan_java_file(target)
check(
    "repo_root relativises file_path",
    all(str(s.file_path) == "edge_basic.java" for s in with_repo_root),
)
check(
    "no repo_root keeps the absolute path",
    all(Path(s.file_path).is_absolute() for s in without_repo_root),
)
check(
    "names/types identical regardless of repo_root",
    [(s.name, s.symbol_type) for s in with_repo_root]
    == [(s.name, s.symbol_type) for s in without_repo_root],
)
with tempfile.TemporaryDirectory() as tmp:
    copy = Path(tmp) / "edge_basic.java"
    copy.write_text(target.read_text())
    check(
        "position-independent output",
        [
            (s.name, s.symbol_type, s.line_number, s.body_hash)
            for s in scan_java_file(copy)
        ]
        == [
            (s.name, s.symbol_type, s.line_number, s.body_hash)
            for s in without_repo_root
        ],
    )


# =========================================================================
# ROUND 4: REAL-WORLD PATTERNS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 4: REAL-WORLD PATTERNS (edge_realworld.java)")
print(SECTION)

rw = test_dir / "edge_realworld.java"
rw_syms = scan_java_file(rw, repo_root=test_dir)
rw_calls = scan_java_calls(rw, repo_root=test_dir)
rw_names = {s.name for s in rw_syms}
check("service class captured", "UserService" in rw_names)
check("nested record captured", "User" in rw_names)
check("nested exception class captured", "NotFoundException" in rw_names)
check("nested generic class captured", "Cache" in rw_names)
check(
    "service method parent_class",
    all(s.parent_class == "UserService" for s in rw_syms if s.name == "create"),
)
check(
    "service-to-helper call captured",
    any(c.caller_name == "create" and c.called_name == "validate" for c in rw_calls),
)
check(
    "nested-class method call captured",
    any(c.caller_name == "log" and c.called_name == "println" for c in rw_calls),
)
check(
    "constructor super() is not a call",
    all(c.called_name != "super" for c in rw_calls),
)
check(
    "throw new X() is not a call",
    all(c.called_name != "NotFoundException" for c in rw_calls),
)


# =========================================================================
# ROUND 5: LINE-NUMBER ACCURACY
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 5: LINE-NUMBER ACCURACY")
print(SECTION)

for path in JAVA_FILES:
    source_lines = path.read_text().splitlines()
    ok = True
    detail = ""
    for s in scan_java_file(path):
        line = source_lines[s.line_number - 1]
        # A declaration's node starts at its first annotation when it has
        # one (annotations are node children — probe J4), so the reported
        # line either names the symbol or is the annotation immediately
        # above it.
        names_here = s.name in line
        annotation_above = line.strip().startswith("@") and any(
            s.name in following
            for following in source_lines[s.line_number : s.line_number + 3]
        )
        if not (names_here or annotation_above):
            ok = False
            detail = (
                f"{path.name}:{s.line_number} does not name {s.name!r} "
                f"(line={line.strip()!r})"
            )
            break
    check(f"{path.name}: every symbol line locates the symbol", ok, detail)
    if not ok:
        break


# =========================================================================
# ROUND 6: CROSS-LANGUAGE REGRESSION
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 6: CROSS-LANGUAGE REGRESSION")
print(SECTION)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "app.py").write_text("def run():\n    return 1\n")
    (root / "app.js").write_text("function run() { return 1; }\n")
    (root / "app.ts").write_text("function run(): number { return 1; }\n")
    (root / "app.rs").write_text("fn run() -> i32 { 1 }\n")
    (root / "app.go").write_text("package main\n\nfunc run() int { return 1 }\n")
    (root / "App.java").write_text("public class App {\n  int run() { return 1; }\n}\n")
    scan = RepositoryScanner(root, use_cache=False).scan()
    check(
        "no parse failures in mixed repo",
        scan.failure_count == 0,
        str(scan.failed_files),
    )
    check("python discovered", len(scan.modules) == 1)
    check("javascript discovered", len(scan.js_files) == 1)
    check("typescript discovered", len(scan.ts_files) == 1)
    check("rust discovered", len(scan.rust_files) == 1)
    check("go discovered", len(scan.go_files) == 1)
    check("java discovered alongside the rest", len(scan.java_files) == 1)
    check("success count covers all six", scan.success_count == 6)


# =========================================================================
# ROUND 7: CHAOS — random truncations must never crash the scanner
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 7: CHAOS (truncated / mutated sources)")
print(SECTION)

rng = random.Random(20260813)
base = (test_dir / "edge_realworld.java").read_text()
crashes = 0
with tempfile.TemporaryDirectory() as tmp:
    chaos = Path(tmp) / "Chaos.java"
    for _ in range(60):
        cut = rng.randrange(1, len(base))
        chaos.write_text(base[:cut])
        try:
            scan_java_file(chaos)
            scan_java_calls(chaos)
        except Exception as exc:  # noqa: BLE001 — chaos must never raise
            crashes += 1
            print(f"      crash at cut={cut}: {type(exc).__name__}: {exc}")
check("60 random truncations never crash", crashes == 0, f"crashes={crashes}")


# =========================================================================
# RESULTS
# =========================================================================
total = pass_count + fail_count
print(f"\n{SECTION}")
print(f"  RESULTS: {pass_count} passed, {fail_count} failed, {total} total")
print(SECTION)
print(f"\n  {'✅ All tests passed!' if fail_count == 0 else '❌ Some tests failed!'}")

if __name__ == "__main__":
    if fail_count > 0:
        sys.exit(1)
