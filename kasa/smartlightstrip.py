"""Module for light strips (KL430)."""
from typing import Any, Dict

from .smartbulb import SmartBulb
from .smartdevice import DeviceType, requires_update


class SmartLightStrip(SmartBulb):
    """Representation of a TP-Link Smart light strip.

    Interaction works just like with the bulbs, only the service name
    for controlling the device is different.

    See :class:`SmartBulb` for more information.
    """

    LIGHT_SERVICE = "smartlife.iot.lightStrip"

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
        """Return effect state."""
        return self.sys_info["lighting_effect_state"]

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return strip specific state information."""
        info = super().state_information

        info["Length"] = self.length

        return info
