#!/usr/bin/env python3
"""Milestone 1 demo — runs the full pipeline on 3 hand-constructed test repos.

Usage::

    python test_milestone1/demo_milestone1.py

Shows:
    - Repository scan results (file count, success/failure)
    - Symbol index contents (functions, classes, methods by type)
    - Change detection (scanning empty → full repo)
    - Determinism proof (3x runs, identical output)
"""

from __future__ import annotations

from pathlib import Path

from nowreck.detector.change_detector import (
    ChangeType,
    DetectedChange,
    detect_changes,
)
from nowreck.scanner.repository_scanner import RepositoryScanner, ScanResult
from nowreck.scanner.symbol_index import (
    SymbolIndex,
    build_symbol_index,
)

REPOS = Path(__file__).resolve().parent / "repos"
HEADER = "=" * 72
SUB = "-" * 72


def _scan_and_index(repo_path: Path) -> tuple[ScanResult, SymbolIndex]:
    scanner = RepositoryScanner(repo_path)
    scan_result = scanner.scan()
    sym_index = build_symbol_index(scan_result)
    return scan_result, sym_index


def _changes_between(
    pre_path: Path | None,
    post_path: Path | None,
) -> list[DetectedChange]:
    if pre_path is not None:
        pre_scan, pre_sym = _scan_and_index(pre_path)
    else:
        pre_scan, pre_sym = ScanResult(), SymbolIndex()
    if post_path is not None:
        post_scan, post_sym = _scan_and_index(post_path)
    else:
        post_scan, post_sym = ScanResult(), SymbolIndex()
    return detect_changes(pre_scan, post_scan, pre_sym, post_sym)


def _show_scan_result(_name: str, scan: ScanResult, sym: SymbolIndex) -> None:
    print(f"\n  Scan:      {scan.success_count} files OK, {scan.failure_count} failed")
    if scan.modules:
        print(f"  .py files: {', '.join(str(p) for p in scan.modules)}")
    if scan.js_files:
        print(f"  .js files: {', '.join(str(p) for p in scan.js_files)}")
    if scan.ts_files:
        print(f"  TS files:  {', '.join(str(p) for p in scan.ts_files)}")
    print(f"  Functions: {len(sym.functions)}")
    print(f"  Classes:   {len(sym.classes)}")
    print(f"  Methods:   {len(sym.methods)}")
    print(f"  Total:     {len(sym.all_symbols)}")


def _show_changes(changes: list[DetectedChange]) -> None:
    if not changes:
        print("  (none)")
        return
    for c in changes:
        desc = c.change_type.name
        loc = str(c.file_path)
        print(f"  {desc:20s}  {loc}")


def main() -> None:
    print(HEADER)
    print("  MILESTONE 1 CHECKPOINT — FULL PIPELINE DEMO")
    print(HEADER)

    repos = [
        ("Pure Python", REPOS / "pure-python" / "src"),
        ("Pure JavaScript", REPOS / "pure-js" / "src"),
        ("Pure TypeScript", REPOS / "pure-ts" / "src"),
        ("Pure TSX", REPOS / "pure-tsx" / "src"),
        ("Mixed Python + JS", REPOS / "mixed"),
    ]

    for name, path in repos:
        print(f"\n{SUB}")
        print(f"  REPO: {name}  ({path})")
        print(SUB)

        # 1. Scan
        scan, sym = _scan_and_index(path)
        _show_scan_result(name, scan, sym)

        # 2. Change detection: empty → full repo
        print("\n  Changes (empty → full repo):")
        changes = _changes_between(None, path)
        _show_changes(changes)

        # 3. Determinism: run 3 times
        print("\n  Determinism (3 runs):")
        syms = [build_symbol_index(RepositoryScanner(path).scan()) for _ in range(3)]
        if syms[0].symbols == syms[1].symbols == syms[2].symbols:
            print("  ✅ Identical across all 3 runs")
        else:
            print("  ❌ MISMATCH!")

        # 4. No-change when identical
        print("\n  No-change (identical pre == post):")
        no_changes = detect_changes(scan, scan, sym, sym)
        if no_changes == []:
            print("  ✅ Correctly empty")
        else:
            print(f"  ❌ Expected 0 changes, got {len(no_changes)}")

        # 5. Calls
        empty_scan = ScanResult()
        empty_sym = SymbolIndex()
        call_changes = detect_changes(empty_scan, scan, empty_sym, sym)
        calls = [c for c in call_changes if c.change_type is ChangeType.CALL_DETECTED]
        print(f"\n  Call detection: {len(calls)} calls")
        for c in calls[:5]:
            print(f"    {c.caller_name} → {c.called_name}  ({c.file_path})")
        if len(calls) > 5:
            print(f"    ... and {len(calls) - 5} more")

    # Final summary
    print(f"\n{SUB}")
    print("  PIPELINE HEALTH CHECK")
    print(SUB)
    all_ok = True
    for name, path in repos:
        scan, sym = _scan_and_index(path)
        ch1 = _changes_between(None, path)
        ch2 = _changes_between(path, None)
        no_ch = detect_changes(scan, scan, sym, sym)
        ok = (
            scan.success_count > 0
            and len(ch1) > 0
            and len(ch2) > 0
            and no_ch == []
        )
        status = "✅" if ok else "❌"
        no_change_status = "ok" if no_ch == [] else "FAIL"
        print(f"  {status} {name:20s}  scan={scan.success_count}"
              f"  add={len(ch1)}  del={len(ch2)}  no-change={no_change_status}")
        if not ok:
            all_ok = False

    print(f"\n{SUB}")
    if all_ok:
        print("  ✅ MILESTONE 1 PASSED — All repositories scanned deterministically")
    else:
        print("  ❌ MILESTONE 1 FAILED — See errors above")
    print(SUB)


if __name__ == "__main__":
    main()
