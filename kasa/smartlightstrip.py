"""Module for light strips (KL430)."""
from typing import Any, Dict, List, Optional

from .credentials import Credentials
from .effects import EFFECT_MAPPING_V1, EFFECT_NAMES_V1
from .smartbulb import SmartBulb
from .smartdevice import DeviceType, SmartDeviceException, requires_update


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

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host, port=port, credentials=credentials, timeout=timeout)
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
    def effect_list(self) -> Optional[List[str]]:
        """Return built-in effects list.

        Example:
            ['Aurora', 'Bubbling Cauldron', ...]
        """
        return EFFECT_NAMES_V1 if self.has_effects else None

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return strip specific state information."""
        info = super().state_information

        info["Length"] = self.length
        if self.has_effects:
            info["Effect"] = self.effect["name"]

        return info

    @requires_update
    async def set_effect(
        self,
        effect: str,
        *,
        brightness: Optional[int] = None,
        transition: Optional[int] = None,
    ) -> None:
        """Set an effect on the device.

        If brightness or transition is defined, its value will be used instead of the effect-specific default.

        See :meth:`effect_list` for available effects, or use :meth:`set_custom_effect` for custom effects.

        :param str effect: The effect to set
        :param int brightness: The wanted brightness
        :param int transition: The wanted transition time
        """
        if effect not in EFFECT_MAPPING_V1:
            raise SmartDeviceException(f"The effect {effect} is not a built in effect.")
        effect_dict = EFFECT_MAPPING_V1[effect]
        if brightness is not None:
            effect_dict["brightness"] = brightness
        if transition is not None:
            effect_dict["transition"] = transition

        await self.set_custom_effect(effect_dict)

    @requires_update
    async def set_custom_effect(
        self,
        effect_dict: Dict,
    ) -> None:
        """Set a custom effect on the device.

        :param str effect_dict: The custom effect dict to set
        """
        if not self.has_effects:
            raise SmartDeviceException("Bulb does not support effects.")
        await self._query_helper(
            "smartlife.iot.lighting_effect",
            "set_lighting_effect",
            effect_dict,
        )
