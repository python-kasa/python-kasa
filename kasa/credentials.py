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


def get_default_credentials(
    tuple: tuple[str, str, str | None], login_version: int | None = None
) -> Credentials:
    """Return decoded default credentials."""
    un = base64.b64decode(tuple[0].encode()).decode()
    if login_version == 3 and tuple[2] is not None:
        pw = base64.b64decode(tuple[2].encode()).decode()
    else:
        pw = base64.b64decode(tuple[1].encode()).decode()
    return Credentials(un, pw)


DEFAULT_CREDENTIALS = {
    "KASA": ("a2FzYUB0cC1saW5rLm5ldA==", "a2FzYVNldHVw", None),
    "KASACAMERA": ("YWRtaW4=", "MjEyMzJmMjk3YTU3YTVhNzQzODk0YTBlNGE4MDFmYzM=", None),
    "TAPO": ("dGVzdEB0cC1saW5rLm5ldA==", "dGVzdA==", None),
    "TAPOCAMERA": ("YWRtaW4=", "YWRtaW4=", "VFBMMDc1NTI2NDYwNjAz"),
}
