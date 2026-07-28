#!/usr/bin/env python3
"""
Phase 2 demo: JS scanner output \u2192 SymbolIndex.

Scans the Phase 1 JS test files, builds a unified SymbolIndex,
and demonstrates querying it.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.javascript_scanner import scan_js_file  # noqa: E402
from nowreck.scanner.symbol_index import (  # noqa: E402
    build_symbol_index_from_symbols,
)

samples = Path(__file__).parent


def demo_index_from_js_scan() -> None:
    """Scan a single JS file and build its SymbolIndex."""
    print("=" * 72)
    print("  Phase 2 Demo: JS Scanner \u2192 SymbolIndex")
    print("=" * 72)

    # --- 1. Scan each test file separately ---
    all_symbols: list = []

    for fname in [
        "plain_function.js",
        "arrow_function.js",
        "class_with_methods.js",
        "export_patterns.js",
    ]:
        syms = scan_js_file(samples / fname, repo_root=samples)
        all_symbols.extend(syms)
        print(f"\n  {fname}: {len(syms)} symbols")

    print(f"\n  Total combined: {len(all_symbols)} symbols")
    print()

    # --- 2. Build a unified SymbolIndex ---
    idx = build_symbol_index_from_symbols(all_symbols)

    print(f"  Index contains {len(idx.symbols)} unique name groups")
    print()

    # --- 3. Query by type ---
    print(f"  Functions:  {len(idx.functions)}")
    for s in idx.functions:
        parent = f" (in {s.parent_class})" if s.parent_class else ""
        line = f"    {s.name:25s} {s.file_path!s:35s} line={s.line_number}{parent}"
        print(line)

    print(f"\n  Classes:    {len(idx.classes)}")
    for s in idx.classes:
        line = f"    {s.name:25s} {s.file_path!s:35s} line={s.line_number}"
        print(line)

    print(f"\n  Methods:    {len(idx.methods)}")
    for s in idx.methods:
        line = (
            f"    {s.name:25s} {s.file_path!s:35s}"
            f" line={s.line_number:3d}  parent={s.parent_class}"
        )
        print(line)

    # --- 4. Query by name ---
    print("\n  --- by_name('getEmail') ---")
    for s in idx.by_name("getEmail"):
        print(f"    {s.name}  {s.symbol_type.name}  "
              f"{s.file_path}  line={s.line_number}")

    print("\n  --- by_name('constructor') (3 classes have one) ---")
    for s in idx.by_name("constructor"):
        print(f"    {s.name}  {s.symbol_type.name}  {s.file_path}  "
              f"line={s.line_number:3d}  parent={s.parent_class}")

    # --- 5. All symbols (deduplicated + sorted) ---
    count = len(idx.all_symbols)
    print(f"\n  all_symbols (deduplicated): {count}")
    print()


def build_from_js_via_python_path() -> None:
    """Demonstrate both pathways produce interchangeable SymbolIndex objects."""
    import ast

    from nowreck.scanner.repository_scanner import ScanResult  # noqa: F811
    from nowreck.scanner.symbol_index import build_symbol_index  # noqa: F811

    source = "def greet(): pass\n"
    module = ast.parse(source)
    scan_result = ScanResult(modules={Path("hello.py"): module})
    py_idx = build_symbol_index(scan_result)

    # Build equivalent index via the JS path (from_symbols)
    js_idx = build_symbol_index_from_symbols(
        [s for s in py_idx.all_symbols]
    )

    print(f"  Python path:  {py_idx.by_name('greet')[0].name}")
    print(f"  JS path:      {js_idx.by_name('greet')[0].name}")
    print(f"  Interchangeable: {py_idx.symbols == js_idx.symbols}")
    print()


if __name__ == "__main__":
    demo_index_from_js_scan()
    build_from_js_via_python_path()
