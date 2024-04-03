"""Module for a SMART device."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence, cast, overload

from ..aestransport import AesTransport
from ..bulb import HSV, Bulb, BulbPreset, ColorTempRange
from ..device import Device, WifiNetwork
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..emeterstatus import EmeterStatus
from ..exceptions import AuthenticationError, DeviceError, KasaException, SmartErrorCode
from ..fan import Fan
from ..feature import Feature
from ..module import ModuleT
from ..smartprotocol import SmartProtocol
from .modules import (
    Brightness,
    CloudModule,
    ColorModule,
    ColorTemperatureModule,
    DeviceModule,
    EnergyModule,
    FanModule,
    Firmware,
    TimeModule,
)
from .smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


# List of modules that wall switches with children, i.e. ks240 report on
# the child but only work on the parent.  See longer note below in _initialize_modules.
# This list should be updated when creating new modules that could have the
# same issue, homekit perhaps?
WALL_SWITCH_PARENT_ONLY_MODULES = [DeviceModule, TimeModule, Firmware, CloudModule]


# Device must go last as the other interfaces also inherit Device
# and python needs a consistent method resolution order.
class SmartDevice(Bulb, Fan, Device):
    """Base class to represent a SMART protocol based device."""

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: SmartProtocol | None = None,
    ) -> None:
        _protocol = protocol or SmartProtocol(
            transport=AesTransport(config=config or DeviceConfig(host=host)),
        )
        super().__init__(host=host, config=config, protocol=_protocol)
        self.protocol: SmartProtocol
        self._components_raw: dict[str, Any] | None = None
        self._components: dict[str, int] = {}
        self._state_information: dict[str, Any] = {}
        self._modules: dict[str, SmartModule] = {}
        self._exposes_child_modules = False
        self._parent: SmartDevice | None = None
        self._children: Mapping[str, SmartDevice] = {}
        self._last_update = {}

    async def _initialize_children(self):
        """Initialize children for power strips."""
        child_info_query = {
            "get_child_device_component_list": None,
            "get_child_device_list": None,
        }
        resp = await self.protocol.query(child_info_query)
        self.internal_state.update(resp)

        children = self.internal_state["get_child_device_list"]["child_device_list"]
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

    @property
    def children(self) -> Sequence[SmartDevice]:
        """Return list of children."""
        return list(self._children.values())

    @property
    def modules(self) -> dict[str, SmartModule]:
        """Return the device modules."""
        return self._modules

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
        """Perform initialization.

        We fetch the device info and the available components as early as possible.
        If the device reports supporting child devices, they are also initialized.
        """
        initial_query = {
            "component_nego": None,
            "get_device_info": None,
            "get_connect_cloud_state": None,
        }
        resp = await self.protocol.query(initial_query)

        # Save the initial state to allow modules access the device info already
        # during the initialization, which is necessary as some information like the
        # supported color temperature range is contained within the response.
        self._last_update.update(resp)
        self._info = self._try_get_response(resp, "get_device_info")

        # Create our internal presentation of available components
        self._components_raw = resp["component_nego"]
        self._components = {
            comp["id"]: int(comp["ver_code"])
            for comp in self._components_raw["component_list"]
        }

        if "child_device" in self._components and not self.children:
            await self._initialize_children()

    async def update(self, update_children: bool = True):
        """Update the device."""
        if self.credentials is None and self.credentials_hash is None:
            raise AuthenticationError("Tapo plug requires authentication.")

        if self._components_raw is None:
            await self._negotiate()
            await self._initialize_modules()

        req: dict[str, Any] = {}

        # TODO: this could be optimized by constructing the query only once
        for module in self._modules.values():
            req.update(module.query())

        self._last_update = resp = await self.protocol.query(req)

        self._info = self._try_get_response(resp, "get_device_info")
        if child_info := self._try_get_response(resp, "get_child_device_list", {}):
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

        # Some wall switches (like ks240) are internally presented as having child
        # devices which report the child's components on the parent's sysinfo, even
        # when they need to be accessed through the children.
        # The logic below ensures that such devices add all but whitelisted, only on
        # the child device.
        skip_parent_only_modules = False
        child_modules_to_skip = {}
        if self._parent and self._parent.device_type == DeviceType.WallSwitch:
            skip_parent_only_modules = True
        elif self._children and self.device_type == DeviceType.WallSwitch:
            # _initialize_modules is called on the parent after the children
            self._exposes_child_modules = True
            for child in self._children.values():
                child_modules_to_skip.update(**child.modules)

        for mod in SmartModule.REGISTERED_MODULES.values():
            _LOGGER.debug("%s requires %s", mod, mod.REQUIRED_COMPONENT)

            if (
                skip_parent_only_modules and mod in WALL_SWITCH_PARENT_ONLY_MODULES
            ) or mod.__name__ in child_modules_to_skip:
                continue
            if mod.REQUIRED_COMPONENT in self._components:
                _LOGGER.debug(
                    "Found required %s, adding %s to modules.",
                    mod.REQUIRED_COMPONENT,
                    mod.__name__,
                )
                module = mod(self, mod.REQUIRED_COMPONENT)
                if await module._check_supported():
                    self._modules[module.name] = module

    async def _initialize_features(self):
        """Initialize device features."""
        self._add_feature(
            Feature(
                self,
                id="device_id",
                name="Device ID",
                attribute_getter="device_id",
                category=Feature.Category.Debug,
            )
        )
        if "device_on" in self._info:
            self._add_feature(
                Feature(
                    self,
                    id="state",
                    name="State",
                    attribute_getter="is_on",
                    attribute_setter="set_state",
                    type=Feature.Type.Switch,
                    category=Feature.Category.Primary,
                )
            )

        if "signal_level" in self._info:
            self._add_feature(
                Feature(
                    self,
                    id="signal_level",
                    name="Signal Level",
                    attribute_getter=lambda x: x._info["signal_level"],
                    icon="mdi:signal",
                    category=Feature.Category.Info,
                )
            )

        if "rssi" in self._info:
            self._add_feature(
                Feature(
                    self,
                    id="rssi",
                    name="RSSI",
                    attribute_getter=lambda x: x._info["rssi"],
                    icon="mdi:signal",
                    category=Feature.Category.Debug,
                )
            )

        if "ssid" in self._info:
            self._add_feature(
                Feature(
                    device=self,
                    id="ssid",
                    name="SSID",
                    attribute_getter="ssid",
                    icon="mdi:wifi",
                    category=Feature.Category.Debug,
                )
            )

        if "overheated" in self._info:
            self._add_feature(
                Feature(
                    self,
                    id="overheated",
                    name="Overheated",
                    attribute_getter=lambda x: x._info["overheated"],
                    icon="mdi:heat-wave",
                    type=Feature.Type.BinarySensor,
                    category=Feature.Category.Info,
                )
            )

        # We check for the key available, and not for the property truthiness,
        # as the value is falsy when the device is off.
        if "on_time" in self._info:
            self._add_feature(
                Feature(
                    device=self,
                    id="on_since",
                    name="On since",
                    attribute_getter="on_since",
                    icon="mdi:clock",
                    category=Feature.Category.Info,
                )
            )

        for module in self._modules.values():
            module._initialize_features()
            for feat in module._module_features.values():
                self._add_feature(feat)

    @overload
    def get_module(self, module_type: type[ModuleT]) -> ModuleT | None: ...

    @overload
    def get_module(self, module_type: str) -> SmartModule | None: ...

    def get_module(
        self, module_type: type[ModuleT] | str
    ) -> ModuleT | SmartModule | None:
        """Return the module from the device modules or None if not present."""
        if isinstance(module_type, str):
            module_name = module_type
        elif issubclass(module_type, SmartModule):
            module_name = module_type.__name__
        else:
            return None
        if module_name in self.modules:
            return self.modules[module_name]
        elif self._exposes_child_modules:
            for child in self._children.values():
                if module_name in child.modules:
                    return child.modules[module_name]
        return None

    @property
    def is_cloud_connected(self):
        """Returns if the device is connected to the cloud."""
        if "CloudModule" not in self.modules:
            return False
        return self.modules["CloudModule"].is_connected

    @property
    def sys_info(self) -> dict[str, Any]:
        """Returns the device info."""
        return self._info  # type: ignore

    @property
    def model(self) -> str:
        """Returns the device model."""
        return str(self._info.get("model"))

    @property
    def alias(self) -> str | None:
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
    def timezone(self) -> dict:
        """Return the timezone and time_difference."""
        ti = self.time
        return {"timezone": ti.tzname()}

    @property
    def hw_info(self) -> dict:
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
    def location(self) -> dict:
        """Return the device location."""
        loc = {
            "latitude": cast(float, self._info.get("latitude", 0)) / 10_000,
            "longitude": cast(float, self._info.get("longitude", 0)) / 10_000,
        }
        return loc

    @property
    def rssi(self) -> int | None:
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
        """Update the internal info state.

        This is used by the parent to push updates to its children.
        """
        self._info = info

    async def _query_helper(
        self, method: str, params: dict | None = None, child_ids=None
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
    def has_emeter(self) -> bool:
        """Return if the device has emeter."""
        return "EnergyModule" in self.modules

    @property
    def is_dimmer(self) -> bool:
        """Whether the device acts as a dimmer."""
        return self.is_dimmable

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
        energy = cast(EnergyModule, self.modules["EnergyModule"])
        return energy.emeter_realtime

    @property
    def emeter_this_month(self) -> float | None:
        """Get the emeter value for this month."""
        energy = cast(EnergyModule, self.modules["EnergyModule"])
        return energy.emeter_this_month

    @property
    def emeter_today(self) -> float | None:
        """Get the emeter value for today."""
        energy = cast(EnergyModule, self.modules["EnergyModule"])
        return energy.emeter_today

    @property
    def on_since(self) -> datetime | None:
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

    async def wifi_scan(self) -> list[WifiNetwork]:
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

        _LOGGER.debug("Querying networks")

        resp = await self.protocol.query({"get_wireless_scan_info": {"start_index": 0}})
        networks = [
            _net_for_scan_info(net) for net in resp["get_wireless_scan_info"]["ap_list"]
        ]
        return networks

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

        self._device_type = self._get_device_type_from_components(
            list(self._components.keys()), self._info["type"]
        )

        return self._device_type

    @property
    def firmware(self) -> FirmwareInterface:
        """Return firmware module."""
        # TODO: open question: does it make sense to expose common modules?
        fw = cast(FirmwareInterface, self.modules["Firmware"])
        return fw

    @staticmethod
    def _get_device_type_from_components(
        components: list[str], device_type: str
    ) -> DeviceType:
        """Find type to be displayed as a supported device category."""
        if "HUB" in device_type:
            return DeviceType.Hub
        if "PLUG" in device_type:
            if "child_device" in components:
                return DeviceType.Strip
            return DeviceType.Plug
        if "light_strip" in components:
            return DeviceType.LightStrip
        if "SWITCH" in device_type and "child_device" in components:
            return DeviceType.WallSwitch
        if "dimmer_calibration" in components:
            return DeviceType.Dimmer
        if "brightness" in components:
            return DeviceType.Bulb
        if "SWITCH" in device_type:
            return DeviceType.WallSwitch
        if "SENSOR" in device_type:
            return DeviceType.Sensor
        if "ENERGY" in device_type:
            return DeviceType.Thermostat
        _LOGGER.warning("Unknown device type, falling back to plug")
        return DeviceType.Plug

    # Fan interface methods

    @property
    def is_fan(self) -> bool:
        """Return True if the device is a fan."""
        return "FanModule" in self.modules

    @property
    def fan_speed_level(self) -> int:
        """Return fan speed level."""
        if not self.is_fan:
            raise KasaException("Device is not a Fan")
        return cast(FanModule, self.modules["FanModule"]).fan_speed_level

    async def set_fan_speed_level(self, level: int):
        """Set fan speed level."""
        if not self.is_fan:
            raise KasaException("Device is not a Fan")
        await cast(FanModule, self.modules["FanModule"]).set_fan_speed_level(level)

    # Bulb interface methods

    @property
    def is_color(self) -> bool:
        """Whether the bulb supports color changes."""
        return "ColorModule" in self.modules

    @property
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""
        return "Brightness" in self.modules

    @property
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""
        return "ColorTemperatureModule" in self.modules

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        if not self.is_variable_color_temp:
            raise KasaException("Color temperature not supported")

        return cast(
            ColorTemperatureModule, self.modules["ColorTemperatureModule"]
        ).valid_temperature_range

    @property
    def hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if not self.is_color:
            raise KasaException("Bulb does not support color.")

        return cast(ColorModule, self.modules["ColorModule"]).hsv

    @property
    def color_temp(self) -> int:
        """Whether the bulb supports color temperature changes."""
        if not self.is_variable_color_temp:
            raise KasaException("Bulb does not support colortemp.")

        return cast(
            ColorTemperatureModule, self.modules["ColorTemperatureModule"]
        ).color_temp

    @property
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        if not self.is_dimmable:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        return cast(Brightness, self.modules["Brightness"]).brightness

    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> dict:
        """Set new HSV.

        Note, transition is not supported and will be ignored.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value between 1 and 100
        :param int transition: transition in milliseconds.
        """
        if not self.is_color:
            raise KasaException("Bulb does not support color.")

        return await cast(ColorModule, self.modules["ColorModule"]).set_hsv(
            hue, saturation, value
        )

    async def set_color_temp(
        self, temp: int, *, brightness=None, transition: int | None = None
    ) -> dict:
        """Set the color temperature of the device in kelvin.

        Note, transition is not supported and will be ignored.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """
        if not self.is_variable_color_temp:
            raise KasaException("Bulb does not support colortemp.")
        return await cast(
            ColorTemperatureModule, self.modules["ColorTemperatureModule"]
        ).set_color_temp(temp)

    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if not self.is_dimmable:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        return await cast(Brightness, self.modules["Brightness"]).set_brightness(
            brightness
        )

    @property
    def presets(self) -> list[BulbPreset]:
        """Return a list of available bulb setting presets."""
        return []

    @property
    def has_effects(self) -> bool:
        """Return True if the device supports effects."""
        return "LightEffectModule" in self.modules
