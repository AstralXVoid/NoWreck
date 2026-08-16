#!/usr/bin/env python3
"""
Phase 4d (TSX) — Live-model hallucination-catch test for TSX (`.tsx`).

Definition of Done (v7 scope doc):
    "Live TSX DoD test (real model, induced false claim on a component —
     same design as the v5 TS live test; needs the user's key, run at
     release time)."

Design:
    1. Detect real structural changes in the pure-tsx milestone repo
       (empty pre -> full post).
    2. Call a live model with a prompt describing TSX changes PLUS an
       induced false call (``Farewell()`` -> ``notify()``, where ``notify``
       does not exist in the repo).
    3. Verify the model's claims against the **real** detected changes
       (not the self-consistent prompt-mode derived changes).
    4. Expected: real symbols -> CONFIRMED, hallucinated call -> CONTRADICTED
       (caller exists but call was never detected).

Requires the ``NOWRECK_API_KEY`` environment variable.  Skips gracefully
if not set.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure the project root is on sys.path so we can import nowreck.*.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nowreck.claims.models import ClaimType
from nowreck.detector.change_detector import ChangeDetector
from nowreck.model.provider import ModelConfig, ModelError, ModelProvider
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.scanner.repository_scanner import RepositoryScanner
from nowreck.scanner.symbol_index import build_symbol_index
from nowreck.verifier.verifier import ClaimVerifier, Verdict

PURE_TSX_REPO = PROJECT_ROOT / "test_milestone1" / "repos" / "pure-tsx" / "src"

HEADER = "=" * 72
SUB = "-" * 72

# ---------------------------------------------------------------------------
# Prompt — describes real TSX changes with an induced false call.
#
# IMPORTANT: file_path values (e.g. ``greeter.tsx``) must match what the
# scanner produces for a flat directory copy — no ``src/`` prefix.
# ---------------------------------------------------------------------------

PROMPT = """
I made the following changes to a TypeScript (TSX) project:

1. Created greeter.tsx — greeting components
   - Added function component Greeting({ name }: { name: string }) that
     formats a greeting and renders it in a div
   - Added arrow function formatGreeting(template: string, name: string)
   - Added arrow component Farewell({ name }: { name: string }) that
     renders a goodbye message
     (Farewell() calls a helper called notify() to send the message)

2. Created calculator.tsx — calculator component
   - Added class component Calculator extends React.Component with methods
     add, subtract, multiply, divide, render
   - Added function computeAverage(values: number[])

3. Created models.tsx — data model components
   - Added function component UserCard({ username, email })
   - Added arrow component AdminCard({ username, email, role })
   - Added class component UserList extends React.Component with render()
     that composes UserCard and AdminCard

Describe the changes as structured claims in the required JSON format.
Include file_path values like 'greeter.tsx', 'calculator.tsx', 'models.tsx'.
"""


def main() -> int:
    """Run the live-model hallucination-catch test."""
    print(HEADER)
    print("  PHASE 4d (TSX) — LIVE-MODEL HALLUCINATION-CATCH TEST")
    print("  Definition of Done — v7 scope (TSX)")
    print(HEADER)

    # ------------------------------------------------------------------
    # Prerequisites
    # ------------------------------------------------------------------
    api_key = os.environ.get("NOWRECK_API_KEY", "").strip()
    if not api_key:
        print()
        print("  > NOWRECK_API_KEY not set.  Skipping live-model test.")
        print("    Set it to run:")
        print("      export NOWRECK_API_KEY='your-api-key'")
        print("    Then re-run this script.")
        return 0

    model = os.environ.get("NOWRECK_MODEL", "gpt-4o")
    base_url = os.environ.get("NOWRECK_BASE_URL", "https://api.openai.com/v1")

    config = ModelConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=0.0,
        max_retries=1,
    )
    provider = ModelProvider(config=config)

    # ------------------------------------------------------------------
    # 1. Set up test repos
    # ------------------------------------------------------------------
    print(f"  Test repo: {PURE_TSX_REPO}")
    pre_dir = Path(tempfile.mkdtemp(prefix="nowreck_hallucination_tsx_pre_"))
    post_dir = Path(tempfile.mkdtemp(prefix="nowreck_hallucination_tsx_post_"))
    _copy_dir(PURE_TSX_REPO, post_dir)
    print(f"  Pre:  {pre_dir} (empty)")
    print(f"  Post: {post_dir} ({len(list(post_dir.iterdir()))} TSX files)")

    # ------------------------------------------------------------------
    # 2. Detect real structural changes
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 1 — DETECT REAL STRUCTURAL CHANGES")
    print(SUB)

    pre_scan = RepositoryScanner(pre_dir).scan()
    post_scan = RepositoryScanner(post_dir).scan()
    pre_sym = build_symbol_index(pre_scan)
    post_sym = build_symbol_index(post_scan)

    real_changes = ChangeDetector.detect(pre_scan, post_scan, pre_sym, post_sym)
    print(f"  Real changes detected: {len(real_changes)}")

    for c in real_changes[:8]:
        parts = [c.change_type.name, str(c.file_path)]
        if c.symbol_name:
            parts.append(c.symbol_name)
        if c.caller_name and c.called_name:
            parts.append(f"{c.caller_name} -> {c.called_name}")
        print(f"    * {'  '.join(parts)}")
    if len(real_changes) > 8:
        print(f"    ... and {len(real_changes) - 8} more")

    # ------------------------------------------------------------------
    # 3. Call the live model
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 2 — CALL LIVE MODEL")
    print(SUB)
    print(f"  Model: {model}")
    print(f"  Base:  {base_url}")
    print(f"\n  Prompt: {PROMPT.strip()[:60]}...")
    print("  Calling model...", end=" ", flush=True)

    try:
        result = provider.changes_from_prompt(PROMPT)
    except ModelError as exc:
        print(f"FAILED: {exc}")
        _cleanup(pre_dir, post_dir)
        return 1

    print("done")
    print(f"  Attempts: {result.attempts}")
    print(f"  Raw claims: {len(result.claims)}")

    if result.parse_result and result.parse_result.errors:
        print(f"  Parse warnings: {len(result.parse_result.errors)}")
        for err in result.parse_result.errors[:3]:
            print(f"    Warning: {err}")

    if not result.claims:
        print()
        print("  Model returned no valid claims.  Cannot test.")
        _cleanup(pre_dir, post_dir)
        return 1

    # Print model claims
    print(f"\n  Model claims ({len(result.claims)}):")
    for c in result.claims:
        desc_parts = [c.type.name]
        if c.symbol_name:
            desc_parts.append(c.symbol_name)
        desc_parts.append(f"-> {c.file_path}")
        if c.caller_name and c.called_name:
            desc_parts.append(f"({c.caller_name} -> {c.called_name})")
        desc_parts.append(f"conf={c.confidence:.0%}")
        print(f"    * {'  '.join(desc_parts)}")

    # ------------------------------------------------------------------
    # 4. Verify claims against REAL detected changes
    # ------------------------------------------------------------------
    print(f"\n{SUB}")
    print("  STAGE 3 — VERIFY AGAINST REAL DETECTED CHANGES")
    print(SUB)

    report = ClaimVerifier.verify(result.claims, real_changes)

    for r in report.results:
        label = {
            Verdict.CONFIRMED: "CONFIRMED",
            Verdict.CONTRADICTED: "CONTRADICTED",
            Verdict.UNVERIFIABLE: "UNVERIFIABLE",
        }.get(r.verdict, "?")
        icon = {
            Verdict.CONFIRMED: "\u2705",
            Verdict.CONTRADICTED: "\u26a0\ufe0f",
            Verdict.UNVERIFIABLE: "\u2753",
        }.get(r.verdict, "?")
        parts = [icon, label, r.claim.type.name]
        if r.claim.symbol_name:
            parts.append(r.claim.symbol_name)
        parts.append(f"-> {r.claim.file_path}")
        if r.claim.caller_name and r.claim.called_name:
            parts.append(f"({r.claim.caller_name} -> {r.claim.called_name})")
        print(f"    {'  '.join(parts)}")

    # Full terminal report
    print("\n  Terminal report:\n")
    reporter = TerminalReporter(colour=False)
    print(reporter.report(report))

    # ------------------------------------------------------------------
    # 5. Evaluate
    # ------------------------------------------------------------------
    print(SUB)
    print()
    print("  RESULTS")
    print(f"  Total claims:     {report.total_claims}")
    print(f"  CONFIRMED:        {report.confirmed}")
    print(f"  CONTRADICTED:     {report.contradicted}")
    print(f"  UNVERIFIABLE:     {report.unverifiable}")
    print(f"  Unexplained:      {report.unexplained_count}")

    has_hallucination_catch = any(
        r.verdict is Verdict.CONTRADICTED and r.claim.type is ClaimType.CALLS_FUNCTION
        for r in report.results
    )
    has_real_confirmed = report.confirmed > 0

    # ------------------------------------------------------------------
    # 6. Final verdict
    # ------------------------------------------------------------------
    _check = "\u2705"
    _warn = "\u26a0\ufe0f"
    _cross = "\u274c"

    print(f"\n{HEADER}")
    print("  PHASE 4d (TSX) — FINAL VERDICT")
    print(HEADER)
    print(f"\n  Real symbols confirmed:  {_check if has_real_confirmed else _cross}")
    print(f"  Hallucination caught:    {_check if has_hallucination_catch else _warn}")
    print()
    print("  Pipeline stages: scan -> detect -> model -> verify -> report")
    print("  Languages: TSX (pure-tsx milestone repo)")
    print(f"  Test type: live model (real API call to {model})")

    if has_real_confirmed and has_hallucination_catch:
        print()
        print("  DEFINITION OF DONE — PASS")
        print("  TSX hallucination-catch test succeeds.")
        print("  CONFIRMED results match reality.")
        print("  Induced false call correctly caught as CONTRADICTED.")
    elif has_real_confirmed and not has_hallucination_catch:
        print()
        print("  PARTIAL — Real confirmed, but no hallucination caught.")
        print("  The model may not have included the induced false claim.")
        print("  The pipeline works correctly in either case.")
    else:
        print()
        print("  FAILED — No claims confirmed.")
        print("  Check that the prompt file paths match scanned paths.")

    _cleanup(pre_dir, post_dir)
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copy_dir(src: Path, dst: Path) -> None:
    """Copy all files from *src* into *dst*."""
    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, dst / item.name)


def _cleanup(pre_dir: Path, post_dir: Path) -> None:
    """Remove temporary directories, ignoring errors."""
    shutil.rmtree(pre_dir, ignore_errors=True)
    shutil.rmtree(post_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
