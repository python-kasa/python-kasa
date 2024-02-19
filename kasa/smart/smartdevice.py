"""Module for a SMART device."""
import base64
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, cast

from ..aestransport import AesTransport
from ..device import Device, WifiNetwork
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..emeterstatus import EmeterStatus
from ..exceptions import AuthenticationError, DeviceError, KasaException, SmartErrorCode
from ..feature import Feature, FeatureType
from ..smartprotocol import SmartProtocol
from .modules import *  # noqa: F403

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .smartmodule import SmartModule


class SmartDevice(Device):
    """Base class to represent a SMART protocol based device."""

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
        self._state_information: Dict[str, Any] = {}
        self.modules: Dict[str, "SmartModule"] = {}
        self._parent: Optional["SmartDevice"] = None
        self._children: Mapping[str, "SmartDevice"] = {}

    async def _initialize_children(self):
        """Initialize children for power strips."""
        children = self.internal_state["child_info"]["child_device_list"]
        children_components = {
            child["device_id"]: {
                comp["id"]: int(comp["ver_code"]) for comp in child["component_list"]
            }
            for child in self.internal_state["get_child_device_component_list"][
                "child_component_list"
            ]
        }
        from .smartchilddevice import SmartChildDevice

        self._children = {
            child_info["device_id"]: await SmartChildDevice.create(
                parent=self,
                child_info=child_info,
                child_components=children_components[child_info["device_id"]],
            )
            for child_info in children
        }
        # TODO: This may not be the best approach, but it allows distinguishing
        #  between power strips and hubs for the time being.
        if all(child.is_plug for child in self._children.values()):
            self._device_type = DeviceType.Strip
        else:
            self._device_type = DeviceType.Hub

    @property
    def children(self) -> Sequence["SmartDevice"]:
        """Return list of children."""
        return list(self._children.values())

    def _try_get_response(self, responses: dict, request: str, default=None) -> dict:
        response = responses.get(request)
        if isinstance(response, SmartErrorCode):
            _LOGGER.debug(
                "Error %s getting request %s for device %s",
                response,
                request,
                self.host,
            )
            response = None
        if response is not None:
            return response
        if default is not None:
            return default
        raise KasaException(
            f"{request} not found in {responses} for device {self.host}"
        )

    async def _negotiate(self):
        resp = await self.protocol.query("component_nego")
        self._components_raw = resp["component_nego"]
        self._components = {
            comp["id"]: int(comp["ver_code"])
            for comp in self._components_raw["component_list"]
        }

    async def update(self, update_children: bool = True):
        """Update the device."""
        if self.credentials is None and self.credentials_hash is None:
            raise AuthenticationError("Tapo plug requires authentication.")

        if self._components_raw is None:
            await self._negotiate()
            await self._initialize_modules()

        req: Dict[str, Any] = {}

        # TODO: this could be optimized by constructing the query only once
        for module in self.modules.values():
            req.update(module.query())

        resp = await self.protocol.query(req)

        self._info = self._try_get_response(resp, "get_device_info")

        self._last_update = {
            "components": self._components_raw,
            **resp,
            "child_info": self._try_get_response(resp, "get_child_device_list", {}),
        }

        if child_info := self._last_update.get("child_info"):
            if not self.children:
                await self._initialize_children()

            # TODO: we don't currently perform queries on children based on modules,
            #  but just update the information that is returned in the main query.
            for info in child_info["child_device_list"]:
                self._children[info["device_id"]]._update_internal_state(info)

        # We can first initialize the features after the first update.
        # We make here an assumption that every device has at least a single feature.
        if not self._features:
            await self._initialize_features()

        _LOGGER.debug("Got an update: %s", self._last_update)

    async def _initialize_modules(self):
        """Initialize modules based on component negotiation response."""
        from .smartmodule import SmartModule

        for mod in SmartModule.REGISTERED_MODULES.values():
            _LOGGER.debug("%s requires %s", mod, mod.REQUIRED_COMPONENT)
            if mod.REQUIRED_COMPONENT in self._components:
                _LOGGER.debug(
                    "Found required %s, adding %s to modules.",
                    mod.REQUIRED_COMPONENT,
                    mod.__name__,
                )
                module = mod(self, mod.REQUIRED_COMPONENT)
                self.modules[module.name] = module

    async def _initialize_features(self):
        """Initialize device features."""
        self._add_feature(Feature(self, "Device ID", attribute_getter="device_id"))
        if "device_on" in self._info:
            self._add_feature(
                Feature(
                    self,
                    "State",
                    attribute_getter="is_on",
                    attribute_setter="set_state",
                    type=FeatureType.Switch,
                )
            )

        if "signal_level" in self._info:
            self._add_feature(
                Feature(
                    self,
                    "Signal Level",
                    attribute_getter=lambda x: x._info["signal_level"],
                    icon="mdi:signal",
                )
            )

        if "rssi" in self._info:
            self._add_feature(
                Feature(
                    self,
                    "RSSI",
                    attribute_getter=lambda x: x._info["rssi"],
                    icon="mdi:signal",
                )
            )

        if "ssid" in self._info:
            self._add_feature(
                Feature(
                    device=self, name="SSID", attribute_getter="ssid", icon="mdi:wifi"
                )
            )

        if "overheated" in self._info:
            self._add_feature(
                Feature(
                    self,
                    "Overheated",
                    attribute_getter=lambda x: x._info["overheated"],
                    icon="mdi:heat-wave",
                    type=FeatureType.BinarySensor,
                )
            )

        # We check for the key available, and not for the property truthiness,
        # as the value is falsy when the device is off.
        if "on_time" in self._info:
            self._add_feature(
                Feature(
                    device=self,
                    name="On since",
                    attribute_getter="on_since",
                    icon="mdi:clock",
                )
            )

        for module in self.modules.values():
            for feat in module._module_features.values():
                self._add_feature(feat)

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
        # TODO: Default to parent's time module for child devices
        if self._parent and "TimeModule" in self.modules:
            _timemod = cast(TimeModule, self._parent.modules["TimeModule"])  # noqa: F405
        else:
            _timemod = cast(TimeModule, self.modules["TimeModule"])  # noqa: F405

        return _timemod.time

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

    def _update_internal_state(self, info):
        """Update internal state.

        This is used by the parent to push updates to its children
        """
        # TODO: cleanup the _last_update, _info mess.
        self._last_update = self._info = info

    async def _query_helper(
        self, method: str, params: Optional[Dict] = None, child_ids=None
    ) -> Any:
        res = await self.protocol.query({method: params})

        return res

    @property
    def ssid(self) -> str:
        """Return ssid of the connected wifi ap."""
        ssid = self._info.get("ssid")
        ssid = base64.b64decode(ssid).decode() if ssid else "No SSID"
        return ssid

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return the key state information."""
        return {
            "overheated": self._info.get("overheated"),
            "signal_level": self._info.get("signal_level"),
            "SSID": self.ssid,
        }

    @property
    def has_emeter(self) -> bool:
        """Return if the device has emeter."""
        return "EnergyModule" in self.modules

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return bool(self._info.get("device_on"))

    async def set_state(self, on: bool):  # TODO: better name wanted.
        """Set the device state.

        See :meth:`is_on`.
        """
        return await self.protocol.query({"set_device_info": {"device_on": on}})

    async def turn_on(self, **kwargs):
        """Turn on the device."""
        await self.set_state(True)

    async def turn_off(self, **kwargs):
        """Turn off the device."""
        await self.set_state(False)

    def update_from_discover_info(self, info):
        """Update state from info from the discover call."""
        self._discovery_info = info
        self._info = info

    async def get_emeter_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        _LOGGER.warning("Deprecated, use `emeter_realtime`.")
        if not self.has_emeter:
            raise KasaException("Device has no emeter")
        return self.emeter_realtime

    @property
    def emeter_realtime(self) -> EmeterStatus:
        """Get the emeter status."""
        energy = cast(EnergyModule, self.modules["EnergyModule"])  # noqa: F405
        return energy.emeter_realtime

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Get the emeter value for this month."""
        energy = cast(EnergyModule, self.modules["EnergyModule"])  # noqa: F405
        return energy.emeter_this_month

    @property
    def emeter_today(self) -> Optional[float]:
        """Get the emeter value for today."""
        energy = cast(EnergyModule, self.modules["EnergyModule"])  # noqa: F405
        return energy.emeter_today

    @property
    def on_since(self) -> Optional[datetime]:
        """Return the time that the device was turned on or None if turned off."""
        if (
            not self._info.get("device_on")
            or (on_time := self._info.get("on_time")) is None
        ):
            return None
        on_time = cast(float, on_time)
        if (timemod := self.modules.get("TimeModule")) is not None:
            timemod = cast(TimeModule, timemod)  # noqa: F405
            return timemod.time - timedelta(seconds=on_time)
        else:  # We have no device time, use current local time.
            return datetime.now().replace(microsecond=0) - timedelta(seconds=on_time)

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
            raise AuthenticationError("Device requires authentication.")

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
            "time": self.internal_state["get_device_time"],
        }

        # The device does not respond to the request but changes the settings
        # immediately which causes us to timeout.
        # Thus, We limit retries and suppress the raised exception as useless.
        try:
            return await self.protocol.query({"set_qs_info": payload}, retry_count=0)
        except DeviceError:
            raise  # Re-raise on device-reported errors
        except KasaException:
            _LOGGER.debug("Received an expected for wifi join, but this is expected")

    async def update_credentials(self, username: str, password: str):
        """Update device credentials.

        This will replace the existing authentication credentials on the device.
        """
        time_data = self.internal_state["get_device_time"]
        payload = {
            "account": {
                "username": base64.b64encode(username.encode()).decode(),
                "password": base64.b64encode(password.encode()).decode(),
            },
            "time": time_data,
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

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        if self._device_type is not DeviceType.Unknown:
            return self._device_type

        if self.children:
            if "SMART.TAPOHUB" in self.sys_info["type"]:
                pass  # TODO: placeholder for future hub PR
            else:
                self._device_type = DeviceType.Strip
        elif "light_strip" in self._components:
            self._device_type = DeviceType.LightStrip
        elif "dimmer_calibration" in self._components:
            self._device_type = DeviceType.Dimmer
        elif "brightness" in self._components:
            self._device_type = DeviceType.Bulb
        elif "PLUG" in self.sys_info["type"]:
            self._device_type = DeviceType.Plug
        else:
            _LOGGER.warning("Unknown device type, falling back to plug")
            self._device_type = DeviceType.Plug

        return self._device_type
