"""Python interface for TP-Link's smart home devices.

All common, shared functionalities are available through `SmartDevice` class::

    x = SmartDevice("192.168.1.1")
    print(x.sys_info)

For device type specific actions `SmartBulb`, `SmartPlug`, or `SmartStrip`
 should be used instead.

Module-specific errors are raised as `SmartDeviceException` and are expected
to be handled by the user of the library.
"""
from kasa.discover import Discover
from kasa.protocol import TPLinkSmartHomeProtocol
from kasa.smartbulb import SmartBulb
from kasa.smartdevice import DeviceType, EmeterStatus, SmartDevice, SmartDeviceException
from kasa.smartplug import SmartPlug
from kasa.smartstrip import SmartStrip
from kasa.smartdimmer import SmartDimmer

__all__ = [
    "Discover",
    "TPLinkSmartHomeProtocol",
    "SmartBulb",
    "DeviceType",
    "EmeterStatus",
    "SmartDevice",
    "SmartDeviceException",
    "SmartPlug",
    "SmartStrip",
    "SmartDimmer",
]
