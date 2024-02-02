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
from typing import TYPE_CHECKING
from warnings import warn

from kasa.bulb import Bulb
from kasa.credentials import Credentials
from kasa.device import Device
from kasa.device_type import DeviceType
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
from kasa.iot.bulb import BulbPreset, TurnOnBehavior, TurnOnBehaviors
from kasa.iotprotocol import (
    IotProtocol,
    _deprecated_TPLinkSmartHomeProtocol,  # noqa: F401
)
from kasa.plug import Plug
from kasa.protocol import BaseProtocol
from kasa.smartprotocol import SmartProtocol

__version__ = version("python-kasa")


__all__ = [
    "Discover",
    "BaseProtocol",
    "IotProtocol",
    "SmartProtocol",
    "BulbPreset",
    "TurnOnBehaviors",
    "TurnOnBehavior",
    "DeviceType",
    "EmeterStatus",
    "Device",
    "Bulb",
    "Plug",
    "SmartDeviceException",
    "AuthenticationException",
    "UnsupportedDeviceException",
    "TimeoutException",
    "Credentials",
    "DeviceConfig",
    "ConnectionType",
    "EncryptType",
    "DeviceFamilyType",
]

from . import iot

deprecated_names = ["TPLinkSmartHomeProtocol"]
deprecated_smart_devices = {
    "SmartDevice": iot.IotDevice,
    "SmartPlug": iot.IotPlug,
    "SmartBulb": iot.IotBulb,
    "SmartLightStrip": iot.IotLightStrip,
    "SmartStrip": iot.IotStrip,
    "SmartDimmer": iot.IotDimmer,
    "SmartBulbPreset": iot.BulbPreset,
}


def __getattr__(name):
    if name in deprecated_names:
        warn(f"{name} is deprecated", DeprecationWarning, stacklevel=1)
        return globals()[f"_deprecated_{name}"]
    if name in deprecated_smart_devices:
        new_class = deprecated_smart_devices[name]
        new_name = (
            ".".join(new_class.__module__.split(".")[:-1]) + "." + new_class.__name__
        )
        warn(
            f"{name} is deprecated, use {new_name} instead",
            DeprecationWarning,
            stacklevel=1,
        )
        return new_class
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    SmartDevice = Device
    SmartBulb = iot.IotBulb
    SmartPlug = iot.IotPlug
    SmartLightStrip = iot.IotLightStrip
    SmartStrip = iot.IotStrip
    SmartDimmer = iot.IotDimmer
    SmartBulbPreset = BulbPreset
