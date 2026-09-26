from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nowreck.claims.models import ClaimType
from nowreck.cli import build_parser
from nowreck.main import (
    _build_model_config,
    _resolve_path,
    handle_config,
    handle_fix,
    main,
    resolve_claims_input,
)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestArgParser:
    def test_fix_with_pre_and_post(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix", "--pre", "/tmp/a", "--post", "/tmp/b"])
        assert args.command == "fix"
        assert args.pre == "/tmp/a"
        assert args.post == "/tmp/b"
        assert args.claims is None
        assert args.no_colour is False
        assert args.prompt is None

    def test_fix_with_prompt(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "Add a function validate_email to somme_file.py"]
        )
        assert args.command == "fix"
        assert args.prompt == "Add a function validate_email to somme_file.py"
        assert args.pre is None
        assert args.post is None

    def test_fix_with_claims(self) -> None:
        claims = '{"claims": []}'
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--claims", claims]
        )
        assert args.claims == claims

    def test_fix_with_no_colour(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--no-colour"]
        )
        assert args.no_colour is True

    def test_fix_with_verbose(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--verbose"]
        )
        assert args.verbose is True

    def test_fix_verbose_defaults_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix", "--pre", "/tmp/a", "--post", "/tmp/b"])
        assert args.verbose is False

    def test_fix_verbose_with_prompt(self) -> None:
        """--verbose is accepted in prompt mode too."""
        parser = build_parser()
        args = parser.parse_args(["fix", "Add a function to app.py", "--verbose"])
        assert args.verbose is True
        assert args.prompt == "Add a function to app.py"

    def test_config_show(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["config", "show"])
        assert args.command == "config"
        assert args.config_command == "show"

    def test_config_set(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["config", "set", "api_key", "sk-test"])
        assert args.command == "config"
        assert args.config_command == "set"
        assert args.key == "api_key"
        assert args.value == "sk-test"

    def test_version(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--version"])
        assert exc.value.code == 0

    def test_no_args_shows_help(self) -> None:
        rc = main([])
        assert rc == 0


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_valid_directory(self) -> None:
        path = _resolve_path("/tmp")
        assert path == Path("/tmp").resolve()

    def test_nonexistent_path(self) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            _resolve_path("/nonexistent_xyz_path")

    def test_file_not_directory(self) -> None:
        with tempfile.NamedTemporaryFile() as f:
            with pytest.raises(ValueError, match="not a directory"):
                _resolve_path(f.name)

    def test_path_too_long_raises_clean_error(self) -> None:
        """A path exceeding the OS filename length limit (PATH_MAX ~4096)
        should raise ValueError with a clean message, not an OSError
        traceback."""
        long_path = "/" + ("a" * 5000) + "/path"
        with pytest.raises(ValueError, match="Cannot access path"):
            _resolve_path(long_path)


# ---------------------------------------------------------------------------
# resolve_claims_input
# ---------------------------------------------------------------------------


class TestResolveClaimsInput:
    """Unit tests for the ``--claims @file`` resolver.

    The traversal guard rejects anything outside the current directory, so
    every test that reads a real file under ``tmp_path`` chdirs into it
    first (pytest's ``tmp_path`` lives under /tmp, outside the project
    directory).
    """

    def test_claims_from_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)  # tmp_path is now inside CWD
        claims_file = tmp_path / "claims.json"
        claims_file.write_text('{"claims": []}')
        result = resolve_claims_input(f"@{claims_file}")
        assert '"claims"' in result

    def test_claims_from_file_traversal(self) -> None:
        with pytest.raises(ValueError, match="must be inside"):
            resolve_claims_input("@/etc/passwd")

    def test_claims_from_file_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="file not found"):
            resolve_claims_input(f"@{tmp_path / 'nonexistent.json'}")

    def test_claims_at_with_no_path(self) -> None:
        with pytest.raises(ValueError, match="requires a file path"):
            resolve_claims_input("@")

    def test_claims_from_file_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """expanduser + CWD guard both exercised: HOME and CWD both point
        at tmp_path, so @~/claims.json expands inside CWD and is accepted."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        claims_file = tmp_path / "claims.json"
        claims_file.write_text('{"claims": []}')
        result = resolve_claims_input("@~/claims.json")
        assert '"claims"' in result

    def test_claims_at_with_whitespace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Leading/trailing whitespace is trimmed before the @ check."""
        monkeypatch.chdir(tmp_path)
        claims_file = tmp_path / "claims.json"
        claims_file.write_text('{"claims": []}')
        result = resolve_claims_input(f"  @{claims_file}  ")
        assert '"claims"' in result

    def test_claims_from_file_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Symlink to a file inside CWD is read through the link."""
        monkeypatch.chdir(tmp_path)
        real = tmp_path / "real.json"
        real.write_text('{"claims": []}')
        link = tmp_path / "link.json"
        link.symlink_to(real)
        result = resolve_claims_input(f"@{link}")
        assert '"claims"' in result

    def test_claims_from_file_symlink_outside(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A symlink pointing OUTSIDE CWD is rejected — resolve() runs
        before the guard, so the target path fails the CWD-relative check."""
        monkeypatch.chdir(tmp_path)
        outside = Path("/etc/passwd")
        if not outside.exists():
            pytest.skip("no /etc/passwd to symlink to")
        link = tmp_path / "claims.json"
        link.symlink_to(outside)
        with pytest.raises(ValueError, match="must be inside"):
            resolve_claims_input(f"@{link}")

    def test_claims_from_file_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty file raises a clear error instead of silently parsing ""."""
        monkeypatch.chdir(tmp_path)
        empty = tmp_path / "empty.json"
        empty.write_text("")
        with pytest.raises(ValueError, match="claims file is empty"):
            resolve_claims_input(f"@{empty}")

    def test_inline_json_returned_unchanged(self) -> None:
        """Non-@ values pass through untouched (only outer whitespace is
        trimmed)."""
        inline = '{"claims": []}'
        assert resolve_claims_input(inline) == inline


# ---------------------------------------------------------------------------
# handle_config
# ---------------------------------------------------------------------------


class TestHandleConfig:
    def _clean_config(self) -> None:
        """Remove persistent config file so tests don't pollute each
        other."""
        config_path = Path.cwd() / ".nowreck" / "config.json"
        if config_path.exists():
            config_path.unlink()
        # Also remove the empty parent dir if safe
        parent = config_path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def test_config_show_empty(self, capsys: pytest.CaptureFixture) -> None:
        self._clean_config()
        parser = build_parser()
        args = parser.parse_args(["config", "show"])
        rc = handle_config(args)
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "No configuration found" in out

    def test_config_set_and_show(self, capsys: pytest.CaptureFixture) -> None:
        self._clean_config()
        parser = build_parser()
        args = parser.parse_args(["config", "set", "foo", "bar"])
        rc = handle_config(args)
        assert rc == 0

        args = parser.parse_args(["config", "show"])
        rc = handle_config(args)
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "foo = bar" in out

        self._clean_config()

    def test_config_show_masks_api_key(self, capsys: pytest.CaptureFixture) -> None:
        """P2-06: config show must never print the full API key."""
        self._clean_config()
        parser = build_parser()
        secret = "sk-SUPERSECRET-1234567890"
        handle_config(parser.parse_args(["config", "set", "api_key", secret]))
        handle_config(parser.parse_args(["config", "show"]))

        out, _ = capsys.readouterr()
        assert secret not in out
        assert "****" in out

        self._clean_config()

    def test_config_set_echo_masks_api_key(self, capsys: pytest.CaptureFixture) -> None:
        """The confirmation line for api_key is masked too."""
        self._clean_config()
        parser = build_parser()
        secret = "sk-SUPERSECRET-1234567890"
        handle_config(parser.parse_args(["config", "set", "api_key", secret]))

        out, _ = capsys.readouterr()
        assert secret not in out
        assert "****" in out

        self._clean_config()

    def test_config_unknown_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["config", "show"])
        args.config_command = "unknown"  # type: ignore[attr-defined]
        rc = handle_config(args)
        assert rc == 1


# ---------------------------------------------------------------------------
# handle_fix — full pipeline integration
# ---------------------------------------------------------------------------


class TestHandleFix:
    def test_fix_no_claims_detects_changes(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef new_fn(): pass\n", encoding="utf-8"
            )
            (post / "helper.py").write_text("def util(): pass\n", encoding="utf-8")

            parser = build_parser()
            args = parser.parse_args(["fix", "--pre", str(pre), "--post", str(post)])

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "Scanning pre snapshot" in out
            assert "Scanning post snapshot" in out
            assert "Changes detected:" in out
            assert "UNEXPLAINED CHANGES" in out

    def test_fix_with_claims_confirmed(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef new_fn(): pass\n", encoding="utf-8"
            )

            claims = json.dumps(
                {
                    "claims": [
                        {
                            "type": "ADD_FUNCTION",
                            "symbol_name": "new_fn",
                            "file_path": "app.py",
                            "confidence": 0.95,
                            "explanation": "Added new function.",
                        },
                    ],
                }
            )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    claims,
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 0
            assert "CONFIRMED" in out

    def test_fix_with_claims_from_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """End-to-end: --claims @file triggers resolve + parse + verify."""
        # Set CWD to tmp_path so the @file path passes the CWD-relative check
        monkeypatch.chdir(tmp_path)

        pre = tmp_path / "pre"
        post = tmp_path / "post"
        pre.mkdir()
        post.mkdir()

        (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
        (post / "app.py").write_text(
            "def old(): pass\n\ndef new_fn(): pass\n", encoding="utf-8"
        )

        claims = json.dumps(
            {
                "claims": [
                    {
                        "type": "ADD_FUNCTION",
                        "symbol_name": "new_fn",
                        "file_path": "app.py",
                    },
                ],
            }
        )
        claims_file = tmp_path / "claims.json"
        claims_file.write_text(claims, encoding="utf-8")

        parser = build_parser()
        args = parser.parse_args(
            [
                "fix",
                "--pre",
                str(pre),
                "--post",
                str(post),
                "--claims",
                f"@{claims_file}",
            ]
        )

        rc = handle_fix(args)
        out, _ = capsys.readouterr()

        assert rc == 0  # claim confirmed
        assert "CONFIRMED" in out

    def test_fix_with_claims_from_missing_file(self) -> None:
        """A missing @file fails cleanly with a clear error (exit 1)."""
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp", "--post", "/tmp", "--claims", "@nope.json"]
        )
        rc = handle_fix(args)
        assert rc == 1

    def test_fix_with_invalid_claims(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef new_fn(): pass\n", encoding="utf-8"
            )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    "not valid json",
                ]
            )

            rc = handle_fix(args)
            out, err = capsys.readouterr()
            assert rc == 1
            assert "Warning" in err

    def test_fix_with_nonexistent_pre_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "fix",
                "--pre",
                "/nonexistent_pre",
                "--post",
                "/tmp",
            ]
        )
        rc = handle_fix(args)
        assert rc == 1

    def test_fix_with_json_flag(self, capsys: pytest.CaptureFixture) -> None:
        """Using --json outputs valid JSON instead of text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef added(): pass\n", encoding="utf-8"
            )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--json",
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            # Output should be valid JSON
            data = json.loads(out)
            assert "version" in data
            assert "summary" in data
            assert "results" in data
            assert "unexplained_changes" in data
            assert data["success"] is False
            assert data["summary"]["unexplained_count"] >= 1

    def test_fix_no_colour_flag(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef added(): pass\n", encoding="utf-8"
            )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--no-colour",
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()
            assert rc == 1
            assert "\033[" not in out

    def test_fix_without_pre_post_or_prompt(self) -> None:
        """When neither prompt nor --pre/--post is provided, show error."""
        parser = build_parser()
        args = parser.parse_args(["fix"])
        rc = handle_fix(args)
        assert rc == 1


class TestV10Flags:
    """Tests for prompt mode with --pre/--post (manual snapshots)."""

    def test_prompt_with_pre_post(self) -> None:
        """Prompt + --pre/--post uses manual snapshot mode."""
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "Add a function", "--pre", "/tmp/a", "--post", "/tmp/b"]
        )
        assert args.prompt == "Add a function"
        assert args.pre == "/tmp/a"
        assert args.post == "/tmp/b"

    def test_prompt_without_pre_post(self) -> None:
        """Prompt without --pre/--post uses auto-snapshot mode."""
        parser = build_parser()
        args = parser.parse_args(["fix", "Add a function"])
        assert args.prompt == "Add a function"
        assert args.pre is None
        assert args.post is None


class TestPromptModeMissingApiKey:
    """Prompt mode with no API key must fail with a clean error — never
    a raw traceback (the ModelError is raised inside ``verify()``, after
    the snapshot is captured)."""

    def test_missing_api_key_is_clean_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.chdir(tmp_path)  # no .nowreck/config.json here
        monkeypatch.delenv("NOWRECK_API_KEY", raising=False)
        (tmp_path / "app.py").write_text(
            "def greet():\n    return 'hi'\n", encoding="utf-8"
        )

        parser = build_parser()
        args = parser.parse_args(["fix", "add a greet function"])

        rc = handle_fix(args)
        _, err = capsys.readouterr()

        assert rc == 1
        assert "Error:" in err
        assert "No API key" in err
        assert "Traceback" not in err

    def test_missing_api_key_with_manual_snapshots_is_clean_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """The manual-snapshot prompt path resolves --pre/--post inside
        the same try — missing key is a clean error there too."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("NOWRECK_API_KEY", raising=False)
        pre = tmp_path / "pre"
        post = tmp_path / "post"
        pre.mkdir()
        post.mkdir()
        (pre / "app.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
        (post / "app.py").write_text(
            "def greet():\n    return 'hello'\n", encoding="utf-8"
        )

        parser = build_parser()
        args = parser.parse_args(
            ["fix", "change greet", "--pre", str(pre), "--post", str(post)]
        )

        rc = handle_fix(args)
        _, err = capsys.readouterr()

        assert rc == 1
        assert "Error:" in err
        assert "Traceback" not in err

    def test_invalid_manual_snapshot_path_is_clean_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A nonexistent --pre/--post path in prompt mode raises ValueError
        inside the handler — caught, not a traceback."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("NOWRECK_API_KEY", raising=False)

        parser = build_parser()
        args = parser.parse_args(
            [
                "fix",
                "change greet",
                "--pre",
                str(tmp_path / "nope"),
                "--post",
                str(tmp_path / "nope2"),
            ]
        )

        rc = handle_fix(args)
        _, err = capsys.readouterr()

        assert rc == 1
        assert "Error:" in err
        assert "Traceback" not in err


class TestBuildModelConfigValidation:
    """P2-08: invalid stored temperature surfaces as ModelError."""

    def test_invalid_temperature_raises_model_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nowreck.model.provider import ModelError

        mock_cfg = MagicMock()
        mock_cfg.load.return_value = {
            "api_key": "sk-test",
            "base_url": "https://api.test.com/v1",
            "model": "m",
            "temperature": 9.9,
        }
        monkeypatch.setattr("nowreck.main.NowreckConfig", lambda: mock_cfg)

        with pytest.raises(ModelError, match="Invalid configuration"):
            _build_model_config()

    def test_valid_temperature_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_cfg = MagicMock()
        mock_cfg.load.return_value = {"temperature": "0.7"}
        monkeypatch.setattr("nowreck.main.NowreckConfig", lambda: mock_cfg)

        cfg = _build_model_config()
        assert cfg.temperature == 0.7


# ---------------------------------------------------------------------------
# v13 flags — --format, --output, --compare
# ---------------------------------------------------------------------------


class TestFormatFlag:
    """Tests for --format flag."""

    def test_format_json_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--format", "json"]
        )
        assert args.format == "json"

    def test_format_sarif_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--format", "sarif"]
        )
        assert args.format == "sarif"

    def test_format_junit_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--format", "junit"]
        )
        assert args.format == "junit"

    def test_format_defaults_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix", "--pre", "/tmp/a", "--post", "/tmp/b"])
        assert args.format is None

    def test_format_invalid_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--format", "xml"]
            )


class TestOutputFlag:
    """Tests for --output flag."""

    def test_output_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--output", "out.json"]
        )
        assert args.output == "out.json"

    def test_output_defaults_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix", "--pre", "/tmp/a", "--post", "/tmp/b"])
        assert args.output is None


class TestCompareFlag:
    """Tests for --compare flag."""

    def test_compare_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix", "--compare", "HEAD~1"])
        assert args.compare == "HEAD~1"

    def test_compare_defaults_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix"])
        assert args.compare is None


class TestFlagConflicts:
    """Tests for flag conflict detection."""

    def test_json_and_format_conflict(self, capsys: pytest.CaptureFixture) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["fix", "--pre", "/tmp/a", "--post", "/tmp/b", "--json", "--format", "json"]
        )
        rc = handle_fix(args)
        _, err = capsys.readouterr()
        assert rc == 1
        assert "cannot use both --json and --format" in err

    def test_compare_and_post_conflict(self, capsys: pytest.CaptureFixture) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix", "--compare", "HEAD~1", "--post", "/tmp/b"])
        rc = handle_fix(args)
        _, err = capsys.readouterr()
        assert rc == 1
        assert "cannot use --compare with --pre or --post" in err

    def test_compare_and_pre_conflict(self, capsys: pytest.CaptureFixture) -> None:
        parser = build_parser()
        args = parser.parse_args(["fix", "--compare", "HEAD~1", "--pre", "/tmp/a"])
        rc = handle_fix(args)
        _, err = capsys.readouterr()
        assert rc == 1
        assert "cannot use --compare with --pre or --post" in err


# ---------------------------------------------------------------------------
# Phase 5 E2E: CHANGED claims per language via the real pre/post pipeline
# ---------------------------------------------------------------------------


# (lang, file_name, pre_src, post_src, parent_class)
#
# ``parent_class`` is required for Java because Java has no top-level
# functions — its callables are always methods of a type, so the
# CHANGED_FUNCTION claim must name the owning class.  Kotlin *does* have
# top-level functions (``app.kt`` below), so it uses ``None`` there;
# ``TestE2EKotlinPipeline`` covers the method-inside-a-class spelling.
_LANG_CASES = [
    (
        "python",
        "app.py",
        "def greet():\n    return 'hi'\n",
        "def greet():\n    return 'hello'\n",
        None,
    ),
    (
        "js",
        "app.js",
        "function greet() { return 'hi'; }\n",
        "function greet() { return 'hello'; }\n",
        None,
    ),
    (
        "ts",
        "app.ts",
        "function greet(): string { return 'hi'; }\n",
        "function greet(): string { return 'hello'; }\n",
        None,
    ),
    (
        "rust",
        "app.rs",
        'fn greet() -> &\'static str { "hi" }\n',
        'fn greet() -> &\'static str { "hello" }\n',
        None,
    ),
    (
        "go",
        "app.go",
        'package main\n\nfunc greet() string { return "hi" }\n',
        'package main\n\nfunc greet() string { return "hello" }\n',
        None,
    ),
    (
        "java",
        "App.java",
        "class App { int greet() { return 1; } }\n",
        "class App { int greet() { return 2; } }\n",
        "App",
    ),
    (
        "kotlin",
        "app.kt",
        'fun greet(): String { return "hi" }\n',
        'fun greet(): String { return "hello" }\n',
        None,
    ),
]


def _make_claim_dict(
    claim_type: ClaimType,
    *,
    symbol_name: str | None = None,
    file_path: str,
    parent_class: str | None = None,
    caller_name: str | None = None,
    called_name: str | None = None,
) -> dict[str, object]:
    """Build a claim dict in the wire format the parser expects."""
    claim: dict[str, object] = {
        "type": claim_type.name,
        "file_path": file_path,
    }
    if symbol_name is not None:
        claim["symbol_name"] = symbol_name
    if parent_class is not None:
        claim["parent_class"] = parent_class
    if caller_name is not None:
        claim["caller_name"] = caller_name
    if called_name is not None:
        claim["called_name"] = called_name
    return claim


class TestE2EChangedPerLanguage:
    """Modify a body in each language → `nowreck fix --pre --post` with a
    CHANGED_FUNCTION claim → CONFIRMED via the real pipeline."""

    @pytest.mark.parametrize(
        "lang,file_name,pre_src,post_src,parent_class", _LANG_CASES
    )
    def test_body_edit_changed_claim_confirmed(
        self,
        capsys: pytest.CaptureFixture,
        lang: str,
        file_name: str,
        pre_src: str,
        post_src: str,
        parent_class: str | None,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            (pre / file_name).write_text(pre_src, encoding="utf-8")
            (post / file_name).write_text(post_src, encoding="utf-8")

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path=file_name,
                    parent_class=parent_class,
                )
            ]
            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 0, out
            assert "CONFIRMED" in out, out

    def test_method_call_claim_confirmed_via_real_pipeline(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """A method-call claim with parent_class confirms through the real
        pre/post pipeline (call capture + strict class matching)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            (pre / "calc.py").write_text(
                "class Calculator:\n    def process(self, x):\n        return x\n",
                encoding="utf-8",
            )
            (post / "calc.py").write_text(
                "class Calculator:\n"
                "    def process(self, x):\n"
                "        return self.validate(x)\n"
                "    def validate(self, x):\n"
                "        return x > 0\n",
                encoding="utf-8",
            )

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            # The honest claim set for this edit: the new method, the
            # method-body change, and the new call — no cross-talk, and
            # nothing left unexplained.
            claims = [
                _make_claim_dict(
                    ClaimType.ADD_FUNCTION,
                    symbol_name="validate",
                    file_path="calc.py",
                    parent_class="Calculator",
                ),
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="process",
                    file_path="calc.py",
                    parent_class="Calculator",
                ),
                _make_claim_dict(
                    ClaimType.CALLS_FUNCTION,
                    file_path="calc.py",
                    parent_class="Calculator",
                    caller_name="process",
                    called_name="validate",
                ),
            ]
            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 0, out
            assert "CONFIRMED" in out, out
            assert "UNEXPLAINED" not in out, out

    def test_hallucinated_changed_claim_unverifiable(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """A CHANGED_FUNCTION claim about a function that was never
        touched stays UNVERIFIABLE (exit 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            src = "def greet():\n    return 'hi'\n"
            (pre / "app.py").write_text(src, encoding="utf-8")
            (post / "app.py").write_text(src, encoding="utf-8")

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path="app.py",
                )
            ]
            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "UNVERIFIABLE" in out

    def test_hallucinated_changed_claim_contradicted_by_removal(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Claiming CHANGED_FUNCTION for a function that was actually
        removed → CONTRADICTED (exit 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            (pre / "app.py").write_text(
                "def greet():\n    return 'hi'\n", encoding="utf-8"
            )
            (post / "app.py").write_text("x = 1\n", encoding="utf-8")

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path="app.py",
                )
            ]
            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "CONTRADICTED" in out


class TestE2EJavaPipeline:
    """Phase 2 gate 5: the real CLI pipeline over Java sources.

    Covers ``--pre/--post`` with all three output formats, ``--compare``
    against a git repo, and both non-CONFIRMED verdict paths for Java.
    """

    _PRE = "class App { int greet() { return 1; } }\n"
    _POST = "class App { int greet() { return 2; } }\n"

    def _snapshots(self, tmpdir: str) -> tuple[Path, Path]:
        pre = Path(tmpdir) / "pre"
        post = Path(tmpdir) / "post"
        pre.mkdir()
        post.mkdir()
        (pre / "App.java").write_text(self._PRE, encoding="utf-8")
        (post / "App.java").write_text(self._POST, encoding="utf-8")
        return pre, post

    @pytest.mark.parametrize("fmt", ["json", "sarif", "junit"])
    def test_java_change_renders_every_format(
        self, capsys: pytest.CaptureFixture, fmt: str
    ) -> None:
        """An unexplained Java change renders through json/sarif/junit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre, post = self._snapshots(tmpdir)

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--format",
                    fmt,
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            # A CHANGED_FUNCTION with no claim is unexplained → exit 1.
            assert rc == 1, out
            if fmt == "json":
                data = json.loads(out)
                assert "version" in data and "results" in data
                unexplained = data["unexplained_changes"]
                assert any(
                    c["symbol_name"] == "greet" and c["parent_class"] == "App"
                    for c in unexplained
                ), unexplained
            elif fmt == "sarif":
                data = json.loads(out)
                assert data["version"] == "2.1.0"
                assert "$schema" in data
            else:
                assert "testsuites" in out
                assert "nowreck" in out

    def test_java_claim_confirmed_via_pre_post(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """The honest claim set for a Java body edit is CONFIRMED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre, post = self._snapshots(tmpdir)

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path="App.java",
                    parent_class="App",
                )
            ]
            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 0, out
            assert "CONFIRMED" in out
            assert "UNEXPLAINED" not in out

    def test_java_hallucinated_claim_unverifiable(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """A CHANGED_FUNCTION claim about a Java method nobody touched is
        UNVERIFIABLE (exit 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            src = "class App { int greet() { return 1; } }\n"
            (pre / "App.java").write_text(src, encoding="utf-8")
            (post / "App.java").write_text(src, encoding="utf-8")

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path="App.java",
                    parent_class="App",
                )
            ]
            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "UNVERIFIABLE" in out

    def test_java_changed_claim_contradicted_by_removal(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Claiming CHANGED_FUNCTION for a Java method that was actually
        removed is CONTRADICTED (exit 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            (pre / "App.java").write_text(
                "class App { int gone() { return 1; } }\n", encoding="utf-8"
            )
            (post / "App.java").write_text("class App { }\n", encoding="utf-8")

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="gone",
                    file_path="App.java",
                    parent_class="App",
                )
            ]
            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "CONTRADICTED" in out

    def test_java_compare_mode_detects_change(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """``--compare HEAD~1`` picks up a Java method-body edit from git."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "App.java").write_text(
            "class App { int greet() { return 1; } }\n", encoding="utf-8"
        )
        env = {
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@t.local",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@t.local",
        }

        def git(*args: str) -> None:
            assert (
                subprocess.run(
                    ["git", *args], cwd=repo, capture_output=True, text=True, env=env
                ).returncode
                == 0
            ), args

        git("init")
        git("add", ".")
        git("commit", "-m", "init")
        (repo / "App.java").write_text(
            "class App { int greet() { return 2; } }\n", encoding="utf-8"
        )
        git("add", ".")
        git("commit", "-m", "change")

        from nowreck.cli import build_parser
        from nowreck.main import handle_fix

        monkeypatch.chdir(repo)
        args = build_parser().parse_args(
            ["fix", "--compare", "HEAD~1", "--format", "json"]
        )
        rc = handle_fix(args)
        out, _ = capsys.readouterr()

        assert rc == 1, out
        data = json.loads(out)
        assert any(
            c["symbol_name"] == "greet" and c["parent_class"] == "App"
            for c in data["unexplained_changes"]
        )


class TestE2EKotlinPipeline:
    """Phase 3 gate 5: the real CLI pipeline over Kotlin sources.

    Covers ``--pre/--post`` with all three output formats, ``--compare``
    against a git repo, both non-CONFIRMED verdict paths, and the Kotlin
    script (``.kts``) spelling, whose declarations are top-level.
    """

    # One-line class bodies holding members trigger a known grammar
    # defect (the parser errors and the body collapses), so the fixture
    # is written the way Kotlin is actually formatted.
    _PRE = "class App {\n    fun greet(): Int {\n        return 1\n    }\n}\n"
    _POST = "class App {\n    fun greet(): Int {\n        return 2\n    }\n}\n"

    def _snapshots(self, tmpdir: str) -> tuple[Path, Path]:
        pre = Path(tmpdir) / "pre"
        post = Path(tmpdir) / "post"
        pre.mkdir()
        post.mkdir()
        (pre / "App.kt").write_text(self._PRE, encoding="utf-8")
        (post / "App.kt").write_text(self._POST, encoding="utf-8")
        return pre, post

    @pytest.mark.parametrize("fmt", ["json", "sarif", "junit"])
    def test_kotlin_change_renders_every_format(
        self, capsys: pytest.CaptureFixture, fmt: str
    ) -> None:
        """An unexplained Kotlin change renders through json/sarif/junit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre, post = self._snapshots(tmpdir)

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--format",
                    fmt,
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            # A CHANGED_FUNCTION with no claim is unexplained → exit 1.
            assert rc == 1, out
            if fmt == "json":
                data = json.loads(out)
                assert "version" in data and "results" in data
                unexplained = data["unexplained_changes"]
                assert any(
                    c["symbol_name"] == "greet" and c["parent_class"] == "App"
                    for c in unexplained
                ), unexplained
            elif fmt == "sarif":
                data = json.loads(out)
                assert data["version"] == "2.1.0"
                assert "$schema" in data
            else:
                assert "testsuites" in out
                assert "nowreck" in out

    def test_kotlin_claim_confirmed_via_pre_post(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """The honest claim set for a Kotlin body edit is CONFIRMED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre, post = self._snapshots(tmpdir)

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path="App.kt",
                    parent_class="App",
                )
            ]
            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 0, out
            assert "CONFIRMED" in out
            assert "UNEXPLAINED" not in out

    def test_kotlin_hallucinated_claim_unverifiable(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """A CHANGED_FUNCTION claim about a Kotlin method nobody touched is
        UNVERIFIABLE (exit 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            src = self._PRE
            (pre / "App.kt").write_text(src, encoding="utf-8")
            (post / "App.kt").write_text(src, encoding="utf-8")

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path="App.kt",
                    parent_class="App",
                )
            ]
            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "UNVERIFIABLE" in out

    def test_kotlin_changed_claim_contradicted_by_removal(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Claiming CHANGED_FUNCTION for a Kotlin method that was actually
        removed is CONTRADICTED (exit 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            (pre / "App.kt").write_text(
                "class App {\n    fun gone(): Int {\n        return 1\n    }\n}\n",
                encoding="utf-8",
            )
            (post / "App.kt").write_text("class App\n", encoding="utf-8")

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="gone",
                    file_path="App.kt",
                    parent_class="App",
                )
            ]
            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "CONTRADICTED" in out

    def test_kotlin_compare_mode_detects_change(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """``--compare HEAD~1`` picks up a Kotlin method-body edit from git."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "App.kt").write_text(self._PRE, encoding="utf-8")
        env = {
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@t.local",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@t.local",
        }

        def git(*args: str) -> None:
            assert (
                subprocess.run(
                    ["git", *args], cwd=repo, capture_output=True, text=True, env=env
                ).returncode
                == 0
            ), args

        git("init")
        git("add", ".")
        git("commit", "-m", "init")
        (repo / "App.kt").write_text(self._POST, encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "change")

        from nowreck.cli import build_parser
        from nowreck.main import handle_fix

        monkeypatch.chdir(repo)
        args = build_parser().parse_args(
            ["fix", "--compare", "HEAD~1", "--format", "json"]
        )
        rc = handle_fix(args)
        out, _ = capsys.readouterr()

        assert rc == 1, out
        data = json.loads(out)
        assert any(
            c["symbol_name"] == "greet" and c["parent_class"] == "App"
            for c in data["unexplained_changes"]
        )

    def test_kts_script_top_level_function_confirmed(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """A ``.kts`` script has top-level functions, so its CHANGED claim
        needs no ``parent_class`` and still confirms end-to-end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            (pre / "build.kts").write_text(
                'fun greet(): String { return "hi" }\n', encoding="utf-8"
            )
            (post / "build.kts").write_text(
                'fun greet(): String { return "hello" }\n', encoding="utf-8"
            )

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            claims = [
                _make_claim_dict(
                    ClaimType.CHANGED_FUNCTION,
                    symbol_name="greet",
                    file_path="build.kts",
                )
            ]
            args = build_parser().parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--claims",
                    json.dumps({"claims": claims}),
                ]
            )
            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 0, out
            assert "CONFIRMED" in out
            assert "UNEXPLAINED" not in out


class TestExternalDirsGetNoCache:
    """Part B P3: `--pre A --post B` scans external snapshot dirs —
    no `.nowreck/` may be written inside them."""

    def test_pre_post_scan_writes_no_cache(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()
            (pre / "app.py").write_text(
                "def greet():\n    return 'hi'\n", encoding="utf-8"
            )
            (post / "app.py").write_text(
                "def greet():\n    return 'hello'\n", encoding="utf-8"
            )

            from nowreck.cli import build_parser
            from nowreck.main import handle_fix

            parser = build_parser()
            args = parser.parse_args(["fix", "--pre", str(pre), "--post", str(post)])

            handle_fix(args)
            capsys.readouterr()

            assert not (pre / ".nowreck").exists()
            assert not (post / ".nowreck").exists()

    def test_compare_mode_writes_no_cache(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """`--compare` extracts git-archive temps — neither snapshot
        dir gets a cache."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "app.py").write_text(
            "def greet():\n    return 'hi'\n", encoding="utf-8"
        )
        env = dict(
            {
                "GIT_AUTHOR_NAME": "T",
                "GIT_AUTHOR_EMAIL": "t@t.local",
                "GIT_COMMITTER_NAME": "T",
                "GIT_COMMITTER_EMAIL": "t@t.local",
            }
        )
        for args in (["init"], ["add", "."], ["commit", "-m", "init"]):
            assert (
                subprocess.run(
                    ["git", *args], cwd=repo, capture_output=True, text=True, env=env
                ).returncode
                == 0
            )
        # Modify + commit so --compare HEAD~1..HEAD sees a change
        (repo / "app.py").write_text(
            "def greet():\n    return 'hello'\n", encoding="utf-8"
        )
        assert (
            subprocess.run(
                ["git", "add", "."], cwd=repo, capture_output=True, text=True, env=env
            ).returncode
            == 0
        )
        assert (
            subprocess.run(
                ["git", "commit", "-m", "change"],
                cwd=repo,
                capture_output=True,
                text=True,
                env=env,
            ).returncode
            == 0
        )

        from nowreck.cli import build_parser
        from nowreck.main import handle_fix

        monkeypatch.chdir(repo)  # compare mode resolves the repo from CWD
        parser = build_parser()
        args = parser.parse_args(["fix", "--compare", "HEAD~1"])
        rc = handle_fix(args)
        capsys.readouterr()

        # A real change exists between the refs and no claims were
        # given → the change is unexplained (exit 1), which is fine —
        # the point is the run completed without writing `.nowreck/`
        # into the user's repo or the throwaway snapshot temps.
        assert rc == 1
        assert not (repo / ".nowreck").exists()


class TestFormatOutput:
    """Tests for format output routing."""

    def test_format_json_output(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef added(): pass\n", encoding="utf-8"
            )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--format",
                    "json",
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            data = json.loads(out)
            assert "version" in data
            assert "results" in data

    def test_format_sarif_output(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef added(): pass\n", encoding="utf-8"
            )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--format",
                    "sarif",
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            data = json.loads(out)
            assert data["version"] == "2.1.0"
            assert "$schema" in data

    def test_format_junit_output(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef added(): pass\n", encoding="utf-8"
            )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--format",
                    "junit",
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert "testsuites" in out
            assert "nowreck" in out

    def test_output_to_file(self, capsys: pytest.CaptureFixture) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre"
            post = Path(tmpdir) / "post"
            pre.mkdir()
            post.mkdir()

            (pre / "app.py").write_text("def old(): pass\n", encoding="utf-8")
            (post / "app.py").write_text(
                "def old(): pass\n\ndef added(): pass\n", encoding="utf-8"
            )

            output_file = Path(tmpdir) / "output.json"
            parser = build_parser()
            args = parser.parse_args(
                [
                    "fix",
                    "--pre",
                    str(pre),
                    "--post",
                    str(post),
                    "--format",
                    "json",
                    "--output",
                    str(output_file),
                ]
            )

            rc = handle_fix(args)
            out, _ = capsys.readouterr()

            assert rc == 1
            assert output_file.exists()
            data = json.loads(output_file.read_text())
            assert "version" in data
            # stdout should be empty
            assert out.strip() == ""
