"""Decorators: decorated functions and methods are still symbols."""

import functools
import time


def timed(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = func(*args, **kwargs)
        return result

    return wrapper


def retry(times: int = 3):
    def decorator(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            for _ in range(times):
                try:
                    return func(*args, **kwargs)
                except OSError:
                    continue
            raise OSError("still failing")

        return inner

    return decorator


@timed
def slow_operation(seconds: float) -> str:
    time.sleep(seconds)
    return "done"


@retry(times=5)
def flaky_call() -> int:
    return 42


class Service:
    @timed
    def handle(self, request: str) -> str:
        return f"handled:{request}"