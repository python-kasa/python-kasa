"""python-kasa exceptions."""


class SmartDeviceException(Exception):
    """Base exception for device errors."""

class SmartDeviceAuthenticationException(Exception):
    """Base exception for authentication  errors."""