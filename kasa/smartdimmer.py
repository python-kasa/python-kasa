"""Module for dimmers (currently only HS220)."""
from typing import Any, Dict

from kasa.smartdevice import DeviceType, SmartDeviceException, requires_update
from kasa.smartplug import SmartPlug


class SmartDimmer(SmartPlug):
    """Representation of a TP-Link Smart Dimmer.

    Dimmers work similarly to plugs, but provide also support for
    adjusting the brightness. This class extends SmartPlug interface.

    Example:
    ```
    dimmer = SmartDimmer("192.168.1.105")
    await dimmer.turn_on()
    print("Current brightness: %s" % dimmer.brightness)

    await dimmer.set_brightness(100)
    ```

    Refer to SmartPlug for the full API.
    """

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
    async def set_brightness(self, value: int):
        """Set the new dimmer brightness level in percentage."""
        if not self.is_dimmable:
            raise SmartDeviceException("Device is not dimmable.")

        if not isinstance(value, int):
            raise ValueError("Brightness must be integer, " "not of %s.", type(value))
        elif 0 <= value <= 100:
            return await self._query_helper(
                "smartlife.iot.dimmer", "set_brightness", {"brightness": value}
            )
        else:
            raise ValueError("Brightness value %s is not valid." % value)

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
