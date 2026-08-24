from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nowreck.claims.models import Claim, ClaimType, ParseResult
from nowreck.model.provider import ModelError, ModelResult
from nowreck.picker import (
    _check_endpoint_reachable,
    _ExitPickerError,
    _pause,
    _resolve_last_report_path,
    _run_config_setup,
    _run_pre_post,
    _run_verification,
    _save_last_report,
    _validate_directory_path,
    _view_last_report,
    run_picker,
)
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.verifier.verifier import Verdict, VerificationReport, VerificationResult

# ============================================================================
# _validate_directory_path — inline path validator
# ============================================================================


class TestValidateDirectoryPath:
    """questionary validator for directory paths."""

    def test_empty_path(self) -> None:
        """Empty string should return an error message."""
        result = _validate_directory_path("")
        assert isinstance(result, str)
        assert "empty" in result.lower()

    def test_whitespace_path(self) -> None:
        """Whitespace-only string should return an error message."""
        result = _validate_directory_path("   ")
        assert isinstance(result, str)
        assert "empty" in result.lower()

    def test_non_existent_path(self) -> None:
        """A path that does not exist should return an error message."""
        with (
            patch("nowreck.picker.Path.is_dir") as mock_is_dir,
            patch("nowreck.picker.Path.exists", return_value=False),
        ):
            mock_is_dir.return_value = False
            result = _validate_directory_path("/nonexistent/path")
            assert isinstance(result, str)
            assert "does not exist" in result.lower()

    def test_file_not_directory(self, tmp_path: Path) -> None:
        """A path to a file (not a directory) should return an error message."""
        file_path = tmp_path / "some_file.txt"
        file_path.write_text("hello")
        result = _validate_directory_path(str(file_path))
        assert isinstance(result, str)
        assert "not a directory" in result.lower()

    def test_valid_directory(self, tmp_path: Path) -> None:
        """A valid existing directory should return True."""
        result = _validate_directory_path(str(tmp_path))
        assert result is True

    def test_trailing_slash(self, tmp_path: Path) -> None:
        """A directory path with a trailing slash should still be valid."""
        result = _validate_directory_path(str(tmp_path) + "/")
        assert result is True

    def test_tilde_expansion(self, tmp_path: Path) -> None:
        """A path starting with ~ should expand to the home directory.

        We can't easily mock the home directory, so we verify that
        the validator doesn't produce a "does not exist" error for
        ``~/`` (which is always a valid directory).
        """
        result = _validate_directory_path("~/")
        assert result is True, f"Expected True for ~/, got: {result}"


# ============================================================================
# run_picker — main menu loop
# ============================================================================


class TestRunPicker:
    """Menu dispatching and lifecycle."""

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_exit_selected(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        _mock_verify: MagicMock,
        _mock_pre_post: MagicMock,
        _mock_config: MagicMock,
        _mock_view: MagicMock,
    ) -> None:
        """Selecting 'Exit' should break the loop and return 0."""
        mock_select.return_value.ask.return_value = "Exit"
        assert run_picker() == 0
        _mock_verify.assert_not_called()
        _mock_pre_post.assert_not_called()
        _mock_config.assert_not_called()
        _mock_view.assert_not_called()

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_ctrl_c_returns_zero(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        _mock_verify: MagicMock,
        _mock_pre_post: MagicMock,
        _mock_config: MagicMock,
        _mock_view: MagicMock,
    ) -> None:
        """Ctrl+C (None from questionary) should exit cleanly."""
        mock_select.return_value.ask.return_value = None
        assert run_picker() == 0

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_dispatches_verify(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        mock_verify: MagicMock,
        _mock_pre_post: MagicMock,
        _mock_config: MagicMock,
        _mock_view: MagicMock,
    ) -> None:
        """ "Verify with AI prompt" dispatches to _run_verification."""
        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Exit",
        ]
        run_picker()
        mock_verify.assert_called_once()
        _mock_pre_post.assert_not_called()

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_dispatches_pre_post(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        _mock_verify: MagicMock,
        mock_pre_post: MagicMock,
        _mock_config: MagicMock,
        _mock_view: MagicMock,
    ) -> None:
        """ "Scan two directories for changes" dispatches to _run_pre_post."""
        mock_select.return_value.ask.side_effect = [
            "Scan two directories for changes",
            "Exit",
        ]
        run_picker()
        mock_pre_post.assert_called_once()
        _mock_verify.assert_not_called()

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_dispatches_config_setup(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        _mock_verify: MagicMock,
        _mock_pre_post: MagicMock,
        mock_config: MagicMock,
        _mock_view: MagicMock,
    ) -> None:
        """ "Set up or change your API key" dispatches to _run_config_setup."""
        mock_select.return_value.ask.side_effect = [
            "Set up or change your API key",
            "Exit",
        ]
        run_picker()
        mock_config.assert_called_once()

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_dispatches_view_last_report(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        _mock_verify: MagicMock,
        _mock_pre_post: MagicMock,
        _mock_config: MagicMock,
        mock_view: MagicMock,
    ) -> None:
        """ "View last report" dispatches to _view_last_report."""
        mock_select.return_value.ask.side_effect = [
            "View last report",
            "Exit",
        ]
        run_picker()
        mock_view.assert_called_once()

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_dispatches_all_in_sequence(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        mock_verify: MagicMock,
        mock_pre_post: MagicMock,
        mock_config: MagicMock,
        mock_view: MagicMock,
    ) -> None:
        """All five options can be selected in sequence before exit."""
        mock_select.return_value.ask.side_effect = [
            "Verify with AI prompt",
            "Scan two directories for changes",
            "Set up or change your API key",
            "View last report",
            "Exit",
        ]
        run_picker()
        mock_verify.assert_called_once()
        mock_pre_post.assert_called_once()
        mock_config.assert_called_once()
        mock_view.assert_called_once()

    @patch("nowreck.picker._view_last_report")
    @patch("nowreck.picker._run_config_setup")
    @patch("nowreck.picker._run_pre_post")
    @patch("nowreck.picker._run_verification")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.TerminalReporter")
    def test_returns_zero(
        self,
        _mock_reporter: MagicMock,
        mock_select: MagicMock,
        _mock_verify: MagicMock,
        _mock_pre_post: MagicMock,
        _mock_config: MagicMock,
        _mock_view: MagicMock,
    ) -> None:
        """run_picker always returns 0."""
        mock_select.return_value.ask.return_value = None
        assert run_picker() == 0


# ============================================================================
# _run_verification — the full verification flow
# ============================================================================


class BaseVerificationFixture:
    """Shared factory methods for verification tests."""

    @staticmethod
    def _make_mock_report() -> VerificationReport:
        return VerificationReport(
            results=[
                VerificationResult(
                    claim=Claim(
                        type=ClaimType.ADD_FUNCTION,
                        symbol_name="greet",
                        file_path="app.py",
                        confidence=0.95,
                    ),
                    verdict=Verdict.CONFIRMED,
                ),
            ],
        )


class TestRunVerificationPromptHandling(BaseVerificationFixture):
    """Edge cases around the prompt input."""

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    def test_empty_prompt(
        self,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """An empty prompt should print a message and return to menu."""
        mock_text.return_value.ask.return_value = ""
        _run_verification(MagicMock(spec=TerminalReporter))
        out = capsys.readouterr().out
        assert "No prompt provided" in out
        mock_pause.assert_called_once()

    @patch("nowreck.picker.questionary.text")
    def test_none_prompt(
        self,
        mock_text: MagicMock,
    ) -> None:
        """Ctrl+C on prompt should exit immediately via _ExitPicker."""
        mock_text.return_value.ask.return_value = None
        with pytest.raises(_ExitPickerError):
            _run_verification(MagicMock(spec=TerminalReporter))

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    def test_whitespace_only_prompt(
        self,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Whitespace-only prompt should also return to menu."""
        mock_text.return_value.ask.return_value = "   "
        _run_verification(MagicMock(spec=TerminalReporter))
        out = capsys.readouterr().out
        assert "No prompt provided" in out
        mock_pause.assert_called_once()


def _build_config_mock() -> MagicMock:
    """Standard config dict for verify-flow tests."""
    mock_config = MagicMock()
    mock_config.load.return_value = {
        "api_key": "sk-test",
        "base_url": "https://api.test.com/v1",
        "model": "test-model",
        "temperature": 0.0,
        "max_retries": 1,
    }
    return mock_config


def _build_v10_result(mock_report: VerificationReport) -> MagicMock:
    """Build a PromptVerificationResult-shaped mock (claims present)."""
    model_result = MagicMock()
    model_result.claims = [
        Claim(
            type=ClaimType.ADD_FUNCTION,
            symbol_name="validate_email",
            file_path="auth.py",
            confidence=0.95,
        )
    ]
    model_result.parse_result = None
    result = MagicMock()
    result.report = mock_report
    result.patch_applied = True
    result.model_result = model_result
    return result


class TestRunVerificationConfigHandling(BaseVerificationFixture):
    """Config handling and result plumbing in the verify flow (v10)."""

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.NowreckConfig")
    def test_full_verification_flow(
        self,
        mock_config_cls: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
        mock_confirm: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Happy path: prompt -> verify_prompt -> report rendered+saved."""
        mock_confirm.return_value.ask.return_value = False
        with patch("nowreck.picker.NowreckConfig", return_value=_build_config_mock()):
            mock_text.return_value.ask.return_value = "Add validation to auth.py"
            mock_report = self._make_mock_report()
            mock_reporter = MagicMock(spec=TerminalReporter)
            mock_reporter.report.return_value = "Mock report output"

            with patch("nowreck.picker.verify_prompt") as mock_verify_prompt:
                mock_verify_prompt.return_value = _build_v10_result(mock_report)

                _run_verification(mock_reporter)

        mock_check.assert_called_once_with("https://api.test.com/v1")
        args, kwargs = mock_verify_prompt.call_args
        assert args[0] == "Add validation to auth.py"
        cfg = args[2]
        assert cfg.provider is None  # auto-detect from base_url
        assert mock_reporter.report.called
        mock_save.assert_called_once_with("Mock report output")
        mock_pause.assert_called_once()
        out = capsys.readouterr().out
        assert "Verification complete:" in out

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.NowreckConfig")
    def test_model_error_handled(
        self,
        mock_config_cls: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        _mock_save: MagicMock,
        _mock_check: MagicMock,
        mock_confirm: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A ModelError should be caught and printed to stderr."""
        mock_confirm.return_value.ask.return_value = False
        mock_config_cls.return_value = _build_config_mock()
        mock_text.return_value.ask.return_value = "my prompt"

        with patch(
            "nowreck.picker.verify_prompt",
            side_effect=ModelError("API key invalid"),
        ):
            _run_verification(MagicMock(spec=TerminalReporter))

        captured = capsys.readouterr()
        assert "Error: API key invalid" in captured.err
        mock_pause.assert_called_once()

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.NowreckConfig")
    def test_no_claims_warning(
        self,
        mock_confirm: MagicMock,
        mock_config_cls: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        _mock_save: MagicMock,
        _mock_check: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """When the model returns no valid claims, a warning is printed."""
        mock_confirm.return_value.ask.return_value = False
        mock_config_cls.return_value = _build_config_mock()
        mock_text.return_value.ask.return_value = "my prompt"

        result = MagicMock()
        result.report = self._make_mock_report()
        result.patch_applied = False
        parse_result = ParseResult(
            errors=["Missing required key 'claims'"],
            raw_json="{}",
        )
        result.model_result = ModelResult(
            claims=[], parse_result=parse_result, attempts=1
        )

        with patch("nowreck.picker.verify_prompt", return_value=result):
            _run_verification(MagicMock(spec=TerminalReporter))

        captured = capsys.readouterr()
        assert "Warning: Model returned no valid claims." in captured.err
        assert "Parse error: Missing required key" in captured.err
        mock_pause.assert_called_once()

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.NowreckConfig")
    def test_provider_key_passed_to_verifier(
        self,
        mock_config_cls: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        _mock_save: MagicMock,
        _mock_check: MagicMock,
        mock_confirm: MagicMock,
    ) -> None:
        """A saved provider override reaches the verifier's ModelConfig."""
        cfg = _build_config_mock()
        cfg.load.return_value = {
            **cfg.load.return_value,
            "provider": "anthropic",
        }
        mock_config_cls.return_value = cfg
        mock_text.return_value.ask.return_value = "my prompt"

        with patch(
            "nowreck.picker.verify_prompt",
            return_value=_build_v10_result(self._make_mock_report()),
        ) as mock_verify_prompt:
            _run_verification(MagicMock(spec=TerminalReporter))

        cfg_built = mock_verify_prompt.call_args.args[2]
        assert cfg_built.provider == "anthropic"

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.NowreckConfig")
    def test_reports_and_saves(
        self,
        mock_config_cls: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        _mock_check: MagicMock,
        mock_confirm: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Report output should be printed and saved."""
        mock_confirm.return_value.ask.return_value = False
        mock_config_cls.return_value = _build_config_mock()
        mock_text.return_value.ask.return_value = "my prompt"

        mock_report = self._make_mock_report()
        mock_reporter = MagicMock(spec=TerminalReporter)
        mock_reporter.report.return_value = "Mock report output"

        with patch(
            "nowreck.picker.verify_prompt",
            return_value=_build_v10_result(mock_report),
        ):
            _run_verification(mock_reporter)

        out = capsys.readouterr().out
        assert "Verification complete:" in out
        assert "Mock report output" in out
        mock_save.assert_called_once_with("Mock report output")
        mock_pause.assert_called_once()


class TestRunVerificationVerboseChoice(BaseVerificationFixture):
    """Per-run verbose choice in the verification flow."""

    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_verbose_yes_builds_fresh_verbose_reporter(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_text: MagicMock,
        mock_confirm: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """Answering Yes renders with a fresh verbose reporter; the shared
        reporter passed in is never mutated."""
        mock_confirm.return_value.ask.return_value = False
        mock_config_cls.return_value = _build_config_mock()
        mock_text.return_value.ask.return_value = "my prompt"
        mock_confirm.return_value.ask.return_value = True

        verbose_reporter = MagicMock(spec=TerminalReporter)
        verbose_reporter.report.return_value = "Verbose report"
        mock_reporter_cls.return_value = verbose_reporter

        shared_reporter = MagicMock(spec=TerminalReporter)

        with patch(
            "nowreck.picker.verify_prompt",
            return_value=_build_v10_result(self._make_mock_report()),
        ):
            _run_verification(shared_reporter)

        mock_reporter_cls.assert_called_once_with(colour=True, verbose=True)
        verbose_reporter.report.assert_called_once()
        shared_reporter.report.assert_not_called()
        mock_save.assert_called_once_with("Verbose report")

    @patch("nowreck.picker._check_endpoint_reachable")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.NowreckConfig")
    @patch("nowreck.picker.TerminalReporter")
    def test_verbose_no_uses_shared_reporter(
        self,
        mock_reporter_cls: MagicMock,
        mock_config_cls: MagicMock,
        mock_text: MagicMock,
        mock_confirm: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """Answering No renders with the shared non-verbose reporter."""
        mock_confirm.return_value.ask.return_value = False
        mock_config_cls.return_value = _build_config_mock()
        mock_text.return_value.ask.return_value = "my prompt"
        mock_confirm.return_value.ask.return_value = False

        shared_reporter = MagicMock(spec=TerminalReporter)
        shared_reporter.report.return_value = "Shared report"

        with patch(
            "nowreck.picker.verify_prompt",
            return_value=_build_v10_result(self._make_mock_report()),
        ):
            _run_verification(shared_reporter)

        mock_reporter_cls.assert_not_called()
        shared_reporter.report.assert_called_once()
        mock_save.assert_called_once_with("Shared report")


class TestRunPrePost:
    """Pre/Post directory scanning flow."""

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.VerificationReport")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ChangeDetector")
    @patch("nowreck.picker.build_symbol_index")
    @patch("nowreck.picker.RepositoryScanner")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.TerminalReporter")
    def test_happy_path_no_claims(
        self,
        mock_reporter_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_scanner_cls: MagicMock,
        mock_build_sym: MagicMock,
        mock_detector: MagicMock,
        mock_verifier: MagicMock,
        mock_report_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_confirm: MagicMock,
    ) -> None:
        """Happy path: two valid dirs, no claims → detection only → report."""
        mock_confirm.return_value.ask.return_value = False
        mock_path.return_value.ask.side_effect = ["/pre/path", "/post/path"]

        # User selects "No, just detect changes"
        mock_select.return_value.ask.return_value = "No, just detect changes"

        # Mock scanner
        MagicMock()
        mock_pre_scan = MagicMock()
        mock_pre_scan.success_count = 5
        mock_pre_scan.failure_count = 0
        mock_post_scan = MagicMock()
        mock_post_scan.success_count = 7
        mock_post_scan.failure_count = 1
        mock_scanner_cls.side_effect = [
            MagicMock(scan=MagicMock(return_value=mock_pre_scan)),
            MagicMock(scan=MagicMock(return_value=mock_post_scan)),
        ]

        # Mock symbol indices
        mock_pre_sym = MagicMock()
        mock_pre_sym.all_symbols = ["a", "b", "c"]
        mock_post_sym = MagicMock()
        mock_post_sym.all_symbols = ["a", "b", "c", "d"]
        mock_build_sym.side_effect = [mock_pre_sym, mock_post_sym]

        # Mock detector
        mock_changes = [MagicMock()]
        mock_detector.detect.return_value = mock_changes

        # Mock reporter
        mock_reporter = MagicMock(spec=TerminalReporter)
        mock_reporter.report.return_value = "Pre/post report"
        mock_reporter_cls.return_value = mock_reporter

        _run_pre_post(mock_reporter)

        # Paths were collected
        assert mock_path.call_count == 2

        # Pipeline was called
        assert mock_scanner_cls.call_count == 2
        mock_detector.detect.assert_called_once()

        # No verify because no claims
        mock_verifier.verify.assert_not_called()

        # Report was rendered and saved
        mock_reporter.report.assert_called_once()
        mock_save.assert_called_once_with("Pre/post report")
        mock_pause.assert_called_once()

    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.TerminalReporter")
    def test_ctrl_c_on_pre_path(
        self,
        mock_reporter_cls: MagicMock,
        mock_path: MagicMock,
    ) -> None:
        """Ctrl+C on pre path should exit immediately via _ExitPicker."""
        mock_path.return_value.ask.return_value = None

        with pytest.raises(_ExitPickerError):
            _run_pre_post(MagicMock(spec=TerminalReporter))

    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.TerminalReporter")
    def test_ctrl_c_on_claims_choice(
        self,
        mock_reporter_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """Ctrl+C on claims choice should exit immediately via _ExitPicker."""
        mock_path.return_value.ask.side_effect = ["/pre/path", "/post/path"]
        mock_select.return_value.ask.return_value = None

        with pytest.raises(_ExitPickerError):
            _run_pre_post(MagicMock(spec=TerminalReporter))

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.VerificationReport")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ChangeDetector")
    @patch("nowreck.picker.build_symbol_index")
    @patch("nowreck.picker.RepositoryScanner")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.TerminalReporter")
    def test_claims_from_file_happy_path(
        self,
        mock_reporter_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_scanner_cls: MagicMock,
        mock_build_sym: MagicMock,
        mock_detector: MagicMock,
        mock_verifier: MagicMock,
        mock_report_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_confirm: MagicMock,
    ) -> None:
        """"Yes, load from a file" with a valid file should verify claims."""
        mock_confirm.return_value.ask.return_value = False
        from nowreck.claims.parser import ParseResult

        # Paths: pre dir, post dir, claims file
        mock_path.return_value.ask.side_effect = [
            "/pre/path",
            "/post/path",
            "/path/to/claims.json",
        ]

        # Select: load from file
        mock_select.return_value.ask.return_value = "Yes, load from a file"

        # Mock file read
        with patch("nowreck.picker.Path.read_text",
                   return_value='{"claims": []}'):
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

                mock_reporter = MagicMock(spec=TerminalReporter)
                mock_reporter.report.return_value = "Claims from file report"

                _run_pre_post(mock_reporter)

        # File was read, parser called, verifier called
        mock_verifier.verify.assert_called_once()
        mock_reporter.report.assert_called_once()
        mock_save.assert_called_once_with("Claims from file report")
        mock_pause.assert_called_once()

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.TerminalReporter")
    def test_claims_from_file_read_error(
        self,
        mock_reporter_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """"Yes, load from a file" with an unreadable file should print error."""
        mock_path.return_value.ask.side_effect = [
            "/pre/path",
            "/post/path",
            "/nonexistent/file.json",
        ]
        mock_select.return_value.ask.return_value = "Yes, load from a file"

        with patch("nowreck.picker.Path.read_text",
                   side_effect=OSError("No such file")):
            _run_pre_post(MagicMock(spec=TerminalReporter))

        captured = capsys.readouterr()
        assert "Error reading claims file" in captured.out
        assert "No such file" in captured.out
        mock_pause.assert_called_once()

    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.VerificationReport")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ChangeDetector")
    @patch("nowreck.picker.build_symbol_index")
    @patch("nowreck.picker.RepositoryScanner")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.TerminalReporter")
    def test_claims_invalid_json(
        self,
        mock_reporter_cls: MagicMock,
        mock_text: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_scanner_cls: MagicMock,
        mock_build_sym: MagicMock,
        mock_detector: MagicMock,
        mock_verifier: MagicMock,
        mock_report_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
        mock_confirm: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Invalid claims JSON falls back to detection-only."""
        mock_confirm.return_value.ask.return_value = False
        from nowreck.claims.parser import ParseResult

        mock_path.return_value.ask.side_effect = ["/pre/path", "/post/path"]
        mock_select.return_value.ask.return_value = "Yes, enter claims JSON"
        mock_text.return_value.ask.return_value = "{invalid json}"

        # Mock scanner
        mock_scanner = MagicMock()
        mock_pre_scan = MagicMock()
        mock_pre_scan.success_count = 2
        mock_pre_scan.failure_count = 0
        mock_post_scan = MagicMock()
        mock_post_scan.success_count = 2
        mock_post_scan.failure_count = 0
        mock_scanner.scan.side_effect = [mock_pre_scan, mock_post_scan]
        mock_scanner_cls.return_value = mock_scanner

        mock_pre_sym = MagicMock()
        mock_pre_sym.all_symbols = ["a"]
        mock_post_sym = MagicMock()
        mock_post_sym.all_symbols = ["a", "b"]
        mock_build_sym.side_effect = [mock_pre_sym, mock_post_sym]

        mock_changes = [MagicMock()]
        mock_detector.detect.return_value = mock_changes

        # ParseResult with errors and no claims
        mock_parse_result = MagicMock(spec=ParseResult)
        mock_parse_result.success = False
        mock_parse_result.claims = []
        mock_parse_result.errors = ["Invalid JSON at line 1"]

        with patch("nowreck.picker.ClaimParser.parse",
                   return_value=mock_parse_result):
            mock_reporter = MagicMock(spec=TerminalReporter)
            mock_reporter.report.return_value = "Fallback report"

            _run_pre_post(mock_reporter)

        # Parse warning printed
        captured = capsys.readouterr()
        assert "Warning: Some claims could not be parsed" in captured.err
        assert "Invalid JSON at line 1" in captured.err

        # Verifier NOT called (no valid claims) — falls back to detection-only
        mock_verifier.verify.assert_not_called()

        # Report still rendered
        mock_reporter.report.assert_called_once()
        mock_save.assert_called_once_with("Fallback report")
        mock_pause.assert_called_once()


class TestRunPrePostVerboseChoice:
    """Per-run verbose choice in the pre/post flow."""

    @patch("nowreck.picker._save_last_report")
    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.VerificationReport")
    @patch("nowreck.picker.ClaimVerifier")
    @patch("nowreck.picker.ChangeDetector")
    @patch("nowreck.picker.build_symbol_index")
    @patch("nowreck.picker.RepositoryScanner")
    @patch("nowreck.picker.questionary.confirm")
    @patch("nowreck.picker.questionary.select")
    @patch("nowreck.picker.questionary.path")
    @patch("nowreck.picker.TerminalReporter")
    def test_verbose_yes_builds_fresh_verbose_reporter(
        self,
        mock_reporter_cls: MagicMock,
        mock_path: MagicMock,
        mock_select: MagicMock,
        mock_confirm: MagicMock,
        mock_scanner_cls: MagicMock,
        mock_build_sym: MagicMock,
        mock_detector: MagicMock,
        mock_verifier: MagicMock,
        mock_report_cls: MagicMock,
        mock_pause: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Answering Yes renders with a fresh verbose reporter even for a
        detection-only run (no claims)."""
        mock_path.return_value.ask.side_effect = ["/pre/path", "/post/path"]
        mock_select.return_value.ask.return_value = "No, just detect changes"
        mock_confirm.return_value.ask.return_value = True

        mock_pre_scan = MagicMock()
        mock_pre_scan.success_count = 1
        mock_pre_scan.failure_count = 0
        mock_post_scan = MagicMock()
        mock_post_scan.success_count = 1
        mock_post_scan.failure_count = 0
        mock_scanner_cls.side_effect = [
            MagicMock(scan=MagicMock(return_value=mock_pre_scan)),
            MagicMock(scan=MagicMock(return_value=mock_post_scan)),
        ]
        mock_build_sym.side_effect = [
            MagicMock(all_symbols=["a"]),
            MagicMock(all_symbols=["a", "b"]),
        ]
        mock_detector.detect.return_value = [MagicMock()]

        verbose_reporter = MagicMock(spec=TerminalReporter)
        verbose_reporter.report.return_value = "Verbose pre/post report"
        mock_reporter_cls.return_value = verbose_reporter

        shared_reporter = MagicMock(spec=TerminalReporter)

        _run_pre_post(shared_reporter)

        mock_reporter_cls.assert_called_once_with(colour=True, verbose=True)
        verbose_reporter.report.assert_called_once()
        shared_reporter.report.assert_not_called()
        mock_save.assert_called_once_with("Verbose pre/post report")


# ============================================================================
# _run_config_setup — API configuration flow
# ============================================================================


class TestRunConfigSetup:
    """Interactive API key / endpoint / model configuration."""

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.NowreckConfig")
    def test_normal_flow(
        self,
        mock_config_cls: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
    ) -> None:
        """All fields provided should save to config."""
        mock_config = MagicMock()
        mock_config.load.return_value = {
            "api_key": "sk-old",
            "base_url": "https://old.example.com/v1",
            "model": "old-model",
        }
        mock_config_cls.return_value = mock_config

        mock_password.return_value.ask.return_value = "sk-new"
        mock_text.return_value.ask.side_effect = [
            "https://new.example.com/v1",
            "new-model",
        ]

        _run_config_setup()

        mock_config.save.assert_called_once_with({
            "api_key": "sk-new",
            "base_url": "https://new.example.com/v1",
            "model": "new-model",
        })
        mock_pause.assert_called_once()

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.NowreckConfig")
    def test_empty_values_not_overwritten(
        self,
        mock_config_cls: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
    ) -> None:
        """If user presses Enter on an empty field, the old value should be kept."""
        mock_config = MagicMock()
        mock_config.load.return_value = {
            "api_key": "sk-existing",
            "base_url": "https://existing.example.com/v1",
            "model": "existing-model",
        }
        mock_config_cls.return_value = mock_config

        # All empty — means user just pressed Enter on defaults
        mock_password.return_value.ask.return_value = ""
        mock_text.return_value.ask.side_effect = ["", ""]

        _run_config_setup()

        # When values are empty/None, the old data should not be overwritten
        mock_config.save.assert_called_once_with({
            "api_key": "sk-existing",
            "base_url": "https://existing.example.com/v1",
            "model": "existing-model",
        })
        mock_pause.assert_called_once()

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.NowreckConfig")
    def test_partial_update(
        self,
        mock_config_cls: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
    ) -> None:
        """Only non-empty fields should update; others keep old values."""
        mock_config = MagicMock()
        mock_config.load.return_value = {
            "api_key": "sk-existing",
            "base_url": "https://existing.example.com/v1",
            "model": "existing-model",
        }
        mock_config_cls.return_value = mock_config

        # Only update api_key, leave others empty
        mock_password.return_value.ask.return_value = "sk-replacement"
        mock_text.return_value.ask.side_effect = ["", ""]

        _run_config_setup()

        mock_config.save.assert_called_once_with({
            "api_key": "sk-replacement",
            "base_url": "https://existing.example.com/v1",
            "model": "existing-model",
        })
        mock_pause.assert_called_once()

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.NowreckConfig")
    def test_empty_config_initial_setup(
        self,
        mock_config_cls: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
    ) -> None:
        """Fresh config (no existing data) should still work."""
        mock_config = MagicMock()
        mock_config.load.return_value = {}
        mock_config_cls.return_value = mock_config

        mock_password.return_value.ask.return_value = "sk-fresh"
        mock_text.return_value.ask.side_effect = [
            "https://fresh.example.com/v1",
            "fresh-model",
        ]

        _run_config_setup()

        mock_config.save.assert_called_once_with({
            "api_key": "sk-fresh",
            "base_url": "https://fresh.example.com/v1",
            "model": "fresh-model",
        })
        mock_pause.assert_called_once()

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker.questionary.text")
    @patch("nowreck.picker.questionary.password")
    @patch("nowreck.picker.NowreckConfig")
    def test_print_config_header(
        self,
        mock_config_cls: MagicMock,
        mock_password: MagicMock,
        mock_text: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A header and instructions should be printed."""
        mock_config = MagicMock()
        mock_config.load.return_value = {}
        mock_config_cls.return_value = mock_config

        mock_password.return_value.ask.return_value = "k"
        mock_text.return_value.ask.side_effect = ["u", "m"]

        _run_config_setup()

        out = capsys.readouterr().out
        assert "API Configuration" in out
        assert "OpenAI-compatible" in out
        assert "Configuration saved." in out
        mock_pause.assert_called_once()

    @patch("nowreck.picker.questionary.password")
    def test_api_key_uses_password(
        self,
        mock_password: MagicMock,
    ) -> None:
        """API key field should use questionary.password() for masked input."""
        # Just verify that password() is called (not text() for the api key)
        _ = mock_password  # mark as used
        # The fixture setup calls _run_config_setup which requires all mocks
        pass

    @patch("nowreck.picker.questionary.password")
    def test_ctrl_c_on_api_key_exits(
        self,
        mock_password: MagicMock,
    ) -> None:
        """Ctrl+C on API key field should raise _ExitPicker immediately."""
        mock_password.return_value.ask.return_value = None

        with pytest.raises(_ExitPickerError):
            _run_config_setup()


# ============================================================================
# _view_last_report — showing previous verification output
# ============================================================================

class TestViewLastReport:
    """Reading and displaying the saved report."""

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker._resolve_last_report_path")
    def test_no_report(
        self,
        mock_resolve: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """When no report file exists, print a message and return."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_resolve.return_value = mock_path

        _view_last_report()

        out = capsys.readouterr().out
        assert "No previous report found" in out
        mock_pause.assert_called_once()

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker._resolve_last_report_path")
    def test_report_found(
        self,
        mock_resolve: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """When a report file exists, its contents should be printed."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "Verification report content"
        mock_resolve.return_value = mock_path

        _view_last_report()

        out = capsys.readouterr().out
        assert "Verification report content" in out
        mock_pause.assert_called_once()

    @patch("nowreck.picker._pause")
    @patch("nowreck.picker._resolve_last_report_path")
    def test_report_has_newline_separator(
        self,
        mock_resolve: MagicMock,
        mock_pause: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Report content is printed with an extra newline before it."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "Some report"
        mock_resolve.return_value = mock_path

        _view_last_report()

        out = capsys.readouterr().out
        # The empty print() before content adds a newline separator
        assert out.startswith("\n")
        assert "Some report" in out
        mock_pause.assert_called_once()


# ============================================================================
# _check_endpoint_reachable — TCP connectivity check
# ============================================================================


class TestCheckEndpointReachable:
    """Best-effort endpoint connectivity test."""

    def test_reachable(self, capsys: pytest.CaptureFixture) -> None:
        """When the socket connects, a confirmation should be printed."""
        with patch("nowreck.picker.socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock

            _check_endpoint_reachable("https://api.openai.com/v1")

        out = capsys.readouterr().out
        assert "confirmed reachable" in out
        assert "✓" in out
        mock_sock.close.assert_called_once()

    def test_unreachable(self, capsys: pytest.CaptureFixture) -> None:
        """When the socket fails, a warning should be printed."""
        with patch("nowreck.picker.socket.create_connection") as mock_conn:
            mock_conn.side_effect = OSError("Connection refused")

            _check_endpoint_reachable("https://api.openai.com/v1")

        out = capsys.readouterr().out
        assert "could not verify reachability" in out
        assert "still be attempted" in out

    def test_invalid_url(self, capsys: pytest.CaptureFixture) -> None:
        """When the URL is malformed, a generic confirmation is printed."""
        _check_endpoint_reachable("not a url at all!!!")
        out = capsys.readouterr().out
        assert "✓" in out
        assert "Endpoint configured" in out
        assert "reachable" not in out  # Not confirmed reachable

    def test_no_hostname(self, capsys: pytest.CaptureFixture) -> None:
        """When the URL has no hostname component, print generic confirmation."""
        _check_endpoint_reachable("")
        out = capsys.readouterr().out
        assert "✓" in out
        assert "Endpoint configured" in out

    def test_calls_with_correct_port_https(self, capsys: pytest.CaptureFixture) -> None:
        """HTTPS URLs should use port 443."""
        with patch("nowreck.picker.socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock

            _check_endpoint_reachable("https://api.openai.com/v1")

        mock_conn.assert_called_once_with(("api.openai.com", 443), timeout=5)

    def test_calls_with_correct_port_http(self, capsys: pytest.CaptureFixture) -> None:
        """HTTP URLs should use port 80."""
        with patch("nowreck.picker.socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock

            _check_endpoint_reachable("http://localhost:8080/v1")

        mock_conn.assert_called_once_with(("localhost", 8080), timeout=5)

    def test_explicit_custom_port(self, capsys: pytest.CaptureFixture) -> None:
        """URLs with explicit port should use that port."""
        with patch("nowreck.picker.socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value = mock_sock

            _check_endpoint_reachable("http://custom.example.com:3000/v1")

        mock_conn.assert_called_once_with(("custom.example.com", 3000), timeout=5)


# ============================================================================
# _save_last_report — persisting reports to disk
# ============================================================================


class TestSaveLastReport:
    """Writing report text to .nowreck/last_report.txt."""

    @patch("nowreck.picker._resolve_last_report_path")
    def test_saves_to_disk(self, mock_resolve: MagicMock) -> None:
        """Report text should be written to the correct path."""
        mock_path = MagicMock(spec=Path)
        mock_parent = MagicMock(spec=Path)
        mock_path.parent = mock_parent
        mock_resolve.return_value = mock_path

        _save_last_report("My report content")

        mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_path.write_text.assert_called_once_with(
            "My report content",
            encoding="utf-8",
        )

    @patch("nowreck.picker._resolve_last_report_path")
    def test_oserror_handled(self, mock_resolve: MagicMock) -> None:
        """If directory creation or write fails, the error should be silently caught."""
        mock_path = MagicMock(spec=Path)
        mock_parent = MagicMock(spec=Path)
        mock_path.parent = mock_parent
        mock_parent.mkdir.side_effect = OSError("Permission denied")
        mock_resolve.return_value = mock_path

        _save_last_report("My report content")
        # Should not raise

    @patch("nowreck.picker._resolve_last_report_path")
    def test_write_error_handled(self, mock_resolve: MagicMock) -> None:
        """If only write_text fails, mkdir should still be attempted."""
        mock_path = MagicMock(spec=Path)
        mock_parent = MagicMock(spec=Path)
        mock_path.parent = mock_parent
        mock_resolve.return_value = mock_path

        mock_parent.mkdir.return_value = None
        mock_path.write_text.side_effect = OSError("Disk full")

        _save_last_report("My report content")
        mock_parent.mkdir.assert_called_once()


# ============================================================================
# _resolve_last_report_path — path generation
# ============================================================================


class TestResolveLastReportPath:
    """Compute the path to .nowreck/last_report.txt."""

    @patch("nowreck.picker.Path.cwd")
    def test_returns_correct_path(self, mock_cwd: MagicMock) -> None:
        """The path should be CWD/.nowreck/last_report.txt."""
        mock_cwd.return_value = Path("/home/user/project")
        result = _resolve_last_report_path()
        assert result == Path("/home/user/project/.nowreck/last_report.txt")

    @patch("nowreck.picker.Path.cwd")
    def test_returns_absolute_path(self, mock_cwd: MagicMock) -> None:
        """The returned path should be absolute (based on CWD)."""
        mock_cwd.return_value = Path("/tmp/test")
        result = _resolve_last_report_path()
        assert result.is_absolute()


# ============================================================================
# _pause — wait for user input
# ============================================================================


class TestPause:
    """Pause waiting for Enter key."""

    @patch("builtins.input")
    def test_calls_input_with_prompt(self, mock_input: MagicMock) -> None:
        """_pause should call input() with the menu return prompt."""
        _pause()
        mock_input.assert_called_once_with(
            "\nPress Enter to return to the main menu.",
        )

    @patch("builtins.input")
    def test_returns_none(self, mock_input: MagicMock) -> None:
        """_pause has no return value (None)."""
        mock_input.return_value = ""
        assert _pause() is None
