"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import base64
import errno
import hashlib
import logging
import struct
from abc import ABC, abstractmethod

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from .credentials import Credentials
from .deviceconfig import DeviceConfig

_LOGGER = logging.getLogger(__name__)
_NO_RETRY_ERRORS = {errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ECONNREFUSED}
_UNSIGNED_INT_NETWORK_ORDER = struct.Struct(">I")


def md5(payload: bytes) -> bytes:
    """Return the MD5 hash of the payload."""
    return hashlib.md5(payload).digest()  # noqa: S324


class BaseTransport(ABC):
    """Base class for all TP-Link protocol transports."""

    DEFAULT_TIMEOUT = 5

    def __init__(
        self,
        *,
        config: DeviceConfig,
    ) -> None:
        """Create a protocol object."""
        self._config = config
        self._host = config.host
        self._port = config.port_override or self.default_port
        self._credentials = config.credentials
        self._credentials_hash = config.credentials_hash
        self._timeout = config.timeout or self.DEFAULT_TIMEOUT

    @property
    @abstractmethod
    def default_port(self) -> int:
        """The default port for the transport."""

    @property
    @abstractmethod
    def credentials_hash(self) -> str:
        """The hashed credentials used by the transport."""

    @abstractmethod
    async def send(self, request: str) -> dict:
        """Send a message to the device and return a response."""

    @abstractmethod
    async def close(self) -> None:
        """Close the transport.  Abstract method to be overriden."""

    @abstractmethod
    async def reset(self) -> None:
        """Reset internal state."""


class BaseProtocol(ABC):
    """Base class for all TP-Link Smart Home communication."""

    def __init__(
        self,
        *,
        transport: BaseTransport,
    ) -> None:
        """Create a protocol object."""
        self._transport = transport

    @property
    def _host(self):
        return self._transport._host

    @property
    def config(self) -> DeviceConfig:
        """Return the connection parameters the device is using."""
        return self._transport._config

    @abstractmethod
    async def query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Query the device for the protocol.  Abstract method to be overriden."""

    @abstractmethod
    async def close(self) -> None:
        """Close the protocol.  Abstract method to be overriden."""


def get_default_credentials(tuple: tuple[str, str]) -> Credentials:
    """Return decoded default credentials."""
    un = base64.b64decode(tuple[0].encode()).decode()
    pw = base64.b64decode(tuple[1].encode()).decode()
    return Credentials(un, pw)


DEFAULT_CREDENTIALS = {
    "KASA": ("a2FzYUB0cC1saW5rLm5ldA==", "a2FzYVNldHVw"),
    "TAPO": ("dGVzdEB0cC1saW5rLm5ldA==", "dGVzdA=="),
}
