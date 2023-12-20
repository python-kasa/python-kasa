"""Module for a TAPO device."""
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, cast

from ..aestransport import AesTransport
from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import AuthenticationException
from ..smartdevice import SmartDevice
from ..smartprotocol import SmartProtocol

_LOGGER = logging.getLogger(__name__)


class TapoDevice(SmartDevice):
    """Base class to represent a TAPO device."""

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host, port=port, credentials=credentials, timeout=timeout)
        self._components: Optional[Dict[str, Any]] = None
        self._state_information: Dict[str, Any] = {}
        self._discovery_info: Optional[Dict[str, Any]] = None
        config = DeviceConfig(
            host=host,
            port=port,
            credentials=credentials,  # type: ignore[arg-type]
            timeout=timeout,
        )
        self.protocol = SmartProtocol(
            transport=AesTransport(config=config),
        )

    async def update(self, update_children: bool = True):
        """Update the device."""
        if self.credentials is None or self.credentials.username is None:
            raise AuthenticationException("Tapo plug requires authentication.")

        if self._components is None:
            resp = await self.protocol.query("component_nego")
            self._components = resp["component_nego"]

        req = {
            "get_device_info": None,
            "get_device_usage": None,
            "get_device_time": None,
        }
        resp = await self.protocol.query(req)
        self._info = resp["get_device_info"]
        self._usage = resp["get_device_usage"]
        self._time = resp["get_device_time"]

        self._last_update = self._data = {
            "components": self._components,
            "info": self._info,
            "usage": self._usage,
            "time": self._time,
        }

        _LOGGER.debug("Got an update: %s", self._data)

    @property
    def sys_info(self) -> Dict[str, Any]:
        """Returns the device info."""
        return self._info  # type: ignore

    @property
    def model(self) -> str:
        """Returns the device model."""
        return str(self._info.get("model"))

    @property
    def alias(self) -> str:
        """Returns the device alias or nickname."""
        return base64.b64decode(str(self._info.get("nickname"))).decode()

    @property
    def time(self) -> datetime:
        """Return the time."""
        td = timedelta(minutes=cast(float, self._time.get("time_diff")))
        if self._time.get("region"):
            tz = timezone(td, str(self._time.get("region")))
        else:
            # in case the device returns a blank region this will result in the
            # tzname being a UTC offset
            tz = timezone(td)
        return datetime.fromtimestamp(
            cast(float, self._time.get("timestamp")),
            tz=tz,
        )

    @property
    def timezone(self) -> Dict:
        """Return the timezone and time_difference."""
        ti = self.time
        return {"timezone": ti.tzname()}

    @property
    def hw_info(self) -> Dict:
        """Return hardware info for the device."""
        return {
            "sw_ver": self._info.get("fw_ver"),
            "hw_ver": self._info.get("hw_ver"),
            "mac": self._info.get("mac"),
            "type": self._info.get("type"),
            "hwId": self._info.get("device_id"),
            "dev_name": self.alias,
            "oemId": self._info.get("oem_id"),
        }

    @property
    def location(self) -> Dict:
        """Return the device location."""
        loc = {
            "latitude": cast(float, self._info.get("latitude")) / 10_000,
            "longitude": cast(float, self._info.get("longitude")) / 10_000,
        }
        return loc

    @property
    def rssi(self) -> Optional[int]:
        """Return the rssi."""
        rssi = self._info.get("rssi")
        return int(rssi) if rssi else None

    @property
    def mac(self) -> str:
        """Return the mac formatted with colons."""
        return str(self._info.get("mac")).replace("-", ":")

    @property
    def device_id(self) -> str:
        """Return the device id."""
        return str(self._info.get("device_id"))  # type: ignore

    @property
    def internal_state(self) -> Any:
        """Return all the internal state data."""
        return self._data

    async def _query_helper(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ) -> Any:
        res = await self.protocol.query({cmd: arg})

        return res

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return the key state information."""
        return {
            "overheated": self._info.get("overheated"),
            "signal_level": self._info.get("signal_level"),
            "SSID": base64.b64decode(str(self._info.get("ssid"))).decode(),
        }

    @property
    def features(self) -> Set[str]:
        """Return the list of supported features."""
        # TODO:
        return set()

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return bool(self._info.get("device_on"))

    async def turn_on(self, **kwargs):
        """Turn on the device."""
        await self.protocol.query({"set_device_info": {"device_on": True}})

    async def turn_off(self, **kwargs):
        """Turn off the device."""
        await self.protocol.query({"set_device_info": {"device_on": False}})

    def update_from_discover_info(self, info):
        """Update state from info from the discover call."""
        self._discovery_info = info
        self._info = info
