#!/usr/bin/env python3
"""Multi-round repeatability, stress, and chaos test for the TSX scanner."""

import os
import random
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.typescript_scanner import (  # noqa: E402
    scan_ts_calls,
    scan_ts_file,
)

test_dir = Path(__file__).resolve().parent

pass_count = 0
fail_count = 0


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

TSX_FILES = [
    test_dir / "edge_tsx_components.tsx",
    test_dir / "edge_tsx_handlers.tsx",
    test_dir / "edge_tsx_exports.tsx",
    test_dir / "edge_tsx_anon_default.tsx",
    test_dir / "edge_tsx_mixed.tsx",
]


def all_symbol_tuples(files: list[Path]) -> set[tuple]:
    """Collect every symbol across *files* as comparable tuples."""
    result: set[tuple] = set()
    for f in files:
        for s in scan_ts_file(f):
            result.add(
                (
                    s.name,
                    s.symbol_type.name,
                    str(s.file_path),
                    s.line_number,
                    s.parent_class,
                )
            )
    return result


# =========================================================================
# ROUND 1: REPEATABILITY — 3 runs, must produce identical results
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 1: REPEATABILITY — 3 runs, must produce identical results")
print(SECTION)

results: list[frozenset[tuple]] = []
for run in range(3):
    results.append(frozenset(all_symbol_tuples(TSX_FILES)))

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
    for f in TSX_FILES:
        for fp, caller, called in scan_ts_calls(f):
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
known_calls = {
    ("handleClick", "trackEvent"),
    ("submit", "sendForm"),
    ("toggle", "flipState"),
    ("Dashboard", "useUser"),
    ("useUser", "fetchUser"),
}
for caller, called in known_calls:
    found = any(c[1] == caller and c[2] == called for c in call_results[0])
    check(f"known call {caller} -> {called} present", found)


# =========================================================================
# ROUND 3: STRESS TEST — large TSX file, many components
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 3: STRESS TEST — large TSX file, many components")
print(SECTION)

large_lines: list[str] = []
for i in range(300):
    large_lines.append(
        f"function Comp{i:04d}({{ name }}: {{ name: string }}): JSX.Element {{\n"
        f"    return <div>{{name}}</div>;\n"
        f"}}\n"
    )
    large_lines.append(f"const Hook{i:04d} = (): JSX.Element => <span>{i}</span>;\n")
    if i % 10 == 0:
        large_lines.append(
            f"class Cls{i:04d} extends React.Component {{\n"
            f"    render(): JSX.Element {{\n"
            f'        return <Comp{i:04d} name="x" />;\n'
            f"    }}\n"
            f"}}\n"
        )

with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
    f.write("".join(large_lines))
    fname = f.name

symbols = scan_ts_file(fname)
check(f"Stress TSX parsed — {len(symbols)} symbols found", len(symbols) > 0)
# Expected: 300 funcs + 300 arrows + 30 classes + 30 renders = 660
total_expected = 300 + 300 + 30 + 30
check(
    f"Stress TSX has expected ~{total_expected} symbols",
    total_expected - 10 <= len(symbols) <= total_expected + 10,
)
os.unlink(fname)


# =========================================================================
# ROUND 4: PATH VARIANTS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 4: PATH VARIANTS")
print(SECTION)

path_str = str(test_dir / "edge_tsx_components.tsx")
path_posix = test_dir / "edge_tsx_components.tsx"
sym_str = scan_ts_file(path_str)
sym_posix = scan_ts_file(path_posix)
check("str path works", len(sym_str) > 0)
check("PosixPath works", len(sym_posix) > 0)
str_names = {s.name for s in sym_str}
posix_names = {s.name for s in sym_posix}
check("str == PosixPath results", str_names == posix_names)


# =========================================================================
# ROUND 5: REAL-WORLD TSX PATTERNS
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 5: REAL-WORLD TSX PATTERNS")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
    f.write("""\
// Common real-world React patterns
import React from "react";

interface ButtonProps {
    label: string;
    onClick: () => void;
}

export function Button({ label, onClick }: ButtonProps): JSX.Element {
    const handlePress = () => {
        analytics.track("button_press", { label });
    };
    return <button onClick={handlePress}>{label}</button>;
}

export const Spinner = (): JSX.Element => (
    <div className="spinner" aria-label="loading" />
);

export default function App(): JSX.Element {
    return (
        <main>
            <Button label="Save" onClick={saveData} />
            <Spinner />
        </main>
    );
}

// Class component with lifecycle + handler methods
export class Counter extends React.Component {
    private count: number = 0;

    increment(): void {
        this.count += 1;
    }

    render(): JSX.Element {
        return <button onClick={() => this.increment()}>Count</button>;
    }
}
""")
    fname = f.name

symbols = scan_ts_file(fname)
sym_names = {s.name for s in symbols}
check("Button (function component) captured", "Button" in sym_names)
check("Spinner (arrow component) captured", "Spinner" in sym_names)
check("App (default function component) captured", "App" in sym_names)
check("Counter (class component) captured", "Counter" in sym_names)
check("increment (method) captured", "increment" in sym_names)
check("render (method) captured", "render" in sym_names)
check("ButtonProps interface captured", "ButtonProps" in sym_names)
os.unlink(fname)


# =========================================================================
# ROUND 6: LINE NUMBER ACCURACY in TSX
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 6: LINE NUMBER ACCURACY in TSX")
print(SECTION)

with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
    f.write("\n\n\n")  # 3 blank lines
    f.write("function OnLine4(): JSX.Element {\n")  # line 4
    f.write("    return <div/>;\n")  # line 5
    f.write("}\n")  # line 6
    f.write("\n")  # line 7 (blank)
    f.write("const OnLine8 = (): JSX.Element => <p/>;\n")  # line 8
    f.write("\n")  # line 9 (blank)
    f.write("class OnLine10 {\n")  # line 10
    f.write("  renderOnLine11(): JSX.Element {\n")  # line 11
    f.write("    return <span/>;\n")  # line 12
    f.write("  }\n")  # line 13
    f.write("}\n")  # line 14
    fname = f.name

symbols = scan_ts_file(fname)
for s in symbols:
    if s.name == "OnLine4":
        check("OnLine4 is on line 4", s.line_number == 4)
    elif s.name == "OnLine8":
        check("OnLine8 is on line 8", s.line_number == 8)
    elif s.name == "OnLine10":
        check("OnLine10 is on line 10", s.line_number == 10)
    elif s.name == "renderOnLine11":
        check("renderOnLine11 is on line 11", s.line_number == 11)
os.unlink(fname)


# =========================================================================
# ROUND 7: CHAOS TEST — random property verification
# =========================================================================
print(f"\n{SECTION}")
print("  ROUND 7: CHAOS TEST — random property verification")
print(SECTION)

all_syms: list[tuple] = []
for f in TSX_FILES:
    for s in scan_ts_file(f):
        all_syms.append((s.name, s.symbol_type, s.line_number, s.parent_class))

if all_syms:
    sample = random.sample(all_syms, min(10, len(all_syms)))
    for sym_name, sym_type, line, parent in sample:
        msg = (
            f"Random symbol: {sym_type.name} {sym_name} (line {line}, parent={parent})"
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
    "ALL TESTS PASSED — No failures across all 7 rounds."
    if fail_count == 0
    else "SOME TESTS FAILED!"
)
print(f"\n  {'✅' if fail_count == 0 else '❌'} {result_text}")
print()

if __name__ == "__main__":
    if fail_count > 0:
        sys.exit(1)
