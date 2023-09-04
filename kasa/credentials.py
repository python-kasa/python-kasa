"""Credentials class for username / passwords."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Credentials:
    """Credentials for authentication."""

    username: Optional[str] = field(default=None, repr=False)
    password: Optional[str] = field(default=None, repr=False)
