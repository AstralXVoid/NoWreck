from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from nowreck.claims.models import Claim, ClaimType
from nowreck.detector.change_detector import ChangeType, DetectedChange
from nowreck.model.provider import ModelResult
from nowreck.picker import run_picker
from nowreck.verifier.verifier import VerificationReport, VerificationResult, Verdict

# ============================================================================
# Integration tests for run_picker()
#
# These tests exercise the *full flow* through run_picker() — from menu
# selection through to pipeline execution and output.  Dependencies are
# mocked at the nowreck.picker module level to simulate real user
# interaction without requiring a terminal or network.
# ============================================================================


class TestPickerIntegrationVerify:
    """End-to-end flow: Verify → provide prompt → pipeline → report."""

    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ModelProvider")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_verify_happy_path(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
        mock_text: MagicMock,
        mock_confirm: MagicMock,
        mock_config_cls: MagicMock,
        mock_provider_cls: MagicMock,
        mock_verifier_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Menu: Verify → prompt → pipeline runs → report printed + saved."""
        # --- Menu: select Verify, then Exit ---
        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Exit",
        ]

        # --- Prompt input ---
        mock_text.return_value.ask.return_value = "Add email validation to auth.py"

        # --- Config loaded (already configured) ---
        mock_config = MagicMock()
        mock_config.load.return_value = {
            "api_key": "sk-test",
            "base_url": "https://api.test.com/v1",
            "model": "test-model",
            "temperature": 0.0,
            "max_retries": 1,
        }
        mock_config_cls.return_value = mock_config
        # Config.setup confirm should never be asked (config exists)
        mock_confirm.return_value.ask.assert_not_called()

        # --- Model provider returns a result ---
        mock_provider = MagicMock()
        mock_result = ModelResult(
            claims=[
                Claim(
                    type=ClaimType.ADD_FUNCTION,
                    symbol_name="validate_email",
                    file_path="auth.py",
                    confidence=0.95,
                ),
            ],
            changes=[
                DetectedChange(
                    change_type=ChangeType.ADD_FUNCTION,
                    file_path=Path("auth.py"),
                    symbol_name="validate_email",
                ),
            ],
            attempts=1,
        )
        mock_provider.changes_from_prompt.return_value = mock_result
        mock_provider_cls.return_value = mock_provider

        # --- Verifier ---
        mock_verifier_cls.verify.return_value = VerificationReport(
            results=[
                VerificationResult(
                    claim=Claim(
                        type=ClaimType.ADD_FUNCTION,
                        symbol_name="validate_email",
                        file_path="auth.py",
                        confidence=0.95,
                    ),
                    verdict=Verdict.CONFIRMED,
                    matched_change=DetectedChange(
                        change_type=ChangeType.ADD_FUNCTION,
                        file_path=Path("auth.py"),
                        symbol_name="validate_email",
                    ),
                ),
            ],
        )

        # --- Reporter ---
        mock_reporter = MagicMock()
        mock_reporter.report.return_value = "Mock report text"
        mock_reporter_cls.return_value = mock_reporter

        # --- Run ---
        rc = run_picker()

        # --- Assertions ---
        assert rc == 0

        # Prompt was collected and sent to the model
        mock_text.return_value.ask.assert_called_once()
        mock_provider.changes_from_prompt.assert_called_once_with(
            "Add email validation to auth.py",
        )

        # Endpoint reachability was checked
        mock_check.assert_called_once_with("https://api.test.com/v1")

        # Verify was called with the right args
        mock_verifier_cls.verify.assert_called_once_with(
            mock_result.claims,
            mock_result.changes,
        )

        # Report was rendered
        mock_reporter.report.assert_called_once()

        # Report was saved
        mock_save.assert_called_once_with("Mock report text")

        # Pause was called (user sees output before returning)
        assert mock_pause.called

    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ModelProvider")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_verify_empty_prompt(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_select: MagicMock,
        mock_text: MagicMock,
        mock_confirm: MagicMock,
        mock_provider_cls: MagicMock,
        mock_verifier_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Empty prompt should abort and return to menu, not call the model."""
        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Exit",
        ]
        mock_text.return_value.ask.return_value = ""

        mock_config = MagicMock()
        mock_config.load.return_value = {
            "api_key": "sk-test",
            "base_url": "https://api.test.com/v1",
            "model": "test-model",
        }
        mock_config_cls.return_value = mock_config

        rc = run_picker()

        assert rc == 0
        out, _ = capsys.readouterr()
        assert "No prompt provided" in out

        # Model should NOT be called
        mock_provider_cls.assert_not_called()
        mock_verifier_cls.verify.assert_not_called()
        mock_save.assert_not_called()

    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ModelProvider")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_verify_missing_config_prompts(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_select: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_confirm: MagicMock,
        mock_provider_cls: MagicMock,
        mock_verifier_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Missing config triggers setup prompt flow through the menu."""
        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Exit",
        ]
        mock_password.return_value.ask.return_value = "sk-new"
        mock_text.return_value.ask.return_value = "my prompt"
        # User says YES to setup config
        mock_confirm.return_value.ask.return_value = True

        # Config starts empty, then has data after setup
        mock_config = MagicMock()
        mock_config.load.side_effect = [
            {},
            {"api_key": "sk-new", "base_url": "https://api.new.com/v1", "model": "new-model"},
            {"api_key": "sk-new", "base_url": "https://api.new.com/v1", "model": "new-model"},
        ]
        mock_config_cls.return_value = mock_config

        mock_provider = MagicMock()
        mock_provider.changes_from_prompt.return_value = ModelResult(
            claims=[], changes=[], attempts=1,
        )
        mock_provider_cls.return_value = mock_provider

        rc = run_picker()

        assert rc == 0
        out, _ = capsys.readouterr()
        assert "You need to configure an API endpoint first." in out

    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ModelProvider")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_verify_missing_config_declined(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_select: MagicMock,
        mock_text: MagicMock,
        mock_confirm: MagicMock,
        mock_provider_cls: MagicMock,
        mock_verifier_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Declining config setup returns to menu without calling model."""
        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Exit",
        ]
        mock_text.return_value.ask.return_value = "my prompt"
        mock_confirm.return_value.ask.return_value = False

        mock_config = MagicMock()
        mock_config.load.return_value = {}
        mock_config_cls.return_value = mock_config

        rc = run_picker()

        assert rc == 0
        mock_provider_cls.assert_not_called()
        mock_verifier_cls.verify.assert_not_called()

    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_verify_model_error(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_select: MagicMock,
        mock_text: MagicMock,
        mock_confirm: MagicMock,
        mock_verifier_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A model error should be caught and reported to stderr."""
        from nowreck.model.provider import ModelError

        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Exit",
        ]
        mock_text.return_value.ask.return_value = "my prompt"

        mock_config = MagicMock()
        mock_config.load.return_value = {
            "api_key": "sk-test",
            "base_url": "https://api.test.com/v1",
            "model": "test-model",
        }
        mock_config_cls.return_value = mock_config

        with patch("nowreck.picker.ModelProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.changes_from_prompt.side_effect = ModelError("API returned 401")
            mock_provider_cls.return_value = mock_provider

            rc = run_picker()

        assert rc == 0
        captured = capsys.readouterr()
        assert "Error: API returned 401" in captured.err


class TestPickerIntegrationPrePost:
    """End-to-end flow: Scan directories → detect changes → report."""

    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.VerificationReport")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ChangeDetector")
    @patch("nowreck.picker.build_symbol_index")
    @patch("nowreck.picker.RepositoryScanner")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_pre_post_happy_path(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_scanner_cls: MagicMock,
        mock_build_sym: MagicMock,
        mock_detector: MagicMock,
        mock_verifier: MagicMock,
        mock_report_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Menu: Scan dirs → paths → detection runs → report printed + saved."""
        mock_select.return_value.ask.side_effect = [
            "Scan two directories for changes",  # main menu
            "No, just detect changes",            # claims choice
            "Exit",                               # after report pause
        ]
        # The menu asks select() 3 times: main menu, claims, then main menu again
        # But _run_pre_post handles the claims select, then returns to the loop
        # which calls select() again for the main menu
        # Actually, _run_pre_post contains its own select() call for claims.
        # So the first select() in run_picker returns "Scan two directories",
        # then inside _run_pre_post, select() returns "No, just detect changes",
        # then after _run_pre_post returns, run_picker's loop calls select() again.
        # So we need 3 values.

        mock_path.return_value.ask.side_effect = [
            "/tmp/pre_dir",
            "/tmp/post_dir",
        ]

        # Mock scanner
        mock_pre_scan = MagicMock()
        mock_pre_scan.success_count = 3
        mock_pre_scan.failure_count = 0
        mock_post_scan = MagicMock()
        mock_post_scan.success_count = 4
        mock_post_scan.failure_count = 0

        mock_scanner = MagicMock()
        mock_scanner.scan.side_effect = [mock_pre_scan, mock_post_scan]
        mock_scanner_cls.return_value = mock_scanner

        # Mock symbol indices
        mock_pre_sym = MagicMock()
        mock_pre_sym.all_symbols = ["a", "b"]
        mock_post_sym = MagicMock()
        mock_post_sym.all_symbols = ["a", "b", "c"]
        mock_build_sym.side_effect = [mock_pre_sym, mock_post_sym]

        # Mock detector
        mock_changes = [MagicMock(), MagicMock()]
        mock_detector.detect.return_value = mock_changes

        # Mock reporter
        mock_reporter = MagicMock()
        mock_reporter.report.return_value = "Pre/post report output"
        mock_reporter_cls.return_value = mock_reporter

        rc = run_picker()

        assert rc == 0

        # Paths were collected
        assert mock_path.return_value.ask.call_count == 2

        # Pipeline was called
        assert mock_scanner.scan.call_count == 2
        mock_detector.detect.assert_called_once()
        mock_verifier.verify.assert_not_called()  # No claims

        # Report was rendered and saved
        mock_reporter.report.assert_called_once()
        mock_save.assert_called_once_with("Pre/post report output")
        assert mock_pause.called

    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.VerificationReport")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ChangeDetector")
    @patch("nowreck.picker.build_symbol_index")
    @patch("nowreck.picker.RepositoryScanner")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_pre_post_with_claims_json(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_scanner_cls: MagicMock,
        mock_build_sym: MagicMock,
        mock_detector: MagicMock,
        mock_verifier: MagicMock,
        mock_report_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Pre/post mode with claims JSON should verify claims."""
        from nowreck.claims.parser import ParseResult

        mock_select.return_value.ask.side_effect = [
            "Scan two directories for changes",
            "Yes, enter claims JSON",
            "Exit",
        ]

        mock_path.return_value.ask.side_effect = [
            "/tmp/pre_dir",
            "/tmp/post_dir",
        ]

        # Mock text input for claims JSON
        with patch("nowreck.picker.questionary.text") as mock_text:
            mock_text.return_value.ask.return_value = '{"claims": [...]}'

            # Mock scanner
            mock_scanner = MagicMock()
            mock_pre_scan = MagicMock()
            mock_pre_scan.success_count = 1
            mock_pre_scan.failure_count = 0
            mock_post_scan = MagicMock()
            mock_post_scan.success_count = 1
            mock_post_scan.failure_count = 0
            mock_scanner.scan.side_effect = [mock_pre_scan, mock_post_scan]
            mock_scanner_cls.return_value = mock_scanner

            mock_pre_sym = MagicMock()
            mock_pre_sym.all_symbols = ["x"]
            mock_post_sym = MagicMock()
            mock_post_sym.all_symbols = ["x", "y"]
            mock_build_sym.side_effect = [mock_pre_sym, mock_post_sym]

            mock_changes = [MagicMock()]
            mock_detector.detect.return_value = mock_changes

            # Mock parser and verifier
            mock_parse_result = MagicMock(spec=ParseResult)
            mock_parse_result.success = True
            mock_parse_result.claims = [MagicMock()]
            mock_parse_result.errors = []

            with patch("nowreck.picker.ClaimParser.parse",
                       return_value=mock_parse_result):
                mock_report = VerificationReport(
                    results=[
                        VerificationResult(
                            claim=Claim(
                                type=ClaimType.ADD_FUNCTION,
                                symbol_name="foo",
                                file_path="bar.py",
                            ),
                            verdict=Verdict.CONFIRMED,
                        ),
                    ],
                )
                mock_verifier.verify.return_value = mock_report

                mock_reporter = MagicMock()
                mock_reporter.report.return_value = "Claims report"
                mock_reporter_cls.return_value = mock_reporter

                rc = run_picker()

        assert rc == 0
        mock_verifier.verify.assert_called_once()

    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.TerminalReporter")
    def test_ctrl_c_on_pre_path_exits(
        self,
        mock_reporter_cls: MagicMock,
        mock_path: MagicMock,
    ) -> None:
        """Ctrl+C on pre path should exit the picker immediately."""
        with patch("nowreck.picker.questionary.select") as mock_select:
            mock_select.return_value.ask.side_effect = [
                "Scan two directories for changes",
                "Exit",
            ]
            mock_path.return_value.ask.return_value = None

            rc = run_picker()

        assert rc == 0

    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.VerificationReport")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ChangeDetector")
    @patch("nowreck.picker.build_symbol_index")
    @patch("nowreck.picker.RepositoryScanner")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_pre_post_claims_from_file(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_scanner_cls: MagicMock,
        mock_build_sym: MagicMock,
        mock_detector: MagicMock,
        mock_verifier: MagicMock,
        mock_report_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Claims loaded from file should be verified through the full flow."""
        from nowreck.claims.parser import ParseResult

        mock_select.return_value.ask.side_effect = [
            "Scan two directories for changes",
            "Yes, load from a file",
            "Exit",
        ]

        mock_path.return_value.ask.side_effect = [
            "/tmp/pre_dir",
            "/tmp/post_dir",
            "/tmp/claims.json",
        ]

        with patch("nowreck.picker.Path.read_text",
                   return_value='{"claims": []}'):
            mock_scanner = MagicMock()
            mock_pre_scan = MagicMock()
            mock_pre_scan.success_count = 1
            mock_pre_scan.failure_count = 0
            mock_post_scan = MagicMock()
            mock_post_scan.success_count = 1
            mock_post_scan.failure_count = 0
            mock_scanner.scan.side_effect = [mock_pre_scan, mock_post_scan]
            mock_scanner_cls.return_value = mock_scanner

            mock_pre_sym = MagicMock()
            mock_pre_sym.all_symbols = ["x"]
            mock_post_sym = MagicMock()
            mock_post_sym.all_symbols = ["x", "y"]
            mock_build_sym.side_effect = [mock_pre_sym, mock_post_sym]

            mock_changes = [MagicMock()]
            mock_detector.detect.return_value = mock_changes

            mock_parse_result = MagicMock(spec=ParseResult)
            mock_parse_result.success = True
            mock_parse_result.claims = [MagicMock()]
            mock_parse_result.errors = []

            with patch("nowreck.picker.ClaimParser.parse",
                       return_value=mock_parse_result):
                mock_report = VerificationReport(
                    results=[
                        VerificationResult(
                            claim=Claim(
                                type=ClaimType.ADD_FUNCTION,
                                symbol_name="bar",
                                file_path="baz.py",
                            ),
                            verdict=Verdict.CONFIRMED,
                        ),
                    ],
                )
                mock_verifier.verify.return_value = mock_report

                mock_reporter = MagicMock()
                mock_reporter.report.return_value = "Claims from file report"
                mock_reporter_cls.return_value = mock_reporter

                rc = run_picker()

        assert rc == 0
        mock_verifier.verify.assert_called_once()
        mock_reporter.report.assert_called_once()
        mock_save.assert_called_once_with("Claims from file report")


class TestPickerIntegrationConfig:
    """End-to-end flow: Set up API key."""

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_config_setup_flow(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_select: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
    ) -> None:
        """Selecting 'Set up API key' should save config and return to menu."""
        mock_select.return_value.ask.side_effect = [
            "Set up or change your API key",
            "Exit",
        ]

        mock_config = MagicMock()
        mock_config.load.return_value = {}
        mock_config_cls.return_value = mock_config

        mock_password.return_value.ask.return_value = "sk-mykey"
        mock_text.return_value.ask.side_effect = [
            "https://api.test.com/v1",
            "my-model",
        ]

        rc = run_picker()

        assert rc == 0
        mock_config.save.assert_called_once_with({
            "api_key": "sk-mykey",
            "base_url": "https://api.test.com/v1",
            "model": "my-model",
        })

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_config_setup_preserves_existing(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_select: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
    ) -> None:
        """Empty fields in config setup should preserve existing values."""
        mock_select.return_value.ask.side_effect = [
            "Set up or change your API key",
            "Exit",
        ]

        mock_config = MagicMock()
        mock_config.load.return_value = {
            "api_key": "sk-existing",
            "base_url": "https://existing.com/v1",
            "model": "existing-model",
        }
        mock_config_cls.return_value = mock_config

        # All empty — user just pressed Enter on defaults
        mock_password.return_value.ask.return_value = ""
        mock_text.return_value.ask.side_effect = ["", ""]

        rc = run_picker()

        assert rc == 0
        mock_config.save.assert_called_once_with({
            "api_key": "sk-existing",
            "base_url": "https://existing.com/v1",
            "model": "existing-model",
        })


class TestPickerIntegrationViewReport:
    """End-to-end flow: View last report."""

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker._resolve_last_report_path")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_view_report_found(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
        mock_resolve: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Viewing a saved report should display its contents."""
        mock_select.return_value.ask.side_effect = [
            "View last report",
            "Exit",
        ]

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "Previous report content"
        mock_resolve.return_value = mock_path

        rc = run_picker()

        assert rc == 0
        out = capsys.readouterr().out
        assert "Previous report content" in out

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker._resolve_last_report_path")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_view_report_not_found(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
        mock_resolve: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """When no report file exists, a message should be shown."""
        mock_select.return_value.ask.side_effect = [
            "View last report",
            "Exit",
        ]

        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_resolve.return_value = mock_path

        rc = run_picker()

        assert rc == 0
        out = capsys.readouterr().out
        assert "No previous report found" in out


class TestPickerIntegrationMultiAction:
    """Multiple menu actions in sequence."""

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_all_five_actions_in_sequence(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
        mock_verify: MagicMock,
        mock_pre_post: MagicMock,
        mock_config: MagicMock,
        mock_view: MagicMock,
    ) -> None:
        """User goes through all five options: Verify → Scan → Config → View → Exit."""
        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Scan two directories for changes",
            "Set up or change your API key",
            "View last report",
            "Exit",
        ]

        rc = run_picker()

        assert rc == 0
        mock_verify.assert_called_once()
        mock_pre_post.assert_called_once()
        mock_config.assert_called_once()
        mock_view.assert_called_once()

    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_ctrl_c_returns_cleanly(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """Ctrl+C (None from questionary) should exit immediately."""
        mock_select.return_value.ask.return_value = None

        rc = run_picker()

        assert rc == 0

    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_repeated_verify_calls(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """Running verify twice should call _run_verification twice."""
        with patch("nowreck.picker._run_verification") as mock_verify:
            mock_select.return_value.ask.side_effect = [
                "Verify with AI prompt",
                "Verify with AI prompt",
                "Exit",
            ]

            rc = run_picker()

            assert rc == 0
            assert mock_verify.call_count == 2


class TestPickerIntegrationExit:
    """Exit behavior edge cases."""

    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_exit_first_action(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """Exit selected immediately should exit cleanly."""
        mock_select.return_value.ask.return_value = "Exit"
        assert run_picker() == 0

    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_returns_zero_always(
        self,
        mock_reporter_cls: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """run_picker should always return 0 regardless of flow."""
        mock_select.return_value.ask.return_value = None
        assert run_picker() == 0


# ============================================================================
# PTY-based terminal test
#
# This test uses Python's stdlib pty module to create a pseudo-terminal and
# script keystrokes into the real ``nowreck --interactive`` binary.  It
# verifies that the menu renders correctly and responds to keyboard input
# in a real terminal environment — no mocking of questionary.
#
# Skipped when tmux is not available (CI, headless environments).
# ============================================================================


class TestPickerTerminal:
    """Real-terminal integration tests using tmux.

    These tests are slower than the mocked tests and require tmux, but
    they verify that ``nowreck --interactive`` actually renders and
    responds to keyboard input in a real PTY environment.

    Skipped when tmux is not available (CI, headless machines).
    """

    _TMUX_SESSION = "nw_picker_term"

    @staticmethod
    def _has_tmux() -> bool:
        import shutil
        return shutil.which("tmux") is not None

    def _poll_pane(
        self,
        expected: str,
        timeout: float = 6.0,
        interval: float = 0.3,
    ) -> str:
        """Poll the tmux pane until *expected* appears or *timeout* elapses.

        Uses ``-S -`` (scrollback) and ``-e`` (preserve ANSI) for best
        compatibility with questionary's cursor-based rendering.

        Returns the full pane content at the end of polling.
        """
        import subprocess
        import time

        deadline = time.monotonic() + timeout
        last_output = ""
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self._TMUX_SESSION,
                 "-p", "-S", "-", "-e"],
                capture_output=True, text=True, timeout=5,
            )
            last_output = result.stdout
            if expected in last_output:
                break
            time.sleep(interval)
        return last_output

    def _session_exists(self) -> bool:
        """Check whether the tmux session is still alive."""
        import subprocess
        result = subprocess.run(
            ["tmux", "has-session", "-t", self._TMUX_SESSION],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0

    def _poll_session_dead(self, timeout: float = 5.0) -> bool:
        """Wait for the tmux session to die (process exited)."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._session_exists():
                return True
            time.sleep(0.3)
        return False

    def _cleanup(self) -> None:
        """Kill the tmux session if it still exists."""
        import subprocess
        subprocess.run(
            ["tmux", "kill-session", "-t", self._TMUX_SESSION],
            capture_output=True, timeout=5,
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_menu_renders_in_terminal(self) -> None:
        """The menu should display all five options."""
        if not self._has_tmux():
            pytest.skip("tmux not available")

        import subprocess

        self._cleanup()

        try:
            # Start nowreck --interactive in a headless tmux session
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", self._TMUX_SESSION,
                 "nowreck --interactive"],
                capture_output=True, timeout=5,
            )

            # Poll until the menu appears
            output = self._poll_pane("What would you like to do?", timeout=6.0)

            assert "What would you like to do?" in output, (
                f"Menu prompt not found. Output:\n{output}"
            )
            assert "Verify with AI prompt" in output, (
                f"Verify option not found. Output:\n{output}"
            )
            assert "Scan two directories for changes" in output, (
                f"Scan dirs option not found. Output:\n{output}"
            )
            assert "Set up or change your API key" in output, (
                f"Config option not found. Output:\n{output}"
            )
            assert "View last report" in output, (
                f"View report option not found. Output:\n{output}"
            )
            assert "Exit" in output, (
                f"Exit option not found. Output:\n{output}"
            )

        finally:
            self._cleanup()

    def test_exit_via_ctrl_c(self) -> None:
        """Ctrl+C should exit the picker cleanly."""
        if not self._has_tmux():
            pytest.skip("tmux not available")

        import subprocess

        self._cleanup()

        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", self._TMUX_SESSION,
                 "nowreck --interactive"],
                capture_output=True, timeout=5,
            )

            # Wait for menu
            self._poll_pane("What would you like to do?", timeout=6.0)

            # Send Ctrl+C
            subprocess.run(
                ["tmux", "send-keys", "-t", self._TMUX_SESSION, "C-c"],
                capture_output=True, timeout=5,
            )

            # Poll until the session dies (process exited)
            died = self._poll_session_dead(timeout=5.0)
            assert died, (
                "nowreck did not exit within 5s after Ctrl+C "
                "— session still alive"
            )

        finally:
            self._cleanup()

    def test_empty_prompt_flow(self) -> None:
        """Sending an empty prompt should show 'No prompt provided'."""
        if not self._has_tmux():
            pytest.skip("tmux not available")

        import subprocess

        self._cleanup()

        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", self._TMUX_SESSION,
                 "nowreck --interactive"],
                capture_output=True, timeout=5,
            )

            # --- Step 1: Wait for menu, select Verify by pressing Enter ---
            self._poll_pane("What would you like to do?", timeout=6.0)

            subprocess.run(
                ["tmux", "send-keys", "-t", self._TMUX_SESSION, "Enter"],
                capture_output=True, timeout=5,
            )

            # --- Step 2: Wait for the text prompt to render ---
            output = self._poll_pane("Describe the change", timeout=6.0)

            # --- Step 3: Send Enter to submit empty prompt ---
            subprocess.run(
                ["tmux", "send-keys", "-t", self._TMUX_SESSION, "Enter"],
                capture_output=True, timeout=5,
            )

            # --- Step 4: Wait for the result message ---
            output = self._poll_pane("No prompt provided", timeout=6.0)

            assert "No prompt provided" in output, (
                f"Expected 'No prompt provided' in:\n{output}"
            )
            assert "Press Enter to return to the main menu" in output, (
                f"Expected menu return prompt in:\n{output}"
            )

        finally:
            self._cleanup()
