"""Credentials class for username / passwords."""

from dataclasses import dataclass, field


@dataclass
class Credentials:
    """Credentials for authentication."""

    #: Username (email address) of the cloud account
    username: str = field(default="", repr=False)
    #: Password of the cloud account
    password: str = field(default="", repr=False)
