"""Module for light strips (KL430)."""
from typing import Any, Dict

from .smartbulb import SmartBulb
from .smartdevice import DeviceType, requires_update


class SmartLightStrip(SmartBulb):
    """Representation of a TP-Link Smart light strip.

    Light strips work similarly to bulbs, but use a different service for controlling,
     and expose some extra information (such as length and active effect).
     This class extends :class:`SmartBulb` interface.

     Examples:
        >>> import asyncio
        >>> strip = SmartLightStrip("127.0.0.1")
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

    def __init__(self, host: str) -> None:
        super().__init__(host)
        self._device_type = DeviceType.LightStrip

    @property  # type: ignore
    @requires_update
    def length(self) -> int:
        """Return length of the strip."""
        return self.sys_info["length"]

    @property  # type: ignore
    @requires_update
    def effect(self) -> Dict:
        """Return effect state.

        Example:
            {'brightness': 50,
             'custom': 0,
             'enable': 0,
             'id': '',
             'name': ''}
        """
        return self.sys_info["lighting_effect_state"]

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return strip specific state information."""
        info = super().state_information

        info["Length"] = self.length

        return info
