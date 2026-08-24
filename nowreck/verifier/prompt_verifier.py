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
        """Apply patch by extracting file changes manually.

        This is a simplified parser for unified diffs.  It handles
        the common case of file additions and modifications.
        """
        applied_files: list[str] = []
        errors: list[str] = []

        # Split patch into per-file sections
        sections = PatchApplier._split_patch_sections(patch)

        for filename, content in sections.items():
            file_path = repo_path / filename
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                applied_files.append(filename)
            except OSError as exc:
                errors.append(f"Failed to write {filename}: {exc}")

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

    @staticmethod
    def _split_patch_sections(patch: str) -> dict[str, str]:
        """Split a unified diff into per-file sections.

        Returns a dict mapping filename → content (for new files) or
        the patched content.  This is a simplified parser.
        """
        sections: dict[str, str] = {}
        current_file: str | None = None
        content_lines: list[str] = []

        for line in patch.splitlines():
            if line.startswith("+++ b/"):
                if current_file and content_lines:
                    sections[current_file] = "\n".join(content_lines)
                current_file = line[6:]
                content_lines = []
            elif line.startswith("--- a/"):
                continue  # Skip the "from" header
            elif current_file is not None:
                if line.startswith("+"):
                    content_lines.append(line[1:])
                elif line.startswith("-"):
                    continue  # Skip removed lines
                elif line.startswith("@@"):
                    continue  # Skip hunk headers
                elif line.startswith("diff "):
                    continue  # Skip diff headers
                elif line.startswith("index "):
                    continue  # Skip index lines
                elif line.startswith("new file"):
                    continue
                elif line.startswith("old file"):
                    continue
                elif line.startswith("rename "):
                    continue
                elif line.startswith("similarity"):
                    continue
                else:
                    content_lines.append(line)

        if current_file and content_lines:
            sections[current_file] = "\n".join(content_lines)

        return sections


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
