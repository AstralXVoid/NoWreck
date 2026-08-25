"""v10 Prompt Mode verifier — eliminates the circular confirmation loop.

The fundamental invariant:

    A model claim must never be used as the source of evidence for
    verifying that same claim.

Architecture:

    Prompt + Repo
        ↓
    SnapshotManager.save_before() → BEFORE state
        ↓
    ModelProvider.changes_from_prompt_v10()
        ↓
    ModelOutput (claims + patch)
        ↓
    Apply patch to repo
        ↓
    SnapshotManager.capture()     → AFTER state
        ↓
    ChangeDetector.detect(before, after)
        ↓
    OBSERVED changes (independent of claims)
        ↓
    ClaimVerifier.verify(claims, observed_changes)
        ↓
    VerificationReport

The key difference from the old Prompt Mode:

    OLD (circular):
        claims → claims_to_changes() → fake "changes" → verifier → MATCH

    NEW (independent):
        before_state + after_state → real changes → verifier → verdict
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from nowreck.detector.change_detector import (
    detect_changes,
)
from nowreck.model.provider import ModelConfig, ModelProvider, ModelResult
from nowreck.scanner.snapshot_manager import Snapshot, SnapshotManager
from nowreck.verifier.verifier import (
    ClaimVerifier,
    VerificationReport,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatchApplicationResult:
    """Result of applying a unified diff patch.

    Attributes:
        success: Whether the patch applied without errors.
        applied_files: Files that were modified by the patch.
        errors: Error messages if the patch failed.
        patch_content: The raw patch string that was attempted.
    """

    success: bool
    applied_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    patch_content: str = ""


@dataclass(frozen=True)
class PromptVerificationResult:
    """Complete result from v10 Prompt Mode verification.

    Attributes:
        report: The verification report with per-claim verdicts.
        patch_applied: Whether the patch was successfully applied.
        patch_result: Details of patch application.
        before_snapshot: The before-state snapshot (for debugging).
        after_snapshot: The after-state snapshot (for debugging).
        model_result: The raw model output.
        has_independent_evidence: Whether independent before/after
            evidence was available for verification.
    """

    report: VerificationReport
    patch_applied: bool
    patch_result: PatchApplicationResult | None = None
    before_snapshot: Snapshot | None = None
    after_snapshot: Snapshot | None = None
    model_result: ModelResult | None = None
    has_independent_evidence: bool = False


@dataclass
class _ManualFilePatch:
    """One file's parsed section of a unified diff (manual applier)."""

    path: str
    is_new: bool
    is_delete: bool
    hunks: list[tuple[int, list[str]]]


class PatchApplier:
    """Applies unified diff patches to a repository.

    Uses ``git apply`` when available, falls back to manual file
    operations.  Does NOT create commits — only modifies the working
    tree.
    """

    @staticmethod
    def apply(patch: str, repo_path: Path) -> PatchApplicationResult:
        """Apply a unified diff patch to the repository.

        Args:
            patch: The unified diff patch string.
            repo_path: Root directory of the repository.

        Returns:
            A ``PatchApplicationResult`` with success status and
            details.
        """
        if not patch.strip():
            return PatchApplicationResult(
                success=False,
                errors=["Empty patch"],
                patch_content=patch,
            )

        # Try git apply first
        result = PatchApplier._try_git_apply(patch, repo_path)
        if result is not None:
            return result

        # Fallback: manual file-by-file application
        return PatchApplier._try_manual_apply(patch, repo_path)

    @staticmethod
    def _try_git_apply(patch: str, repo_path: Path) -> PatchApplicationResult | None:
        """Try applying via ``git apply``."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "apply", "--check"],
                input=patch,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                # --check failed, try without it
                logger.info("git apply --check failed: %s", result.stderr.strip())
                return None

            # Apply for real
            result = subprocess.run(
                ["git", "apply"],
                input=patch,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                applied_files = PatchApplier._extract_files_from_patch(patch)
                return PatchApplicationResult(
                    success=True,
                    applied_files=applied_files,
                    patch_content=patch,
                )
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _try_manual_apply(patch: str, repo_path: Path) -> PatchApplicationResult:
        """Apply a unified diff without ``git`` — positionally correct.

        Hunks are applied at their declared line offsets: context is
        verified against the original, removals advance the read
        cursor, additions splice into the output, and inter-hunk gaps
        are copied verbatim.  A hunk that cannot be matched fails its
        file (reported in ``errors``); unrelated files still apply and
        the overall result reports failure.
        """
        applied_files: list[str] = []
        errors: list[str] = []

        for fp in PatchApplier._parse_patch(patch):
            target = repo_path / fp.path
            try:
                if fp.is_delete:
                    target.unlink(missing_ok=True)
                    applied_files.append(fp.path)
                    continue

                original = target.read_text(encoding="utf-8") if target.exists() else ""
                had_trailing_nl = original.endswith("\n")
                orig_lines = original.split("\n")
                if had_trailing_nl:
                    orig_lines.pop()  # artifact of split on trailing \n

                new_lines: list[str] = []
                read_pos = 0
                problem: str | None = None

                for old_start, hunk_lines in fp.hunks:
                    anchor = max(old_start - 1, 0)
                    if anchor < read_pos:
                        problem = f"overlapping hunk at line {anchor + 1}"
                        break
                    new_lines.extend(orig_lines[read_pos:anchor])
                    read_pos = anchor

                    mismatch = False
                    for raw in hunk_lines:
                        tag, body = raw[:1], raw[1:]
                        if tag == "+":
                            new_lines.append(body)
                        elif tag == "-":
                            if (
                                read_pos >= len(orig_lines)
                                or orig_lines[read_pos] != body
                            ):
                                problem = (
                                    f"{fp.path}: removed-line mismatch "
                                    f"near line {read_pos + 1}"
                                )
                                mismatch = True
                                break
                            read_pos += 1
                        else:  # context (" " or historically-blank "")
                            if (
                                read_pos >= len(orig_lines)
                                or orig_lines[read_pos] != body
                            ):
                                problem = (
                                    f"{fp.path}: context mismatch near "
                                    f"line {read_pos + 1}"
                                )
                                mismatch = True
                                break
                            new_lines.append(body)
                            read_pos += 1
                    if mismatch:
                        break

                if problem is None:
                    new_lines.extend(orig_lines[read_pos:])
                    text = "\n".join(new_lines)
                    if had_trailing_nl or fp.is_new:
                        text += "\n"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text, encoding="utf-8")
                    applied_files.append(fp.path)
                elif problem.startswith(fp.path):
                    errors.append(problem)
                else:
                    errors.append(f"{fp.path}: {problem}")
            except OSError as exc:
                errors.append(f"Failed to write {fp.path}: {exc}")

        if errors:
            return PatchApplicationResult(
                success=False,
                applied_files=applied_files,
                errors=errors,
                patch_content=patch,
            )

        return PatchApplicationResult(
            success=True,
            applied_files=applied_files,
            patch_content=patch,
        )

    @staticmethod
    def _parse_patch(patch: str) -> list[_ManualFilePatch]:
        """Parse a unified diff into per-file hunk structures."""
        files: list[_ManualFilePatch] = []
        current: _ManualFilePatch | None = None
        lines = patch.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i]

            if line.startswith("--- ") and i + 1 < len(lines):
                nxt = lines[i + 1]
                if nxt.startswith("+++ "):
                    old_path = line[4:].split("\t")[0].strip()
                    new_path = nxt[4:].split("\t")[0].strip()
                    is_new = old_path == "/dev/null"
                    is_delete = new_path == "/dev/null"
                    path = new_path if not is_delete else old_path
                    if path.startswith(("b/", "a/")):
                        path = path[2:]
                    current = _ManualFilePatch(
                        path=path,
                        is_new=is_new,
                        is_delete=is_delete,
                        hunks=[],
                    )
                    files.append(current)
                    i += 2
                    continue

            if current is not None and line.startswith("@@"):
                match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if match:
                    old_start = int(match.group(1))
                    hunk_lines: list[str] = []
                    i += 1
                    while i < len(lines):
                        body = lines[i]
                        if body.startswith("@@"):
                            break
                        if body.startswith(("diff ", "index ")):
                            break
                        if body.startswith("--- ") and (
                            i + 1 < len(lines) and lines[i + 1].startswith("+++ ")
                        ):
                            break
                        if body.startswith("\\"):  # "\ No newline ..."
                            i += 1
                            continue
                        if body.strip() == "":
                            # Blank context line (trailing space often lost).
                            hunk_lines.append(" ")
                            i += 1
                            continue
                        if body[0] in "+- ":
                            hunk_lines.append(body)
                            i += 1
                            continue
                        if body.startswith(
                            ("new file", "old file", "rename ", "similarity")
                        ):
                            i += 1
                            continue
                        break
                    current.hunks.append((old_start, hunk_lines))
                    continue

            i += 1

        return files

    @staticmethod
    def _extract_files_from_patch(patch: str) -> list[str]:
        """Extract file paths from a unified diff header."""
        files: list[str] = []
        for line in patch.splitlines():
            if line.startswith("--- a/"):
                path = line[6:]
                if path not in files:
                    files.append(path)
            elif line.startswith("+++ b/"):
                path = line[6:]
                if path not in files:
                    files.append(path)
        return files


class PromptModeVerifier:
    """v10 Prompt Mode verifier — independent evidence from before/after.

    This is the core fix for the circular confirmation loop problem.

    Usage::

        verifier = PromptModeVerifier(repo_path, model_config)
        result = verifier.verify(
            prompt="Add a greet function that says hello",
        )
        print(result.report.confirmed)
        print(result.report.contradicted)

    The verifier:

    1. Captures BEFORE state
    2. Gets claims + patch from model
    3. Applies patch to repo
    4. Captures AFTER state
    5. Runs ChangeDetector to get OBSERVED changes
    6. Verifies claims against observed changes
    7. Restores repo state (SnapshotManager.restore + cleanup — runs
       in a finally block, so it happens even when a step raises)
    """

    def __init__(
        self,
        repo_path: str | Path,
        model_config: ModelConfig | None = None,
    ) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._snapshot_mgr = SnapshotManager(self._repo_path)
        self._model_provider = ModelProvider(model_config)

    def verify(
        self,
        prompt: str,
        *,
        repo_context: str = "",
        restore_after: bool = True,
    ) -> PromptVerificationResult:
        """Run full v10 verification pipeline.

        Args:
            prompt: Natural-language description of what the model did.
            repo_context: Optional context about the repository.
            restore_after: Whether to restore the repo to its original
                state after verification.  Defaults to ``True``.

        Returns:
            A ``PromptVerificationResult`` with independent evidence.
        """
        # Step 1: Save BEFORE state (temp copy / git stash so we can
        # put the working tree back after the model's patch).
        before = self._snapshot_mgr.save_before()
        n_files = (
            len(before.scan_result.modules)
            + len(before.scan_result.js_files)
            + len(before.scan_result.ts_files)
            + len(before.scan_result.rust_files)
            + len(before.scan_result.go_files)
        )
        logger.info("Captured BEFORE state: %d files", n_files)

        patch_applied = False
        patch_result: PatchApplicationResult | None = None

        try:
            # Step 2: Get claims + patch from model
            model_result = self._model_provider.changes_from_prompt_v10(
                prompt, repo_context
            )
            logger.info(
                "Model returned %d claims, patch %s",
                len(model_result.claims),
                "present" if model_result.patch else "absent",
            )

            # Step 3: Apply patch (if available)
            if model_result.patch:
                patch_result = PatchApplier.apply(model_result.patch, self._repo_path)
                patch_applied = patch_result.success
                logger.info(
                    "Patch applied: %s (files: %s)",
                    patch_applied,
                    patch_result.applied_files,
                )
            else:
                patch_result = PatchApplicationResult(
                    success=False,
                    errors=["No patch provided by model"],
                )

            # Step 4: Capture AFTER state
            after = self._snapshot_mgr.capture()
            n_files_after = (
                len(after.scan_result.modules)
                + len(after.scan_result.js_files)
                + len(after.scan_result.ts_files)
                + len(after.scan_result.rust_files)
                + len(after.scan_result.go_files)
            )
            logger.info("Captured AFTER state: %d files", n_files_after)

            # Step 5: Run ChangeDetector — INDEPENDENT of claims
            observed_changes = detect_changes(
                before.scan_result,
                after.scan_result,
                before.symbol_index,
                after.symbol_index,
            )
            logger.info(
                "Observed %d changes (independent of claims)",
                len(observed_changes),
            )

            # Step 6: Verify claims against observed changes
            report = ClaimVerifier.verify(model_result.claims, observed_changes)
            logger.info(
                "Verification: %d confirmed, %d contradicted, %d unverifiable",
                report.confirmed,
                report.contradicted,
                report.unverifiable,
            )
        finally:
            # Steps 7+8: ALWAYS settle the working tree and release
            # snapshot resources — on success and on failure alike.
            self._finalize_repo_state(
                before, patch_result, patch_applied, restore_after
            )

        # Determine if we have independent evidence
        has_evidence = len(observed_changes) > 0 or patch_applied

        return PromptVerificationResult(
            report=report,
            patch_applied=patch_applied,
            patch_result=patch_result,
            before_snapshot=before,
            after_snapshot=after,
            model_result=model_result,
            has_independent_evidence=has_evidence,
        )

    def verify_with_snapshots(
        self,
        prompt: str,
        *,
        before_path: Path,
        after_path: Path,
    ) -> PromptVerificationResult:
        """Verify using user-provided before/after directories.

        Args:
            prompt: Natural-language description of changes.
            before_path: Path to the before-state directory.
            after_path: Path to the after-state directory.

        Returns:
            A ``PromptVerificationResult`` with independent evidence.
        """
        before_mgr = SnapshotManager(before_path)
        before = before_mgr.capture()

        after_mgr = SnapshotManager(after_path)
        after = after_mgr.capture()

        # Get claims from model (no patch — user provided dirs)
        model_result = self._model_provider.changes_from_prompt_v10(prompt)

        # Detect independent changes
        observed_changes = detect_changes(
            before.scan_result,
            after.scan_result,
            before.symbol_index,
            after.symbol_index,
        )

        report = ClaimVerifier.verify(model_result.claims, observed_changes)

        has_evidence = len(observed_changes) > 0

        return PromptVerificationResult(
            report=report,
            patch_applied=False,
            patch_result=None,
            before_snapshot=before,
            after_snapshot=after,
            model_result=model_result,
            has_independent_evidence=has_evidence,
        )

    def _finalize_repo_state(
        self,
        before: Snapshot,
        patch_result: PatchApplicationResult | None,
        patch_applied: bool,
        restore_after: bool,
    ) -> None:
        """Restore the working tree and release snapshot resources.

        Called from ``verify()``'s ``finally`` block, so it runs on the
        success path **and** whenever any step raises.  Guarantees:

        * Snapshots taken via ``git stash`` are always popped — the
          stash holds the user's uncommitted changes regardless of
          whether a patch was applied.
        * Temp-copy snapshots restore the tree when a patch was
          actually applied and ``restore_after`` was requested.
        * Temporary snapshot files are always cleaned up (best-effort).
        """
        snapshot_dir = before.snapshot_dir
        from_git_stash = (
            snapshot_dir is not None and (snapshot_dir / ".git_stash").exists()
        )
        try:
            if from_git_stash:
                logger.info("Snapshot used git stash — popping to return user changes.")
                if self._snapshot_mgr.restore(before):
                    logger.info("git stash pop succeeded.")
                else:
                    logger.warning(
                        "git stash pop failed — uncommitted changes may "
                        "still be in 'git stash list'."
                    )
            elif patch_applied and restore_after:
                n_files = len(patch_result.applied_files) if patch_result else 0
                logger.info(
                    "Restoring repo (%d patched files) from snapshot.",
                    n_files,
                )
                if self._snapshot_mgr.restore(before):
                    logger.info("Repo restored to pre-patch state.")
                else:
                    logger.warning(
                        "Restore failed — repo may still contain patch changes."
                    )
            # else: nothing to undo (tree untouched or restore disabled).
        finally:
            self._snapshot_mgr.cleanup(before)


def verify_prompt(
    prompt: str,
    repo_path: str | Path,
    model_config: ModelConfig | None = None,
    *,
    repo_context: str = "",
) -> PromptVerificationResult:
    """Convenience function for v10 prompt verification.

    Creates a ``PromptModeVerifier``, runs verification, and returns
    the result.  The repo is restored to its original state after
    verification.

    Args:
        prompt: Natural-language description of changes.
        repo_path: Path to the repository.
        model_config: Model configuration.  Uses defaults if ``None``.
        repo_context: Optional context about the repository.

    Returns:
        A ``PromptVerificationResult`` with independent evidence.
    """
    verifier = PromptModeVerifier(repo_path, model_config)
    return verifier.verify(prompt, repo_context=repo_context)
