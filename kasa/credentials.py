"""Credentials class for username / passwords."""

from dataclasses import dataclass, field


@dataclass
class Credentials:
    """Credentials for authentication."""

    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)

    def __bool__(self):
        """Overridden to allow easy checks for valid credentials."""
        return self.username != "" and self.password != ""