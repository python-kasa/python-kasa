"""Registry of the protocol and transport to use for connection parameters.

The most specific registration matching the connection parameters is used,
family value before device type, then encryption type, then https,
registering the same parameters again replaces the earlier registration::

    registry.register_transport(
        "SMART", "AES", SmartProtocol, AesTransport, https=False
    )
    registry.register_transport(
        "SMART.TAPOROBOVAC", "AES", SmartProtocol, SslTransport
    )
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from .deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from .iot import IotBulb, IotPlug
from .protocols import IotProtocol, SmartProtocol
from .protocols.smartcamprotocol import SmartCamProtocol
from .smart import SmartDevice
from .smartcam import SmartCamDevice
from .transports import (
    AesTransport,
    KlapTransport,
    KlapTransportV2,
    LinkieTransportV2,
    SslTransport,
    XorTransport,
)
from .transports.sslaestransport import SslAesTransport

if TYPE_CHECKING:
    from .device import Device
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


def _iot_klap_transport(*, config: DeviceConfig) -> BaseTransport:
    login_version = config.connection_type.login_version
    transport_cls = (
        KlapTransportV2 if login_version and login_version >= 2 else KlapTransport
    )
    return transport_cls(config=config)


class Registry:
    """The registered transports, starting with the built-in ones."""

    def __init__(self) -> None:
        self._entries: list[Entry] = []
        self.register_transport("IOT", "XOR", IotProtocol, XorTransport, https=False)
        self.register_transport(
            "IOT", "KLAP", IotProtocol, _iot_klap_transport, https=False
        )
        self.register_transport(
            "SMART", "AES", SmartProtocol, AesTransport, https=False
        )
        self.register_transport("SMART", "KLAP", SmartProtocol, KlapTransportV2)
        # H200 is device family SMART.TAPOHUB and uses SmartCamProtocol so use
        # https to distuingish from SmartProtocol devices
        self.register_transport(
            "SMART", "AES", SmartCamProtocol, SslAesTransport, https=True
        )
        self.register_transport(
            "SMART.IPCAMERA", None, SmartCamProtocol, SslAesTransport
        )
        self.register_transport(
            "SMART.TAPODOORBELL", None, SmartCamProtocol, SslAesTransport
        )
        self.register_transport("IOT.IPCAMERA", None, IotProtocol, LinkieTransportV2)
        # Older FW used a different transport
        self.register_transport("SMART.TAPOROBOVAC", "AES", SmartProtocol, SslTransport)

    def register_transport(
        self,
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
        key = (family, encryption, https)
        self._entries = [
            entry
            for entry in self._entries
            if (entry.family, entry.encryption, entry.https) != key
        ]
        enum = DeviceEncryptionType
        if encryption is not None and encryption not in enum._value2member_map_:
            member = object.__new__(enum)
            member._name_ = member._value_ = encryption
            enum._value2member_map_[encryption] = member
            enum._member_map_[encryption] = member
            enum._member_names_.append(encryption)
        self._entries.append(Entry(family, encryption, https, protocol, transport))

    def lookup(self, parameters: DeviceConnectionParameters) -> Entry | None:
        """Return the most specific entry for the parameters."""
        return max(
            (entry for entry in self._entries if entry.matches(parameters)),
            key=lambda entry: entry.specificity,
            default=None,
        )

    def get_protocol(self, config: DeviceConfig) -> BaseProtocol | None:
        """Return the protocol for the device config."""
        _LOGGER.debug("Finding protocol for %s", config.host)
        if not (entry := self.lookup(config.connection_type)):
            return None
        return entry.protocol(transport=entry.transport(config=config))

    def get_device_class(
        self, parameters: DeviceConnectionParameters
    ) -> type[Device] | None:
        """Return the device class for the connection parameters."""
        if not (entry := self.lookup(parameters)):
            return None
        if issubclass(entry.protocol, SmartCamProtocol):
            return SmartCamDevice
        if issubclass(entry.protocol, SmartProtocol):
            return SmartDevice
        # IOT device classes are decided by the sysinfo, discovery only has the family
        return {"IOT.SMARTPLUGSWITCH": IotPlug, "IOT.SMARTBULB": IotBulb}.get(
            parameters.device_family.value
        )

    def _choices(self) -> dict[tuple[DeviceFamily, DeviceEncryptionType, bool], Entry]:
        """Return the entry chosen for every family, encryption type and https."""
        choices = {
            (family, encryption, https): self.lookup(
                DeviceConnectionParameters(
                    device_family=family, encryption_type=encryption, https=https
                )
            )
            for family in DeviceFamily
            for encryption in DeviceEncryptionType
            for https in (False, True)
        }
        return {key: entry for key, entry in choices.items() if entry is not None}

    def load_plugins(self) -> None:
        """Call the installed plugins with the registry, skipping failing ones."""
        if os.environ.get("KASA_DISABLE_PLUGINS"):
            return

        for entry_point in entry_points(group="kasa.plugins"):
            entries = list(self._entries)
            before = self._choices()
            try:
                entry_point.load()(self)
            except KeyboardInterrupt:
                raise
            except BaseException:
                self._entries = entries  # drop what the plugin registered
                _LOGGER.exception("Unable to load plugin %s", entry_point.name)
                continue

            _LOGGER.info("Loaded plugin %s", entry_point.name)
            after = self._choices()
            # a plugin cannot unregister, so every key in before is in after
            overrides = dict.fromkeys(
                (old, after[key]) for key, old in before.items() if after[key] != old
            )
            for old, new in overrides:
                _LOGGER.warning(
                    "Plugin %s overrides %s (%s) with %s (%s)",
                    entry_point.name,
                    old.transport,
                    old,
                    new.transport,
                    new,
                )


REGISTRY = Registry()
