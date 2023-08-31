"""python-kasa exceptions."""


class SmartDeviceException(Exception):
    """Base exception for device errors."""


class UnsupportedDeviceException(SmartDeviceException):
    """Exception for trying to connect to unsupported devices."""


class SmartDeviceAuthenticationException(SmartDeviceException):
    """Base exception for device authentication errors."""
