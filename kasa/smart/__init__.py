"""Package for supporting tapo-branded and newer kasa devices."""

from .smartchilddevice import SmartChildDevice
from .smartdevice import SmartDevice

__all__ = ["SmartDevice", "SmartChildDevice"]
