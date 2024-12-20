"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import errno
import hashlib
import logging
import struct
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from ..deviceconfig import DeviceConfig

_LOGGER = logging.getLogger(__name__)
_NO_RETRY_ERRORS = {errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ECONNREFUSED}
_UNSIGNED_INT_NETWORK_ORDER = struct.Struct(">I")

_T = TypeVar("_T")


if TYPE_CHECKING:
    from ..transports import BaseTransport


def redact_data(data: _T, redactors: dict[str, Callable[[Any], Any] | None]) -> _T:
    """Redact sensitive data for logging."""
    if not isinstance(data, dict | list):
        return data

    if isinstance(data, list):
        return cast(_T, [redact_data(val, redactors) for val in data])

    redacted = {**data}

    for key, value in redacted.items():
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        if key in redactors:
            if redactor := redactors[key]:
                try:
                    redacted[key] = redactor(value)
                except:  # noqa: E722
                    redacted[key] = "**REDACTEX**"
            else:
                redacted[key] = "**REDACTED**"
        elif isinstance(value, dict):
            redacted[key] = redact_data(value, redactors)
        elif isinstance(value, list):
            redacted[key] = [redact_data(item, redactors) for item in value]

    return cast(_T, redacted)


def mask_mac(mac: str) -> str:
    """Return mac address with last two octects blanked."""
    if len(mac) == 12:
        return f"{mac[:6]}000000"
    delim = ":" if ":" in mac else "-"
    rest = delim.join(format(s, "02x") for s in bytes.fromhex("000000"))
    return f"{mac[:8]}{delim}{rest}"


def md5(payload: bytes) -> bytes:
    """Return the MD5 hash of the payload."""
    return hashlib.md5(payload).digest()  # noqa: S324


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
    def _host(self) -> str:
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
