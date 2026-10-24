"""Registry of the protocol and transport to use for connection parameters.

The most specific registration matching the connection parameters is used,
family value before device type, then encryption type, then https,
registering the same parameters again replaces the earlier registration::

    register_transport("SMART", "AES", SmartProtocol, AesTransport, https=False)
    register_transport("SMART.TAPOROBOVAC", "AES", SmartProtocol, SslTransport)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from .deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)

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

    def __str__(self) -> str:
        return f"{self.family} {self.encryption} https={self.https}"


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
    enum = DeviceEncryptionType
    if encryption is not None and encryption not in enum._value2member_map_:
        member = object.__new__(enum)
        member._name_ = member._value_ = encryption
        enum._value2member_map_[encryption] = member
        enum._member_map_[encryption] = member
        enum._member_names_.append(encryption)
    _ENTRIES.append(Entry(family, encryption, https, protocol, transport))


def lookup(parameters: DeviceConnectionParameters) -> Entry | None:
    """Return the most specific entry for the parameters."""
    return max(
        (entry for entry in _ENTRIES if entry.matches(parameters)),
        key=lambda entry: entry.specificity,
        default=None,
    )


def _all_parameters() -> list[DeviceConnectionParameters]:
    """Return every combination of the parameters entries are chosen by."""
    return [
        DeviceConnectionParameters(
            device_family=family, encryption_type=encryption, https=https
        )
        for family in DeviceFamily
        for encryption in DeviceEncryptionType
        for https in (False, True)
    ]


def _log_overrides(
    plugin: str,
    parameters: list[DeviceConnectionParameters],
    before: list[Entry | None],
) -> None:
    """Warn about the entries a plugin takes devices over from."""
    overrides = dict.fromkeys(
        (old, new)
        for params, old in zip(parameters, before, strict=True)
        if old is not None and (new := lookup(params)) is not None and new != old
    )
    for old, new in overrides:
        _LOGGER.warning(
            "Plugin %s overrides %s (%s) with %s (%s)",
            plugin,
            old.transport,
            old,
            new.transport,
            new,
        )


def load_plugins() -> None:
    """Load the installed plugins, skipping the ones that fail."""
    if os.environ.get("KASA_DISABLE_PLUGINS"):
        return

    for entry_point in entry_points(group="kasa.plugins"):
        entries = list(_ENTRIES)
        parameters = _all_parameters()
        before = [lookup(params) for params in parameters]
        try:
            entry_point.load()()
        except KeyboardInterrupt:
            raise
        except BaseException:
            _ENTRIES[:] = entries  # drop what the plugin registered before failing
            _LOGGER.exception("Unable to load plugin %s", entry_point.name)
        else:
            _LOGGER.info("Loaded plugin %s", entry_point.name)
            _log_overrides(entry_point.name, parameters, before)
