"""python-kasa exceptions."""


class SmartDeviceException(Exception):
    """Base exception for device errors."""


class UnsupportedDeviceException(SmartDeviceException):
    """Exception for trying to connect to unsupported devices."""

    def __init__(self, *args, discovery_result=None):
        self.discovery_result = discovery_result
        super().__init__(args)


class AuthenticationException(SmartDeviceException):
    """Base exception for device authentication errors."""
