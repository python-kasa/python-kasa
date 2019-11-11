"""
This module provides a way to interface with TP-Link's smart home devices,
such as smart plugs (HS1xx), wall switches (HS2xx), and light bulbs (LB1xx).

All common, shared functionalities are available through `SmartDevice` class::

    x = SmartDevice("192.168.1.1")
    print(x.sys_info)

For device type specific actions `SmartBulb` or `SmartPlug` must be used instead.

Module-specific errors are raised as `SmartDeviceException` and are expected
to be handled by the user of the library.
"""
from pyHS100.discover import Discover
from pyHS100.protocol import TPLinkSmartHomeProtocol
from pyHS100.smartbulb import SmartBulb
from pyHS100.smartdevice import (
    DeviceType,
    EmeterStatus,
    SmartDevice,
    SmartDeviceException,
)
from pyHS100.smartplug import SmartPlug
from pyHS100.smartstrip import SmartStrip, SmartStripException

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
    "SmartStripException",
]
