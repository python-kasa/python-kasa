import builtins
import logging
import re

import aiohttp
import pytest
from pytest_mock import MockerFixture
from yarl import URL

from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    KasaException,
    TimeoutError,
    _ConnectionError,
)
from kasa.httpclient import HttpClient


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
    ],
    ids=(
        "ServerDisconnectedError",
        "ClientOSError",
        "ServerTimeoutError",
        "TimeoutError",
        "BuiltinTimeoutError",
        "Exception",
        "ServerFingerprintMismatch",
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
    if mock_read:
        assert mock_response.call_count == 1
    else:
        assert conn.call_count == 1


class _OkResponse:
    status = 200
    connection = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_t, exc_v, exc_tb) -> None:
        pass

    async def read(self) -> bytes:
        return b"{}"


async def test_httpclient_debug_log_hides_session_token(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """The /stok=<token>/ds session token of TPAP and camera logins is not logged."""

    async def _post(url, *_, **__):
        return _OkResponse()

    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=_post)
    client = HttpClient(DeviceConfig("127.0.0.1"))

    with caplog.at_level(logging.DEBUG, logger="kasa.httpclient"):
        await client.post(URL("https://127.0.0.1:4433/stok=S3cr3tT0k3n/ds"), data=b"x")
        await client.post(URL("http://127.0.0.1/app/handshake1"), data=b"x")

    assert "S3cr3tT0k3n" not in caplog.text
    assert "Posting to https://127.0.0.1:4433/stok=REDACTED/ds" in caplog.text
    assert "Posting to http://127.0.0.1/app/handshake1" in caplog.text
