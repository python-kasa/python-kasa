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
from warnings import warn

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    ConnectionType,
    DeviceConfig,
    DeviceFamilyType,
    EncryptType,
)
from kasa.discover import Discover
from kasa.emeterstatus import EmeterStatus
from kasa.exceptions import (
    AuthenticationException,
    SmartDeviceException,
    TimeoutException,
    UnsupportedDeviceException,
)
from kasa.iotprotocol import IotProtocol
from kasa.protocol import BaseProtocol
from kasa.smartbulb import SmartBulb, SmartBulbPreset, TurnOnBehavior, TurnOnBehaviors
from kasa.smartdevice import DeviceType, SmartDevice
from kasa.smartdimmer import SmartDimmer
from kasa.smartlightstrip import SmartLightStrip
from kasa.smartplug import SmartPlug
from kasa.smartprotocol import SmartProtocol
from kasa.smartstrip import SmartStrip

__version__ = version("python-kasa")


__all__ = [
    "Discover",
    "BaseProtocol",
    "IotProtocol",
    "SmartProtocol",
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
    "TimeoutException",
    "Credentials",
    "DeviceConfig",
    "ConnectionType",
    "EncryptType",
    "DeviceFamilyType",
]

deprecated_names = ["TPLinkSmartHomeProtocol"]


def __getattr__(name):
    if name in deprecated_names:
        warn(f"{name} is deprecated", DeprecationWarning, stacklevel=1)
        return globals()[f"_deprecated_{name}"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
