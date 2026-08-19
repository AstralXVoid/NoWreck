#!/usr/bin/env python3
"""Type-level sample suite for Go scanner.

Formal assertions for interface / struct / type alias collection across
the dedicated samples.  Every line number was hand-verified against the source.

Mirrors test_ts_samples/test_phase1_types.py structure.
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.go_scanner import scan_go_file  # noqa: E402

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


def symbols_by_name(path: Path) -> dict[str, list]:
    """Return symbol names grouped by name for easy assertion."""
    result: dict[str, list] = {}
    for s in scan_go_file(path):
        result.setdefault(s.name, []).append(s)
    return result


def check_symbol(
    syms: dict[str, list],
    name: str,
    expected_type: str,
    expected_line: int,
) -> None:
    """Assert a symbol exists with the right type and line number."""
    found = syms.get(name, [])
    check(f"{name} captured", len(found) == 1, f"count={len(found)}")
    if found:
        check(
            f"{name} is type {expected_type}",
            found[0].symbol_type.name == expected_type,
            f"actual={found[0].symbol_type.name}",
        )
        check(
            f"{name} line {expected_line}",
            found[0].line_number == expected_line,
            f"actual={found[0].line_number}",
        )


# =========================================================================
# SECTION 1: Basic type-level declarations (edge_basic.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 1: Basic type-level declarations (edge_basic.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_basic.go")

check_symbol(syms, "Shape", "INTERFACE", 30)
check_symbol(syms, "UserID", "TYPE_ALIAS", 34)

# Positive control: functions and structs
check_symbol(syms, "greet", "FUNCTION", 5)
check_symbol(syms, "User", "CLASS", 13)

# Methods
check_symbol(syms, "Display", "METHOD", 22)
check_symbol(syms, "UpdateAge", "METHOD", 26)


# =========================================================================
# SECTION 2: Interface patterns (edge_interfaces.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 2: Interface patterns (edge_interfaces.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_interfaces.go")

check_symbol(syms, "Reader", "INTERFACE", 5)
check_symbol(syms, "Writer", "INTERFACE", 9)
check_symbol(syms, "ReadWriter", "INTERFACE", 14)
check_symbol(syms, "Any", "INTERFACE", 35)
check_symbol(syms, "Stringer", "INTERFACE", 38)
check_symbol(syms, "Logger", "INTERFACE", 43)

# Structs implementing interfaces
check_symbol(syms, "Buffer", "CLASS", 20)
check_symbol(syms, "ConsoleLogger", "CLASS", 47)
check_symbol(syms, "FileLogger", "CLASS", 53)

# Methods
check_symbol(syms, "Read", "METHOD", 24)
check_symbol(syms, "Write", "METHOD", 29)
# Log appears on both ConsoleLogger and FileLogger — check both exist
log_methods = syms.get("Log", [])
check("Log captured on multiple structs", len(log_methods) == 2)
log_parents = {m.parent_class for m in log_methods}
check("Log parent_classes include ConsoleLogger", "ConsoleLogger" in log_parents)
check("Log parent_classes include FileLogger", "FileLogger" in log_parents)


# =========================================================================
# SECTION 3: Struct patterns (edge_structs.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 3: Struct patterns (edge_structs.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_structs.go")

check_symbol(syms, "Base", "CLASS", 5)
check_symbol(syms, "Extended", "CLASS", 10)
check_symbol(syms, "Address", "CLASS", 20)
check_symbol(syms, "Person", "CLASS", 25)
check_symbol(syms, "Config", "CLASS", 35)
check_symbol(syms, "Handler", "CLASS", 45)

# Methods
check_symbol(syms, "FullName", "METHOD", 15)
check_symbol(syms, "Location", "METHOD", 30)
check_symbol(syms, "Process", "METHOD", 49)

# Constructor function
check_symbol(syms, "DefaultConfig", "FUNCTION", 40)


# =========================================================================
# SECTION 4: Export patterns (edge_export.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 4: Export patterns (edge_export.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_export.go")

# Exported
check_symbol(syms, "ExportedFunc", "FUNCTION", 7)
check_symbol(syms, "ExportedStruct", "CLASS", 17)
check_symbol(syms, "ExportedInterface", "INTERFACE", 27)
check_symbol(syms, "Status", "TYPE_ALIAS", 37)

# Unexported (still captured)
check_symbol(syms, "unexportedFunc", "FUNCTION", 12)
check_symbol(syms, "unexportedStruct", "CLASS", 22)
check_symbol(syms, "unexportedInterface", "INTERFACE", 32)
check_symbol(syms, "internalID", "TYPE_ALIAS", 45)


# =========================================================================
# SECTION 5: Method receiver patterns (edge_methods.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 5: Method receiver patterns (edge_methods.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_methods.go")

check_symbol(syms, "Counter", "CLASS", 5)
check_symbol(syms, "Calculator", "CLASS", 28)
check_symbol(syms, "MyInt", "TYPE_ALIAS", 49)

# Value receiver methods
check_symbol(syms, "Value", "METHOD", 10)
check_symbol(syms, "Increment", "METHOD", 15)
check_symbol(syms, "String", "METHOD", 23)

# Reset appears on both Counter and Calculator — check both exist
reset_methods = syms.get("Reset", [])
check("Reset captured on multiple structs", len(reset_methods) == 2)
reset_parents = {m.parent_class for m in reset_methods}
check("Reset parent_classes include Counter", "Counter" in reset_parents)
check("Reset parent_classes include Calculator", "Calculator" in reset_parents)

# Calculator methods
check_symbol(syms, "Add", "METHOD", 32)
check_symbol(syms, "Subtract", "METHOD", 36)
check_symbol(syms, "Result", "METHOD", 40)

# Type alias method
check_symbol(syms, "IsPositive", "METHOD", 51)

# Verify parent_class
value_methods = syms.get("Value", [])
if value_methods:
    check(
        "Value parent_class is Counter",
        value_methods[0].parent_class == "Counter",
        f"actual={value_methods[0].parent_class}",
    )


# =========================================================================
# SECTION 6: Goroutine and concurrency patterns (edge_goroutines.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 6: Goroutine and concurrency patterns (edge_goroutines.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_goroutines.go")

check_symbol(syms, "runAsync", "FUNCTION", 8)
check_symbol(syms, "createChannel", "FUNCTION", 16)
check_symbol(syms, "selectOnChannels", "FUNCTION", 28)
check_symbol(syms, "Pipeline", "CLASS", 40)
check_symbol(syms, "Run", "METHOD", 47)
check_symbol(syms, "Processor", "INTERFACE", 55)
check_symbol(syms, "MessageChan", "TYPE_ALIAS", 60)

# Anonymous goroutine NOT captured
check("anonymous goroutine NOT captured as symbol",
      not any(s.name == "func" for s in scan_go_file(test_dir / "edge_goroutines.go")))


# =========================================================================
# SECTION 7: Real-world patterns (edge_realworld.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 7: Real-world patterns (edge_realworld.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_realworld.go")

check_symbol(syms, "ValidationError", "CLASS", 12)
check_symbol(syms, "Error", "METHOD", 17)
check_symbol(syms, "handleUser", "FUNCTION", 22)
check_symbol(syms, "Server", "CLASS", 27)
check_symbol(syms, "ServeHTTP", "METHOD", 31)
check_symbol(syms, "LoggingMiddleware", "FUNCTION", 36)
check_symbol(syms, "loadConfig", "FUNCTION", 43)
check_symbol(syms, "FetchWithContext", "FUNCTION", 51)
check_symbol(syms, "handleError", "FUNCTION", 61)
check_symbol(syms, "Config", "CLASS", 70)
check_symbol(syms, "Handler", "INTERFACE", 75)


# =========================================================================
# SECTION 8: Negatives — members and constants NOT captured
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 8: Negatives — members and constants NOT captured")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_negatives.go")

# Interface method signatures are NOT captured
check("interface method 'Find' NOT captured", "Find" not in syms)
check("interface method 'Save' NOT captured", "Save" not in syms)
check("interface method 'Delete' NOT captured", "Delete" not in syms)

# Struct fields are NOT captured
check("struct field 'Title' NOT captured", "Title" not in syms)
check("struct field 'Content' NOT captured", "Content" not in syms)
check("struct field 'Views' NOT captured", "Views" not in syms)

# Constants are NOT captured
check("const 'MaxRetries' NOT captured", "MaxRetries" not in syms)
check("const 'Timeout' NOT captured", "Timeout" not in syms)

# Variables are NOT captured
check("var 'globalConfig' NOT captured", "globalConfig" not in syms)

# Nested function inside func body is NOT captured
check("nested helper NOT captured", "helper" not in syms)

# But top-level items ARE captured
check("top-level 'Repository' captured", "Repository" in syms)
check("top-level 'Article' captured", "Article" in syms)
check("method 'Summary' captured", "Summary" in syms)
check("top-level 'outer' captured", "outer" in syms)
check("type alias 'MyString' captured", "MyString" in syms)
check("method 'Upper' captured", "Upper" in syms)


# =========================================================================
# SECTION 9: Method parent_class accuracy
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 9: Method parent_class accuracy")
print(SECTION_SEP)

# edge_basic.go
syms = symbols_by_name(test_dir / "edge_basic.go")
display_methods = syms.get("Display", [])
check("User::Display parent_class is User",
      any(m.parent_class == "User" for m in display_methods),
      f"actual={[m.parent_class for m in display_methods]}")

update_methods = syms.get("UpdateAge", [])
check("User::UpdateAge parent_class is User",
      any(m.parent_class == "User" for m in update_methods),
      f"actual={[m.parent_class for m in update_methods]}")

# edge_interfaces.go: multiple structs with same method name
syms = symbols_by_name(test_dir / "edge_interfaces.go")
log_methods = syms.get("Log", [])
check("Logger methods: ConsoleLogger::Log and FileLogger::Log both captured",
      len(log_methods) == 2,
      f"count={len(log_methods)}")
if log_methods:
    parents = {m.parent_class for m in log_methods}
    check("Log parent_classes include ConsoleLogger",
          "ConsoleLogger" in parents,
          f"actual={parents}")
    check("Log parent_classes include FileLogger",
          "FileLogger" in parents,
          f"actual={parents}")


# =========================================================================
# SECTION 10: Type alias as method receiver (edge_methods.go)
# =========================================================================
print(f"\n{SECTION_SEP}")
print("  SECTION 10: Type alias as method receiver (edge_methods.go)")
print(SECTION_SEP)

syms = symbols_by_name(test_dir / "edge_methods.go")

# MyInt type alias with method
check_symbol(syms, "MyInt", "TYPE_ALIAS", 49)
is_pos = syms.get("IsPositive", [])
if is_pos:
    check(
        "IsPositive parent_class is MyInt",
        is_pos[0].parent_class == "MyInt",
        f"actual={is_pos[0].parent_class}",
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
