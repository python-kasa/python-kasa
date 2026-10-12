"""Registry of the protocol and transport to use for connection parameters.

The most specific registration matching the connection parameters is used,
family value before device type, then encryption type, then https,
registering the same parameters again replaces the earlier registration::

    register_transport("SMART", "AES", SmartProtocol, AesTransport, https=False)
    register_transport("SMART.TAPOROBOVAC", "AES", SmartProtocol, SslTransport)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .deviceconfig import DeviceConnectionParameters

if TYPE_CHECKING:
    from .protocols import BaseProtocol
    from .transports import BaseTransport

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Entry:
    """The protocol and transport to use for matching connection parameters."""

    family: str  # "IOT"/"SMART" or a full family value like "SMART.IPCAMERA"
    encryption: str | None  # None matches any encryption type
    https: bool | None  # None matches both
    protocol: type[BaseProtocol]
    transport: Callable[..., BaseTransport]

    def matches(self, parameters: DeviceConnectionParameters) -> bool:
        """Return True if the entry applies to the connection parameters."""
        family = parameters.device_family.value
        return (
            self.family in (family, family.partition(".")[0])
            and self.encryption in (None, parameters.encryption_type.value)
            and self.https in (None, parameters.https)
        )

    @property
    def specificity(self) -> int:
        """Family value before device type, then encryption type, then https."""
        return (
            4 * ("." in self.family)
            + 2 * (self.encryption is not None)
            + (self.https is not None)
        )


_ENTRIES: list[Entry] = []


def register_transport(
    family: str,
    encryption: str | None,
    protocol: type[BaseProtocol],
    transport: Callable[..., BaseTransport],
    *,
    https: bool | None = None,
) -> None:
    """Register the protocol and transport for connection parameters.

    Registering the same parameters again replaces the earlier registration.

    :param family: Device type (``IOT``, ``SMART``) or a device family value.
    :param encryption: Encryption type value, None matches any.
    :param protocol: Protocol class.
    :param transport: Called as ``transport(config=config)``.
    :param https: None matches both.
    """
    existing = next(
        (
            entry
            for entry in _ENTRIES
            if entry.family == family
            and entry.encryption == encryption
            and entry.https == https
        ),
        None,
    )
    if existing:
        _LOGGER.warning(
            "Replacing transport %s for %s %s https=%s with %s",
            existing.transport,
            family,
            encryption,
            https,
            transport,
        )
        _ENTRIES.remove(existing)
    _ENTRIES.append(Entry(family, encryption, https, protocol, transport))


def lookup(parameters: DeviceConnectionParameters) -> Entry | None:
    """Return the most specific entry for the parameters."""
    return max(
        (entry for entry in _ENTRIES if entry.matches(parameters)),
        key=lambda entry: entry.specificity,
        default=None,
    )
