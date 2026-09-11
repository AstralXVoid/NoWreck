"""Closures and lambdas: nested functions are NOT symbols.

Audit dimension: nested-function visibility (documented boundary).
"""


def make_multiplier(factor: int):
    def multiply(x: int) -> int:
        return x * factor

    return multiply


def apply_all(ops, values):
    results = []
    for op in ops:
        for value in values:
            results.append(op(value))
    return results


double = make_multiplier(2)
triple = make_multiplier(3)

squared = lambda x: x * x  # noqa: E731