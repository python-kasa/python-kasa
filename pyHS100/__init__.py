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
# flake8: noqa
from .smartdevice import SmartDevice, SmartDeviceException, EmeterStatus
from .smartdevice import SmartDevice, SmartDeviceException, EmeterStatus, DeviceType
from .smartplug import SmartPlug
from .smartbulb import SmartBulb
from .smartstrip import SmartStrip, SmartStripException
from .protocol import TPLinkSmartHomeProtocol
from .discover import Discover
