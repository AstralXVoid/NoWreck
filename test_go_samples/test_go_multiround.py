#!/usr/bin/env python3
"""Multi-round repeatability, stress, and chaos test for the Go scanner.

Mirrors test_ts_samples/test_phase1_multiround.py but for Go files.
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

from nowreck.scanner.go_scanner import scan_go_calls, scan_go_file  # noqa: E402

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

GO_FILES = [
    test_dir / "edge_basic.go",
    test_dir / "edge_export.go",
    test_dir / "edge_interfaces.go",
    test_dir / "edge_methods.go",
    test_dir / "edge_structs.go",
    test_dir / "edge_goroutines.go",
    test_dir / "edge_realworld.go",
]


def all_symbol_tuples(files: list[Path]) -> set[tuple]:
    """Collect every symbol across *files* as comparable tuples."""
    result: set[tuple] = set()
    for f in files:
        for s in scan_go_file(f):
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
    results.append(frozenset(all_symbol_tuples(GO_FILES)))

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
    for f in GO_FILES:
        for fp, caller, called in scan_go_calls(f):
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
        f"func Func{i:04d}(x int) int {{ return x + {i} }}\n"
    )
    large_lines.append(
        f"type Struct{i:04d} struct {{ Field int }}\n"
    )
    large_lines.append(
        f"func (s *Struct{i:04d}) Method() int {{ return 0 }}\n"
    )

large_source = "".join(large_lines)

with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
    f.write(large_source)
    fname = f.name

symbols = scan_go_file(fname)
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

path_str = str(test_dir / "edge_basic.go")
path_posix = test_dir / "edge_basic.go"
sym_str = scan_go_file(path_str)
sym_posix = scan_go_file(path_posix)
check("str path works", len(sym_str) > 0)
check("PosixPath works", len(sym_posix) > 0)
str_names = {s.name for s in sym_str}
posix_names = {s.name for s in sym_posix}
check("str == PosixPath results", str_names == posix_names)


# =========================================================================
# ROUND 5: REAL-WORLD GO PATTERNS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 5: REAL-WORLD GO PATTERNS")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
    f.write("""\
package main

import "net/http"

// HTTP server struct
type HTTPServer struct {
    addr string
}

// Constructor
func NewHTTPServer(addr string) *HTTPServer {
    return &HTTPServer{addr: addr}
}

// Method on server
func (s *HTTPServer) Listen() error {
    return http.ListenAndServe(s.addr, nil)
}

// Handler struct
type UserHandler struct {
    db Database
}

// Interface
type Database interface {
    Get(id uint64) (string, error)
    Set(id uint64, value string) error
}

// Method on handler
func (h *UserHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
}

// Enum-like constants via type
type Status int

const (
    StatusActive  Status = 1
    StatusDeleted Status = 2
)

// Method on custom type
func (s Status) String() string {
    return "status"
}

// Function with error
func LoadConfig(path string) (*Config, error) {
    return &Config{Name: path}, nil
}

// Config struct
type Config struct {
    Name string
}

// Type alias
type HandlerFunc = func(http.ResponseWriter, *http.Request)
""")
    fname = f.name

symbols = scan_go_file(fname)
sym_names = {s.name for s in symbols}
check("HTTPServer (struct) captured", "HTTPServer" in sym_names)
check("NewHTTPServer (constructor) captured", "NewHTTPServer" in sym_names)
check("Listen (method) captured", "Listen" in sym_names)
check("UserHandler (struct) captured", "UserHandler" in sym_names)
check("Database (interface) captured", "Database" in sym_names)
check("ServeHTTP (method) captured", "ServeHTTP" in sym_names)
check("Status (type alias) captured", "Status" in sym_names)
check("LoadConfig (function) captured", "LoadConfig" in sym_names)
check("Config (struct) captured", "Config" in sym_names)
check("HandlerFunc (type alias) captured", "HandlerFunc" in sym_names)
os.unlink(fname)


# =========================================================================
# ROUND 6: LINE NUMBER ACCURACY
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 6: LINE NUMBER ACCURACY")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
    f.write("package main\n\n\n")  # lines 1-3
    f.write("func OnLine4() int { return 0 }\n")  # line 4
    f.write("\n\n")  # blank lines
    f.write("type OnLine7 struct {\n")  # line 7
    f.write("    Field int\n")  # line 8
    f.write("}\n")  # line 9
    f.write("\n")  # blank
    f.write("type OnLine11 interface {\n")  # line 11
    f.write("    Method()\n")  # line 12
    f.write("}\n")  # line 13
    fname = f.name

symbols = scan_go_file(fname)
for s in symbols:
    if s.name == "OnLine4":
        check("OnLine4 is on line 4", s.line_number == 4)
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

# Verify Rust scanner still works
from nowreck.scanner.rust_scanner import scan_rust_file as rust_scan  # noqa: E402

rust_test = test_dir.parent / "test_rust_samples" / "edge_basic.rs"
if rust_test.exists():
    rust_syms = rust_scan(rust_test)
    msg = f"Rust edge_basic.rs still works ({len(rust_syms)} symbols)"
    check(msg, len(rust_syms) > 0)


# =========================================================================
# ROUND 8: CHAOS TEST — random property verification
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 8: CHAOS TEST — random property verification")
print(SECTION)

all_syms: list[tuple] = []
for f in GO_FILES:
    for s in scan_go_file(f):
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
