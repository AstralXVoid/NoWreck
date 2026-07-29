#!/usr/bin/env python3
"""Phase 1 comprehensive bug & error test battery.

Covers:
  - Core positive detection (the 4 existing test files)
  - Edge cases (empty, comments-only, syntax errors, unicode, etc.)
  - Negative cases (things that should NOT be captured)
  - Error handling (non-existent file, non-JS file)
  - CRLF line endings
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.javascript_scanner import scan_js_file  # noqa: E402
from nowreck.scanner.symbol_index import SymbolType  # noqa: E402

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

TestResult = tuple[str, bool, str]  # (file_name, passed, message)

pass_count = 0
fail_count = 0
results: list[TestResult] = []


def check(test_name: str, passed: bool, message: str) -> None:
    global pass_count, fail_count
    if passed:
        pass_count += 1
    else:
        fail_count += 1
    results.append((test_name, passed, message))


def has_symbol(symbols, name: str, sym_type: SymbolType,
               parent_class: str | None = None) -> bool:
    """Check if a symbol exists with the given properties."""
    for sym in symbols:
        if (sym.name == name
                and sym.symbol_type == sym_type
                and sym.parent_class == parent_class):
            return True
    return False


def count_by_type(symbols, sym_type: SymbolType) -> int:
    return sum(1 for sym in symbols if sym.symbol_type == sym_type)


def symbol_names(symbols) -> list[str]:
    return sorted(sym.name for sym in symbols)


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

def test_file(file_path: str | Path, repo_root: str | Path | None = None) -> list:
    """Helper to run scan_js_file and return symbols."""
    return scan_js_file(file_path, repo_root)


def run_tests() -> None:
    samples_dir = Path(__file__).parent

    # ======================================================================
    # 1. Core positive detection (regression \u2014 existing test files)
    # ======================================================================
    print("=" * 72)
    print("  SECTION 1: Core positive detection (regression)")
    print("=" * 72)

    # --- plain_function.js ---
    syms = test_file(samples_dir / "plain_function.js", repo_root=samples_dir)
    check("plain_function: count",
          len(syms) == 3,
          f"Expected 3 symbols, got {len(syms)}: {symbol_names(syms)}")
    check("plain_function: greet",
          has_symbol(syms, "greet", SymbolType.FUNCTION),
          "Missing greet FUNCTION")
    check("plain_function: calculateTotal",
          has_symbol(syms, "calculateTotal", SymbolType.FUNCTION),
          "Missing calculateTotal FUNCTION")
    check("plain_function: getTimestamp",
          has_symbol(syms, "getTimestamp", SymbolType.FUNCTION),
          "Missing getTimestamp FUNCTION")

    # --- arrow_function.js ---
    syms = test_file(samples_dir / "arrow_function.js", repo_root=samples_dir)
    check("arrow_function: count",
          len(syms) == 5,
          f"Expected 5 symbols (arrow fns only), got {len(syms)}: "
          f"{symbol_names(syms)}")
    for name in ("greet", "double", "square", "counter", "oldStyle"):
        check(f"arrow_function: {name}",
              has_symbol(syms, name, SymbolType.FUNCTION),
              f"Missing arrow FUNCTION {name}")
    check("arrow_function: regularFuncExpr excluded",
          not has_symbol(syms, "regularFunc", SymbolType.FUNCTION),
          "regularFunc is NOT an arrow function \u2014 should not be captured")

    # --- class_with_methods.js ---
    syms = test_file(samples_dir / "class_with_methods.js", repo_root=samples_dir)
    check("class_methods: count",
          len(syms) == 12,
          f"Expected 12 symbols, got {len(syms)}: {symbol_names(syms)}")
    # Classes
    check("class_methods: UserService class",
          has_symbol(syms, "UserService", SymbolType.CLASS),
          "Missing UserService CLASS")
    check("class_methods: ApiClient class",
          has_symbol(syms, "ApiClient", SymbolType.CLASS),
          "Missing ApiClient CLASS")
    check("class_methods: EmptyClass class",
          has_symbol(syms, "EmptyClass", SymbolType.CLASS),
          "Missing EmptyClass CLASS")
    # Methods with parent_class
    check("class_methods: constructor(UserService)",
          has_symbol(syms, "constructor", SymbolType.METHOD, "UserService"),
          "Missing constructor METHOD in UserService")
    check("class_methods: getName(UserService)",
          has_symbol(syms, "getName", SymbolType.METHOD, "UserService"),
          "Missing getName METHOD in UserService")
    check("class_methods: getEmail(UserService)",
          has_symbol(syms, "getEmail", SymbolType.METHOD, "UserService"),
          "Missing getEmail METHOD in UserService")
    check("class_methods: validate(UserService)",
          has_symbol(syms, "validate", SymbolType.METHOD, "UserService"),
          "Missing validate METHOD in UserService")
    check("class_methods: fetch(ApiClient)",
          has_symbol(syms, "fetch", SymbolType.METHOD, "ApiClient"),
          "Missing fetch METHOD in ApiClient")
    check("class_methods: get(ApiClient)",
          has_symbol(syms, "get", SymbolType.METHOD, "ApiClient"),
          "Missing get METHOD in ApiClient")
    check("class_methods: post(ApiClient)",
          has_symbol(syms, "post", SymbolType.METHOD, "ApiClient"),
          "Missing post METHOD in ApiClient")
    check("class_methods: helper top-level function",
          has_symbol(syms, "helper", SymbolType.FUNCTION),
          "Missing helper top-level FUNCTION")

    # --- export_patterns.js ---
    syms = test_file(samples_dir / "export_patterns.js", repo_root=samples_dir)
    check("export_patterns: count",
          len(syms) == 8,
          f"Expected 8 symbols, got {len(syms)}: {symbol_names(syms)}")
    check("export_patterns: formatDate",
          has_symbol(syms, "formatDate", SymbolType.FUNCTION),
          "Missing export function formatDate")
    check("export_patterns: Logger class",
          has_symbol(syms, "Logger", SymbolType.CLASS),
          "Missing export class Logger")
    check("export_patterns: Logger.log method",
          has_symbol(syms, "log", SymbolType.METHOD, "Logger"),
          "Missing log METHOD in Logger")
    check("export_patterns: Logger.warn method",
          has_symbol(syms, "warn", SymbolType.METHOD, "Logger"),
          "Missing warn METHOD in Logger")
    check("export_patterns: parseJson arrow",
          has_symbol(syms, "parseJson", SymbolType.FUNCTION),
          "Missing export const parseJson arrow")
    check("export_patterns: identity arrow",
          has_symbol(syms, "identity", SymbolType.FUNCTION),
          "Missing export const identity arrow")
    check("export_patterns: legacyMode arrow",
          has_symbol(syms, "legacyMode", SymbolType.FUNCTION),
          "Missing export var legacyMode arrow")
    # Negative: anonymous default export should NOT be captured
    defaults = [s for s in syms
                if s.name == "" or s.name is None or s.name == "default"]
    check("export_patterns: no anonymous default",
          len(defaults) == 0,
          "Anonymous default export should not produce a symbol")

    # ======================================================================
    # 2. Edge cases
    # ======================================================================
    print()
    print("=" * 72)
    print("  SECTION 2: Edge cases")
    print("=" * 72)

    # --- edge_empty.js ---
    syms = test_file(samples_dir / "edge_empty.js", repo_root=samples_dir)
    check("edge_empty: no symbols",
          len(syms) == 0,
          f"Expected 0 symbols for empty file, got {len(syms)}")

    # --- edge_only_comments.js ---
    syms = test_file(samples_dir / "edge_only_comments.js", repo_root=samples_dir)
    check("edge_only_comments: no symbols",
          len(syms) == 0,
          f"Expected 0 symbols for comments-only file, got {len(syms)}")

    # --- edge_only_imports.js ---
    syms = test_file(samples_dir / "edge_only_imports.js", repo_root=samples_dir)
    check("edge_only_imports: no symbols",
          len(syms) == 0,
          f"Expected 0 symbols for imports-only file, got {len(syms)}")

    # --- edge_syntax_errors.js ---
    try:
        syms = test_file(
            samples_dir / "edge_syntax_errors.js", repo_root=samples_dir)
        check("edge_syntax_errors: no crash",
              True,
              f"No crash. Got {len(syms)} symbol(s): {symbol_names(syms)}")
    except Exception as exc:
        check("edge_syntax_errors: crash",
              False,
              f"CRASHED: {exc}")

    # --- edge_nested.js ---
    syms = test_file(samples_dir / "edge_nested.js", repo_root=samples_dir)
    check("edge_nested: count",
          len(syms) == 4,
          f"Expected 4 symbols (3 top-level + 1 method), got {len(syms)}: "
          f"{symbol_names(syms)}")
    check("edge_nested: topLevel",
          has_symbol(syms, "topLevel", SymbolType.FUNCTION),
          "Missing topLevel FUNCTION")
    check("edge_nested: OuterClass",
          has_symbol(syms, "OuterClass", SymbolType.CLASS),
          "Missing OuterClass CLASS")
    check("edge_nested: OuterClass.method",
          has_symbol(syms, "method", SymbolType.METHOD, "OuterClass"),
          "Missing method METHOD in OuterClass")
    check("edge_nested: outerArrow",
          has_symbol(syms, "outerArrow", SymbolType.FUNCTION),
          "Missing outerArrow FUNCTION")
    # Negative: nested functions should NOT be captured
    check("edge_nested: nested excluded",
          not has_symbol(syms, "nested", SymbolType.FUNCTION),
          "nested() inside topLevel should not be captured")
    check("edge_nested: deeplyNested excluded",
          not has_symbol(syms, "deeplyNested", SymbolType.FUNCTION),
          "deeplyNested() should not be captured")
    check("edge_nested: InnerClass excluded",
          not has_symbol(syms, "InnerClass", SymbolType.CLASS),
          "InnerClass inside function should not be captured")
    check("edge_nested: innerArrow excluded",
          not has_symbol(syms, "innerArrow", SymbolType.FUNCTION),
          "innerArrow inside function should not be captured")

    # --- edge_async_generators.js ---
    syms = test_file(
        samples_dir / "edge_async_generators.js", repo_root=samples_dir)
    check("edge_async: fetchData",
          has_symbol(syms, "fetchData", SymbolType.FUNCTION),
          "Missing async function fetchData")
    check("edge_async: processAsync",
          has_symbol(syms, "processAsync", SymbolType.FUNCTION),
          "Missing async arrow processAsync")
    # Generators are captured (v4 scope — Gap 2)
    check("edge_async: generator generateIds captured",
          has_symbol(syms, "generateIds", SymbolType.FUNCTION),
          "Missing generator function generateIds")
    check("edge_async: async generator streamResults captured",
          has_symbol(syms, "streamResults", SymbolType.FUNCTION),
          "Missing async generator function streamResults")
    check("edge_async: generator expression makeRange captured",
          has_symbol(syms, "makeRange", SymbolType.FUNCTION),
          "Missing generator expression makeRange")

    # --- edge_generators.js (dedicated generator test file) ---
    syms = test_file(
        samples_dir / "edge_generators.js", repo_root=samples_dir)
    check("edge_generators: no crash",
          True,
          f"No crash. Got {len(syms)} symbol(s)")
    # Positive: generators should be captured
    check("edge_generators: idGenerator",
          has_symbol(syms, "idGenerator", SymbolType.FUNCTION),
          "Missing generator function idGenerator")
    check("edge_generators: streamGenerator",
          has_symbol(syms, "streamGenerator", SymbolType.FUNCTION),
          "Missing async generator function streamGenerator")
    check("edge_generators: counter (gen expr const)",
          has_symbol(syms, "counter", SymbolType.FUNCTION),
          "Missing generator expression counter")
    check("edge_generators: range (gen expr let)",
          has_symbol(syms, "range", SymbolType.FUNCTION),
          "Missing generator expression range")
    check("edge_generators: sequence (gen expr var)",
          has_symbol(syms, "sequence", SymbolType.FUNCTION),
          "Missing generator expression sequence")
    check("edge_generators: exportedGenerator",
          has_symbol(syms, "exportedGenerator", SymbolType.FUNCTION),
          "Missing exported generator function exportedGenerator")
    check("edge_generators: exportedDefaultGen (default export)",
          has_symbol(syms, "exportedDefaultGen", SymbolType.FUNCTION),
          "Missing default-exported generator function exportedDefaultGen")
    # Positive controls: regular functions still work
    check("edge_generators: normalFunction (control)",
          has_symbol(syms, "normalFunction", SymbolType.FUNCTION),
          "Missing normal function (positive control)")
    check("edge_generators: normalArrow (control)",
          has_symbol(syms, "normalArrow", SymbolType.FUNCTION),
          "Missing normal arrow (positive control)")
    # Negative control: non-generator function expression should NOT be captured
    check("edge_generators: notAGenerator excluded (negative control)",
          not has_symbol(syms, "notAGenerator", SymbolType.FUNCTION),
          "notAGenerator is a function expression, not arrow — should not be captured")

    # --- edge_getters_setters.js ---
    syms = test_file(
        samples_dir / "edge_getters_setters.js", repo_root=samples_dir)
    check("edge_gs: FullFeatured class",
          has_symbol(syms, "FullFeatured", SymbolType.CLASS),
          "Missing FullFeatured CLASS")
    for method in ("constructor", "regularMethod"):
        check(f"edge_gs: FullFeatured.{method}",
              has_symbol(syms, method, SymbolType.METHOD, "FullFeatured"),
              f"Missing {method} METHOD in FullFeatured")
    # Class expression assigned to const - should NOT be captured as FUNCTION
    check("edge_gs: MyClassExpr class expression excluded",
          not has_symbol(syms, "MyClassExpr", SymbolType.FUNCTION),
          "MyClassExpr is a class expression, not an arrow")

    # --- edge_iife.js (v4 Gap 3: explicit IIFE exclusion) ---
    syms = test_file(
        samples_dir / "edge_iife.js", repo_root=samples_dir)
    check("edge_iife: no crash",
          True,
          f"No crash. Got {len(syms)} symbol(s)")
    # IIFEs should NOT be captured
    check("edge_iife: config IIFE excluded",
          not has_symbol(syms, "config", SymbolType.FUNCTION),
          "config is an IIFE — should not be captured")
    check("edge_iife: theme IIFE excluded",
          not has_symbol(syms, "theme", SymbolType.FUNCTION),
          "theme is an arrow IIFE — should not be captured")
    check("edge_iife: legacyConfig IIFE excluded",
          not has_symbol(syms, "legacyConfig", SymbolType.FUNCTION),
          "legacyConfig is a var IIFE — should not be captured")
    # Positive controls: regular functions MUST still be captured
    check("edge_iife: normalArrow captured (control)",
          has_symbol(syms, "normalArrow", SymbolType.FUNCTION),
          "normalArrow is a regular arrow — should be captured")
    check("edge_iife: normalFunction captured (control)",
          has_symbol(syms, "normalFunction", SymbolType.FUNCTION),
          "normalFunction is a regular function — should be captured")
    check("edge_iife: container captured (control)",
          has_symbol(syms, "container", SymbolType.FUNCTION),
          "container is a regular function — should be captured")

    # --- edge_naming.js ---
    syms = test_file(samples_dir / "edge_naming.js", repo_root=samples_dir)
    check("edge_naming: \u03c0Squared",
          has_symbol(syms, "\u03c0Squared", SymbolType.FUNCTION),
          "Missing \u03c0Squared arrow (unicode)")
    check("edge_naming: \u03c0 not a function (value, not arrow)",
          not has_symbol(syms, "\u03c0", SymbolType.FUNCTION),
          "\u03c0 is a value (Math.PI), not an arrow")
    check("edge_naming: long name",
          has_symbol(
              syms,
              "thisIsAnExtremelyLongFunctionNameThatNobodyWouldActuallyUseInPractice",  # noqa: E501
              SymbolType.FUNCTION),
          "Missing long name arrow")
    check("edge_naming: _privateHelper",
          has_symbol(syms, "_privateHelper", SymbolType.FUNCTION),
          "Missing _privateHelper")
    check("edge_naming: $getValue",
          has_symbol(syms, "$getValue", SymbolType.FUNCTION),
          "Missing $getValue")
    check("edge_naming: Function (same name as built-in)",
          has_symbol(syms, "Function", SymbolType.FUNCTION),
          "Missing Function (same name as built-in)")
    check("edge_naming: Symbol (same name as built-in)",
          has_symbol(syms, "Symbol", SymbolType.FUNCTION),
          "Missing Symbol (same name as built-in)")
    # Duplicate names: both 'process' should be present
    process_count = sum(
        1 for s in syms
        if s.name == "process" and s.symbol_type == SymbolType.FUNCTION)
    check("edge_naming: duplicate process() entries",
          process_count == 2,
          f"Expected 2 'process' FUNCTION entries, got {process_count}")

    # --- edge_single_line.js ---
    syms = test_file(samples_dir / "edge_single_line.js", repo_root=samples_dir)
    check("edge_single_line: count",
          len(syms) == 4,
          f"Expected 4 symbols (a, b, C, d), got {len(syms)}: "
          f"{symbol_names(syms)}")
    for name in ("a", "b"):
        check(f"edge_single_line: function {name}",
              has_symbol(syms, name, SymbolType.FUNCTION),
              f"Missing {name} FUNCTION")
    check("edge_single_line: class C",
          has_symbol(syms, "C", SymbolType.CLASS),
          "Missing C CLASS")
    check("edge_single_line: arrow d",
          has_symbol(syms, "d", SymbolType.FUNCTION),
          "Missing d arrow FUNCTION")

    # --- edge_windows_crlf.js ---
    syms = test_file(
        samples_dir / "edge_windows_crlf.js", repo_root=samples_dir)
    check("edge_crlf: windowsStyle fn",
          has_symbol(syms, "windowsStyle", SymbolType.FUNCTION),
          "Missing windowsStyle FUNCTION")
    check("edge_crlf: WinClass class",
          has_symbol(syms, "WinClass", SymbolType.CLASS),
          "Missing WinClass CLASS")
    check("edge_crlf: WinClass.winMethod",
          has_symbol(syms, "winMethod", SymbolType.METHOD, "WinClass"),
          "Missing winMethod METHOD in WinClass")
    check("edge_crlf: winArrow",
          has_symbol(syms, "winArrow", SymbolType.FUNCTION),
          "Missing winArrow export FUNCTION")

    # ======================================================================
    # 3. Negative cases (things that should NOT be captured)
    # ======================================================================
    print()
    print("=" * 72)
    print("  SECTION 3: Negative cases")
    print("=" * 72)

    syms = test_file(
        samples_dir / "edge_negative_cases.js", repo_root=samples_dir)
    check("negative: no false positives",
          len(syms) == 0,
          f"Expected 0 symbols (no false positives), got {len(syms)}: "
          f"{symbol_names(syms)}")

    # ======================================================================
    # 4. Error handling
    # ======================================================================
    print()
    print("=" * 72)
    print("  SECTION 4: Error handling")
    print("=" * 72)

    # --- Non-existent file ---
    nonexistent = samples_dir / "this_file_does_not_exist.js"
    try:
        test_file(nonexistent)
        check("error: non-existent file",
              False,
              "Expected FileNotFoundError, got no exception")
    except FileNotFoundError:
        check("error: non-existent file",
              True,
              "Correctly raised FileNotFoundError")
    except Exception as exc:
        check("error: non-existent file",
              False,
              f"Expected FileNotFoundError, got {type(exc).__name__}: {exc}")

    # --- Non-JS file (Python file) ---
    py_file = project_root / "nowreck" / "scanner" / "javascript_scanner.py"
    try:
        syms = test_file(py_file, repo_root=project_root)
        check("error: non-JS file (Python)",
              True,
              f"No crash. Got {len(syms)} 'symbols' from a Python file: "
              f"{symbol_names(syms) if syms else 'none'}")
    except Exception as exc:
        check("error: non-JS file (Python)",
              False,
              f"CRASHED: {type(exc).__name__}: {exc}")

    # --- Non-JS file (binary) ---
    binary_test = samples_dir / "_binary_test.bin"
    binary_test.write_bytes(b"\x00\x01\x02\x03\x04")
    try:
        syms = test_file(binary_test, repo_root=samples_dir)
        check("error: binary file",
              True,
              f"No crash. Got {len(syms)} symbols from binary file")
    except Exception as exc:
        check("error: binary file",
              False,
              f"CRASHED: {type(exc).__name__}: {exc}")
    finally:
        binary_test.unlink(missing_ok=True)

    # --- export_default.js: verify named default exports are captured ---
    syms = test_file(
        samples_dir / "edge_export_default.js", repo_root=samples_dir)
    check("export_default: no crash",
          True,
          f"No crash. Got {len(syms)} symbol(s): {symbol_names(syms)}")
    # Regular named exports (always worked)
    check("export_default: namedFn",
          has_symbol(syms, "namedFn", SymbolType.FUNCTION),
          "Missing namedFn FUNCTION (regular named export)")
    check("export_default: NamedClass",
          has_symbol(syms, "NamedClass", SymbolType.CLASS),
          "Missing NamedClass CLASS (regular named export)")
    check("export_default: NamedClass.doThing",
          has_symbol(syms, "doThing", SymbolType.METHOD, "NamedClass"),
          "Missing doThing METHOD in NamedClass")
    # Named default exports (also work — tree-sitter provides `declaration` field)
    check("export_default: explicitDefault (default function)",
          has_symbol(syms, "explicitDefault", SymbolType.FUNCTION),
          "Missing explicitDefault FUNCTION (export default function)")
    check("export_default: Bar (default class)",
          has_symbol(syms, "Bar", SymbolType.CLASS),
          "Missing Bar CLASS (export default class)")
    check("export_default: Bar.barMethod (default class method)",
          has_symbol(syms, "barMethod", SymbolType.METHOD, "Bar"),
          "Missing barMethod METHOD in Bar")
    # Anonymous default exports (correctly NOT captured — no name)
    defaults = [s for s in syms
                if s.name == "" or s.name is None or s.name == "default"]
    check("export_default: no anonymous default symbols",
          len(defaults) == 0,
          f"Anonymous default exports should not produce symbols; got {defaults}")

    # ======================================================================
    # Summary
    # ======================================================================
    print()
    print("=" * 72)
    print(f"  RESULTS: {pass_count} passed, {fail_count} failed, "
          f"{pass_count + fail_count} total")
    print("=" * 72)
    print()

    if fail_count > 0:
        print("  FAILED TESTS:")
        for name, passed, msg in results:
            if not passed:
                print(f"    \u274c {name}")
                print(f"       {msg}")
        print()
        sys.exit(1)
    else:
        print("  \u2705 All tests passed!")
        print()


if __name__ == "__main__":
    run_tests()
