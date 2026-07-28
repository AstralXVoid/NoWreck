# Python utility module (shared with JS utils)


def validate_email(email: str) -> bool:
    """Check if an email looks valid."""
    if "@" in email and "." in email:
        parts = email.split("@")
        if len(parts) == 2 and len(parts[1].split(".")) >= 2:
            print(f"Validated: {email}")
            return True
    return False


def format_date(year: int, month: int, day: int) -> str:
    """Format a date string."""
    return f"{year}-{month:02d}-{day:02d}"


class Logger:
    """Simple structured logger."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def log(self, message: str) -> None:
        output = f"[{self.prefix}] {message}"
        print(output)
        return output
