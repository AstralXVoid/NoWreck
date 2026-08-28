from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from nowreck.claims.parser import ClaimParser
from nowreck.cli import build_parser
from nowreck.detector.change_detector import ChangeDetector
from nowreck.model.provider import ModelConfig, ModelError, mask_key
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.scanner.repository_scanner import RepositoryScanner, ScanResult
from nowreck.scanner.symbol_index import SymbolIndex, build_symbol_index
from nowreck.storage.config import NowreckConfig
from nowreck.verifier.verifier import ClaimVerifier, VerificationReport

# ---------------------------------------------------------------------------
# ASCII banner
# ---------------------------------------------------------------------------

_BANNER = r"""  +------------------------------------+
  |            NoWreck v0.13.0         |
  |    Deterministic AI Verifier       |
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

    # --interactive flag launches the terminal picker.
    if args.interactive:
        from nowreck.picker import run_picker

        return run_picker()

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
    # Flag conflict detection
    if args.json and args.format:
        print(
            "Error: cannot use both --json and --format",
            file=sys.stderr,
        )
        return 1

    if args.compare and (args.pre or args.post):
        print(
            "Error: cannot use --compare with --pre or --post",
            file=sys.stderr,
        )
        return 1

    # Deprecation warning for --json
    if args.json:
        import warnings

        warnings.warn(
            "--json is deprecated, use --format json instead",
            DeprecationWarning,
            stacklevel=2,
        )
        print(
            "Warning: --json is deprecated, use --format json instead",
            file=sys.stderr,
        )

    # Resolve effective format
    output_format = args.format
    if args.json:
        output_format = "json"

    prompt = args.prompt
    colour = not args.no_colour
    reporter = TerminalReporter(colour=colour, verbose=args.verbose)
    _log_file = sys.stderr if output_format else sys.stdout

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

    # Handle --compare flag
    if args.compare:
        return _handle_compare_mode(
            args=args,
            reporter=reporter,
            log=_log,
            output_format=output_format,
        )

    if not args.pre or not args.post:
        print(
            "Error: Use either 'nowreck fix \"<prompt>\"' or "
            "'nowreck fix --pre PATH --post PATH' or "
            "'nowreck fix --compare REF'.",
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
    output = _format_report(report, output_format, reporter)
    _write_output(output, args.output)

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
                # Never echo credential material back to the terminal.
                if key == "api_key":
                    value = mask_key(str(value))
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
        if key == "api_key":
            value = mask_key(str(value))
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

    v10 independent verification (default):
        ``nowreck fix "<prompt>"``
        Captures before/after state, applies the model's patch,
        and verifies claims against independently observed changes.

    Manual snapshot mode:
        ``nowreck fix "<prompt>" --pre ./before --post ./after``
        Uses user-provided directories instead of auto-snapshots.
    """
    from nowreck.verifier.prompt_verifier import PromptModeVerifier

    try:
        model_config = _build_model_config()
    except ModelError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    repo_path = Path.cwd()

    verifier = PromptModeVerifier(repo_path, model_config)

    if args.pre and args.post:
        # Manual snapshot mode
        before_path = _resolve_path(args.pre)
        after_path = _resolve_path(args.post)
        log(f"Using manual snapshots: {before_path} \u2192 {after_path}")
        result = verifier.verify_with_snapshots(
            prompt,
            before_path=before_path,
            after_path=after_path,
        )
    else:
        # Auto-snapshot mode
        log("Capturing before state...")
        result = verifier.verify(
            prompt,
            restore_after=True,
        )

    if not result.model_result or not result.model_result.claims:
        print(
            "Warning: Model returned no valid claims.",
            file=sys.stderr,
        )
        if result.model_result and result.model_result.parse_result:
            for err in result.model_result.parse_result.errors:
                print(f"  Parse error: {err}", file=sys.stderr)

    n_claims = len(result.model_result.claims) if result.model_result else 0
    patch_status = "applied" if result.patch_applied else "not applied"
    log(
        f"Claims: {n_claims}, "
        f"Patch: {patch_status}, "
        f"Evidence: {'independent' if result.has_independent_evidence else 'none'}"
    )

    # Resolve effective format
    output_format = args.format
    if args.json:
        output_format = "json"

    # Format and write output
    if output_format == "json":
        output = reporter.report_json_v10(result)
    elif output_format == "sarif":
        from nowreck.reporter.sarif_reporter import SarifReporter

        output = SarifReporter().report(result.report)
    elif output_format == "junit":
        from nowreck.reporter.junit_reporter import JUnitReporter

        output = JUnitReporter().report(result.report)
    else:
        output = reporter.report_v10(result)

    _write_output(output, args.output)

    report = result.report
    total_issues = report.unverifiable + report.contradicted + report.unexplained_count
    return 0 if total_issues == 0 else 1


def _build_model_config() -> ModelConfig:
    """Build a ``ModelConfig`` from saved configuration and environment
    variables."""
    cfg = NowreckConfig()
    data = cfg.load()

    try:
        return ModelConfig(
            api_key=_get_str_or(data, "api_key", ""),
            model=_get_str_or(data, "model", "gpt-4o"),
            base_url=_get_str_or(data, "base_url", "https://api.openai.com/v1"),
            temperature=_get_float_or(data, "temperature", 0.0),
            max_retries=_get_int_or(data, "max_retries", 1),
            provider=_get_str_or(data, "provider", "") or None,
        )
    except ValueError as exc:
        # Invalid stored values (e.g. out-of-range temperature) must
        # fail with a readable message, not a traceback.
        raise ModelError(f"Invalid configuration: {exc}") from exc


_logger = logging.getLogger(__name__)


def _get_str_or(data: dict[str, object], key: str, default: str) -> str:
    """Get a string value from ``data[key]`` with a safe fallback.

    Phase 5 / 3.4: any non-string value (int, float, bool, None,
    list, dict, etc.) is coerced via :func:`str` only when the
    value was already a string; otherwise the supplied *default*
    is returned and a debug-level log entry is emitted so an
    operator can spot mis-stored config without crashing the run.
    """
    val: object = data.get(key, default)
    if isinstance(val, str):
        return val
    _logger.debug(
        "Config key %r expected str, got %s; using default %r",
        key, type(val).__name__, default,
    )
    return default


def _get_float_or(data: dict[str, object], key: str, default: float) -> float:
    """Get a float value from ``data[key]`` with a safe fallback.

    Phase 5 / 3.4: accepts ``int``, ``float``, or numeric ``str``.
    Anything else (including ``None``, ``bool``, ``list``, ``dict``)
    silently returns *default* with a debug log entry rather than
    raising, so a corrupted config file cannot break startup.
    """
    val: object = data.get(key, default)
    if isinstance(val, bool):
        # ``bool`` is a subclass of ``int`` in Python — guard against
        # ``True``/``False`` being silently treated as 1/0 here.
        _logger.debug(
            "Config key %r expected float, got bool; using default %r",
            key, default,
        )
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            _logger.debug(
                "Config key %r=%r is not a valid float; using default %r",
                key, val, default,
            )
    return default


def _get_int_or(data: dict[str, object], key: str, default: int) -> int:
    """Get an int value from ``data[key]`` with a safe fallback.

    Phase 5 / 3.4: accepts ``int``, integral ``float`` (e.g. ``1.0``),
    or numeric ``str``.  Anything else (including ``bool``,
    ``None``, ``list``, ``dict``) silently returns *default* with a
    debug log entry rather than raising, so a corrupted config file
    cannot break startup.
    """
    val: object = data.get(key, default)
    if isinstance(val, bool):
        # ``bool`` is a subclass of ``int`` in Python — guard against
        # ``True``/``False`` being silently treated as 1/0 here.
        _logger.debug(
            "Config key %r expected int, got bool; using default %r",
            key, default,
        )
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if val.is_integer():
            return int(val)
        _logger.debug(
            "Config key %r=%r is not an integral float; using default %r",
            key, val, default,
        )
        return default
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            _logger.debug(
                "Config key %r=%r is not a valid int; using default %r",
                key, val, default,
            )
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
    path = Path(raw).expanduser().resolve()
    try:
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")
    except OSError as exc:
        raise ValueError(f"Cannot access path: {exc}") from exc
    return path


def _format_report(
    report: VerificationReport,
    output_format: str | None,
    terminal_reporter: TerminalReporter,
) -> str:
    """Format the verification report according to the output format."""
    if output_format == "json":
        return terminal_reporter.report_json(report)
    if output_format == "sarif":
        from nowreck.reporter.sarif_reporter import SarifReporter

        return SarifReporter().report(report)
    if output_format == "junit":
        from nowreck.reporter.junit_reporter import JUnitReporter

        return JUnitReporter().report(report)
    # Default: terminal
    return terminal_reporter.report(report)


def _write_output(output: str, output_path: str | None) -> None:
    """Write output to file or stdout."""
    if output_path is None:
        print(output)
        return

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")


def _handle_compare_mode(
    args: argparse.Namespace,
    reporter: TerminalReporter,
    log: Callable[[str], None],
    output_format: str | None,
) -> int:
    """Handle --compare mode: extract git snapshots and scan."""
    from nowreck.git_integration import GitError, GitSnapshot

    ref = args.compare

    try:
        with GitSnapshot(ref) as pre_snapshot:
            # Default post is HEAD
            post_ref = "HEAD"

            with GitSnapshot(post_ref) as post_snapshot:
                log(f"Comparing {ref} against {post_ref}")
                log(f"Pre snapshot:  {pre_snapshot.path}")
                log(f"Post snapshot: {post_snapshot.path}")

                # 1. Scan
                pre_scan = RepositoryScanner(pre_snapshot.path).scan()
                log(
                    f"  \u2192 {pre_scan.success_count} files parsed, "
                    f"{pre_scan.failure_count} failed"
                )

                post_scan = RepositoryScanner(post_snapshot.path).scan()
                log(
                    f"  \u2192 {post_scan.success_count} files parsed, "
                    f"{post_scan.failure_count} failed"
                )

                # 2. Build symbol indices
                pre_symbols = build_symbol_index(pre_scan)
                post_symbols = build_symbol_index(post_scan)
                log(
                    f"Symbols: {len(pre_symbols.all_symbols)} pre \u2192 "
                    f"{len(post_symbols.all_symbols)} post"
                )

                # 3. Detect changes
                changes = ChangeDetector.detect(
                    pre_scan,
                    post_scan,
                    pre_symbols,
                    post_symbols,
                )
                log(f"Changes detected: {len(changes)}")

                # 4. Verify claims if provided
                if args.claims:
                    parse_result = ClaimParser.parse(args.claims)
                    if not parse_result.success:
                        print(
                            "Warning: Some claims could not be parsed:",
                            file=sys.stderr,
                        )
                        for err in parse_result.errors:
                            print(f"  - {err}", file=sys.stderr)

                    if parse_result.claims:
                        log(f"Claims parsed: {len(parse_result.claims)}")
                        report = ClaimVerifier.verify(
                            parse_result.claims, changes
                        )
                    else:
                        report = VerificationReport(unexplained_changes=changes)
                else:
                    report = VerificationReport(unexplained_changes=changes)

                # 5. Format and output
                output = _format_report(report, output_format, reporter)
                _write_output(output, args.output)

                total_issues = (
                    report.unverifiable
                    + report.contradicted
                    + report.unexplained_count
                )
                return 0 if total_issues == 0 else 1

    except GitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
