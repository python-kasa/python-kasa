"""Module for light strips (KL430)."""

from __future__ import annotations

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..module import Module
from ..protocol import BaseProtocol
from .iotbulb import IotBulb
from .iotdevice import requires_update
from .modules.lighteffect import LightEffect


class IotLightStrip(IotBulb):
    """Representation of a TP-Link Smart light strip.

    Light strips work similarly to bulbs, but use a different service for controlling,
    and expose some extra information (such as length and active effect).
    This class extends :class:`SmartBulb` interface.

    Examples:
        >>> import asyncio
        >>> strip = IotLightStrip("127.0.0.1")
        >>> asyncio.run(strip.update())
        >>> print(strip.alias)
        KL430 pantry lightstrip

        Getting the length of the strip:

        >>> strip.length
        16

        Currently active effect:

        >>> strip.effect
        {'brightness': 50, 'custom': 0, 'enable': 0, 'id': '', 'name': ''}

    .. note::
        The device supports some features that are not currently implemented,
        feel free to find out how to control them and create a PR!


    See :class:`SmartBulb` for more examples.
    """

    LIGHT_SERVICE = "smartlife.iot.lightStrip"
    SET_LIGHT_METHOD = "set_light_state"

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        super().__init__(host=host, config=config, protocol=protocol)
        self._device_type = DeviceType.LightStrip

    async def _initialize_modules(self):
        """Initialize modules not added in init."""
        await super()._initialize_modules()
        self.add_module(
            Module.LightEffect,
            LightEffect(self, "smartlife.iot.lighting_effect"),
        )

    @property  # type: ignore
    @requires_update
    def length(self) -> int:
        """Return length of the strip."""
        return self.sys_info["length"]
