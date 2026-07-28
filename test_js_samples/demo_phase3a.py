#!/usr/bin/env python3
"""
Phase 3a demo: mixed Python + JavaScript repository scan.

Creates a temporary directory with .py and .js files, runs the
RepositoryScanner on it, then builds a unified SymbolIndex and
demonstrates queries across both languages.
"""

import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _make_mixed_repo() -> Path:
    """Create a temporary repo with both Python and JS files."""
    tmp = Path(tempfile.mkdtemp(prefix="nowreck_demo_"))

    # Python files
    (tmp / "greeter.py").write_text(
        "def greet(name: str) -> str:\n"
        '    return f"Hello, {name}!"\n'
        "\n"
        "class Person:\n"
        "    def __init__(self, name: str) -> None:\n"
        "        self.name = name\n"
        "\n"
        "    def speak(self) -> str:\n"
        '        return f"{self.name} says hi!"\n',
    )

    # JavaScript files
    (tmp / "app.js").write_text(
        "function greet() {\n"
        '  return "Hello from JS!";\n'
        "}\n"
        "\n"
        "const helper = () => {\n"
        "  return 42;\n"
        "};\n",
    )
    (tmp / "widget.js").write_text(
        "class Widget {\n"
        "  constructor(name) {\n"
        "    this.name = name;\n"
        "  }\n"
        "\n"
        "  render() {\n"
        '    return `<div>${this.name}</div>`;\n'
        "  }\n"
        "\n"
        "  destroy() {\n"
        '    console.log("destroyed");\n'
        "  }\n"
        "}\n",
    )

    return tmp


def main() -> int:
    from nowreck.scanner.repository_scanner import RepositoryScanner
    from nowreck.scanner.symbol_index import (
        SymbolIndex,
        build_symbol_index,
    )

    repo = _make_mixed_repo()
    print(f"Repository: {repo}")
    print()

    # ── Scan the mixed repo ──────────────────────────────────────
    scanner = RepositoryScanner(repo)
    result = scanner.scan()

    print(f"Python files found: {len(result.modules)}")
    for path in sorted(result.modules):
        print(f"  {path}")
    print(f"JS files found:     {len(result.js_files)}")
    for path in sorted(result.js_files):
        print(f"  {path}")
    print(f"Failed files:       {result.failure_count}")
    print(f"Total success:      {result.success_count}")
    print()

    # ── Build unified SymbolIndex ─────────────────────────────────
    idx: SymbolIndex = build_symbol_index(result)

    print(f"Unified SymbolIndex has {len(idx.all_symbols)} symbols")
    print()

    # ── Query by type ─────────────────────────────────────────────
    print("All functions:")
    for sym in sorted(idx.functions, key=lambda s: (s.file_path, s.line_number)):
        print(f"  {sym.name:12s}  ({sym.file_path}:{sym.line_number})")

    print()
    print("All classes:")
    for sym in sorted(idx.classes, key=lambda s: (s.file_path, s.line_number)):
        print(f"  {sym.name:12s}  ({sym.file_path}:{sym.line_number})")

    print()
    print("All methods:")
    for sym in sorted(idx.methods, key=lambda s: (s.file_path, s.line_number)):
        parent = f"  ← {sym.parent_class}"
        print(f"  {sym.name:12s}  ({sym.file_path}:{sym.line_number}){parent}")

    # ── Cross-language name lookup ─────────────────────────────────
    print()
    print("Name lookup for 'greet':")
    for sym in idx.by_name("greet"):
        lang = "Python" if sym.file_path.suffix == ".py" else "JavaScript"
        print(f"  {sym.name:12s}  ({lang}, {sym.file_path}:{sym.line_number})")

    # ── Cleanup ───────────────────────────────────────────────────
    import shutil

    shutil.rmtree(repo)

    return 0


if __name__ == "__main__":
    sys.exit(main())
