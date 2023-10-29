"""Module for dimmers (currently only HS220)."""
from enum import Enum
from typing import Any, Dict, Optional

from kasa.credentials import Credentials
from kasa.modules import AmbientLight, Motion
from kasa.smartdevice import DeviceType, SmartDeviceException, requires_update
from kasa.smartplug import SmartPlug


class ButtonAction(Enum):
    """Button action."""

    NoAction = "none"
    Instant = "instant_on_off"
    Gentle = "gentle_on_off"
    Preset = "customize_preset"


class ActionType(Enum):
    """Button action."""

    DoubleClick = "double_click_action"
    LongPress = "long_press_action"


class FadeType(Enum):
    """Fade on/off setting."""

    FadeOn = "fade_on"
    FadeOff = "fade_off"


class SmartDimmer(SmartPlug):
    r"""Representation of a TP-Link Smart Dimmer.

    Dimmers work similarly to plugs, but provide also support for
    adjusting the brightness. This class extends :class:`SmartPlug` interface.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values,
    but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`SmartDeviceException`\s,
    and should be handled by the user of the library.

    Examples:
    >>> import asyncio
    >>> dimmer = SmartDimmer("192.168.1.105")
    >>> asyncio.run(dimmer.turn_on())
    >>> dimmer.brightness
    25

    >>> asyncio.run(dimmer.set_brightness(50))
    >>> asyncio.run(dimmer.update())
    >>> dimmer.brightness
    50

    Refer to :class:`SmartPlug` for the full API.
    """

    DIMMER_SERVICE = "smartlife.iot.dimmer"

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host, port=port, credentials=credentials, timeout=timeout)
        self._device_type = DeviceType.Dimmer
        # TODO: need to be verified if it's okay to call these on HS220 w/o these
        # TODO: need to be figured out what's the best approach to detect support
        self.add_module("motion", Motion(self, "smartlife.iot.PIR"))
        self.add_module("ambient", AmbientLight(self, "smartlife.iot.LAS"))

    @property  # type: ignore
    @requires_update
    def brightness(self) -> int:
        """Return current brightness on dimmers.

        Will return a range between 0 - 100.
        """
        if not self.is_dimmable:
            raise SmartDeviceException("Device is not dimmable.")

        sys_info = self.sys_info
        return int(sys_info["brightness"])

    @requires_update
    async def set_brightness(
        self, brightness: int, *, transition: Optional[int] = None
    ):
        """Set the new dimmer brightness level in percentage.

        :param int transition: transition duration in milliseconds.
            Using a transition will cause the dimmer to turn on.
        """
        if not self.is_dimmable:
            raise SmartDeviceException("Device is not dimmable.")

        if not isinstance(brightness, int):
            raise ValueError(
                "Brightness must be integer, " "not of %s.", type(brightness)
            )

        if not 0 <= brightness <= 100:
            raise ValueError("Brightness value %s is not valid." % brightness)

        # Dimmers do not support a brightness of 0, but bulbs do.
        # Coerce 0 to 1 to maintain the same interface between dimmers and bulbs.
        if brightness == 0:
            brightness = 1

        if transition is not None:
            return await self.set_dimmer_transition(brightness, transition)

        return await self._query_helper(
            self.DIMMER_SERVICE, "set_brightness", {"brightness": brightness}
        )

    async def turn_off(self, *, transition: Optional[int] = None, **kwargs):
        """Turn the bulb off.

        :param int transition: transition duration in milliseconds.
        """
        if transition is not None:
            return await self.set_dimmer_transition(brightness=0, transition=transition)

        return await super().turn_off()

    @requires_update
    async def turn_on(self, *, transition: Optional[int] = None, **kwargs):
        """Turn the bulb on.

        :param int transition: transition duration in milliseconds.
        """
        if transition is not None:
            return await self.set_dimmer_transition(
                brightness=self.brightness, transition=transition
            )

        return await super().turn_on()

    async def set_dimmer_transition(self, brightness: int, transition: int):
        """Turn the bulb on to brightness percentage over transition milliseconds.

        A brightness value of 0 will turn off the dimmer.
        """
        if not isinstance(brightness, int):
            raise ValueError(
                "Brightness must be integer, " "not of %s.", type(brightness)
            )

        if not 0 <= brightness <= 100:
            raise ValueError("Brightness value %s is not valid." % brightness)

        if not isinstance(transition, int):
            raise ValueError(
                "Transition must be integer, " "not of %s.", type(transition)
            )
        if transition <= 0:
            raise ValueError("Transition value %s is not valid." % transition)

        return await self._query_helper(
            self.DIMMER_SERVICE,
            "set_dimmer_transition",
            {"brightness": brightness, "duration": transition},
        )

    @requires_update
    async def get_behaviors(self):
        """Return button behavior settings."""
        behaviors = await self._query_helper(
            self.DIMMER_SERVICE, "get_default_behavior", {}
        )
        return behaviors

    @requires_update
    async def set_button_action(
        self, action_type: ActionType, action: ButtonAction, index: Optional[int] = None
    ):
        """Set action to perform on button click/hold.

        :param action_type ActionType: whether to control double click or hold action.
        :param action ButtonAction: what should the button do
         (nothing, instant, gentle, change preset)
        :param index int: in case of preset change, the preset to select
        """
        action_type_setter = f"set_{action_type}"

        payload: Dict[str, Any] = {"mode": str(action)}
        if index is not None:
            payload["index"] = index

        await self._query_helper(self.DIMMER_SERVICE, action_type_setter, payload)

    @requires_update
    async def set_fade_time(self, fade_type: FadeType, time: int):
        """Set time for fade in / fade out."""
        fade_type_setter = f"set_{fade_type}_time"
        payload = {"fadeTime": time}

        await self._query_helper(self.DIMMER_SERVICE, fade_type_setter, payload)

    @property  # type: ignore
    @requires_update
    def is_dimmable(self) -> bool:
        """Whether the switch supports brightness changes."""
        sys_info = self.sys_info
        return "brightness" in sys_info

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return switch-specific state information."""
        info = super().state_information
        info["Brightness"] = self.brightness

        return info
