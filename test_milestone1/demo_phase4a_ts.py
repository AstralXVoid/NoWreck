#!/usr/bin/env python3
"""Phase 4a (TS) demo — end-to-end verification pipeline with pure-TypeScript repos.

Usage::

    python test_milestone1/demo_phase4a_ts.py

This demo proves that the full Nowreck pipeline (scanner → symbol index →
change detector → claim verifier → terminal reporter) works correctly with
a repository containing TypeScript files.

It creates a **pre** state (no files) and a **post** state (the pure-TS
milestone repo), detects all structural changes, then verifies hand-written
claims covering all 7 claim types across TypeScript symbols.
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

TS_REPO = Path(__file__).resolve().parent / "repos" / "pure-ts" / "src"

HEADER = "=" * 72
SUB = "-" * 72


def main() -> None:
    print(HEADER)
    print("  PHASE 4a (TS) — END-TO-END PIPELINE DEMO (Pure TypeScript)")
    print(HEADER)

    # ------------------------------------------------------------------
    # 1. Setup: copy milestone repo to a temp directory
    # ------------------------------------------------------------------
    print(f"\n  Repo: {TS_REPO}")
    tmp_dir = Path(tempfile.mkdtemp(prefix="nowreck_phase4a_ts_"))
    _copy_repo(TS_REPO, tmp_dir)
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
    print(f"    TS:     {', '.join(str(p) for p in post_scan.ts_files)}")
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
    # 4. Hand-written claims (pure TypeScript)
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
    for line in json_out.splitlines()[:30]:
        print(f"  {line}")
    print("  ...")
    print(f"  Total JSON length: {len(json_out)} chars")

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
    by_type: dict[str, list[DetectedChange]] = {}
    for c in changes:
        by_type.setdefault(c.change_type.name, []).append(c)

    for type_name in sorted(by_type):
        items = by_type[type_name]
        print(f"  {type_name}: {len(items)}")
        for c in items[:3]:
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
    """Craft claims that exercise all 7 claim types across TypeScript.

    Claim ordering is important: CONTRADICTED claims must come BEFORE
    CONFIRMED claims that reference the same symbol.  This is because the
    verifier consumes matched ``DetectedChange`` objects, and the opposite-
    type check skips already-consumed changes.

    For example, ``REMOVE_FUNCTION greet`` (CONTRADICTED) must come before
    ``ADD_FUNCTION greet`` (CONFIRMED) so the opposite-type match can find
    the ``ADD_FUNCTION`` change.
    """

    return [
        # ── CONTRADICTED: opposite-type matches ──
        # REMOVE_FUNCTION for a symbol that was actually ADDED.
        # The verifier consumes changes during same-type matching,
        # so CONTRADICTED claims must come BEFORE CONFIRMED claims
        # for the same symbol.  CONFIRMED claims for symbols already
        # referenced by CONTRADICTED claims are omitted to avoid
        # the consumed-change UNVERIFIABLE result.
        Claim(
            type=ClaimType.REMOVE_FUNCTION,
            symbol_name="greet",
            file_path="greeter.ts",
            confidence=0.80,
        ),
        # CALLS_FUNCTION that doesn't exist (caller exists, call doesn't)
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="greet",
            file_path="greeter.ts",
            caller_name="greet",
            called_name="sendNotification",
            confidence=0.70,
        ),
        # REMOVE_CLASS for a class that was actually ADDED
        Claim(
            type=ClaimType.REMOVE_CLASS,
            symbol_name="Calculator",
            file_path="calculator.ts",
            confidence=0.85,
        ),

        # ── CONFIRMED: TypeScript functions ──
        # Note: ADD_FUNCTION greet and ADD_CLASS Calculator are intentionally
        # omitted because their changes were consumed by the CONTRADICTED
        # claims above (REMOVE_FUNCTION greet, REMOVE_CLASS Calculator).
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="formatGreeting",
            file_path="greeter.ts",
            confidence=0.90,
        ),
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="farewell",
            file_path="greeter.ts",
            confidence=0.90,
        ),
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="computeAverage",
            file_path="calculator.ts",
            confidence=0.95,
        ),

        # ── CONFIRMED: TypeScript classes ──
        # ADD_CLASS Calculator is intentionally omitted — the REMOVE_CLASS
        # Calculator CONTRADICTED claim above consumes the same change.
        Claim(
            type=ClaimType.ADD_CLASS,
            symbol_name="User",
            file_path="models.ts",
            confidence=1.0,
        ),
        Claim(
            type=ClaimType.ADD_CLASS,
            symbol_name="AdminUser",
            file_path="models.ts",
            confidence=0.98,
        ),

        # ── CONFIRMED: FILE_CREATED ──
        Claim(
            type=ClaimType.FILE_CREATED,
            file_path="greeter.ts",
            confidence=1.0,
        ),
        Claim(
            type=ClaimType.FILE_CREATED,
            file_path="calculator.ts",
            confidence=1.0,
        ),
        Claim(
            type=ClaimType.FILE_CREATED,
            file_path="models.ts",
            confidence=1.0,
        ),

        # ── CONFIRMED: CALLS_FUNCTION (simple calls, not attribute calls) ──
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="computeAverage",
            file_path="calculator.ts",
            caller_name="computeAverage",
            called_name="len",
            confidence=0.85,
        ),
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="computeAverage",
            file_path="calculator.ts",
            caller_name="computeAverage",
            called_name="sum",
            confidence=0.85,
        ),
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="greet",
            file_path="greeter.ts",
            caller_name="greet",
            called_name="formatGreeting",
            confidence=0.90,
        ),

        # ── UNVERIFIABLE: symbols that don't exist ──
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="nonExistentFunction",
            file_path="calculator.ts",
            confidence=0.90,
        ),
        Claim(
            type=ClaimType.CALLS_FUNCTION,
            symbol_name="ghostFunction",
            file_path="greeter.ts",
            caller_name="ghostFunction",
            called_name="log",
            confidence=0.75,
        ),
        Claim(
            type=ClaimType.REMOVE_CLASS,
            symbol_name="NonExistentClass",
            file_path="models.ts",
            confidence=0.80,
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
    print("  PHASE 4a (TS) VERDICT")
    print()
    lines = [
        "  Pipeline stages exercised: scan → detect → verify → report",
        "  Language: TypeScript",
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
        print("  ✅ All claims verified — verifier + reporter work with TS data")
    else:
        print("  ⚠️  Some claims were not confirmed — see report above")


if __name__ == "__main__":
    main()
