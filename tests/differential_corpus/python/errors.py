"""Error handling: custom exceptions, raise/try/except/finally."""


class ConfigError(Exception):
    pass


class ValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


def parse_config(raw: str) -> dict:
    if not raw.strip():
        raise ConfigError("empty config")
    result = {}
    for line in raw.splitlines():
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def load_with_fallback(path: str, fallback: dict) -> dict:
    try:
        with open(path) as handle:
            return parse_config(handle.read())
    except (ConfigError, OSError) as exc:
        print(f"falling back: {exc}")
        return fallback
    finally:
        print("load attempt finished")