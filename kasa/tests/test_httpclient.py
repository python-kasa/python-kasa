import asyncio
import re

import aiohttp
import pytest

from ..deviceconfig import DeviceConfig
from ..exceptions import (
    KasaException,
    TimeoutError,
    _ConnectionError,
)
from ..httpclient import HttpClient


@pytest.mark.parametrize(
    "error, error_raises, error_message",
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
            asyncio.TimeoutError(),
            TimeoutError,
            "Unable to query the device, timed out: ",
        ),
        (Exception(), KasaException, "Unable to query the device: "),
        (
            aiohttp.ServerFingerprintMismatch("exp", "got", "host", 1),
            KasaException,
            "Unable to query the device: ",
        ),
    ],
    ids=(
        "ServerDisconnectedError",
        "ClientOSError",
        "ServerTimeoutError",
        "TimeoutError",
        "Exception",
        "ServerFingerprintMismatch",
    ),
)
@pytest.mark.parametrize("mock_read", (False, True), ids=("post", "read"))
async def test_httpclient_errors(mocker, error, error_raises, error_message, mock_read):
    class _mock_response:
        def __init__(self, status, error):
            self.status = status
            self.error = error
            self.call_count = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_t, exc_v, exc_tb):
            pass

        async def read(self):
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
        "\("  # type: ignore
        + "['\"]"
        + re.escape(f"{error_message}{host}: {error}")
        + "['\"]"
        + re.escape(f", {repr(error)})")
    )
    with pytest.raises(error_raises, match=error_message) as exc_info:
        await client.post("http://foobar")

    assert re.match(full_msg, str(exc_info.value))
    if mock_read:
        assert mock_response.call_count == 1
    else:
        assert conn.call_count == 1
