"""Credentials class for username / passwords."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from kasa.json import loads as json_loads


@dataclass
class Credentials:
    """Credentials for authentication."""

    #: Username (email address) of the cloud account
    username: str = field(default="", repr=False)
    #: Password of the cloud account
    password: str = field(default="", repr=False)


def _credentials_from_plaintext_hash(credentials_hash: str) -> Credentials | None:
    """Recover the credentials from a hash that stores them in plaintext.

    The ssl aes and tpap transports store base64 json of the plaintext
    credentials, so a transport handed one of those after a device changed its
    encryption type can derive its own hash rather than failing to
    authenticate. Klap and aes hashes are one way, so this only works in that
    direction.
    """
    try:
        decoded = json_loads(base64.b64decode(credentials_hash.encode()))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    username = decoded.get("un")
    password = decoded.get("pwd")
    if isinstance(username, str) and isinstance(password, str):
        return Credentials(username, password)
    return None


def get_default_credentials(crdentials: tuple[str, str]) -> Credentials:
    """Return decoded default credentials."""
    un = base64.b64decode(crdentials[0].encode()).decode()
    pw = base64.b64decode(crdentials[1].encode()).decode()
    return Credentials(un, pw)


DEFAULT_CREDENTIALS = {
    "KASA": ("a2FzYUB0cC1saW5rLm5ldA==", "a2FzYVNldHVw"),
    "KASACAMERA": ("YWRtaW4=", "MjEyMzJmMjk3YTU3YTVhNzQzODk0YTBlNGE4MDFmYzM="),
    "TAPO": ("dGVzdEB0cC1saW5rLm5ldA==", "dGVzdA=="),
    "TAPOCAMERA": ("YWRtaW4=", "YWRtaW4="),
    "TAPOCAMERA_LV3": ("YWRtaW4=", "VFBMMDc1NTI2NDYwNjAz"),
}
