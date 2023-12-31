"""python-kasa exceptions."""
from enum import IntEnum
from typing import Optional


class SmartDeviceException(Exception):
    """Base exception for device errors."""

    def __init__(self, *args, **kwargs):
        self.error_code: Optional["SmartErrorCode"] = kwargs.get("error_code", None)
        super().__init__(*args)


class UnsupportedDeviceException(SmartDeviceException):
    """Exception for trying to connect to unsupported devices."""

    def __init__(self, *args, **kwargs):
        self.discovery_result = kwargs.get("discovery_result")
        super().__init__(*args, **kwargs)


class AuthenticationException(SmartDeviceException):
    """Base exception for device authentication errors."""


class RetryableException(SmartDeviceException):
    """Retryable exception for device errors."""

class TimeoutException(SmartDeviceException):
    """Timeout exception for device errors."""


class SmartErrorCode(IntEnum):
    """Enum for SMART Error Codes."""

    SUCCESS = 0

    # Transport Errors
    SESSION_TIMEOUT_ERROR = 9999
    MULTI_REQUEST_FAILED_ERROR = 1200
    HTTP_TRANSPORT_FAILED_ERROR = 1112
    LOGIN_FAILED_ERROR = 1111
    HAND_SHAKE_FAILED_ERROR = 1100
    TRANSPORT_NOT_AVAILABLE_ERROR = 1002
    CMD_COMMAND_CANCEL_ERROR = 1001
    NULL_TRANSPORT_ERROR = 1000

    # Common Method Errors
    COMMON_FAILED_ERROR = -1
    UNSPECIFIC_ERROR = -1001
    UNKNOWN_METHOD_ERROR = -1002
    JSON_DECODE_FAIL_ERROR = -1003
    JSON_ENCODE_FAIL_ERROR = -1004
    AES_DECODE_FAIL_ERROR = -1005
    REQUEST_LEN_ERROR_ERROR = -1006
    CLOUD_FAILED_ERROR = -1007
    PARAMS_ERROR = -1008
    INVALID_PUBLIC_KEY_ERROR = -1010  # Unverified
    SESSION_PARAM_ERROR = -1101

    # Method Specific Errors
    QUICK_SETUP_ERROR = -1201
    DEVICE_ERROR = -1301
    DEVICE_NEXT_EVENT_ERROR = -1302
    FIRMWARE_ERROR = -1401
    FIRMWARE_VER_ERROR_ERROR = -1402
    LOGIN_ERROR = -1501
    TIME_ERROR = -1601
    TIME_SYS_ERROR = -1602
    TIME_SAVE_ERROR = -1603
    WIRELESS_ERROR = -1701
    WIRELESS_UNSUPPORTED_ERROR = -1702
    SCHEDULE_ERROR = -1801
    SCHEDULE_FULL_ERROR = -1802
    SCHEDULE_CONFLICT_ERROR = -1803
    SCHEDULE_SAVE_ERROR = -1804
    SCHEDULE_INDEX_ERROR = -1805
    COUNTDOWN_ERROR = -1901
    COUNTDOWN_CONFLICT_ERROR = -1902
    COUNTDOWN_SAVE_ERROR = -1903
    ANTITHEFT_ERROR = -2001
    ANTITHEFT_CONFLICT_ERROR = -2002
    ANTITHEFT_SAVE_ERROR = -2003
    ACCOUNT_ERROR = -2101
    STAT_ERROR = -2201
    STAT_SAVE_ERROR = -2202
    DST_ERROR = -2301
    DST_SAVE_ERROR = -2302


SMART_RETRYABLE_ERRORS = [
    SmartErrorCode.TRANSPORT_NOT_AVAILABLE_ERROR,
    SmartErrorCode.HTTP_TRANSPORT_FAILED_ERROR,
    SmartErrorCode.UNSPECIFIC_ERROR,
]

SMART_AUTHENTICATION_ERRORS = [
    SmartErrorCode.LOGIN_ERROR,
    SmartErrorCode.LOGIN_FAILED_ERROR,
    SmartErrorCode.AES_DECODE_FAIL_ERROR,
    SmartErrorCode.HAND_SHAKE_FAILED_ERROR,
]

SMART_TIMEOUT_ERRORS = [
    SmartErrorCode.SESSION_TIMEOUT_ERROR,
]
