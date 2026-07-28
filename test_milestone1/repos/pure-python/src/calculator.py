"""Calculator module."""


class Calculator:
    """A simple calculator."""

    def add(self, a: float, b: float) -> float:
        return float(a + b)

    def subtract(self, a: float, b: float) -> float:
        return float(a - b)

    def multiply(self, a: float, b: float) -> float:
        result = a * b
        print(f"multiply({a}, {b}) = {result}")
        return result

    def divide(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b


def compute_average(values: list[float]) -> float:
    """Compute the average of a list of numbers."""
    total = sum(values)
    count = len(values)
    return total / count
