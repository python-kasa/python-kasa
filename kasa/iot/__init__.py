"""Package for supporting legacy kasa devices."""

from .iotbulb import IotBulb
from .iotdevice import IotDevice
from .iotdimmer import IotDimmer
from .iotlightstrip import IotLightStrip
from .iotplug import IotPlug, IotWallSwitch
from .iotstrip import IotStrip

__all__ = [
    "IotDevice",
    "IotPlug",
    "IotBulb",
    "IotStrip",
    "IotDimmer",
    "IotLightStrip",
    "IotWallSwitch",
]
