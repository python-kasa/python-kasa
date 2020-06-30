"""Module for smart plugs (HS100, HS110, ..)."""
import logging
from typing import Any, Dict

from kasa.smartdevice import DeviceType, SmartDevice, requires_update

_LOGGER = logging.getLogger(__name__)


class SmartPlug(SmartDevice):
    """Representation of a TP-Link Smart Switch.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`SmartDeviceException`s,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> plug = SmartPlug("127.0.0.1")
        >>> asyncio.run(plug.update())
        >>> plug.alias
        Kitchen

        Setting the LED state:

        >>> asyncio.run(plug.set_led(True))
        >>> asyncio.run(plug.update())
        >>> plug.led
        True

    For more examples, see the :class:`SmartDevice` class.
    """

    def __init__(self, host: str) -> None:
        super().__init__(host)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Plug

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return whether device is on."""
        sys_info = self.sys_info
        return bool(sys_info["relay_state"])

    async def turn_on(self, **kwargs):
        """Turn the switch on."""
        return await self._query_helper("system", "set_relay_state", {"state": 1})

    async def turn_off(self, **kwargs):
        """Turn the switch off."""
        return await self._query_helper("system", "set_relay_state", {"state": 0})

    @property  # type: ignore
    @requires_update
    def led(self) -> bool:
        """Return the state of the led."""
        sys_info = self.sys_info
        return bool(1 - sys_info["led_off"])

    async def set_led(self, state: bool):
        """Set the state of the led (night mode)."""
        return await self._query_helper(
            "system", "set_led_off", {"off": int(not state)}
        )

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return switch-specific state information."""
        info = {"LED state": self.led, "On since": self.on_since}
        return info
