"""python-kasa exceptions."""


class SmartDeviceException(Exception):
    """Base exception for device errors."""


class UnsupportedDeviceException(SmartDeviceException):
    """Exception for trying to connect to unsupported devices."""


class AuthenticationException(SmartDeviceException):
    """Base exception for device authentication errors."""


class RetryableException(SmartDeviceException):
    """Retryable exception for device errors."""


class TimeoutException(SmartDeviceException):
    """Timeout exception for device errors."""
