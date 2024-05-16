"""Module for smart plugs (HS100, HS110, ..)."""

from __future__ import annotations

import logging

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..module import Module
from ..protocol import BaseProtocol
from .iotdevice import IotDevice, requires_update
from .modules import Antitheft, Cloud, Led, Schedule, Time, Usage

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

    For more examples, see the :class:`Device` class.
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

    async def _initialize_modules(self):
        """Initialize modules."""
        await super()._initialize_modules()
        self.add_module(Module.IotSchedule, Schedule(self, "schedule"))
        self.add_module(Module.IotUsage, Usage(self, "schedule"))
        self.add_module(Module.IotAntitheft, Antitheft(self, "anti_theft"))
        self.add_module(Module.IotTime, Time(self, "time"))
        self.add_module(Module.IotCloud, Cloud(self, "cnCloud"))
        self.add_module(Module.Led, Led(self, "system"))

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
