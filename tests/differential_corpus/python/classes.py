"""Classes: methods, class attributes, properties, nested class.

Audit dimension: symbol extraction (CLASS + METHOD, one level deep).
"""


class Account:
    """A bank account with a nested currency helper."""

    currency = "USD"

    def __init__(self, owner: str, balance: float = 0.0) -> None:
        self.owner = owner
        self.balance = balance

    def deposit(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("deposit must be positive")
        self.balance += amount

    def withdraw(self, amount: float) -> bool:
        if amount > self.balance:
            return False
        self.balance -= amount
        return True

    @property
    def formatted_balance(self) -> str:
        return f"{self.currency} {self.balance:.2f}"

    class Metadata:
        """Nested class — not a symbol; outer shell content."""

        schema_version = 1


class SavingsAccount(Account):
    interest_rate = 0.02

    def apply_interest(self) -> None:
        self.balance *= 1 + self.interest_rate