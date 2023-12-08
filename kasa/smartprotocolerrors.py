"""Module for defining SMART protocol errors."""
from enum import Enum


class ErrorCode(Enum):
    """Enum for SMART Error Codes."""

    SUCCESS = 0

    UNKNOWN_ERROR_CODE = 999999
    ERROR_CODE_NONE = 999998
    ERROR_CODE_INVALID = 999997

    ACCOUNT_ERROR = -2101
    AES_DECODE_FAIL_ERROR = -1005
    ANTITHEFT_CONFLICT_ERROR = -2002
    ANTITHEFT_ERROR = -2001
    ANTITHEFT_SAVE_ERROR = -2003
    CLOUD_FAILED_ERROR = -1007
    CMD_COMMAND_CANCEL_ERROR = 1001
    COMMON_FAILED_ERROR = -1
    COUNTDOWN_CONFLICT_ERROR = -1902
    COUNTDOWN_ERROR = -1901
    COUNTDOWN_SAVE_ERROR = -1903
    DEVICE_ERROR = -1301
    DEVICE_NEXT_EVENT_ERROR = -1302
    DST_ERROR = -2301
    DST_SAVE_ERROR = -2302
    FIRMWARE_ERROR = -1401
    FIRMWARE_VER_ERROR_ERROR = -1402
    HAND_SHAKE_FAILED_ERROR = 1100
    HTTP_TRANSPORT_FAILED_ERROR = 1112
    JSON_DECODE_FAIL_ERROR = -1003
    JSON_ENCODE_FAIL_ERROR = -1004
    INVALID_PUBLIC_KEY_ERROR = -1010  # Unverified
    LOGIN_ERROR = -1501
    LOGIN_FAILED_ERROR = 1111
    MULTI_REQUEST_FAILED_ERROR = 1200
    NULL_TRANSPORT_ERROR = 1000
    PARAMS_ERROR = -1008
    QUICK_SETUP_ERROR = -1201
    REQUEST_LEN_ERROR_ERROR = -1006
    SCHEDULE_CONFLICT_ERROR = -1803
    SCHEDULE_ERROR = -1801
    SCHEDULE_FULL_ERROR = -1802
    SCHEDULE_INDEX_ERROR = -1805
    SCHEDULE_SAVE_ERROR = -1804
    SESSION_PARAM_ERROR = -1101
    SESSION_TIMEOUT_ERROR = 9999
    STAT_ERROR = -2201
    STAT_SAVE_ERROR = -2202
    TIME_ERROR = -1601
    TIME_SAVE_ERROR = -1603
    TIME_SYS_ERROR = -1602
    TRANSPORT_NOT_AVAILABLE_ERROR = 1002
    UNKNOWN_METHOD_ERROR = -1002
    UNSPECIFIC_ERROR = -1001
    WIRELESS_ERROR = -1701
    WIRELESS_UNSUPPORTED_ERROR = -1702

    @classmethod
    def _missing_(cls, value):
        if value is None:
            return cls.ERROR_CODE_NONE
        if isinstance(value, int):
            return cls.UNKNOWN_ERROR_CODE
        else:
            return cls.ERROR_CODE_INVALID


RETRYABLE_ERRORS = [
    ErrorCode.TRANSPORT_NOT_AVAILABLE_ERROR,
    ErrorCode.HTTP_TRANSPORT_FAILED_ERROR,
    ErrorCode.UNSPECIFIC_ERROR,
]

AUTHENTICATION_ERRORS = [
    ErrorCode.LOGIN_ERROR,
    ErrorCode.LOGIN_FAILED_ERROR,
    ErrorCode.AES_DECODE_FAIL_ERROR,
    ErrorCode.HAND_SHAKE_FAILED_ERROR,
]

TIMEOUT_ERRORS = [
    ErrorCode.SESSION_TIMEOUT_ERROR,
]
