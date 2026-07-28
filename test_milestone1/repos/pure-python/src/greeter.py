"""Greeting utilities."""


def greet(name: str) -> str:
    """Greet someone by name."""
    message = format_greeting("Hello", name)
    print(message)
    return message


def format_greeting(template: str, name: str) -> str:
    """Format a greeting string."""
    return f"{template}, {name}!"


def farewell(name: str) -> str:
    """Say goodbye."""
    msg = f"Goodbye, {name}!"
    print(msg)
    return msg
