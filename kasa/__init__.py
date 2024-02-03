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
from kasa.descriptors import Descriptor, DescriptorCategory, DescriptorType
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
from kasa.iot.iotbulb import BulbPreset, TurnOnBehavior, TurnOnBehaviors
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
    "Descriptor",
    "DescriptorType",
    "DescriptorCategory",
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
    "SmartBulbPreset": BulbPreset,
}


def __getattr__(name):
    if name in deprecated_names:
        warn(f"{name} is deprecated", DeprecationWarning, stacklevel=1)
        return globals()[f"_deprecated_{name}"]
    if name in deprecated_smart_devices:
        new_class = deprecated_smart_devices[name]
        package_name = ".".join(new_class.__module__.split(".")[:-1])
        warn(
            f"{name} is deprecated, use {new_class.__name__} "
            + f"from package {package_name} instead or use Discover.discover_single()"
            + " and Device.connect() to support new protocols",
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
    # Instanstiate all classes so the type checkers catch abstract issues
    from . import smart

    smart.SmartDevice("127.0.0.1")
    smart.SmartPlug("127.0.0.1")
    smart.SmartBulb("127.0.0.1")
    iot.IotDevice("127.0.0.1")
    iot.IotPlug("127.0.0.1")
    iot.IotBulb("127.0.0.1")
    iot.IotLightStrip("127.0.0.1")
    iot.IotStrip("127.0.0.1")
    iot.IotDimmer("127.0.0.1")
