#!/usr/bin/env python3
"""Phase 4a demo — end-to-end verification pipeline with mixed Python/JS repos.

Usage::

    python test_milestone1/demo_phase4a.py

This demo proves that the full Nowreck pipeline (scanner → symbol index →
change detector → claim verifier → terminal reporter) works correctly with
a repository containing both Python and JavaScript files.

It creates a **pre** state (no files) and a **post** state (the mixed
Python + JS milestone repo), detects all structural changes, then verifies
hand-written claims covering all 7 claim types across both languages.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import DetectedChange, detect_changes
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.scanner.repository_scanner import RepositoryScanner, ScanResult
from nowreck.scanner.symbol_index import SymbolIndex, build_symbol_index
from nowreck.verifier.verifier import ClaimVerifier, VerificationReport

MIXED_REPO = Path(__file__).resolve().parent / "repos" / "mixed"

HEADER = "=" * 72
SUB = "-" * 72


def main() -> None:
    print(HEADER)
    print("  PHASE 4a — END-TO-END PIPELINE DEMO (Mixed Python + JS)")
    print(HEADER)

    # ------------------------------------------------------------------
    # 1. Setup: copy milestone repo to a temp directory
    # ------------------------------------------------------------------
    print(f"\n  Repo: {MIXED_REPO}")
    tmp_dir = Path(tempfile.mkdtemp(prefix="nowreck_phase4a_"))
    _copy_repo(MIXED_REPO, tmp_dir)
    print(f"  Copied to: {tmp_dir}")

    # ------------------------------------------------------------------
    # 2. Scan pre state (empty) and post state (full repo)
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 1 — SCAN")
    print(SUB)

    pre_scan = ScanResult()
    pre_sym = SymbolIndex()
    print("  Pre state:  empty (0 files)")

    post_scan, post_sym = _scan(tmp_dir)
    print(f"  Post state: {post_scan.success_count} files OK, {post_scan.failure_count} failed")
    print(f"    Python: {', '.join(str(p) for p in post_scan.modules)}")
    print(f"    JS:     {', '.join(str(p) for p in post_scan.js_files)}")
    print(f"    Symbols: {len(post_sym.functions)} functions,"
          f" {len(post_sym.classes)} classes,"
          f" {len(post_sym.methods)} methods")

    # ------------------------------------------------------------------
    # 3. Detect changes (empty → full repo)
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 2 — CHANGE DETECTION")
    print(SUB)

    detected = detect_changes(pre_scan, post_scan, pre_sym, post_sym)
    _print_changes(detected)

    # ------------------------------------------------------------------
    # 4. Hand-written claims (mixed Python + JS)
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 3 — HAND-WRITTEN CLAIMS")
    print(SUB)

    claims = _build_claims()
    for c in claims:
        desc = _describe_claim(c)
        print(f"  {desc}")

    # ------------------------------------------------------------------
    # 5. Verify claims against detected changes
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 4 — VERIFICATION")
    print(SUB)

    report = ClaimVerifier.verify(claims, detected)
    _print_verdict_counts(report)

    # ------------------------------------------------------------------
    # 6. Render terminal report (coloured output)
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 5 — TERMINAL REPORT")
    print(SUB)

    reporter = TerminalReporter(colour=True)
    output = reporter.report(report)
    print(f"\n{output}")

    # ------------------------------------------------------------------
    # 7. JSON report (for CI tools)
    # ------------------------------------------------------------------
    print("  JSON report snippet:")
    json_out = TerminalReporter.report_json(report)
    # Show first 30 lines
    for line in json_out.splitlines()[:30]:
        print(f"  {line}")
    print("  ...")
    print(f"\n  Total JSON length: {len(json_out)} chars")

    # ------------------------------------------------------------------
    # 8. Cleanup
    # ------------------------------------------------------------------
    shutil.rmtree(tmp_dir)
    print(f"\n{SUB}")
    _print_final_verdict(report)
    print(SUB)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copy_repo(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, dst / item.name)


def _scan(path: Path) -> tuple[ScanResult, SymbolIndex]:
    scanner = RepositoryScanner(path)
    scan_result = scanner.scan()
    sym_index = build_symbol_index(scan_result)
    return scan_result, sym_index


def _print_changes(changes: list[DetectedChange]) -> None:
    if not changes:
        print("  (none)")
        return
    # Group by type
    by_type: dict[str, list[DetectedChange]] = {}
    for c in changes:
        by_type.setdefault(c.change_type.name, []).append(c)

    for type_name in sorted(by_type):
        items = by_type[type_name]
        print(f"  {type_name}: {len(items)}")
        for c in items[:3]:  # show first 3
            parts = [str(c.file_path)]
            if c.symbol_name:
                parts.append(c.symbol_name)
            if c.caller_name and c.called_name:
                parts.append(f"  {c.caller_name} → {c.called_name}")
            separator = " — "
            print(f"    {separator.join(parts)}")
        if len(items) > 3:
            print(f"    ... and {len(items) - 3} more")


def _build_claims() -> list[Claim]:
    """Craft claims that exercise all 7 claim types across Python and JS.

    Claim ordering is important: CONTRADICTED claims must come BEFORE
    CONFIRMED claims that reference the same symbol.  This is because the
    verifier consumes matched ``DetectedChange`` objects, and the opposite-
    type check skips already-consumed changes.

    For example, ``REMOVE_FUNCTION load_config`` (CONTRADICTED) must come
    before ``ADD_FUNCTION load_config`` (CONFIRMED) so the opposite-type
    match can find the ``ADD_FUNCTION`` change.
    """

    return [
        # ── CONTRADICTED: opposite-type matches ──
        # REMOVE_FUNCTION for a symbol that was actually ADDED.
        # Must come before ADD_FUNCTION load_config so the opposite-type
        # check can find the ADD_FUNCTION change.
        Claim(
            type=ClaimType.REMOVE_FUNCTION,
            symbol_name="load_config",
            file_path="main.py",
            confidence=0.80,
        ),
        # CALLS_FUNCTION that doesn't exist (caller exists, call doesn't)
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="validateEmail",
            file_path="utils.js",
            caller_name="validateEmail",
            called_name="sendNotification",
            confidence=0.70,
        ),

        # ── CONFIRMED: Python symbols ──
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="validate_email",
            file_path="utils.py",
            confidence=0.95,
        ),
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="load_config",
            file_path="main.py",
            confidence=0.90,
        ),
        Claim(
            type=ClaimType.ADD_CLASS,
            symbol_name="Logger",
            file_path="utils.py",
            confidence=1.0,
        ),
        Claim(
            type=ClaimType.FILE_CREATED,
            file_path="main.py",
            confidence=1.0,
        ),

        # ── CONFIRMED: JS symbols ──
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="validateEmail",
            file_path="utils.js",
            confidence=0.95,
        ),
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="pad",
            file_path="utils.js",
            confidence=0.90,
        ),
        Claim(
            type=ClaimType.ADD_CLASS,
            symbol_name="UiHandler",
            file_path="ui_handler.js",
            confidence=0.98,
        ),
        Claim(
            type=ClaimType.FILE_CREATED,
            file_path="utils.js",
            confidence=1.0,
        ),

        # ── CONFIRMED: CALLS_FUNCTION ──
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="load_config",
            file_path="main.py",
            caller_name="load_config",
            called_name="print",
            confidence=0.85,
        ),
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="formatDate",
            file_path="utils.js",
            caller_name="formatDate",
            called_name="pad",
            confidence=0.85,
        ),

        # ── UNVERIFIABLE: symbols that don't exist ──
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="nonExistentFunction",
            file_path="utils.py",
            confidence=0.90,
        ),
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="ghostFunction",
            file_path="utils.js",
            caller_name="ghostFunction",
            called_name="log",
            confidence=0.75,
        ),
    ]


def _describe_claim(claim: Claim) -> str:
    parts = [claim.type.name]
    if claim.symbol_name:
        parts.append(claim.symbol_name)
    if claim.parent_class:
        parts[-1] = f"{claim.parent_class}.{parts[-1]}"
    parts.append(f"→ {claim.file_path}")
    if claim.caller_name and claim.called_name:
        parts.append(f"({claim.caller_name} → {claim.called_name})")
    parts.append(f"conf={claim.confidence:.0%}")
    return "  ".join(parts)


def _print_verdict_counts(report: VerificationReport) -> None:
    print(f"  Total claims:     {report.total_claims}")
    print(f"  CONFIRMED:        {report.confirmed}")
    print(f"  CONTRADICTED:     {report.contradicted}")
    print(f"  UNVERIFIABLE:     {report.unverifiable}")
    print(f"  Unexplained:      {report.unexplained_count}")
    print(f"  All claims match: {'YES' if report.success else 'NO'}")


def _print_final_verdict(report: VerificationReport) -> None:
    print("  PHASE 4a VERDICT")
    print()
    lines = [
        "  Pipeline stages exercised: scan → detect → verify → report",
        "  Languages: Python + JavaScript",
        f"  Claims tested: {report.total_claims}",
        f"  CONFIRMED: {report.confirmed}",
        f"  CONTRADICTED: {report.contradicted}",
        f"  UNVERIFIABLE: {report.unverifiable}",
        f"  Unexplained: {report.unexplained_count}",
    ]
    for line in lines:
        print(line)
    print()
    if report.success:
        print("  ✅ All claims verified — verifier + reporter work with JS data")
    else:
        print("  ⚠️  Some claims were not confirmed — see report above")


if __name__ == "__main__":
    main()
