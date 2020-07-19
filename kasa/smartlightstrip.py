"""Module for light strips (KL430)."""
from .smartbulb import SmartBulb
from .smartdevice import DeviceType


class SmartLightStrip(SmartBulb):
    """Representation of a TP-Link Smart light strip.

    Interaction works just like with the bulbs, only the service name
    for controlling the device is different.
    """

    LIGHT_SERVICE = "smartlife.iot.lightStrip"

    def __init__(self, host: str) -> None:
        super().__init__(host)
        self._device_type = DeviceType.LightStrip
