"""Basic module: plain functions, defaults, module-level calls.

Audit dimension: symbol extraction completeness (top-level functions).
"""

from collections import deque

GREETING = "hello"


def greet(name: str, excited: bool = False) -> str:
    message = f"{GREETING}, {name}"
    if excited:
        return message.upper()
    return message


def _internal_helper(value: int) -> int:
    return value * 2


def compute_total(values: list[int]) -> int:
    total = 0
    for v in values:
        total += _internal_helper(v)
    return total


def process_queue() -> None:
    work = deque([1, 2, 3])
    while work:
        item = work.popleft()
        print(item)


module_result = compute_total([1, 2, 3])