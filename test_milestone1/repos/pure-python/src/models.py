"""Data models."""


class User:
    """Represents a user in the system."""

    def __init__(self, username: str, email: str) -> None:
        self.username = username
        self.email = email

    def display(self) -> str:
        info = f"User({self.username}, {self.email})"
        print(info)
        return info

    def to_dict(self) -> dict[str, str]:
        return {"username": self.username, "email": self.email}


class AdminUser(User):
    """An admin user with elevated privileges."""

    def __init__(self, username: str, email: str, role: str) -> None:
        super().__init__(username, email)
        self.role = role

    def display(self) -> str:
        info = f"Admin({self.username}, {self.email}, role={self.role})"
        print(info)
        return info
