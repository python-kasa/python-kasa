import datetime
import logging
from typing import Any, Dict

from pyHS100.protocol import TPLinkSmartHomeProtocol
from pyHS100.smartdevice import DeviceType, SmartDevice, SmartDeviceException

_LOGGER = logging.getLogger(__name__)


class SmartPlug(SmartDevice):
    """Representation of a TP-Link Smart Switch.

    Usage example when used as library:
    p = SmartPlug("192.168.1.105")
    # print the devices alias
    print(p.alias)
    # change state of plug
    p.turn_on()
    p.turn_off()
    # query and print current state of plug
    print(p.state)

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.
    """

    def __init__(
        self,
        host: str,
        protocol: "TPLinkSmartHomeProtocol" = None,
        context: str = None,
        cache_ttl: int = 3,
        *,
        ioloop=None,
    ) -> None:
        SmartDevice.__init__(self, host, protocol, context, cache_ttl, ioloop=ioloop)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Plug

    async def get_brightness(self) -> int:
        """Return current brightness on dimmers.

        Will return a range between 0 - 100.

        :returns: integer
        :rtype: int
        """
        if not await self.is_dimmable():
            raise SmartDeviceException("Device is not dimmable.")

        sys_info = await self.get_sys_info()
        return int(sys_info["brightness"])

    async def set_brightness(self, value: int):
        """Set the new dimmer brightness level.

        Note:
        When setting brightness, if the light is not
        already on, it will be turned on automatically.

        :param value: integer between 1 and 100

        """
        if not await self.is_dimmable():
            raise SmartDeviceException("Device is not dimmable.")

        if not isinstance(value, int):
            raise ValueError("Brightness must be integer, " "not of %s.", type(value))
        elif 0 < value <= 100:
            self.turn_on()
            await self._query_helper(
                "smartlife.iot.dimmer", "set_brightness", {"brightness": value}
            )
        else:
            raise ValueError("Brightness value %s is not valid." % value)

    async def is_dimmable(self):
        """Whether the switch supports brightness changes.

        :return: True if switch supports brightness changes, False otherwise
        :rtype: bool
        """
        sys_info = await self.get_sys_info()
        return "brightness" in sys_info

    async def get_has_emeter(self):
        """Return whether device has an energy meter.

        :return: True if energy meter is available
                 False otherwise
        """
        sys_info = await self.get_sys_info()
        features = sys_info["feature"].split(":")
        return "ENE" in features

    async def is_on(self) -> bool:
        """Return whether device is on.

        :return: True if device is on, False otherwise
        """
        sys_info = await self.get_sys_info()
        return bool(sys_info["relay_state"])

    async def turn_on(self):
        """Turn the switch on.

        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_relay_state", {"state": 1})

    async def turn_off(self):
        """Turn the switch off.

        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_relay_state", {"state": 0})

    async def get_led(self) -> bool:
        """Return the state of the led.

        :return: True if led is on, False otherwise
        :rtype: bool
        """
        sys_info = await self.get_sys_info()
        return bool(1 - sys_info["led_off"])

    async def set_led(self, state: bool):
        """Set the state of the led (night mode).

        :param bool state: True to set led on, False to set led off
        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_led_off", {"off": int(not state)})

    async def get_on_since(self) -> datetime.datetime:
        """Return pretty-printed on-time.

        :return: datetime for on since
        :rtype: datetime
        """
        sys_info = await self.get_sys_info()
        if self.context:
            for plug in sys_info["children"]:
                if plug["id"] == self.context:
                    on_time = plug["on_time"]
                    break
        else:
            on_time = sys_info["on_time"]

        return datetime.datetime.now() - datetime.timedelta(seconds=on_time)

    async def get_state_information(self) -> Dict[str, Any]:
        """Return switch-specific state information.

        :return: Switch information dict, keys in user-presentable form.
        :rtype: dict
        """
        info = {
            "LED state": await self.get_led(),
            "On since": await self.get_on_since(),
        }
        if await self.is_dimmable():
            info["Brightness"] = await self.get_brightness()
        return info
