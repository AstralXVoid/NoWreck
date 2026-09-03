from __future__ import annotations

import argparse

from nowreck import __version__

_EPILOG = """\
commands:
  fix             Run the verification pipeline.
                  Prompt mode: nowreck fix "<prompt>"
                    Calls the configured model, generates claims, verifies.
                  Pre/Post mode: nowreck fix --pre PATH --post PATH
                    Scans two repo snapshots, detects changes, verifies.
                  Compare mode: nowreck fix --compare REF
                    Compares a git ref against HEAD.

  config show     Display current local configuration.
                  Shows: api_key (masked), model, base_url, temperature,
                  max_retries, provider.

  config set      Set a configuration value.
                  Keys: api_key, model, base_url, temperature,
                  max_retries, provider.

providers:        OpenAI, Anthropic, Gemini (auto-detected from base_url)
output formats:   json, sarif (GitHub Code Scanning), junit (CI reports)

Run 'nowreck fix --help' or 'nowreck config --help' for subcommand options.
"""


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for nowreck."""
    parser = argparse.ArgumentParser(
        prog="nowreck",
        description="Deterministic verifier for AI code change explanations",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        help="AI claims as JSON string, or @file to read from file (advanced)",
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
        help=(
            "[DEPRECATED: use --format json] "
            "Output structured JSON instead of coloured text (for CI)"
        ),
    )
    fix_parser.add_argument(
        "--format",
        choices=["json", "sarif", "junit"],
        default=None,
        help=(
            "Output format: json, sarif (GitHub Code Scanning), "
            "or junit (CI test reports)"
        ),
    )
    fix_parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Write output to file instead of stdout",
    )
    fix_parser.add_argument(
        "--compare",
        metavar="REF",
        default=None,
        help=(
            "Compare git ref against HEAD (shorthand for "
            "--pre REF --post HEAD)"
        ),
    )
    fix_parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help=(
            "Show full deterministic evidence per claim in the terminal "
            "report (no effect with --json or --format)"
        ),
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
