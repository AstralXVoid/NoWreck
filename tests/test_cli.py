from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from nowreck.cli import build_parser
from nowreck.main import _resolve_path, handle_config, handle_fix, main

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
