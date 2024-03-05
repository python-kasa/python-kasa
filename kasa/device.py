"""Module for Device base class."""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .credentials import Credentials
from .device_type import DeviceType
from .deviceconfig import DeviceConfig
from .emeterstatus import EmeterStatus
from .exceptions import KasaException
from .feature import Feature
from .iotprotocol import IotProtocol
from .protocol import BaseProtocol
from .xortransport import XorTransport


@dataclass
class WifiNetwork:
    """Wifi network container."""

    ssid: str
    key_type: int
    # These are available only on softaponboarding
    cipher_type: Optional[int] = None
    bssid: Optional[str] = None
    channel: Optional[int] = None
    rssi: Optional[int] = None

    # For SMART devices
    signal_level: Optional[int] = None


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
        config: Optional[DeviceConfig] = None,
        protocol: Optional[BaseProtocol] = None,
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
        self._discovery_info: Optional[Dict[str, Any]] = None

        self.modules: Dict[str, Any] = {}
        self._features: Dict[str, Feature] = {}
        self._parent: Optional["Device"] = None
        self._children: Mapping[str, "Device"] = {}

    @staticmethod
    async def connect(
        *,
        host: Optional[str] = None,
        config: Optional[DeviceConfig] = None,
    ) -> "Device":
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
    def is_on(self) -> bool:
        """Return true if the device is on."""

    @property
    def is_off(self) -> bool:
        """Return True if device is off."""
        return not self.is_on

    @abstractmethod
    async def turn_on(self, **kwargs) -> Optional[Dict]:
        """Turn on the device."""

    @abstractmethod
    async def turn_off(self, **kwargs) -> Optional[Dict]:
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
    def credentials(self) -> Optional[Credentials]:
        """The device credentials."""
        return self.protocol._transport._credentials

    @property
    def credentials_hash(self) -> Optional[str]:
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
    def alias(self) -> Optional[str]:
        """Returns the device alias or nickname."""

    async def _raw_query(self, request: Union[str, Dict]) -> Any:
        """Send a raw query to the device."""
        return await self.protocol.query(request=request)

    @property
    def children(self) -> Sequence["Device"]:
        """Returns the child devices."""
        return list(self._children.values())

    def get_child_device(self, id_: str) -> "Device":
        """Return child device by its ID."""
        return self._children[id_]

    @property
    @abstractmethod
    def sys_info(self) -> Dict[str, Any]:
        """Returns the device info."""

    @property
    def is_bulb(self) -> bool:
        """Return True if the device is a bulb."""
        return self.device_type == DeviceType.Bulb

    @property
    def is_light_strip(self) -> bool:
        """Return True if the device is a led strip."""
        return self.device_type == DeviceType.LightStrip

    @property
    def is_plug(self) -> bool:
        """Return True if the device is a plug."""
        return self.device_type == DeviceType.Plug

    @property
    def is_wallswitch(self) -> bool:
        """Return True if the device is a switch."""
        return self.device_type == DeviceType.WallSwitch

    @property
    def is_strip(self) -> bool:
        """Return True if the device is a strip."""
        return self.device_type == DeviceType.Strip

    @property
    def is_strip_socket(self) -> bool:
        """Return True if the device is a strip socket."""
        return self.device_type == DeviceType.StripSocket

    @property
    def is_dimmer(self) -> bool:
        """Return True if the device is a dimmer."""
        return self.device_type == DeviceType.Dimmer

    @property
    def is_dimmable(self) -> bool:
        """Return  True if the device is dimmable."""
        return False

    @property
    def is_variable_color_temp(self) -> bool:
        """Return True if the device supports color temperature."""
        return False

    @property
    def is_color(self) -> bool:
        """Return True if the device supports color changes."""
        return False

    def get_plug_by_name(self, name: str) -> "Device":
        """Return child device for the given name."""
        for p in self.children:
            if p.alias == name:
                return p

        raise KasaException(f"Device has no child with {name}")

    def get_plug_by_index(self, index: int) -> "Device":
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
    def timezone(self) -> Dict:
        """Return the timezone and time_difference."""

    @property
    @abstractmethod
    def hw_info(self) -> Dict:
        """Return hardware info for the device."""

    @property
    @abstractmethod
    def location(self) -> Dict:
        """Return the device location."""

    @property
    @abstractmethod
    def rssi(self) -> Optional[int]:
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
    @abstractmethod
    def state_information(self) -> Dict[str, Any]:
        """Return the key state information."""

    @property
    def features(self) -> Dict[str, Feature]:
        """Return the list of supported features."""
        return self._features

    def _add_feature(self, feature: Feature):
        """Add a new feature to the device."""
        desc_name = feature.name.lower().replace(" ", "_")
        if desc_name in self._features:
            raise KasaException("Duplicate feature name %s" % desc_name)
        self._features[desc_name] = feature

    @property
    @abstractmethod
    def has_emeter(self) -> bool:
        """Return if the device has emeter."""

    @property
    @abstractmethod
    def on_since(self) -> Optional[datetime]:
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
    def emeter_this_month(self) -> Optional[float]:
        """Get the emeter value for this month."""

    @property
    @abstractmethod
    def emeter_today(self) -> Union[Optional[float], Any]:
        """Get the emeter value for today."""
        # Return type of Any ensures consumers being shielded from the return
        # type by @update_required are not affected.

    @abstractmethod
    async def wifi_scan(self) -> List[WifiNetwork]:
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
