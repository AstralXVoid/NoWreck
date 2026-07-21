from __future__ import annotations

import argparse

from nowreck import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for nowreck."""
    parser = argparse.ArgumentParser(
        prog="nowreck",
        description="Deterministic verifier for AI code change explanations",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=False,
        help="Launch the interactive terminal picker",
    )

    subparsers = parser.add_subparsers(dest="command")

    # ------------------------------------------------------------------
    # nowreck fix — run the full verification pipeline
    # ------------------------------------------------------------------
    fix_parser = subparsers.add_parser(
        "fix",
        help="Verify AI claims about code changes",
    )
    fix_parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help=(
            "Natural language description of code changes. "
            "When provided, nowreck calls the configured model to generate "
            "claims and verifies them automatically (no --pre/--post needed)."
        ),
    )
    fix_parser.add_argument(
        "--pre",
        metavar="PATH",
        default=None,
        help="Path to the pre-change repository snapshot (advanced)",
    )
    fix_parser.add_argument(
        "--post",
        metavar="PATH",
        default=None,
        help="Path to the post-change repository snapshot (advanced)",
    )
    fix_parser.add_argument(
        "--claims",
        metavar="JSON",
        default=None,
        help="AI claims as a JSON string (advanced — skip to detect only)",
    )
    fix_parser.add_argument(
        "--no-colour",
        action="store_true",
        default=False,
        help="Disable coloured terminal output",
    )
    fix_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output structured JSON instead of coloured text (for CI)",
    )

    # ------------------------------------------------------------------
    # nowreck config — manage local configuration
    # ------------------------------------------------------------------
    config_parser = subparsers.add_parser(
        "config",
        help="Manage local configuration",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_subparsers.add_parser(
        "show",
        help="Show current configuration",
    )
    set_parser = config_subparsers.add_parser(
        "set",
        help="Set a configuration value",
    )
    set_parser.add_argument("key", help="Configuration key")
    set_parser.add_argument("value", help="Configuration value")

    return parser
