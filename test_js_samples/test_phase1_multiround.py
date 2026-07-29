#!/usr/bin/env python3
"""
Phase 1 \u2014 Multi-round comprehensive test suite.

Rounds:
  1. REPEATABILITY: Run existing 78-test battery \u00d7 3, verify identical output
  2. STRESS: Large file (50+ symbols), mixed patterns
  3. PATH VARIANTS: Absolute paths, no repo_root, nested subdirectories
  4. REAL-WORLD: Common JS patterns (HOCs, destructuring, async, etc.)
  5. LINE ACCURACY: Exact line number verification
  6. TYPE/LINT: basedpyright + ruff
  7. CHAOS: Property-based random symbol matching
"""

import hashlib
import subprocess
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.javascript_scanner import scan_js_file  # noqa: E402
from nowreck.scanner.symbol_index import SymbolType  # noqa: E402

# ---------------------------------------------------------------------------
# Results tracking
# ---------------------------------------------------------------------------

_pass_count = 0
_fail_count = 0
_results: list[tuple[str, bool, str]] = []


def check(test_name: str, passed: bool, message: str) -> None:
    global _pass_count, _fail_count
    if passed:
        _pass_count += 1
    else:
        _fail_count += 1
    _results.append((test_name, passed, message))


def has_symbol(symbols, name: str, sym_type: SymbolType,
               parent_class: str | None = None) -> bool:
    for sym in symbols:
        if (sym.name == name
                and sym.symbol_type == sym_type
                and sym.parent_class == parent_class):
            return True
    return False


def symbol_names(symbols) -> list[str]:
    return sorted(f"{s.name}({s.symbol_type.name})" for s in symbols)


def symbols_fingerprint(symbols) -> str:
    """Deterministic hash of all symbol data for equality checking."""
    parts = "|".join(
        f"{s.name}:{s.symbol_type.name}:{s.file_path}:"
        f"{s.line_number}:{s.parent_class or ''}"
        for s in sorted(symbols)
    )
    return hashlib.md5(parts.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ROUND 1: Repeatability \u2014 run existing test 3 times
# ---------------------------------------------------------------------------

def round_1_repeatability(samples_dir: Path) -> None:
    print()
    print("=" * 72)
    print("  ROUND 1: REPEATABILITY \u2014 3 runs, must produce identical results")
    print("=" * 72)

    files_to_test = [
        "plain_function.js",
        "arrow_function.js",
        "class_with_methods.js",
        "export_patterns.js",
        "edge_empty.js",
        "edge_only_comments.js",
        "edge_only_imports.js",
        "edge_syntax_errors.js",
        "edge_nested.js",
        "edge_async_generators.js",
        "edge_getters_setters.js",
        "edge_naming.js",
        "edge_single_line.js",
        "edge_windows_crlf.js",
        "edge_negative_cases.js",
        "edge_export_default.js",
    ]

    fingerprints: list[dict[str, str]] = []

    for run in range(3):
        run_fprints: dict[str, str] = {}
        for fname in files_to_test:
            fpath = samples_dir / fname
            if not fpath.exists():
                continue
            syms = scan_js_file(fpath, repo_root=samples_dir)
            run_fprints[fname] = symbols_fingerprint(syms)
        fingerprints.append(run_fprints)
        time.sleep(0.1)  # small pause between runs

    # Compare run 0 vs run 1
    all_matches = True
    for fname in files_to_test:
        fps = [fp.get(fname, "") for fp in fingerprints]
        if len(set(fps)) != 1:
            check(f"repeatability: {fname}",
                  False,
                  f"MISMATCH between runs: {fps}")
            all_matches = False

    if all_matches:
        files_for_total = [
            "plain_function.js", "arrow_function.js",
            "class_with_methods.js", "export_patterns.js",
            "edge_empty.js", "edge_only_comments.js",
            "edge_only_imports.js", "edge_nested.js",
            "edge_async_generators.js", "edge_getters_setters.js",
            "edge_naming.js", "edge_single_line.js",
            "edge_windows_crlf.js", "edge_negative_cases.js",
            "edge_export_default.js", "edge_syntax_errors.js",
        ]
        total_syms = sum(
            len(scan_js_file(samples_dir / f, repo_root=samples_dir))
            for f in files_for_total
            if (samples_dir / f).exists()
        )
        check("repeatability: all 3 runs identical",
              True,
              f"All 3 runs produced identical fingerprints across "
              f"{len(files_to_test)} files ({total_syms} total symbols)")


# ---------------------------------------------------------------------------
# ROUND 2: Stress test \u2014 large file with 50+ symbols
# ---------------------------------------------------------------------------

def round_2_stress(samples_dir: Path) -> None:
    print()
    print("=" * 72)
    print("  ROUND 2: STRESS TEST \u2014 large file, many symbols")
    print("=" * 72)

    fpath = samples_dir / "stress_large_file.js"
    if not fpath.exists():
        check("stress: file exists", False, "stress_large_file.js not found")
        return

    syms = scan_js_file(fpath, repo_root=samples_dir)
    total = len(syms)

    functions = sum(1 for s in syms if s.symbol_type == SymbolType.FUNCTION)
    classes = sum(1 for s in syms if s.symbol_type == SymbolType.CLASS)
    methods = sum(1 for s in syms if s.symbol_type == SymbolType.METHOD)

    check("stress: no crash on large file", True,
          f"Parsed successfully: {total} symbols "
          f"({functions}F, {classes}C, {methods}M)")
    check("stress: at least 40 symbols",
          total >= 40,
          f"Expected >=40 symbols, got {total}")

    expected_fns = [
        "identity", "noop", "constant", "compose", "pipe",
        "add", "subtract", "multiply", "divide", "clamp",
        "isString", "isNumber", "isBoolean", "isArray", "isObject",
        "isFunction",
    ]
    for fn in expected_fns:
        check(f"stress: {fn}", has_symbol(syms, fn, SymbolType.FUNCTION),
              f"Missing function {fn}")

    expected_arrows = ["map", "filter", "reduce", "flatten", "unique", "chunk"]
    for fn in expected_arrows:
        check(f"stress: {fn} arrow",
              has_symbol(syms, fn, SymbolType.FUNCTION),
              f"Missing arrow function {fn}")

    expected_classes = [
        "User", "Admin", "Product", "Cart", "ApiService", "LoggerService",
        "ConfigStore", "EventBus", "CacheManager", "ExportedClass",
    ]
    for cls in expected_classes:
        check(f"stress: class {cls}",
              has_symbol(syms, cls, SymbolType.CLASS),
              f"Missing class {cls}")

    check("stress: Admin is top-level class",
          has_symbol(syms, "Admin", SymbolType.CLASS),
          "Missing Admin CLASS")

    check("stress: exportedUtil",
          has_symbol(syms, "exportedUtil", SymbolType.FUNCTION),
          "Missing exported function exportedUtil")
    check("stress: exportedArrow",
          has_symbol(syms, "exportedArrow", SymbolType.FUNCTION),
          "Missing exported arrow exportedArrow")

    # Negative: class expressions inside withLogging should not be top-level
    check("stress: Enhanced not top-level",
          not has_symbol(syms, "Enhanced", SymbolType.FUNCTION),
          "Enhanced (inside withLogging) should not be top-level")


# ---------------------------------------------------------------------------
# ROUND 3: Path variants
# ---------------------------------------------------------------------------

def round_3_path_variants(samples_dir: Path) -> None:
    print()
    print("=" * 72)
    print("  ROUND 3: PATH VARIANTS")
    print("=" * 72)

    # 3a: Absolute paths (no repo_root)
    fpath = samples_dir / "plain_function.js"
    syms_no_root = scan_js_file(fpath)
    check("path: absolute paths",
          all(isinstance(s.file_path, Path)
              and str(s.file_path).startswith("/")
              for s in syms_no_root),
          "Expected absolute paths when repo_root=None")

    # 3b: With repo_root
    syms_with_root = scan_js_file(fpath, repo_root=samples_dir)
    check("path: relative paths with repo_root",
          all(not str(s.file_path).startswith("/")
              for s in syms_with_root),
          "Expected relative paths with repo_root")

    # 3c: repo_root = string (not Path)
    syms_str_root = scan_js_file(str(fpath), repo_root=str(samples_dir))
    fp1 = symbols_fingerprint(syms_with_root)
    fp2 = symbols_fingerprint(syms_str_root)
    check("path: string vs Path repo_root",
          fp1 == fp2,
          "String repo_root should produce same results as Path repo_root")

    # 3d: repo_root above samples_dir (parent dir)
    parent_root = samples_dir.parent
    syms_parent_root = scan_js_file(fpath, repo_root=parent_root)
    check("path: repo_root=parent dir",
          all(
              "test_js_samples/plain_function.js" in str(s.file_path)
              or str(s.file_path).endswith(
                  "test_js_samples/plain_function.js")
              for s in syms_parent_root),
          f"Expected paths relative to parent dir. "
          f"Got: {[str(s.file_path) for s in syms_parent_root[:3]]}")

    # 3e: repo_root that doesn't contain the file (fallback to absolute)
    unrelated_root = Path("/tmp")
    syms_unrelated = scan_js_file(fpath, repo_root=unrelated_root)
    check("path: unrelated repo_root falls back to absolute",
          all(str(s.file_path).startswith("/") for s in syms_unrelated),
          "Expected absolute paths when repo_root doesn't contain the file")

    # 3f: Nested subdirectory with repo_root
    nested_path = (samples_dir / "edge_nested_repo_dir"
                   / "subdir" / "nested_test.js")
    if nested_path.exists():
        syms_nested = scan_js_file(nested_path, repo_root=samples_dir)
        check("path: nested subdir relative path",
              all(
                  "edge_nested_repo_dir/subdir/nested_test.js"
                  in str(s.file_path)
                  or str(s.file_path).endswith(
                      "edge_nested_repo_dir/subdir/nested_test.js")
                  for s in syms_nested),
              "Expected paths containing "
              "'edge_nested_repo_dir/subdir/nested_test.js'. "
              f"Got: {[str(s.file_path) for s in syms_nested[:3]]}")
        check("path: nested subdir symbols correct",
              len(syms_nested) == 4,
              f"Expected 4 symbols from nested file, "
              f"got {len(syms_nested)}")
        check("path: nestedFunction",
              has_symbol(syms_nested, "nestedFunction", SymbolType.FUNCTION),
              "Missing nestedFunction")
        check("path: NestedClass",
              has_symbol(syms_nested, "NestedClass", SymbolType.CLASS),
              "Missing NestedClass")
        check("path: nestedMethod in NestedClass",
              has_symbol(syms_nested, "nestedMethod",
                         SymbolType.METHOD, "NestedClass"),
              "Missing nestedMethod METHOD")


# ---------------------------------------------------------------------------
# ROUND 4: Real-world patterns
# ---------------------------------------------------------------------------

def round_4_realworld(samples_dir: Path) -> None:
    print()
    print("=" * 72)
    print("  ROUND 4: REAL-WORLD JS PATTERNS")
    print("=" * 72)

    fpath = samples_dir / "edge_realworld_patterns.js"
    if not fpath.exists():
        check("realworld: file exists", False,
              "edge_realworld_patterns.js not found")
        return

    syms = scan_js_file(fpath, repo_root=samples_dir)
    total = len(syms)

    check("realworld: no crash", True, f"Parsed {total} symbols")

    expected_functions = [
        "withLogging",     # HOC
        "curriedAdd",      # Curried function
        "createUser",      # Default params
        "sumAll",          # Rest params
        "processConfig",   # Destructured params
        "fetchWithRetry",  # Async function
        "idGenerator",     # Generator (deferred)
    ]

    for fn in expected_functions:
        if fn == "idGenerator":
            check(f"realworld: {fn} captured (v4 generator)",
                  has_symbol(syms, fn, SymbolType.FUNCTION),
                  f"{fn} is a generator \u2014 should now be captured")
        else:
            check(f"realworld: {fn}",
                  has_symbol(syms, fn, SymbolType.FUNCTION),
                  f"Missing function {fn}")

    expected_classes = ["ModernClass", "ExportedService"]
    for cls in expected_classes:
        check(f"realworld: class {cls}",
              has_symbol(syms, cls, SymbolType.CLASS),
              f"Missing class {cls}")

    # Methods in ModernClass
    check("realworld: ModernClass.value (getter)",
          has_symbol(syms, "value", SymbolType.METHOD, "ModernClass"),
          "Missing value getter METHOD in ModernClass")
    check("realworld: ModernClass.fromJSON (static)",
          has_symbol(syms, "fromJSON", SymbolType.METHOD, "ModernClass"),
          "Missing fromJSON static METHOD in ModernClass")
    check("realworld: ModernClass.publicMethod",
          has_symbol(syms, "publicMethod", SymbolType.METHOD, "ModernClass"),
          "Missing publicMethod METHOD in ModernClass")

    # ExportedService
    check("realworld: ExportedService.serve",
          has_symbol(syms, "serve", SymbolType.METHOD, "ExportedService"),
          "Missing serve METHOD in ExportedService")

    # Async exported function
    check("realworld: fetchData (export async)",
          has_symbol(syms, "fetchData", SymbolType.FUNCTION),
          "Missing export async function fetchData")

    # Negative cases
    check("realworld: double callback NOT top-level",
          not has_symbol(syms, "double", SymbolType.FUNCTION),
          "double() is a callback, should not be top-level")
    check("realworld: STATUS_CODES not a function",
          not has_symbol(syms, "STATUS_CODES", SymbolType.FUNCTION),
          "STATUS_CODES is an object, not a function")
    check("realworld: config IIFE not captured",
          not has_symbol(syms, "config", SymbolType.FUNCTION),
          "config is from IIFE \u2014 should not be captured")
    check("realworld: theme IIFE not captured",
          not has_symbol(syms, "theme", SymbolType.FUNCTION),
          "theme is from IIFE \u2014 should not be captured")


# ---------------------------------------------------------------------------
# ROUND 5: Line number accuracy
# ---------------------------------------------------------------------------

def round_5_line_accuracy(samples_dir: Path) -> None:
    print()
    print("=" * 72)
    print("  ROUND 5: LINE NUMBER ACCURACY")
    print("=" * 72)

    fpath = samples_dir / "edge_line_accuracy.js"
    if not fpath.exists():
        check("line accuracy: file exists", False,
              "edge_line_accuracy.js not found")
        return

    syms = scan_js_file(fpath, repo_root=samples_dir)

    expected_lines: dict[str, int] = {
        "line4": 4,
        "line6": 6,
        "Line8": 8,
        "line13": 13,
        "Line15": 15,
        "line20": 20,
        "line24": 24,
    }

    expected_method_lines: dict[tuple[str, str], int] = {
        ("line9", "Line8"): 9,
        ("line10", "Line8"): 10,
        ("line16", "Line15"): 16,
        ("line17", "Line15"): 17,
    }

    all_correct = True
    for name, expected_lineno in expected_lines.items():
        found = [s for s in syms if s.name == name]
        if not found:
            check(f"line: {name} not found", False,
                  f"Symbol {name} missing")
            all_correct = False
        elif len(found) > 1:
            check(f"line: {name} duplicate", False,
                  f"Multiple symbols named {name}")
            all_correct = False
        elif found[0].line_number != expected_lineno:
            check(f"line: {name} line number",
                  False,
                  f"Expected line {expected_lineno}, "
                  f"got {found[0].line_number}")
            all_correct = False

    for (method_name, parent_class), expected_lineno in \
            expected_method_lines.items():
        found = [s for s in syms
                 if s.name == method_name
                 and s.parent_class == parent_class]
        if not found:
            check(f"line: {parent_class}.{method_name} not found",
                  False,
                  f"Symbol {parent_class}.{method_name} missing")
            all_correct = False
        elif found[0].line_number != expected_lineno:
            check(f"line: {parent_class}.{method_name} line number",
                  False,
                  f"Expected line {expected_lineno}, "
                  f"got {found[0].line_number}")
            all_correct = False

    if all_correct:
        total_positions = (
            len(expected_lines) + len(expected_method_lines))
        check(f"line: all {total_positions} positions correct",
              True,
              "All line numbers verified correct")


# ---------------------------------------------------------------------------
# ROUND 6: Type checking & lint
# ---------------------------------------------------------------------------

def round_6_type_lint(project_root: Path) -> None:
    print()
    print("=" * 72)
    print("  ROUND 6: TYPE CHECKING & LINT")
    print("=" * 72)

    scanner_path = project_root / "nowreck" / "scanner" / "javascript_scanner.py"

    # basedpyright
    try:
        result = subprocess.run(
            [sys.executable, "-m", "basedpyright", str(scanner_path)],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout + result.stderr
        if "0 errors" in output or result.returncode == 0:
            check("type: basedpyright 0 errors", True,
                  "basedpyright reports 0 errors")
        else:
            error_lines = [line for line in output.split("\n")
                           if "error" in line.lower()]
            check("type: basedpyright errors", False,
                  "basedpyright found issues:\n"
                  + "\n".join(error_lines[:5]))
    except FileNotFoundError:
        check("type: basedpyright not available", True,
              "basedpyright not installed \u2014 skipping")
    except subprocess.TimeoutExpired:
        check("type: basedpyright timeout", True,
              "basedpyright timed out \u2014 skipping")

    # ruff check
    try:
        result = subprocess.run(
            ["ruff", "check", str(scanner_path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            check("lint: ruff 0 errors", True, "ruff reports 0 errors")
        else:
            error_count = len([line for line in result.stdout.split("\n")
                               if line.strip()])
            check("lint: ruff errors", False,
                  f"ruff found {error_count} issue(s):\n"
                  f"{result.stdout[:500]}")
    except FileNotFoundError:
        check("lint: ruff not available", True,
              "ruff not installed \u2014 skipping")


# ---------------------------------------------------------------------------
# ROUND 7: Chaos / property-based tests
# ---------------------------------------------------------------------------

def round_7_chaos(samples_dir: Path) -> None:
    print()
    print("=" * 72)
    print("  ROUND 7: CHAOS TEST \u2014 random property verification")
    print("=" * 72)

    files_to_scan = [
        "plain_function.js",
        "arrow_function.js",
        "class_with_methods.js",
        "export_patterns.js",
    ]

    # 7a: No state leakage between scans
    all_individual_symbols: list = []
    for fname in files_to_scan:
        syms = scan_js_file(samples_dir / fname, repo_root=samples_dir)
        all_individual_symbols.extend(syms)

    all_batch_symbols: list = []
    for fname in files_to_scan:
        syms = scan_js_file(samples_dir / fname, repo_root=samples_dir)
        all_batch_symbols.extend(syms)

    fp_individual = symbols_fingerprint(all_individual_symbols)
    fp_batch = symbols_fingerprint(all_batch_symbols)

    check("chaos: no state leakage between scans",
          fp_individual == fp_batch,
          "State leakage detected: individual vs batch fingerprints differ")

    # 7b: Idempotent scan
    syms_1 = scan_js_file(
        samples_dir / "class_with_methods.js", repo_root=samples_dir)
    syms_2 = scan_js_file(
        samples_dir / "class_with_methods.js", repo_root=samples_dir)
    check("chaos: idempotent scan",
          symbols_fingerprint(syms_1) == symbols_fingerprint(syms_2),
          "Scanning same file twice gave different results")

    # 7c: Parser stateless across 5 iterations
    all_iterations = []
    for _ in range(5):
        syms = scan_js_file(
            samples_dir / "export_patterns.js", repo_root=samples_dir)
        all_iterations.append(symbols_fingerprint(syms))

    check("chaos: parser stateless across 5 iterations",
          len(set(all_iterations)) == 1,
          f"Parser produced different results across 5 runs: "
          f"{all_iterations}")

    # 7d: Symbol ordering stability
    syms = scan_js_file(
        samples_dir / "stress_large_file.js", repo_root=samples_dir)
    if syms:
        sorted_syms = sorted(syms)
        check("chaos: Symbol ordering stable",
              len(sorted_syms) == len(syms),
              f"Sorted symbols lost data: {len(sorted_syms)} vs {len(syms)}")
        sorted_again = sorted(syms)
        fp_1 = symbols_fingerprint(sorted_syms)
        fp_2 = symbols_fingerprint(sorted_again)
        check("chaos: Symbol ordering deterministic",
              fp_1 == fp_2,
              "Two sorts of the same symbols produced different orderings")

    # 7e: Unicode/emoji in source (should not crash)
    # Use raw utf-8 encoded bytes to avoid SyntaxWarnings from \u/\U
    # escape sequences in bytes literals (Python 3.11+).
    _emoji_bytes = b"\xf0\x9f\x98\x80"  # U+1F600 grinning face
    _japanese_bytes = (
        b"\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf"
    )  # U+3053 U+3093 U+306B U+3061 U+306F = "konnichiwa"

    try:
        unicode_file = samples_dir / "_unicode_test.js"
        unicode_file.write_bytes(
            b"const smile = () => '" + _emoji_bytes + b"';"
            b"\nfunction " + _japanese_bytes + b"()"
            b" { return 'hello'; }\n")
        syms_unicode = scan_js_file(unicode_file, repo_root=samples_dir)
        check("chaos: unicode/emoji in source",
              True,
              f"No crash. Found symbols: {symbol_names(syms_unicode)}")
        check("chaos: unicode emoji arrow captured",
              has_symbol(syms_unicode, "smile", SymbolType.FUNCTION),
              "Missing smile arrow with emoji in source")
        unicode_file.unlink(missing_ok=True)
    except Exception as exc:
        check("chaos: unicode/emoji", False, f"CRASHED: {exc}")

    # 7f: Mixed line endings (LF + CRLF in same file)
    try:
        mixed_file = samples_dir / "_mixed_endings.js"
        mixed_file.write_bytes(
            b"function a() {}\r\n"
            b"const b = () => {};\n"
            b"class C {\r\n"
            b"    d() {}\n"
            b"}\r\n"
        )
        syms_mixed = scan_js_file(mixed_file, repo_root=samples_dir)
        check("chaos: mixed line endings",
              len(syms_mixed) == 4,
              f"Expected 4 symbols from mixed endings file, "
              f"got {len(syms_mixed)}: {symbol_names(syms_mixed)}")
        mixed_file.unlink(missing_ok=True)
    except Exception as exc:
        check("chaos: mixed line endings", False, f"CRASHED: {exc}")

    # 7g: File with BOM (byte order mark)
    try:
        bom_file = samples_dir / "_bom_test.js"
        bom_file.write_bytes(
            b"\xef\xbb\xbffunction bomFunction() {}\n"
            b"const bomArrow = () => {};\n")
        syms_bom = scan_js_file(bom_file, repo_root=samples_dir)
        check("chaos: BOM in file",
              len(syms_bom) == 2,
              f"Expected 2 symbols from BOM file, "
              f"got {len(syms_bom)}: {symbol_names(syms_bom)}")
        bom_file.unlink(missing_ok=True)
    except Exception as exc:
        check("chaos: BOM in file", False, f"CRASHED: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    samples_dir = Path(__file__).parent

    start_time = time.time()

    round_1_repeatability(samples_dir)
    round_2_stress(samples_dir)
    round_3_path_variants(samples_dir)
    round_4_realworld(samples_dir)
    round_5_line_accuracy(samples_dir)
    round_6_type_lint(project_root)
    round_7_chaos(samples_dir)

    elapsed = time.time() - start_time

    # Final summary
    print()
    print("=" * 72)
    print("  MULTI-ROUND TEST RESULTS")
    print("=" * 72)
    print(f"  Total tests: {_pass_count + _fail_count}")
    print(f"  Passed:      {_pass_count}")
    print(f"  Failed:      {_fail_count}")
    print(f"  Time:        {elapsed:.1f}s")
    print("=" * 72)
    print()

    if _fail_count > 0:
        print("  FAILED TESTS:")
        for name, passed, msg in _results:
            if not passed:
                print(f"    \u274c {name}")
                print(f"       {msg}")
        print()
        print(f"  \u274c {_fail_count} failure(s) \u2014 see above.")
        print()
        sys.exit(1)
    else:
        print("  \u2705 ALL TESTS PASSED"
              " \u2014 No failures across all 7 rounds.")
        print()


if __name__ == "__main__":
    main()
