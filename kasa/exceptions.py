"""python-kasa exceptions."""


class SmartDeviceException(Exception):
    """Base exception for device errors."""

class SmartDeviceAuthenticationException(SmartDeviceException):
    """Base exception for authenticated  errors."""