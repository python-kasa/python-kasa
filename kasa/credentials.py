"""Credentials class for username / passwords."""

from dataclasses import dataclass, field


@dataclass
class Credentials:
    """Credentials for authentication."""

    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
