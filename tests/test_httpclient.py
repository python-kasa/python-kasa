import builtins
import re

import aiohttp
import pytest
from aiohttp.http_exceptions import HttpProcessingError
from multidict import CIMultiDict, CIMultiDictProxy
from pytest_mock import MockerFixture
from yarl import URL

from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    KasaException,
    TimeoutError,
    _ConnectionError,
    _InvalidResponseError,
)
from kasa.httpclient import HttpClient


def _response_error(cause: Exception | None) -> aiohttp.ClientResponseError:
    """Return the error aiohttp raises for a response, with its cause."""
    url = URL("http://127.0.0.1/app/request")
    request_info = aiohttp.RequestInfo(
        url, "POST", CIMultiDictProxy(CIMultiDict()), url
    )
    error = aiohttp.ClientResponseError(
        request_info, (), status=400, message="Bad status line"
    )
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("error", "error_raises", "error_message"),
    [
        (
            aiohttp.ServerDisconnectedError(),
            _ConnectionError,
            "Device connection error: ",
        ),
        (
            aiohttp.ClientOSError(),
            _ConnectionError,
            "Device connection error: ",
        ),
        (
            aiohttp.ServerTimeoutError(),
            TimeoutError,
            "Unable to query the device, timed out: ",
        ),
        (
            TimeoutError(),
            TimeoutError,
            "Unable to query the device, timed out: ",
        ),
        # aiohttp raises the builtin TimeoutError when ClientTimeout(total=...)
        # expires after the connection is established.
        (
            builtins.TimeoutError(),
            TimeoutError,
            "Unable to query the device, timed out: ",
        ),
        (Exception(), KasaException, "Unable to query the device: "),
        (
            aiohttp.ServerFingerprintMismatch(b"exp", b"got", "host", 1),
            KasaException,
            "Unable to query the device: ",
        ),
        # A plain html page without an http status line can't be parsed.
        (
            _response_error(HttpProcessingError(code=400, message="Bad status line")),
            _InvalidResponseError,
            "Unable to parse the device response: ",
        ),
        (
            _response_error(None),
            KasaException,
            "Unable to query the device: ",
        ),
    ],
    ids=(
        "ServerDisconnectedError",
        "ClientOSError",
        "ServerTimeoutError",
        "TimeoutError",
        "BuiltinTimeoutError",
        "Exception",
        "ServerFingerprintMismatch",
        "ParseError",
        "ClientResponseError",
    ),
)
@pytest.mark.parametrize("mock_read", [False, True], ids=("post", "read"))
async def test_httpclient_errors(
    mocker: MockerFixture,
    error: Exception,
    error_raises: type[Exception],
    error_message: str,
    mock_read: bool,
) -> None:
    class _mock_response:
        def __init__(self, status, error) -> None:
            self.status = status
            self.error = error
            self.call_count = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_t, exc_v, exc_tb) -> None:
            pass

        async def read(self) -> bytes:
            self.call_count += 1
            raise self.error

    mock_response = _mock_response(200, error)

    async def _post(url, *_, **__):
        nonlocal mock_response
        return mock_response

    host = "127.0.0.1"

    side_effect = _post if mock_read else error

    conn = mocker.patch.object(aiohttp.ClientSession, "post", side_effect=side_effect)
    client = HttpClient(DeviceConfig(host))
    # Exceptions with parameters print with double quotes, without use single quotes
    full_msg = (
        re.escape("(")
        + "['\"]"
        + re.escape(f"{error_message}{host}: {error}")
        + "['\"]"
        + re.escape(f", {repr(error)})")
    )
    with pytest.raises(error_raises, match=error_message) as exc_info:
        await client.post(URL("http://foobar"))

    assert re.match(full_msg, str(exc_info.value))
    assert type(exc_info.value) is error_raises
    if mock_read:
        assert mock_response.call_count == 1
    else:
        assert conn.call_count == 1
