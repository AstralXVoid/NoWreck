#!/usr/bin/env python3
"""Phase 1 demo: parse hand-written .js files and display Symbol output."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from nowreck.scanner.javascript_scanner import scan_js_file  # noqa: E402


def main() -> None:
    samples_dir = Path(__file__).parent

    js_files = sorted(samples_dir.glob("*.js"))

    print("=" * 72)
    print("  NoWreck v3 \u2014 Phase 1: JavaScript Scanner Demo")
    print("=" * 72)
    print()

    for js_file in js_files:
        print(f"  File: {js_file.name}")
        print("-" * 72)
        try:
            symbols = scan_js_file(js_file, repo_root=samples_dir)
            if symbols:
                print(f"  Found {len(symbols)} symbol(s):")
                print()
                for sym in symbols:
                    parent_part = (
                        f"  parent_class={sym.parent_class!r}"
                        if sym.parent_class else ""
                    )
                    extra = f", {parent_part}" if parent_part else ""
                    parts = (
                        f"name={sym.name!r},"
                        f" type={sym.symbol_type.name},"
                        f" file={sym.file_path!s},"
                        f" line={sym.line_number}"
                    )
                    print(f"    Symbol({parts}{extra})")
            else:
                print("  (no symbols found)")
        except Exception as exc:
            print(f"  ERROR: {exc}")
        print()
        print()

    print("=" * 72)
    print("  Demo complete.")
    print("=" * 72)


if __name__ == "__main__":
    main()
