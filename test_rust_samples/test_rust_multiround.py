#!/usr/bin/env python3
"""Multi-round repeatability, stress, and chaos test for the Rust scanner.

Mirrors test_ts_samples/test_phase1_multiround.py but for Rust files.
Covers: repeatability, stress, path variants, real-world patterns,
line number accuracy, cross-language regression, chaos test.
"""
import os
import random
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.rust_scanner import scan_rust_calls, scan_rust_file  # noqa: E402

test_dir = Path(__file__).resolve().parent

pass_count = 0
fail_count = 0


def check(label: str, condition: bool) -> None:
    global pass_count, fail_count  # noqa: PLW0603
    if condition:
        pass_count += 1
        print(f"  ✅ {label}")
    else:
        fail_count += 1
        print(f"  ❌ {label}")


SECTION = "=" * 70

RUST_FILES = [
    test_dir / "edge_basic.rs",
    test_dir / "edge_pub.rs",
    test_dir / "edge_traits.rs",
    test_dir / "edge_generics.rs",
    test_dir / "edge_closures.rs",
    test_dir / "edge_derive.rs",
    test_dir / "edge_realworld.rs",
]


def all_symbol_tuples(files: list[Path]) -> set[tuple]:
    """Collect every symbol across *files* as comparable tuples."""
    result: set[tuple] = set()
    for f in files:
        for s in scan_rust_file(f):
            result.add((
                s.name,
                s.symbol_type.name,
                str(s.file_path),
                s.line_number,
                s.parent_class,
            ))
    return result


# =========================================================================
# ROUND 1: REPEATABILITY — 3 runs, must produce identical results
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 1: REPEATABILITY — 3 runs, must produce identical results")
print(SECTION)

results: list[frozenset[tuple]] = []
for run in range(3):
    results.append(frozenset(all_symbol_tuples(RUST_FILES)))

check(f"Run 1 == Run 2: {results[0] == results[1]}", results[0] == results[1])
check(f"Run 1 == Run 3: {results[0] == results[2]}", results[0] == results[2])
check(f"Run 2 == Run 3: {results[1] == results[2]}", results[1] == results[2])
print(f"\n  All 3 runs produced {len(results[0])} unique symbol tuples.")


# =========================================================================
# ROUND 2: CALL REPEATABILITY — 3 runs, identical call sets
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 2: CALL REPEATABILITY — 3 runs, identical call sets")
print(SECTION)

call_results: list[frozenset[tuple]] = []
for run in range(3):
    all_calls: set[tuple] = set()
    for f in RUST_FILES:
        for fp, caller, called in scan_rust_calls(f):
            all_calls.add((str(fp), caller, called))
    call_results.append(frozenset(all_calls))

check(
    f"Call run 1 == run 2: {call_results[0] == call_results[1]}",
    call_results[0] == call_results[1],
)
check(
    f"Call run 1 == run 3: {call_results[0] == call_results[2]}",
    call_results[0] == call_results[2],
)


# =========================================================================
# ROUND 3: STRESS TEST — large file, many symbols
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 3: STRESS TEST — large file, many symbols")
print(SECTION)

large_lines: list[str] = []
for i in range(500):
    large_lines.append(
        f"fn func{i:04d}(x: i32) -> i32 {{ x + {i} }}\n"
    )
    large_lines.append(
        f"struct Struct{i:04d} {{ field: i32 }}\n"
    )
    large_lines.append(
        f"impl Struct{i:04d} {{ fn method(&self) -> i32 {{ 0 }} }}\n"
    )

large_source = "".join(large_lines)

with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
    f.write(large_source)
    fname = f.name

symbols = scan_rust_file(fname)
check(
    f"Stress file parsed — {len(symbols)} symbols found",
    len(symbols) > 0,
)
# Expected: 500 funcs + 500 structs + 500 methods = 1500
total_expected = 500 + 500 + 500
check(
    f"Stress file has expected ~{total_expected} symbols",
    total_expected - 10 <= len(symbols) <= total_expected + 10,
)
os.unlink(fname)


# =========================================================================
# ROUND 4: PATH VARIANTS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 4: PATH VARIANTS")
print(SECTION)

path_str = str(test_dir / "edge_basic.rs")
path_posix = test_dir / "edge_basic.rs"
sym_str = scan_rust_file(path_str)
sym_posix = scan_rust_file(path_posix)
check("str path works", len(sym_str) > 0)
check("PosixPath works", len(sym_posix) > 0)
str_names = {s.name for s in sym_str}
posix_names = {s.name for s in sym_posix}
check("str == PosixPath results", str_names == posix_names)


# =========================================================================
# ROUND 5: REAL-WORLD RUST PATTERNS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 5: REAL-WORLD RUST PATTERNS")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
    f.write("""\
// Common real-world Rust patterns

use std::collections::HashMap;

/// A service that manages users.
struct UserService {
    users: HashMap<u64, String>,
}

impl UserService {
    fn new() -> Self {
        UserService { users: HashMap::new() }
    }

    fn add_user(&mut self, id: u64, name: &str) {
        self.users.insert(id, name.to_string());
    }

    fn get_user(&self, id: u64) -> Option<&String> {
        self.users.get(&id)
    }

    fn remove_user(&mut self, id: u64) -> bool {
        self.users.remove(&id).is_some()
    }
}

// Trait with multiple methods
trait Repository {
    fn find(&self, id: u64) -> Option<String>;
    fn save(&mut self, id: u64, data: &str);
    fn list_all(&self) -> Vec<String>;
}

// Enum with data variants
#[derive(Debug)]
enum Event {
    Click { x: i32, y: i32 },
    KeyPress(char),
    Scroll(f64),
    Quit,
}

impl Event {
    fn name(&self) -> &str {
        match self {
            Event::Click { .. } => "click",
            Event::KeyPress(_) => "keypress",
            Event::Scroll(_) => "scroll",
            Event::Quit => "quit",
        }
    }
}

// Async function
async fn fetch_all(urls: Vec<String>) -> Vec<String> {
    urls.into_iter().map(|u| format!("response from {}", u)).collect()
}

// Generic struct
struct Cache<K, V> {
    entries: HashMap<K, V>,
}

impl<K, V> Cache<K, V> {
    fn new() -> Self {
        Cache { entries: HashMap::new() }
    }
}

// Type alias
type UserId = u64;
""")
    fname = f.name

symbols = scan_rust_file(fname)
sym_names = {s.name for s in symbols}
check("UserService (struct) captured", "UserService" in sym_names)
check("new (impl method) captured", "new" in sym_names)
check("add_user (impl method) captured", "add_user" in sym_names)
check("get_user (impl method) captured", "get_user" in sym_names)
check("remove_user (impl method) captured", "remove_user" in sym_names)
check("Repository (trait) captured", "Repository" in sym_names)
check("Event (enum) captured", "Event" in sym_names)
check("name (impl method on enum) captured", "name" in sym_names)
check("fetch_all (async fn) captured", "fetch_all" in sym_names)
check("Cache (generic struct) captured", "Cache" in sym_names)
check("UserId (type alias) captured", "UserId" in sym_names)
os.unlink(fname)


# =========================================================================
# ROUND 6: LINE NUMBER ACCURACY
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 6: LINE NUMBER ACCURACY")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
    f.write("\n\n\n")  # 3 blank lines
    f.write("fn on_line_4() -> i32 { 0 }\n")  # line 4
    f.write("\n\n")  # blank lines
    f.write("struct OnLine7 {\n")  # line 7
    f.write("    field: i32,\n")  # line 8
    f.write("}\n")  # line 9
    f.write("\n")  # blank
    f.write("trait OnLine11 {\n")  # line 11
    f.write("    fn method(&self);\n")  # line 12
    f.write("}\n")  # line 13
    fname = f.name

symbols = scan_rust_file(fname)
for s in symbols:
    if s.name == "on_line_4":
        check("on_line_4 is on line 4", s.line_number == 4)
    elif s.name == "OnLine7":
        check("OnLine7 is on line 7", s.line_number == 7)
    elif s.name == "OnLine11":
        check("OnLine11 is on line 11", s.line_number == 11)
os.unlink(fname)


# =========================================================================
# ROUND 7: CROSS-LANGUAGE REGRESSION
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 7: CROSS-LANGUAGE REGRESSION")
print(SECTION)

# Verify JS scanner still works (regression check)
from nowreck.scanner.javascript_scanner import scan_js_file as js_scan  # noqa: E402

js_test = test_dir.parent / "test_js_samples" / "edge_basic.js"
if js_test.exists():
    js_syms = js_scan(js_test)
    check(f"JS edge_basic.js still works ({len(js_syms)} symbols)", len(js_syms) > 0)

# Verify TS scanner still works
from nowreck.scanner.typescript_scanner import scan_ts_file as ts_scan  # noqa: E402

ts_test = test_dir.parent / "test_ts_samples" / "edge_basic.ts"
if ts_test.exists():
    ts_syms = ts_scan(ts_test)
    check(f"TS edge_basic.ts still works ({len(ts_syms)} symbols)", len(ts_syms) > 0)

# Verify Go scanner still works
from nowreck.scanner.go_scanner import scan_go_file as go_scan  # noqa: E402

go_test = test_dir.parent / "test_go_samples" / "edge_basic.go"
if go_test.exists():
    go_syms = go_scan(go_test)
    check(f"Go edge_basic.go still works ({len(go_syms)} symbols)", len(go_syms) > 0)


# =========================================================================
# ROUND 8: CHAOS TEST — random property verification
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 8: CHAOS TEST — random property verification")
print(SECTION)

all_syms: list[tuple] = []
for f in RUST_FILES:
    for s in scan_rust_file(f):
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
print(SECTION)
result_text = (
    "ALL TESTS PASSED — No failures across all 8 rounds."
    if fail_count == 0
    else "SOME TESTS FAILED!"
)
print(f"\n  {'✅' if fail_count == 0 else '❌'} {result_text}")
print()

if __name__ == "__main__":
    if fail_count > 0:
        sys.exit(1)
