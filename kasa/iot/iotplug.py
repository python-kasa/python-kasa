"""Module for smart plugs (HS100, HS110, ..)."""

from __future__ import annotations

import logging

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..feature import Feature
from ..protocol import BaseProtocol
from .iotdevice import IotDevice, requires_update
from .modules import Antitheft, Cloud, Schedule, Time, Usage

_LOGGER = logging.getLogger(__name__)


class IotPlug(IotDevice):
    r"""Representation of a TP-Link Smart Plug.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values,
    but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`KasaException`\s,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> plug = IotPlug("127.0.0.1")
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

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        super().__init__(host=host, config=config, protocol=protocol)
        self._device_type = DeviceType.Plug
        self.add_module("schedule", Schedule(self, "schedule"))
        self.add_module("usage", Usage(self, "schedule"))
        self.add_module("antitheft", Antitheft(self, "anti_theft"))
        self.add_module("time", Time(self, "time"))
        self.add_module("cloud", Cloud(self, "cnCloud"))

    async def _initialize_features(self):
        await super()._initialize_features()

        self._add_feature(
            Feature(
                device=self,
                name="LED",
                icon="mdi:led-{state}",
                attribute_getter="led",
                attribute_setter="set_led",
                type=Feature.Type.Switch,
            )
        )

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


class IotWallSwitch(IotPlug):
    """Representation of a TP-Link Smart Wall Switch."""

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        super().__init__(host=host, config=config, protocol=protocol)
        self._device_type = DeviceType.WallSwitch
