"""Module for bulbs (LB*, KL*, KB*)."""
import logging
import re
from enum import Enum
from typing import Any, Dict, List, NamedTuple, Optional, cast

try:
    from pydantic.v1 import BaseModel, Field, root_validator
except ImportError:
    from pydantic import BaseModel, Field, root_validator

from .credentials import Credentials
from .modules import Antitheft, Cloud, Countdown, Emeter, Schedule, Time, Usage
from .smartdevice import DeviceType, SmartDevice, SmartDeviceException, requires_update


class ColorTempRange(NamedTuple):
    """Color temperature range."""

    min: int
    max: int


class HSV(NamedTuple):
    """Hue-saturation-value."""

    hue: int
    saturation: int
    value: int


class SmartBulbPreset(BaseModel):
    """Bulb configuration preset."""

    index: int
    brightness: int

    # These are not available for effect mode presets on light strips
    hue: Optional[int]
    saturation: Optional[int]
    color_temp: Optional[int]

    # Variables for effect mode presets
    custom: Optional[int]
    id: Optional[str]
    mode: Optional[int]


class BehaviorMode(str, Enum):
    """Enum to present type of turn on behavior."""

    #: Return to the last state known state.
    Last = "last_status"
    #: Use chosen preset.
    Preset = "customize_preset"


class TurnOnBehavior(BaseModel):
    """Model to present a single turn on behavior.

    :param int preset: the index number of wanted preset.
    :param BehaviorMode mode: last status or preset mode. If you are changing existing settings, you should not set this manually.

    To change the behavior, it is only necessary to change the :attr:`preset` field
    to contain either the preset index, or ``None`` for the last known state.
    """

    #: Index of preset to use, or ``None`` for the last known state.
    preset: Optional[int] = Field(alias="index", default=None)
    #: Wanted behavior
    mode: BehaviorMode

    @root_validator
    def _mode_based_on_preset(cls, values):
        """Set the mode based on the preset value."""
        if values["preset"] is not None:
            values["mode"] = BehaviorMode.Preset
        else:
            values["mode"] = BehaviorMode.Last

        return values

    class Config:
        """Configuration to make the validator run when changing the values."""

        validate_assignment = True


class TurnOnBehaviors(BaseModel):
    """Model to contain turn on behaviors."""

    #: The behavior when the bulb is turned on programmatically.
    soft: TurnOnBehavior = Field(alias="soft_on")
    #: The behavior when the bulb has been off from mains power.
    hard: TurnOnBehavior = Field(alias="hard_on")


TPLINK_KELVIN = {
    "LB130": ColorTempRange(2500, 9000),
    "LB120": ColorTempRange(2700, 6500),
    "LB230": ColorTempRange(2500, 9000),
    "KB130": ColorTempRange(2500, 9000),
    "KL130": ColorTempRange(2500, 9000),
    "KL125": ColorTempRange(2500, 6500),
    "KL135": ColorTempRange(2500, 6500),
    r"KL120\(EU\)": ColorTempRange(2700, 6500),
    r"KL120\(US\)": ColorTempRange(2700, 5000),
    r"KL430": ColorTempRange(2500, 9000),
}


NON_COLOR_MODE_FLAGS = {"transition_period", "on_off"}

_LOGGER = logging.getLogger(__name__)


class SmartBulb(SmartDevice):
    r"""Representation of a TP-Link Smart Bulb.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`SmartDeviceExceptions <kasa.exceptions.SmartDeviceException>`,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> bulb = SmartBulb("127.0.0.1")
        >>> asyncio.run(bulb.update())
        >>> print(bulb.alias)
        Bulb2

        Bulbs, like any other supported devices, can be turned on and off:

        >>> asyncio.run(bulb.turn_off())
        >>> asyncio.run(bulb.turn_on())
        >>> asyncio.run(bulb.update())
        >>> print(bulb.is_on)
        True

        You can use the ``is_``-prefixed properties to check for supported features:

        >>> bulb.is_dimmable
        True
        >>> bulb.is_color
        True
        >>> bulb.is_variable_color_temp
        True

        All known bulbs support changing the brightness:

        >>> bulb.brightness
        30
        >>> asyncio.run(bulb.set_brightness(50))
        >>> asyncio.run(bulb.update())
        >>> bulb.brightness
        50

        Bulbs supporting color temperature can be queried to know which range is accepted:

        >>> bulb.valid_temperature_range
        ColorTempRange(min=2500, max=9000)
        >>> asyncio.run(bulb.set_color_temp(3000))
        >>> asyncio.run(bulb.update())
        >>> bulb.color_temp
        3000

        Color bulbs can be adjusted by passing hue, saturation and value:

        >>> asyncio.run(bulb.set_hsv(180, 100, 80))
        >>> asyncio.run(bulb.update())
        >>> bulb.hsv
        HSV(hue=180, saturation=100, value=80)

        If you don't want to use the default transitions, you can pass `transition` in milliseconds.
        This applies to all transitions (:func:`turn_on`, :func:`turn_off`, :func:`set_hsv`, :func:`set_color_temp`, :func:`set_brightness`) if supported by the device.
        Light strips (e.g., KL420L5) do not support this feature, but silently ignore the parameter.
        The following changes the brightness over a period of 10 seconds:

        >>> asyncio.run(bulb.set_brightness(100, transition=10_000))

        Bulb configuration presets can be accessed using the :func:`presets` property:

        >>> bulb.presets
        [SmartBulbPreset(index=0, brightness=50, hue=0, saturation=0, color_temp=2700, custom=None, id=None, mode=None), SmartBulbPreset(index=1, brightness=100, hue=0, saturation=75, color_temp=0, custom=None, id=None, mode=None), SmartBulbPreset(index=2, brightness=100, hue=120, saturation=75, color_temp=0, custom=None, id=None, mode=None), SmartBulbPreset(index=3, brightness=100, hue=240, saturation=75, color_temp=0, custom=None, id=None, mode=None)]

        To modify an existing preset, pass :class:`~kasa.smartbulb.SmartBulbPreset` instance to :func:`save_preset` method:

        >>> preset = bulb.presets[0]
        >>> preset.brightness
        50
        >>> preset.brightness = 100
        >>> asyncio.run(bulb.save_preset(preset))
        >>> bulb.presets[0].brightness
        100

    """

    LIGHT_SERVICE = "smartlife.iot.smartbulb.lightingservice"
    SET_LIGHT_METHOD = "transition_light_state"
    emeter_type = "smartlife.iot.common.emeter"

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host=host, port=port, credentials=credentials, timeout=timeout)
        self._device_type = DeviceType.Bulb
        self.add_module("schedule", Schedule(self, "smartlife.iot.common.schedule"))
        self.add_module("usage", Usage(self, "smartlife.iot.common.schedule"))
        self.add_module("antitheft", Antitheft(self, "smartlife.iot.common.anti_theft"))
        self.add_module("time", Time(self, "smartlife.iot.common.timesetting"))
        self.add_module("emeter", Emeter(self, self.emeter_type))
        self.add_module("countdown", Countdown(self, "countdown"))
        self.add_module("cloud", Cloud(self, "smartlife.iot.common.cloud"))

    @property  # type: ignore
    @requires_update
    def is_color(self) -> bool:
        """Whether the bulb supports color changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_color"])

    @property  # type: ignore
    @requires_update
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_dimmable"])

    @property  # type: ignore
    @requires_update
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_variable_color_temp"])

    @property  # type: ignore
    @requires_update
    def valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Color temperature not supported")

        for model, temp_range in TPLINK_KELVIN.items():
            sys_info = self.sys_info
            if re.match(model, sys_info["model"]):
                return temp_range

        _LOGGER.warning("Unknown color temperature range, fallback to 2700-5000")
        return ColorTempRange(2700, 5000)

    @property  # type: ignore
    @requires_update
    def light_state(self) -> Dict[str, str]:
        """Query the light state."""
        light_state = self.sys_info["light_state"]
        if light_state is None:
            raise SmartDeviceException(
                "The device has no light_state or you have not called update()"
            )

        # if the bulb is off, its state is stored under a different key
        # as is_on property depends on on_off itself, we check it here manually
        is_on = light_state["on_off"]
        if not is_on:
            off_state = {**light_state["dft_on_state"], "on_off": is_on}
            return cast(dict, off_state)

        return light_state

    @property  # type: ignore
    @requires_update
    def has_effects(self) -> bool:
        """Return True if the device supports effects."""
        return "lighting_effect_state" in self.sys_info

    async def get_light_details(self) -> Dict[str, int]:
        """Return light details.

        Example::

            {'lamp_beam_angle': 290, 'min_voltage': 220, 'max_voltage': 240,
             'wattage': 5, 'incandescent_equivalent': 40, 'max_lumens': 450,
              'color_rendering_index': 80}
        """
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_details")

    async def get_turn_on_behavior(self) -> TurnOnBehaviors:
        """Return the behavior for turning the bulb on."""
        return TurnOnBehaviors.parse_obj(
            await self._query_helper(self.LIGHT_SERVICE, "get_default_behavior")
        )

    async def set_turn_on_behavior(self, behavior: TurnOnBehaviors):
        """Set the behavior for turning the bulb on.

        If you do not want to manually construct the behavior object,
        you should use :func:`get_turn_on_behavior` to get the current settings.
        """
        return await self._query_helper(
            self.LIGHT_SERVICE, "set_default_behavior", behavior.dict(by_alias=True)
        )

    async def get_light_state(self) -> Dict[str, Dict]:
        """Query the light state."""
        # TODO: add warning and refer to use light.state?
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_state")

    async def set_light_state(
        self, state: Dict, *, transition: Optional[int] = None
    ) -> Dict:
        """Set the light state."""
        if transition is not None:
            state["transition_period"] = transition

        # if no on/off is defined, turn on the light
        if "on_off" not in state:
            state["on_off"] = 1

        # If we are turning on without any color mode flags,
        # we do not want to set ignore_default to ensure
        # we restore the previous state.
        if state["on_off"] and NON_COLOR_MODE_FLAGS.issuperset(state):
            state["ignore_default"] = 0
        else:
            # This is necessary to allow turning on into a specific state
            state["ignore_default"] = 1

        light_state = await self._query_helper(
            self.LIGHT_SERVICE, self.SET_LIGHT_METHOD, state
        )
        return light_state

    @property  # type: ignore
    @requires_update
    def hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if not self.is_color:
            raise SmartDeviceException("Bulb does not support color.")

        light_state = cast(dict, self.light_state)

        hue = light_state["hue"]
        saturation = light_state["saturation"]
        value = light_state["brightness"]

        return HSV(hue, saturation, value)

    def _raise_for_invalid_brightness(self, value):
        if not isinstance(value, int) or not (0 <= value <= 100):
            raise ValueError(
                "Invalid brightness value: {} " "(valid range: 0-100%)".format(value)
            )

    @requires_update
    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: Optional[int] = None,
        *,
        transition: Optional[int] = None,
    ) -> Dict:
        """Set new HSV.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
        """
        if not self.is_color:
            raise SmartDeviceException("Bulb does not support color.")

        if not isinstance(hue, int) or not (0 <= hue <= 360):
            raise ValueError(
                "Invalid hue value: {} " "(valid range: 0-360)".format(hue)
            )

        if not isinstance(saturation, int) or not (0 <= saturation <= 100):
            raise ValueError(
                "Invalid saturation value: {} "
                "(valid range: 0-100%)".format(saturation)
            )

        light_state = {
            "hue": hue,
            "saturation": saturation,
            "color_temp": 0,
        }

        if value is not None:
            self._raise_for_invalid_brightness(value)
            light_state["brightness"] = value

        return await self.set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def color_temp(self) -> int:
        """Return color temperature of the device in kelvin."""
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        light_state = self.light_state
        return int(light_state["color_temp"])

    @requires_update
    async def set_color_temp(
        self, temp: int, *, brightness=None, transition: Optional[int] = None
    ) -> Dict:
        """Set the color temperature of the device in kelvin.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        valid_temperature_range = self.valid_temperature_range
        if temp < valid_temperature_range[0] or temp > valid_temperature_range[1]:
            raise ValueError(
                "Temperature should be between {} "
                "and {}, was {}".format(*valid_temperature_range, temp)
            )

        light_state = {"color_temp": temp}
        if brightness is not None:
            light_state["brightness"] = brightness

        return await self.set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        light_state = self.light_state
        return int(light_state["brightness"])

    @requires_update
    async def set_brightness(
        self, brightness: int, *, transition: Optional[int] = None
    ) -> Dict:
        """Set the brightness in percentage.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        self._raise_for_invalid_brightness(brightness)

        light_state = {"brightness": brightness}
        return await self.set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return bulb-specific state information."""
        info: Dict[str, Any] = {
            "Brightness": self.brightness,
            "Is dimmable": self.is_dimmable,
        }
        if self.is_variable_color_temp:
            info["Color temperature"] = self.color_temp
            info["Valid temperature range"] = self.valid_temperature_range
        if self.is_color:
            info["HSV"] = self.hsv
        info["Presets"] = self.presets

        return info

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return whether the device is on."""
        light_state = self.light_state
        return bool(light_state["on_off"])

    async def turn_off(self, *, transition: Optional[int] = None, **kwargs) -> Dict:
        """Turn the bulb off.

        :param int transition: transition in milliseconds.
        """
        return await self.set_light_state({"on_off": 0}, transition=transition)

    async def turn_on(self, *, transition: Optional[int] = None, **kwargs) -> Dict:
        """Turn the bulb on.

        :param int transition: transition in milliseconds.
        """
        return await self.set_light_state({"on_off": 1}, transition=transition)

    @property  # type: ignore
    @requires_update
    def has_emeter(self) -> bool:
        """Return that the bulb has an emeter."""
        return True

    async def set_alias(self, alias: str) -> None:
        """Set the device name (alias).

        Overridden to use a different module name.
        """
        return await self._query_helper(
            "smartlife.iot.common.system", "set_dev_alias", {"alias": alias}
        )

    @property  # type: ignore
    @requires_update
    def presets(self) -> List[SmartBulbPreset]:
        """Return a list of available bulb setting presets."""
        return [SmartBulbPreset(**vals) for vals in self.sys_info["preferred_state"]]

    async def save_preset(self, preset: SmartBulbPreset):
        """Save a setting preset.

        You can either construct a preset object manually, or pass an existing one
        obtained using :func:`presets`.
        """
        if len(self.presets) == 0:
            raise SmartDeviceException("Device does not supported saving presets")

        if preset.index >= len(self.presets):
            raise SmartDeviceException("Invalid preset index")

        return await self._query_helper(
            self.LIGHT_SERVICE, "set_preferred_state", preset.dict(exclude_none=True)
        )

    @property
    def max_device_response_size(self) -> int:
        """Returns the maximum response size the device can safely construct."""
        return 4096
