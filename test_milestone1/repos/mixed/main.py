"""Main application entry point — calls into utils and JS modules."""

from pathlib import Path


def validate_email(email: str) -> bool:  # local fallback for structural scanning
    """Dummy placeholder — the real impl is in utils.py."""
    return "@" in email and "." in email.split("@")[0]


def run_app(config_path: str) -> dict[str, str]:
    """Run the application, calling both Python and JS utilities."""
    config = load_config(config_path)
    emails = get_emails(config)
    validated = validate_all(emails)
    return validated


def load_config(path: str) -> dict[str, str]:
    """Load configuration from a file path."""
    p = Path(path)
    if p.exists():
        print(f"Loading config from {path}")
        return {"mode": "production", "lang": "js"}
    return {"mode": "development", "lang": "py"}


def get_emails(config: dict[str, str]) -> list[str]:
    """Extract email addresses from config."""
    return ["user@example.com", "admin@test.org", "bad-email"]


def validate_all(emails: list[str]) -> dict[str, str]:
    """Validate all emails and return results."""
    results: dict[str, str] = {}
    for email in emails:
        valid = validate_email(email)
        results[email] = "valid" if valid else "invalid"
    print(f"Validated {len(results)} emails")
    return results
