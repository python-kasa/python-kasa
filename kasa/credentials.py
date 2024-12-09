"""Credentials class for username / passwords."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field


@dataclass
class Credentials:
    """Credentials for authentication."""

    #: Username (email address) of the cloud account
    username: str = field(default="", repr=False)
    #: Password of the cloud account
    password: str = field(default="", repr=False)


def get_default_credentials(tuple: tuple[str, str]) -> Credentials:
    """Return decoded default credentials."""
    un = base64.b64decode(tuple[0].encode()).decode()
    pw = base64.b64decode(tuple[1].encode()).decode()
    return Credentials(un, pw)


DEFAULT_CREDENTIALS = {
    "KASA": ("a2FzYUB0cC1saW5rLm5ldA==", "a2FzYVNldHVw"),
    "KASACAMERA": ("YWRtaW4=", "MjEyMzJmMjk3YTU3YTVhNzQzODk0YTBlNGE4MDFmYzM="),
    "TAPO": ("dGVzdEB0cC1saW5rLm5ldA==", "dGVzdA=="),
    "TAPOCAMERA": ("YWRtaW4=", "YWRtaW4="),
}
