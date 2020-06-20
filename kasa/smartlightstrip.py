"""Module for LED strips."""
from .smartbulb import SmartBulb
from .smartdevice import DeviceType


class SmartLightStrip(SmartBulb):
    """Representation of a TP-Link Smart light strip."""

    LIGHT_SERVICE = "smartlife.iot.lightStrip"
    SET_LIGHT_METHOD = SmartBulb.SET_LIGHT_METHOD

    def __init__(self, host: str, force_set_light=False) -> None:
        super().__init__(host=host)
        self._device_type = DeviceType.LightStrip
        if force_set_light:
            self.SET_LIGHT_METHOD = "set_light_state"
