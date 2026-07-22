from __future__ import annotations

import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import questionary

from nowreck.claims.parser import ClaimParser
from nowreck.detector.change_detector import ChangeDetector
from nowreck.model.provider import ModelConfig, ModelError, ModelProvider
from nowreck.reporter.terminal_reporter import TerminalReporter
from nowreck.scanner.repository_scanner import RepositoryScanner
from nowreck.scanner.symbol_index import build_symbol_index
from nowreck.storage.config import NowreckConfig
from nowreck.verifier.verifier import ClaimVerifier, VerificationReport

# ---------------------------------------------------------------------------
# Exit signal — raised from any depth to exit the picker immediately
# ---------------------------------------------------------------------------


class _ExitPicker(Exception):
    """Raised when the user presses Ctrl+C during any questionary prompt.

    Propagates up through nested helper functions to ``run_picker()``,
    where it's caught to break the main loop and exit cleanly.
    """
    pass


# ---------------------------------------------------------------------------
# Paths under .nowreck/
# ---------------------------------------------------------------------------

_LAST_REPORT_REL = Path(".nowreck") / "last_report.txt"


def run_picker() -> int:
    """Run the interactive terminal picker.

    Presents a menu-driven interface that collects input through
    interactive prompts and calls the existing verification pipeline
    under the hood — same code path, friendlier front door.

    Returns:
        Exit code (0 for success).
    """
    reporter = TerminalReporter(colour=True)

    while True:
        try:
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    "Verify with AI prompt",
                    "Scan two directories for changes",
                    "Set up or change your API key",
                    "View last report",
                    "Exit",
                ],
                instruction=" ",
            ).ask()
        except _ExitPicker:
            break

        # User pressed Ctrl+C or selected Exit
        if choice is None or choice == "Exit":
            break

        try:
            if choice == "Verify with AI prompt":
                _run_verification(reporter)
            elif choice == "Scan two directories for changes":
                _run_pre_post(reporter)
            elif choice == "Set up or change your API key":
                _run_config_setup()
            elif choice == "View last report":
                _view_last_report()
        except _ExitPicker:
            break

    return 0


# ---------------------------------------------------------------------------
# Verification flow
# ---------------------------------------------------------------------------


def _run_verification(reporter: TerminalReporter) -> None:
    """Walk the user through running a full verification."""
    prompt = questionary.text(
        "Describe the change you want the AI to make:",
        multiline=False,
    ).ask()

    if prompt is None:
        raise _ExitPicker()

    if not prompt.strip():
        print("No prompt provided. Returning to menu.")
        _pause()
        return

    # Check that configuration is present before proceeding.
    config = NowreckConfig()
    data = config.load()

    api_key = str(data.get("api_key", "") or "")
    base_url = str(data.get("base_url", "") or "")
    model_name = str(data.get("model", "") or "")

    if not api_key or not base_url or not model_name:
        print()
        print("You need to configure an API endpoint first.")
        should_setup = questionary.confirm(
            "Set up your API configuration now?",
            default=True,
        ).ask()

        if should_setup is None:
            raise _ExitPicker()

        if should_setup:
            _run_config_setup()
            data = config.load()
            api_key = str(data.get("api_key", "") or "")
            base_url = str(data.get("base_url", "") or "")
            model_name = str(data.get("model", "") or "")
            if not api_key or not base_url or not model_name:
                print("Incomplete API configuration. Returning to menu.")
                _pause()
                return
        else:
            _pause()
            return

    # Check endpoint reachability before calling the model.
    print()
    _check_endpoint_reachable(base_url)

    try:
        temperature = float(data.get("temperature", 0.0))
        max_retries = int(data.get("max_retries", 1))
    except (ValueError, TypeError):
        temperature = 0.0
        max_retries = 1

    model_config = ModelConfig(
        api_key=api_key,
        model=model_name,
        base_url=base_url,
        temperature=temperature,
        max_retries=max_retries,
    )

    provider = ModelProvider(config=model_config)

    print("Running verification...")
    try:
        result = provider.changes_from_prompt(prompt)
    except ModelError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        _pause()
        return

    if not result.claims:
        print("Warning: Model returned no valid claims.", file=sys.stderr)
        if result.parse_result:
            for err in result.parse_result.errors:
                print(f"  Parse error: {err}", file=sys.stderr)

    if result.attempts > 1:
        print(f"Claims parsed on attempt {result.attempts}")
    else:
        print(f"Claims parsed: {len(result.claims)}")

    print(f"Changes derived: {len(result.changes)}")
    report = ClaimVerifier.verify(result.claims, result.changes)

    print()
    output = reporter.report(report)
    print(output)

    # Save for "View last report"
    _save_last_report(output)

    _pause()


# ---------------------------------------------------------------------------
# Configuration setup
# ---------------------------------------------------------------------------


def _run_config_setup() -> None:
    """Walk the user through configuring API credentials."""
    config = NowreckConfig()
    data = config.load()

    print()
    print("--- API Configuration ---")
    print("Enter the details for an OpenAI-compatible model provider.")

    api_key_raw: str | None = questionary.password(
        "API key (leave blank to keep current):",
        default=str(data.get("api_key", "")),
    ).ask()

    if api_key_raw is None:
        raise _ExitPicker()

    base_url: str | None = questionary.text(
        "Base URL:",
        default=str(data.get("base_url", "https://api.openai.com/v1")),
    ).ask()

    if base_url is None:
        raise _ExitPicker()

    model_name: str | None = questionary.text(
        "Model:",
        default=str(data.get("model", "gpt-4o")),
    ).ask()

    if model_name is None:
        raise _ExitPicker()

    # Only save non-empty values — never overwrite with empty string.
    if api_key_raw:
        data["api_key"] = api_key_raw
    if base_url:
        data["base_url"] = base_url
    if model_name:
        data["model"] = model_name

    config.save(data)
    print("Configuration saved.")
    _pause()


# ---------------------------------------------------------------------------
# Pre/Post mode — scanning two directory snapshots
# ---------------------------------------------------------------------------


def _run_pre_post(reporter: TerminalReporter) -> None:
    """Walk the user through scanning two directories for changes.

    Collects pre/post snapshot paths, optionally a claims JSON, and
    runs the detection pipeline — no API key required unless claims
    are provided.
    """
    # 1. Collect pre path with inline validation.
    pre_path_str = questionary.path(
        "Path to the pre-change snapshot:",
        only_directories=True,
        validate=_validate_directory_path,
    ).ask()

    if pre_path_str is None:
        raise _ExitPicker()

    pre_path = Path(pre_path_str).resolve()

    # 2. Collect post path with inline validation.
    post_path_str = questionary.path(
        "Path to the post-change snapshot:",
        only_directories=True,
        validate=_validate_directory_path,
    ).ask()

    if post_path_str is None:
        raise _ExitPicker()

    post_path = Path(post_path_str).resolve()

    # 3. Ask about claims.
    claims_choice = questionary.select(
        "Do you have claims to verify?",
        choices=[
            "No, just detect changes",
            "Yes, enter claims JSON",
            "Yes, load from a file",
        ],
        instruction=" ",
    ).ask()

    if claims_choice is None:
        raise _ExitPicker()

    claims_json: str | None = None

    if claims_choice == "Yes, enter claims JSON":
        claims_json = questionary.text(
            "Paste the claims JSON:",
            multiline=True,
        ).ask()
        if claims_json is None:
            raise _ExitPicker()
        if not claims_json.strip():
            print("No claims provided. Running detection only.")
            claims_json = None
    elif claims_choice == "Yes, load from a file":
        claims_path_str = questionary.path(
            "Path to claims JSON file:",
            file_filter=lambda p: p.endswith(".json"),
        ).ask()
        if claims_path_str is None:
            raise _ExitPicker()
        try:
            claims_json = Path(claims_path_str).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading claims file: {exc}")
            _pause()
            return

    # 4. Scan.
    print()
    print(f"Scanning pre snapshot:  {pre_path}")
    pre_scan = RepositoryScanner(pre_path).scan()
    print(
        f"  \u2192 {pre_scan.success_count} files parsed, "
        f"{pre_scan.failure_count} failed"
    )

    post_scan = RepositoryScanner(post_path).scan()
    print(f"Scanning post snapshot: {post_path}")
    print(
        f"  \u2192 {post_scan.success_count} files parsed, "
        f"{post_scan.failure_count} failed"
    )

    # 5. Build symbol indices.
    pre_symbols = build_symbol_index(pre_scan)
    post_symbols = build_symbol_index(post_scan)
    print(
        f"Symbols: {len(pre_symbols.all_symbols)} pre \u2192 "
        f"{len(post_symbols.all_symbols)} post"
    )

    # 6. Detect changes.
    changes = ChangeDetector.detect(
        pre_scan,
        post_scan,
        pre_symbols,
        post_symbols,
    )
    print(f"Changes detected: {len(changes)}")

    # 7. Optionally verify claims.
    if claims_json:
        parse_result = ClaimParser.parse(claims_json)
        if not parse_result.success:
            print("Warning: Some claims could not be parsed:", file=sys.stderr)
            for err in parse_result.errors:
                print(f"  - {err}", file=sys.stderr)

        if parse_result.claims:
            print(f"Claims parsed: {len(parse_result.claims)}")
            report = ClaimVerifier.verify(parse_result.claims, changes)
        else:
            report = VerificationReport(unexplained_changes=changes)
    else:
        report = VerificationReport(unexplained_changes=changes)

    # 8. Report.
    print()
    output = reporter.report(report)
    print(output)

    # Save for "View last report"
    _save_last_report(output)

    _pause()


# ---------------------------------------------------------------------------
# Helpers — path validation
# ---------------------------------------------------------------------------


def _validate_directory_path(path_str: str) -> bool | str:
    """Validate that *path_str* points to an existing directory.

    Returns ``True`` if valid, or an error message string if not.
    This is called inline by questionary as the user types.
    """
    if not path_str.strip():
        return "Path cannot be empty."

    resolved = Path(path_str).expanduser().resolve()
    if not resolved.exists():
        return f"Path does not exist: {resolved}"
    if not resolved.is_dir():
        return f"Path is not a directory: {resolved}"
    return True


# ---------------------------------------------------------------------------
# View last report
# ---------------------------------------------------------------------------


def _view_last_report() -> None:
    """Display the last saved verification report."""
    report_path = _resolve_last_report_path()
    if not report_path.exists():
        print("No previous report found. Run a verification first.")
        _pause()
        return

    try:
        content = report_path.read_text(encoding="utf-8")
    except OSError:
        print("Could not read the last report file.")
        _pause()
        return

    print()
    print(content)
    _pause()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_endpoint_reachable(base_url: str) -> None:
    """Check whether the base URL is reachable.

    Prints a confirmation or a warning, then returns.
    This is a best-effort check — a failure doesn't block execution
    (the actual model call may still work through a different route).
    """
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        print("  ✓ Endpoint configured")
        return

    if not host:
        print("  ✓ Endpoint configured")
        return

    # TCP-level connectivity check (lightweight, no HTTP semantics).
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        print("  ✓ Endpoint configured (confirmed reachable)")
    except OSError:
        print("  ⚠ Endpoint configured (could not verify reachability)")
        print("    The model call will still be attempted.")
    except KeyboardInterrupt:
        print("  ✓ Endpoint configured")
        return


def _save_last_report(text: str) -> None:
    """Save report text to disk for later recall."""
    path = _resolve_last_report_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass  # best-effort


def _resolve_last_report_path() -> Path:
    """Return the absolute path to the last-report file."""
    return Path.cwd() / _LAST_REPORT_REL


def _pause() -> None:
    """Wait for the user to press Enter before continuing.

    Handles ``KeyboardInterrupt`` (Ctrl+C) and ``EOFError`` by raising
    ``_ExitPicker``, which propagates up to ``run_picker()`` and exits
    the tool immediately.
    """
    try:
        input("\nPress Enter to return to the main menu.")
    except (KeyboardInterrupt, EOFError):
        raise _ExitPicker()
