"""python-kasa exceptions."""

from __future__ import annotations

from asyncio import TimeoutError as _asyncioTimeoutError
from enum import IntEnum
from functools import cache
from typing import Any


class KasaException(Exception):
    """Base exception for library errors."""


class TimeoutError(KasaException, _asyncioTimeoutError):
    """Timeout exception for device errors."""

    def __repr__(self) -> str:
        return KasaException.__repr__(self)

    def __str__(self) -> str:
        return KasaException.__str__(self)


class _ConnectionError(KasaException):
    """Connection exception for device errors."""


class UnsupportedDeviceError(KasaException):
    """Exception for trying to connect to unsupported devices."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.discovery_result = kwargs.get("discovery_result")
        self.host = kwargs.get("host")
        super().__init__(*args)


class DeviceError(KasaException):
    """Base exception for device errors."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.error_code: SmartErrorCode | None = kwargs.get("error_code")
        super().__init__(*args)

    def __repr__(self) -> str:
        err_code = self.error_code.__repr__() if self.error_code else ""
        return f"{self.__class__.__name__}({err_code})"

    def __str__(self) -> str:
        err_code = f" (error_code={self.error_code.name})" if self.error_code else ""
        return super().__str__() + err_code


class AuthenticationError(DeviceError):
    """Base exception for device authentication errors."""


class _RetryableError(DeviceError):
    """Retryable exception for device errors."""


class SmartErrorCode(IntEnum):
    """Enum for SMART Error Codes."""

    def __str__(self) -> str:
        return f"{self.name}({self.value})"

    @staticmethod
    @cache
    def from_int(value: int) -> SmartErrorCode:
        """Convert an integer to a SmartErrorCode."""
        return SmartErrorCode(value)

    SUCCESS = 0

    # Transport Errors
    SESSION_TIMEOUT_ERROR = 9999
    MULTI_REQUEST_FAILED_ERROR = 1200
    HTTP_TRANSPORT_FAILED_ERROR = 1112
    LOGIN_FAILED_ERROR = 1111
    HAND_SHAKE_FAILED_ERROR = 1100
    #: Real description unknown, seen after an encryption-changing fw upgrade
    TRANSPORT_UNKNOWN_CREDENTIALS_ERROR = 1003
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

    VACUUM_BATTERY_LOW = -3001

    SYSTEM_ERROR = -40101
    INVALID_ARGUMENTS = -40209

    # Camera error codes
    SESSION_EXPIRED = -40401
    BAD_USERNAME = -40411  # determined from testing
    HOMEKIT_LOGIN_FAIL = -40412
    DEVICE_BLOCKED = -40404
    DEVICE_FACTORY = -40405
    OUT_OF_LIMIT = -40406
    OTHER_ERROR = -40407
    SYSTEM_BLOCKED = -40408
    NONCE_EXPIRED = -40409
    FFS_NONE_PWD = -90000
    TIMEOUT_ERROR = 40108
    UNSUPPORTED_METHOD = -40106
    ONE_SECOND_REPEAT_REQUEST = -40109
    INVALID_NONCE = -40413
    PROTOCOL_FORMAT_ERROR = -40210
    IP_CONFLICT = -40321
    DIAGNOSE_TYPE_NOT_SUPPORT = -69051
    DIAGNOSE_TASK_FULL = -69052
    DIAGNOSE_TASK_BUSY = -69053
    DIAGNOSE_INTERNAL_ERROR = -69055
    DIAGNOSE_ID_NOT_FOUND = -69056
    DIAGNOSE_TASK_NULL = -69057
    CLOUD_LINK_DOWN = -69060
    ONVIF_SET_WRONG_TIME = -69061
    CLOUD_NTP_NO_RESPONSE = -69062
    CLOUD_GET_WRONG_TIME = -69063
    SNTP_SRV_NO_RESPONSE = -69064
    SNTP_GET_WRONG_TIME = -69065
    LINK_UNCONNECTED = -69076
    WIFI_SIGNAL_WEAK = -69077
    LOCAL_NETWORK_POOR = -69078
    CLOUD_NETWORK_POOR = -69079
    INTER_NETWORK_POOR = -69080
    DNS_TIMEOUT = -69081
    DNS_ERROR = -69082
    PING_NO_RESPONSE = -69083
    DHCP_MULTI_SERVER = -69084
    DHCP_ERROR = -69085
    STREAM_SESSION_CLOSE = -69094
    STREAM_BITRATE_EXCEPTION = -69095
    STREAM_FULL = -69096
    STREAM_NO_INTERNET = -69097
    HARDWIRED_NOT_FOUND = -72101

    # Library internal for unknown error codes
    INTERNAL_UNKNOWN_ERROR = -100_000
    # Library internal for query errors
    INTERNAL_QUERY_ERROR = -100_001


SMART_RETRYABLE_ERRORS = [
    SmartErrorCode.TRANSPORT_NOT_AVAILABLE_ERROR,
    SmartErrorCode.HTTP_TRANSPORT_FAILED_ERROR,
    SmartErrorCode.UNSPECIFIC_ERROR,
    SmartErrorCode.SESSION_TIMEOUT_ERROR,
    SmartErrorCode.SESSION_EXPIRED,
    SmartErrorCode.INVALID_NONCE,
]

SMART_AUTHENTICATION_ERRORS = [
    SmartErrorCode.LOGIN_ERROR,
    SmartErrorCode.LOGIN_FAILED_ERROR,
    SmartErrorCode.AES_DECODE_FAIL_ERROR,
    SmartErrorCode.HAND_SHAKE_FAILED_ERROR,
    SmartErrorCode.TRANSPORT_UNKNOWN_CREDENTIALS_ERROR,
    SmartErrorCode.HOMEKIT_LOGIN_FAIL,
]
