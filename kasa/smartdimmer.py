"""Module for dimmers (currently only HS220)."""
from typing import Any, Dict

from kasa.smartdevice import DeviceType, SmartDeviceException, requires_update
from kasa.smartplug import SmartPlug


class SmartDimmer(SmartPlug):
    """Representation of a TP-Link Smart Dimmer.

    Dimmers work similarly to plugs, but provide also support for
    adjusting the brightness. This class extends :class:`SmartPlug` interface.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`SmartDeviceException`s,
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

    def __init__(self, host: str) -> None:
        super().__init__(host)
        self._device_type = DeviceType.Dimmer

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
    async def set_brightness(self, brightness: int, *, transition: int = None):
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

    async def turn_off(self, *, transition: int = None, **kwargs):
        """Turn the bulb off.

        :param int transition: transition duration in milliseconds.
        """
        if transition is not None:
            return await self.set_dimmer_transition(brightness=0, transition=transition)

        return await super().turn_off()

    @requires_update
    async def turn_on(self, *, transition: int = None, **kwargs):
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
