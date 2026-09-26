#!/usr/bin/env python3
"""Multi-round repeatability, stress, and chaos test for the Kotlin scanner.

Mirrors test_java_samples/test_java_multiround.py.  Covers: repeatability,
stress, path variants, real-world patterns, line-number accuracy,
cross-language regression, and a chaos pass.
"""

import random
import sys
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.kotlin_scanner import (  # noqa: E402
    scan_kotlin_calls,
    scan_kotlin_file,
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

KOTLIN_FILES = sorted(test_dir.glob("edge_*.kt")) + [test_dir / "basic.kt"]


def all_symbol_tuples(files: list[Path]) -> set[tuple]:
    """Collect every symbol across *files* as comparable tuples."""
    result: set[tuple] = set()
    for f in files:
        for s in scan_kotlin_file(f):
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
        for c in scan_kotlin_calls(f):
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

runs = [all_symbol_tuples(KOTLIN_FILES) for _ in range(3)]
check(
    "3 symbol runs identical", runs[0] == runs[1] == runs[2], f"{len(runs[0])} symbols"
)
call_runs = [all_call_tuples(KOTLIN_FILES) for _ in range(3)]
check("3 call runs identical", call_runs[0] == call_runs[1] == call_runs[2])
check("sample corpus is non-trivial", len(runs[0]) > 60, f"symbols={len(runs[0])}")
check(
    "call corpus is non-trivial", len(call_runs[0]) > 40, f"calls={len(call_runs[0])}"
)


# =========================================================================
# ROUND 2: STRESS — a generated large file
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 2: STRESS (generated 20 classes x 50 methods)")
print(SECTION)

lines: list[str] = ["package stress", ""]
for ci in range(20):
    lines.append(f"class C{ci} {{")
    for mi in range(50):
        lines.append(f"    fun m{mi}(a: Int): Int = call{mi}(a) + {ci}")
        lines.append(f"    private fun call{mi}(a: Int): Int = a * {mi}")
    lines.append("}")
large = "\n".join(lines) + "\n"

with tempfile.TemporaryDirectory() as tmp:
    big = Path(tmp) / "Big.kt"
    big.write_text(large)
    start = time.perf_counter()
    big_syms = scan_kotlin_file(big)
    big_calls = scan_kotlin_calls(big)
    elapsed = time.perf_counter() - start
    rescan_identical = scan_kotlin_file(big) == big_syms

expected_classes = 20
expected_methods = 20 * 100  # 50 callers + 50 callees each
check(
    "stress symbol count",
    len(big_syms) == expected_classes + expected_methods,
    f"got {len(big_syms)}",
)
check("stress call count", len(big_calls) == 20 * 50, f"got {len(big_calls)}")
check(
    "stress scan is fast",
    elapsed < 5.0,
    f"took {elapsed:.2f}s for {len(large.splitlines())} lines",
)
check("stress re-scan identical", rescan_identical)


# =========================================================================
# ROUND 3: PATH VARIANTS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 3: PATH VARIANTS")
print(SECTION)

target = test_dir / "edge_basic.kt"
with_repo_root = scan_kotlin_file(target, repo_root=test_dir)
without_repo_root = scan_kotlin_file(target)
check(
    "repo_root relativises file_path",
    all(str(s.file_path) == "edge_basic.kt" for s in with_repo_root),
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
    copy = Path(tmp) / "edge_basic.kt"
    copy.write_text(target.read_text())
    check(
        "position-independent output",
        [
            (s.name, s.symbol_type, s.line_number, s.body_hash)
            for s in scan_kotlin_file(copy)
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
print("  ROUND 4: REAL-WORLD PATTERNS (edge_realworld.kt)")
print(SECTION)

rw = test_dir / "edge_realworld.kt"
rw_syms = scan_kotlin_file(rw, repo_root=test_dir)
rw_calls = scan_kotlin_calls(rw, repo_root=test_dir)
rw_names = {s.name for s in rw_syms}
check("interface captured", "Repository" in rw_names)
check("typealias captured", "Logger" in rw_names)
check("data class captured", "User" in rw_names)
check("enum captured", "Status" in rw_names)
check("class captured", "InMemoryRepository" in rw_names)
# ``save`` is declared twice on purpose (interface + implementation), so the
# check is scoped to the implementing class rather than to the bare name.
check(
    "service method parent_class",
    len(
        [
            s
            for s in rw_syms
            if s.name == "save" and s.parent_class == "InMemoryRepository"
        ]
    )
    == 1,
)
check(
    "service-to-helper call captured",
    any(c.caller_name == "save" and c.called_name == "notifyChanged" for c in rw_calls),
)
check(
    "top-level flow captured",
    any(c.caller_name == "main" and c.called_name == "process" for c in rw_calls),
)
check(
    "no call is attributed to an empty caller",
    all(c.caller_name.strip() for c in rw_calls),
)


# =========================================================================
# ROUND 5: LINE-NUMBER ACCURACY
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 5: LINE-NUMBER ACCURACY")
print(SECTION)

for path in KOTLIN_FILES:
    source_lines = path.read_text().splitlines()
    ok = True
    detail = ""
    for s in scan_kotlin_file(path):
        line = source_lines[s.line_number - 1]
        # A declaration's node starts at its annotation when it has one
        # (annotations are node children, probe K8), and a *detached*
        # annotation is folded in as the declaration's start (D4), so the
        # reported line either names the symbol or is an annotation
        # immediately above it.
        names_here = s.name in line
        annotation_above = line.strip().startswith("@") and any(
            s.name in following
            for following in source_lines[s.line_number : s.line_number + 3]
        )
        # A secondary constructor is a METHOD named after its class but,
        # unlike Java, its line reads ``constructor(...)`` — the class name
        # is never spelled there.
        secondary_constructor = (
            s.symbol_type.name == "METHOD"
            and s.parent_class == s.name
            and "constructor" in line
        )
        if not (names_here or annotation_above or secondary_constructor):
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
    (root / "App.kt").write_text("fun run(): Int {\n    return 1\n}\n")
    (root / "script.kts").write_text("fun script(): Int {\n    return 2\n}\n")
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
    check("java discovered", len(scan.java_files) == 1)
    check("kotlin discovered alongside the rest", len(scan.kotlin_files) == 2)
    check("success count covers all eight files", scan.success_count == 8)


# =========================================================================
# ROUND 7: CHAOS — random truncations must never crash the scanner
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 7: CHAOS (truncated / mutated sources)")
print(SECTION)

rng = random.Random(20260920)
base = (test_dir / "edge_realworld.kt").read_text()
crashes = 0
with tempfile.TemporaryDirectory() as tmp:
    chaos = Path(tmp) / "Chaos.kt"
    for _ in range(60):
        cut = rng.randrange(1, len(base))
        chaos.write_text(base[:cut])
        try:
            scan_kotlin_file(chaos)
            scan_kotlin_calls(chaos)
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
