"""Module for a TAPO device."""
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, cast

from ..aestransport import AesTransport
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..emeterstatus import EmeterStatus
from ..exceptions import AuthenticationException, SmartDeviceException
from ..modules import Emeter
from ..smartdevice import SmartDevice, WifiNetwork
from ..smartprotocol import SmartProtocol

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .childdevice import ChildDevice


class TapoDevice(SmartDevice):
    """Base class to represent a TAPO device."""

    def __init__(
        self,
        host: str,
        *,
        config: Optional[DeviceConfig] = None,
        protocol: Optional[SmartProtocol] = None,
    ) -> None:
        _protocol = protocol or SmartProtocol(
            transport=AesTransport(config=config or DeviceConfig(host=host)),
        )
        super().__init__(host=host, config=config, protocol=_protocol)
        self.protocol: SmartProtocol
        self._components_raw: Optional[Dict[str, Any]] = None
        self._components: Dict[str, int] = {}
        self._children: Dict[str, "ChildDevice"] = {}
        self._energy: Dict[str, Any] = {}
        self._state_information: Dict[str, Any] = {}

    async def _initialize_children(self):
        """Initialize children for power strips."""
        children = self._last_update["child_info"]["child_device_list"]
        # TODO: Use the type information to construct children,
        #  as hubs can also have them.
        from .childdevice import ChildDevice

        self._children = {
            child["device_id"]: ChildDevice(parent=self, child_id=child["device_id"])
            for child in children
        }
        self._device_type = DeviceType.Strip

    @property
    def children(self):
        """Return list of children.

        This is just to keep the existing SmartDevice API intact.
        """
        return list(self._children.values())

    @children.setter
    def children(self, children):
        """Initialize from a list of children.

        This is just to keep the existing SmartDevice API intact.
        """
        self._children = {child["device_id"]: child for child in children}

    async def update(self, update_children: bool = True):
        """Update the device."""
        if self.credentials is None and self.credentials_hash is None:
            raise AuthenticationException("Tapo plug requires authentication.")

        if self._components_raw is None:
            resp = await self.protocol.query("component_nego")
            self._components_raw = resp["component_nego"]
            self._components = {
                comp["id"]: comp["ver_code"]
                for comp in self._components_raw["component_list"]
            }
            await self._initialize_modules()

        extra_reqs: Dict[str, Any] = {}

        if "child_device" in self._components:
            extra_reqs = {**extra_reqs, "get_child_device_list": None}

        if "energy_monitoring" in self._components:
            extra_reqs = {
                **extra_reqs,
                "get_energy_usage": None,
                "get_current_power": None,
            }

        req = {
            "get_device_info": None,
            "get_device_usage": None,
            "get_device_time": None,
            **extra_reqs,
        }

        resp = await self.protocol.query(req)

        self._info = resp["get_device_info"]
        self._usage = resp["get_device_usage"]
        self._time = resp["get_device_time"]
        # Emeter is not always available, but we set them still for now.
        self._energy = resp.get("get_energy_usage", {})
        self._emeter = resp.get("get_current_power", {})

        self._last_update = {
            "components": self._components_raw,
            "info": self._info,
            "usage": self._usage,
            "time": self._time,
            "energy": self._energy,
            "emeter": self._emeter,
            "child_info": resp.get("get_child_device_list", {}),
        }

        if child_info := self._last_update.get("child_info"):
            if not self.children:
                await self._initialize_children()
            for info in child_info["child_device_list"]:
                self._children[info["device_id"]].update_internal_state(info)

        _LOGGER.debug("Got an update: %s", self._last_update)

    async def _initialize_modules(self):
        """Initialize modules based on component negotiation response."""
        if "energy_monitoring" in self._components:
            self.emeter_type = "emeter"
            self.modules["emeter"] = Emeter(self, self.emeter_type)

    @property
    def sys_info(self) -> Dict[str, Any]:
        """Returns the device info."""
        return self._info  # type: ignore

    @property
    def model(self) -> str:
        """Returns the device model."""
        return str(self._info.get("model"))

    @property
    def alias(self) -> Optional[str]:
        """Returns the device alias or nickname."""
        if self._info and (nickname := self._info.get("nickname")):
            return base64.b64decode(nickname).decode()
        else:
            return None

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
            "latitude": cast(float, self._info.get("latitude", 0)) / 10_000,
            "longitude": cast(float, self._info.get("longitude", 0)) / 10_000,
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
        return str(self._info.get("device_id"))

    @property
    def internal_state(self) -> Any:
        """Return all the internal state data."""
        return self._last_update

    async def _query_helper(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ) -> Any:
        res = await self.protocol.query({cmd: arg})

        return res

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return the key state information."""
        ssid = self._info.get("ssid")
        ssid = base64.b64decode(ssid).decode() if ssid else "No SSID"

        return {
            "overheated": self._info.get("overheated"),
            "signal_level": self._info.get("signal_level"),
            "SSID": ssid,
        }

    @property
    def features(self) -> Set[str]:
        """Return the list of supported features."""
        # TODO:
        return set()

    @property
    def has_emeter(self) -> bool:
        """Return if the device has emeter."""
        return "energy_monitoring" in self._components

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

    async def get_emeter_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        self._verify_emeter()
        resp = await self.protocol.query("get_energy_usage")
        self._energy = resp["get_energy_usage"]
        return self.emeter_realtime

    def _convert_energy_data(self, data, scale) -> Optional[float]:
        """Return adjusted emeter information."""
        return data if not data else data * scale

    @property
    def emeter_realtime(self) -> EmeterStatus:
        """Get the emeter status."""
        return EmeterStatus(
            {
                "power_mw": self._energy.get("current_power"),
                "total": self._convert_energy_data(
                    self._energy.get("today_energy"), 1 / 1000
                ),
            }
        )

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Get the emeter value for this month."""
        return self._convert_energy_data(self._energy.get("month_energy"), 1 / 1000)

    @property
    def emeter_today(self) -> Optional[float]:
        """Get the emeter value for today."""
        return self._convert_energy_data(self._energy.get("today_energy"), 1 / 1000)

    async def wifi_scan(self) -> List[WifiNetwork]:
        """Scan for available wifi networks."""

        def _net_for_scan_info(res):
            return WifiNetwork(
                ssid=base64.b64decode(res["ssid"]).decode(),
                cipher_type=res["cipher_type"],
                key_type=res["key_type"],
                channel=res["channel"],
                signal_level=res["signal_level"],
                bssid=res["bssid"],
            )

        async def _query_networks(networks=None, start_index=0):
            _LOGGER.debug("Querying networks using start_index=%s", start_index)
            if networks is None:
                networks = []

            resp = await self.protocol.query(
                {"get_wireless_scan_info": {"start_index": start_index}}
            )
            network_list = [
                _net_for_scan_info(net)
                for net in resp["get_wireless_scan_info"]["ap_list"]
            ]
            networks.extend(network_list)

            if resp["get_wireless_scan_info"].get("sum", 0) > start_index + 10:
                return await _query_networks(networks, start_index=start_index + 10)

            return networks

        return await _query_networks()

    async def wifi_join(self, ssid: str, password: str, keytype: str = "wpa2_psk"):
        """Join the given wifi network.

        This method returns nothing as the device tries to activate the new
        settings immediately instead of responding to the request.

        If joining the network fails, the device will return to the previous state
        after some delay.
        """
        if not self.credentials:
            raise AuthenticationException("Device requires authentication.")

        payload = {
            "account": {
                "username": base64.b64encode(
                    self.credentials.username.encode()
                ).decode(),
                "password": base64.b64encode(
                    self.credentials.password.encode()
                ).decode(),
            },
            "wireless": {
                "key_type": keytype,
                "password": base64.b64encode(password.encode()).decode(),
                "ssid": base64.b64encode(ssid.encode()).decode(),
            },
            "time": self.internal_state["time"],
        }

        # The device does not respond to the request but changes the settings
        # immediately which causes us to timeout.
        # Thus, We limit retries and suppress the raised exception as useless.
        try:
            return await self.protocol.query({"set_qs_info": payload}, retry_count=0)
        except SmartDeviceException as ex:
            if ex.error_code:  # Re-raise on device-reported errors
                raise

            _LOGGER.debug("Received an expected for wifi join, but this is expected")

    async def update_credentials(self, username: str, password: str):
        """Update device credentials.

        This will replace the existing authentication credentials on the device.
        """
        t = self.internal_state["time"]
        payload = {
            "account": {
                "username": base64.b64encode(username.encode()).decode(),
                "password": base64.b64encode(password.encode()).decode(),
            },
            "time": t,
        }
        return await self.protocol.query({"set_qs_info": payload})

    async def set_alias(self, alias: str):
        """Set the device name (alias)."""
        return await self.protocol.query(
            {"set_device_info": {"nickname": base64.b64encode(alias.encode()).decode()}}
        )

    async def reboot(self, delay: int = 1) -> None:
        """Reboot the device.

        Note that giving a delay of zero causes this to block,
        as the device reboots immediately without responding to the call.
        """
        await self.protocol.query({"device_reboot": {"delay": delay}})

    async def factory_reset(self) -> None:
        """Reset device back to factory settings.

        Note, this does not downgrade the firmware.
        """
        await self.protocol.query("device_reset")
