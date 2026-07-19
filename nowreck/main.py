from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from nowreck.claims.parser import ClaimParser
from nowreck.cli import build_parser
from nowreck.detector.change_detector import ChangeDetector
from nowreck.model.provider import ModelConfig, ModelError, ModelProvider
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.scanner.repository_scanner import RepositoryScanner, ScanResult
from nowreck.scanner.symbol_index import SymbolIndex, build_symbol_index
from nowreck.storage.config import NowreckConfig
from nowreck.verifier.verifier import ClaimVerifier, VerificationReport

# ---------------------------------------------------------------------------
# ASCII banner
# ---------------------------------------------------------------------------

_BANNER = r"""  +------------------------------------+
  |            NoWreck v0.1.0           |
  |    Deterministic AI Verifier        |
  +------------------------------------+"""


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the appropriate subcommand."""
    cmd_args = argv if argv is not None else sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    # Show the banner every time the bare ``nowreck`` command is run.
    if not cmd_args:
        print(_BANNER)
        print()

    if args.command == "fix":
        return handle_fix(args)
    if args.command == "config":
        return handle_config(args)
    parser.print_help()
    return 0


# ---------------------------------------------------------------------------
# nowreck fix
# ---------------------------------------------------------------------------


def handle_fix(args: argparse.Namespace) -> int:
    """Run the full verification pipeline.

    Two modes:

    **Prompt mode** (default):
        ``nowreck fix "<prompt>"``
        Calls the configured AI model with the prompt, gets claims + diff,
        and verifies automatically.  Requires an API key.

    **Pre/Post mode** (advanced):
        ``nowreck fix --pre PATH --post PATH [--claims JSON]``
        Scans two repository snapshots, detects structural changes, and
        optionally verifies claims against them.
    """
    prompt = args.prompt
    colour = not args.no_colour
    reporter = TerminalReporter(colour=colour)
    _log_file = sys.stderr if args.json else sys.stdout

    def _log(msg: str) -> None:
        print(msg, file=_log_file)

    # ------------------------------------------------------------------
    # Prompt mode — call the model directly
    # ------------------------------------------------------------------

    if prompt is not None:
        return _handle_prompt_mode(
            prompt=prompt,
            args=args,
            reporter=reporter,
            log=_log,
        )

    # ------------------------------------------------------------------
    # Pre/Post mode — scan actual repos
    # ------------------------------------------------------------------

    if not args.pre or not args.post:
        print(
            "Error: Use either 'nowreck fix \"<prompt>\"' or "
            "'nowreck fix --pre PATH --post PATH'.",
            file=sys.stderr,
        )
        return 1

    try:
        pre_path = _resolve_path(args.pre)
        post_path = _resolve_path(args.post)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # 1. Scan
    _log(f"Scanning pre snapshot:  {pre_path}")
    pre_scan = RepositoryScanner(pre_path).scan()
    _log(
        f"  \u2192 {pre_scan.success_count} files parsed, "
        f"{pre_scan.failure_count} failed"
    )

    _log(f"Scanning post snapshot: {post_path}")
    post_scan = RepositoryScanner(post_path).scan()
    _log(
        f"  \u2192 {post_scan.success_count} files parsed, "
        f"{post_scan.failure_count} failed"
    )

    # 2. Build symbol indices
    pre_symbols = build_symbol_index(pre_scan)
    post_symbols = build_symbol_index(post_scan)
    _log(
        f"Symbols: {len(pre_symbols.all_symbols)} pre \u2192 "
        f"{len(post_symbols.all_symbols)} post"
    )

    report = _detect_and_verify(
        args, pre_scan, post_scan, pre_symbols, post_symbols, _log
    )

    # Print report
    if args.json:
        print(reporter.report_json(report))
    else:
        print()
        print(reporter.report(report))

    total_issues = report.unverifiable + report.contradicted + report.unexplained_count
    return 0 if total_issues == 0 else 1


# ---------------------------------------------------------------------------
# nowreck config
# ---------------------------------------------------------------------------


def handle_config(args: argparse.Namespace) -> int:
    """Manage local configuration."""
    config = NowreckConfig()

    cmd = args.config_command

    if cmd == "show":
        data = config.load()
        if data:
            for key, value in sorted(data.items()):
                print(f"{key} = {value}")
        else:
            print("No configuration found.")
        return 0

    if cmd == "set":
        key = args.key
        value = args.value
        data = config.load()
        data[key] = value
        config.save(data)
        print(f"Set {key} = {value}")
        return 0

    print("Usage: nowreck config show|set <key> <value>")
    return 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _handle_prompt_mode(
    prompt: str,
    args: argparse.Namespace,
    reporter: TerminalReporter,
    log: Callable[[str], None],
) -> int:
    """Run the full verification pipeline in prompt mode.

    Calls the configured AI model with a natural-language prompt, gets
    claims + derived changes, and verifies them automatically.
    """
    model_config = _build_model_config()
    provider = ModelProvider(config=model_config)

    log("Calling model to generate claims from prompt...")
    try:
        result = provider.changes_from_prompt(prompt)
    except ModelError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not result.claims:
        print("Warning: Model returned no valid claims.", file=sys.stderr)
        if result.parse_result:
            for err in result.parse_result.errors:
                print(f"  Parse error: {err}", file=sys.stderr)

    if result.attempts > 1:
        log(f"Claims parsed on attempt {result.attempts}")
    else:
        log(f"Claims parsed: {len(result.claims)}")

    log(f"Changes derived: {len(result.changes)}")
    report = ClaimVerifier.verify(result.claims, result.changes)

    if args.json:
        print(reporter.report_json(report))
    else:
        print()
        print(reporter.report(report))

    total_issues = report.unverifiable + report.contradicted + report.unexplained_count
    return 0 if total_issues == 0 else 1


def _build_model_config() -> ModelConfig:
    """Build a ``ModelConfig`` from saved configuration and environment
    variables."""
    cfg = NowreckConfig()
    data = cfg.load()

    return ModelConfig(
        api_key=_get_str_or(data, "api_key", ""),
        model=_get_str_or(data, "model", "gpt-4o"),
        base_url=_get_str_or(data, "base_url", "https://api.openai.com/v1"),
        temperature=_get_float_or(data, "temperature", 0.0),
        max_retries=_get_int_or(data, "max_retries", 1),
    )


def _get_str_or(data: dict[str, object], key: str, default: str) -> str:
    """Get a string value from the config dict, falling back to *default*."""
    val = data.get(key, default)
    return str(val)


def _get_float_or(data: dict[str, object], key: str, default: float) -> float:
    """Get a float value from the config dict, falling back to *default*."""
    val: object = data.get(key, default)
    if isinstance(val, (int, float)):
        return float(val)
    return default


def _get_int_or(data: dict[str, object], key: str, default: int) -> int:
    """Get an int value from the config dict, falling back to *default*."""
    val: object = data.get(key, default)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    return default


def _detect_and_verify(
    args: argparse.Namespace,
    pre_scan: ScanResult,
    post_scan: ScanResult,
    pre_symbols: SymbolIndex,
    post_symbols: SymbolIndex,
    log: Callable[[str], None],
) -> VerificationReport:
    """Run the change detection + optional claim verification for the
    pre/post mode."""
    changes = ChangeDetector.detect(
        pre_scan,
        post_scan,
        pre_symbols,
        post_symbols,
    )
    log(f"Changes detected: {len(changes)}")

    if args.claims:
        parse_result = ClaimParser.parse(args.claims)
        if not parse_result.success:
            print("Warning: Some claims could not be parsed:", file=sys.stderr)
            for err in parse_result.errors:
                print(f"  - {err}", file=sys.stderr)

        if parse_result.claims:
            log(f"Claims parsed: {len(parse_result.claims)}")
            return ClaimVerifier.verify(parse_result.claims, changes)

    return VerificationReport(unexplained_changes=changes)


def _resolve_path(raw: str) -> Path:
    """Resolve a user-provided path, raising on invalid input."""
    path = Path(raw).resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")
    return path
