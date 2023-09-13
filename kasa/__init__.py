"""Python interface for TP-Link's smart home devices.

All common, shared functionalities are available through `SmartDevice` class::

    x = SmartDevice("192.168.1.1")
    print(x.sys_info)

For device type specific actions `SmartBulb`, `SmartPlug`, or `SmartStrip`
 should be used instead.

Module-specific errors are raised as `SmartDeviceException` and are expected
to be handled by the user of the library.
"""
from importlib.metadata import version

from kasa.credentials import Credentials
from kasa.discover import Discover
from kasa.emeterstatus import EmeterStatus
from kasa.exceptions import (
    AuthenticationException,
    SmartDeviceException,
    UnsupportedDeviceException,
)
from kasa.protocol import TPLinkSmartHomeProtocol
from kasa.smartbulb import SmartBulb, SmartBulbPreset, TurnOnBehavior, TurnOnBehaviors
from kasa.smartdevice import DeviceType, SmartDevice
from kasa.smartdimmer import SmartDimmer
from kasa.smartlightstrip import SmartLightStrip
from kasa.smartplug import SmartPlug
from kasa.smartstrip import SmartStrip

__version__ = version("python-kasa")


__all__ = [
    "Discover",
    "TPLinkSmartHomeProtocol",
    "SmartBulb",
    "SmartBulbPreset",
    "TurnOnBehaviors",
    "TurnOnBehavior",
    "DeviceType",
    "EmeterStatus",
    "SmartDevice",
    "SmartDeviceException",
    "SmartPlug",
    "SmartStrip",
    "SmartDimmer",
    "SmartLightStrip",
    "AuthenticationException",
    "UnsupportedDeviceException",
    "Credentials",
]
