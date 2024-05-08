"""Module for Device base class."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping, Sequence
from warnings import warn

from .credentials import Credentials
from .device_type import DeviceType
from .deviceconfig import DeviceConfig
from .emeterstatus import EmeterStatus
from .exceptions import KasaException
from .feature import Feature
from .iotprotocol import IotProtocol
from .module import Module
from .protocol import BaseProtocol
from .xortransport import XorTransport

if TYPE_CHECKING:
    from .modulemapping import ModuleMapping, ModuleName


@dataclass
class WifiNetwork:
    """Wifi network container."""

    ssid: str
    key_type: int
    # These are available only on softaponboarding
    cipher_type: int | None = None
    bssid: str | None = None
    channel: int | None = None
    rssi: int | None = None

    # For SMART devices
    signal_level: int | None = None


_LOGGER = logging.getLogger(__name__)


class Device(ABC):
    """Common device interface.

    Do not instantiate this class directly, instead get a device instance from
    :func:`Device.connect()`, :func:`Discover.discover()`
    or :func:`Discover.discover_single()`.
    """

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        """Create a new Device instance.

        :param str host: host name or IP address of the device
        :param DeviceConfig config: device configuration
        :param BaseProtocol protocol: protocol for communicating with the device
        """
        if config and protocol:
            protocol._transport._config = config
        self.protocol: BaseProtocol = protocol or IotProtocol(
            transport=XorTransport(config=config or DeviceConfig(host=host)),
        )
        _LOGGER.debug("Initializing %s of type %s", self.host, type(self))
        self._device_type = DeviceType.Unknown
        # TODO: typing Any is just as using Optional[Dict] would require separate
        #       checks in accessors. the @updated_required decorator does not ensure
        #       mypy that these are not accessed incorrectly.
        self._last_update: Any = None
        self._discovery_info: dict[str, Any] | None = None

        self._features: dict[str, Feature] = {}
        self._parent: Device | None = None
        self._children: Mapping[str, Device] = {}

    @staticmethod
    async def connect(
        *,
        host: str | None = None,
        config: DeviceConfig | None = None,
    ) -> Device:
        """Connect to a single device by the given hostname or device configuration.

        This method avoids the UDP based discovery process and
        will connect directly to the device.

        It is generally preferred to avoid :func:`discover_single()` and
        use this function instead as it should perform better when
        the WiFi network is congested or the device is not responding
        to discovery requests.

        :param host: Hostname of device to query
        :param config: Connection parameters to ensure the correct protocol
            and connection options are used.
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        from .device_factory import connect  # pylint: disable=import-outside-toplevel

        return await connect(host=host, config=config)  # type: ignore[arg-type]

    @abstractmethod
    async def update(self, update_children: bool = True):
        """Update the device."""

    async def disconnect(self):
        """Disconnect and close any underlying connection resources."""
        await self.protocol.close()

    @property
    @abstractmethod
    def modules(self) -> ModuleMapping[Module]:
        """Return the device modules."""

    @property
    @abstractmethod
    def is_on(self) -> bool:
        """Return true if the device is on."""

    @property
    def is_off(self) -> bool:
        """Return True if device is off."""
        return not self.is_on

    @abstractmethod
    async def turn_on(self, **kwargs) -> dict | None:
        """Turn on the device."""

    @abstractmethod
    async def turn_off(self, **kwargs) -> dict | None:
        """Turn off the device."""

    @property
    def host(self) -> str:
        """The device host."""
        return self.protocol._transport._host

    @host.setter
    def host(self, value):
        """Set the device host.

        Generally used by discovery to set the hostname after ip discovery.
        """
        self.protocol._transport._host = value
        self.protocol._transport._config.host = value

    @property
    def port(self) -> int:
        """The device port."""
        return self.protocol._transport._port

    @property
    def credentials(self) -> Credentials | None:
        """The device credentials."""
        return self.protocol._transport._credentials

    @property
    def credentials_hash(self) -> str | None:
        """The protocol specific hash of the credentials the device is using."""
        return self.protocol._transport.credentials_hash

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        return self._device_type

    @abstractmethod
    def update_from_discover_info(self, info):
        """Update state from info from the discover call."""

    @property
    def config(self) -> DeviceConfig:
        """Return the device configuration."""
        return self.protocol.config

    @property
    @abstractmethod
    def model(self) -> str:
        """Returns the device model."""

    @property
    @abstractmethod
    def alias(self) -> str | None:
        """Returns the device alias or nickname."""

    async def _raw_query(self, request: str | dict) -> Any:
        """Send a raw query to the device."""
        return await self.protocol.query(request=request)

    @property
    def children(self) -> Sequence[Device]:
        """Returns the child devices."""
        return list(self._children.values())

    def get_child_device(self, id_: str) -> Device:
        """Return child device by its ID."""
        return self._children[id_]

    @property
    @abstractmethod
    def sys_info(self) -> dict[str, Any]:
        """Returns the device info."""

    def get_plug_by_name(self, name: str) -> Device:
        """Return child device for the given name."""
        for p in self.children:
            if p.alias == name:
                return p

        raise KasaException(f"Device has no child with {name}")

    def get_plug_by_index(self, index: int) -> Device:
        """Return child device for the given index."""
        if index + 1 > len(self.children) or index < 0:
            raise KasaException(
                f"Invalid index {index}, device has {len(self.children)} plugs"
            )
        return self.children[index]

    @property
    @abstractmethod
    def time(self) -> datetime:
        """Return the time."""

    @property
    @abstractmethod
    def timezone(self) -> dict:
        """Return the timezone and time_difference."""

    @property
    @abstractmethod
    def hw_info(self) -> dict:
        """Return hardware info for the device."""

    @property
    @abstractmethod
    def location(self) -> dict:
        """Return the device location."""

    @property
    @abstractmethod
    def rssi(self) -> int | None:
        """Return the rssi."""

    @property
    @abstractmethod
    def mac(self) -> str:
        """Return the mac formatted with colons."""

    @property
    @abstractmethod
    def device_id(self) -> str:
        """Return the device id."""

    @property
    @abstractmethod
    def internal_state(self) -> Any:
        """Return all the internal state data."""

    @property
    def state_information(self) -> dict[str, Any]:
        """Return available features and their values."""
        return {feat.name: feat.value for feat in self._features.values()}

    @property
    def features(self) -> dict[str, Feature]:
        """Return the list of supported features."""
        return self._features

    def _add_feature(self, feature: Feature):
        """Add a new feature to the device."""
        if feature.id in self._features:
            raise KasaException("Duplicate feature id %s" % feature.id)
        assert feature.id is not None  # TODO: hack for typing # noqa: S101
        self._features[feature.id] = feature

    @property
    @abstractmethod
    def has_emeter(self) -> bool:
        """Return if the device has emeter."""

    @property
    @abstractmethod
    def on_since(self) -> datetime | None:
        """Return the time that the device was turned on or None if turned off."""

    @abstractmethod
    async def get_emeter_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""

    @property
    @abstractmethod
    def emeter_realtime(self) -> EmeterStatus:
        """Get the emeter status."""

    @property
    @abstractmethod
    def emeter_this_month(self) -> float | None:
        """Get the emeter value for this month."""

    @property
    @abstractmethod
    def emeter_today(self) -> float | None | Any:
        """Get the emeter value for today."""
        # Return type of Any ensures consumers being shielded from the return
        # type by @update_required are not affected.

    @abstractmethod
    async def wifi_scan(self) -> list[WifiNetwork]:
        """Scan for available wifi networks."""

    @abstractmethod
    async def wifi_join(self, ssid: str, password: str, keytype: str = "wpa2_psk"):
        """Join the given wifi network."""

    @abstractmethod
    async def set_alias(self, alias: str):
        """Set the device name (alias)."""

    def __repr__(self):
        if self._last_update is None:
            return f"<{self.device_type} at {self.host} - update() needed>"
        return f"<{self.device_type} at {self.host} - {self.alias} ({self.model})>"

    _deprecated_device_type_attributes = {
        # is_type
        "is_bulb": (Module.Light, DeviceType.Bulb),
        "is_dimmer": (Module.Light, DeviceType.Dimmer),
        "is_light_strip": (Module.LightEffect, DeviceType.LightStrip),
        "is_plug": (Module.Led, DeviceType.Plug),
        "is_wallswitch": (Module.Led, DeviceType.WallSwitch),
        "is_strip": (None, DeviceType.Strip),
        "is_strip_socket": (None, DeviceType.StripSocket),
    }

    def _get_replacing_attr(self, module_name: ModuleName, *attrs):
        if module_name not in self.modules:
            return None

        for attr in attrs:
            if hasattr(self.modules[module_name], attr):
                return getattr(self.modules[module_name], attr)

        return None

    _deprecated_other_attributes = {
        # light attributes
        "is_color": (Module.Light, ["is_color"]),
        "is_dimmable": (Module.Light, ["is_dimmable"]),
        "is_variable_color_temp": (Module.Light, ["is_variable_color_temp"]),
        "brightness": (Module.Light, ["brightness"]),
        "set_brightness": (Module.Light, ["set_brightness"]),
        "hsv": (Module.Light, ["hsv"]),
        "set_hsv": (Module.Light, ["set_hsv"]),
        "color_temp": (Module.Light, ["color_temp"]),
        "set_color_temp": (Module.Light, ["set_color_temp"]),
        "valid_temperature_range": (Module.Light, ["valid_temperature_range"]),
        "has_effects": (Module.Light, ["has_effects"]),
        "_deprecated_set_light_state": (Module.Light, ["has_effects"]),
        # led attributes
        "led": (Module.Led, ["led"]),
        "set_led": (Module.Led, ["set_led"]),
        # light effect attributes
        # The return values for effect is a str instead of dict so the lightstrip
        # modules have a _deprecated method to return the value as before.
        "effect": (Module.LightEffect, ["_deprecated_effect", "effect"]),
        # The return values for effect_list includes the Off effect so the lightstrip
        # modules have a _deprecated method to return the values as before.
        "effect_list": (Module.LightEffect, ["_deprecated_effect_list", "effect_list"]),
        "set_effect": (Module.LightEffect, ["set_effect"]),
        "set_custom_effect": (Module.LightEffect, ["set_custom_effect"]),
        # light preset attributes
        "presets": (Module.LightPreset, ["_deprecated_presets", "preset_states_list"]),
        "save_preset": (Module.LightPreset, ["_deprecated_save_preset"]),
    }

    def __getattr__(self, name):
        # is_device_type
        if dep_device_type_attr := self._deprecated_device_type_attributes.get(name):
            module = dep_device_type_attr[0]
            msg = f"{name} is deprecated"
            if module:
                msg += f", use: {module} in device.modules instead"
            warn(msg, DeprecationWarning, stacklevel=1)
            return self.device_type == dep_device_type_attr[1]
        # Other deprecated attributes
        if (dep_attr := self._deprecated_other_attributes.get(name)) and (
            (replacing_attr := self._get_replacing_attr(dep_attr[0], *dep_attr[1]))
            is not None
        ):
            module_name = dep_attr[0]
            msg = (
                f"{name} is deprecated, use: "
                + f"Module.{module_name} in device.modules instead"
            )
            warn(msg, DeprecationWarning, stacklevel=1)
            return replacing_attr
        raise AttributeError(f"Device has no attribute {name!r}")
