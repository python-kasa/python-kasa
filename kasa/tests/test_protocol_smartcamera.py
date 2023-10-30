import errno
import logging
from base64 import b64encode

import httpx
import pytest

from ..credentials import Credentials
from ..exceptions import SmartDeviceException
from ..smartcameraprotocol import SmartCameraProtocol


@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries(mocker, retry_count):
    conn = mocker.patch("httpx.Client.post", side_effect=Exception("dummy exception"))
    with pytest.raises(SmartDeviceException):
        await SmartCameraProtocol(
            "127.0.0.1", credentials=Credentials("user", "pass")
        ).query({}, retry_count=retry_count)

    assert conn.call_count == retry_count + 1


async def test_protocol_no_retry_on_unreachable(mocker):
    conn = mocker.patch.object(
        SmartCameraProtocol,
        "_connect",
        side_effect=OSError(errno.EHOSTUNREACH, "No route to host"),
    )
    with pytest.raises(SmartDeviceException):
        await SmartCameraProtocol(
            "127.0.0.1", credentials=Credentials("user", "pass")
        ).query({}, retry_count=5)

    assert conn.call_count == 1


async def test_protocol_no_retry_connection_refused(mocker):
    conn = mocker.patch.object(
        SmartCameraProtocol, "_connect", side_effect=ConnectionRefusedError
    )
    with pytest.raises(SmartDeviceException):
        await SmartCameraProtocol(
            "127.0.0.1", credentials=Credentials("user", "pass")
        ).query({}, retry_count=5)

    assert conn.call_count == 1


async def test_protocol_retry_recoverable_error(mocker):
    conn = mocker.patch.object(
        SmartCameraProtocol,
        "_connect",
        side_effect=OSError(errno.ECONNRESET, "Connection reset by peer"),
    )
    with pytest.raises(SmartDeviceException):
        await SmartCameraProtocol(
            "127.0.0.1", credentials=Credentials("user", "pass")
        ).query({}, retry_count=5)

    assert conn.call_count == 6


@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_reconnect(mocker, retry_count):
    remaining = retry_count
    encrypted = b64encode(
        SmartCameraProtocol.encrypt('{"great":"success"}')[
            SmartCameraProtocol.BLOCK_SIZE :
        ]
    )

    def _fail_one_less_than_retry_count(*_, **__):
        nonlocal remaining
        remaining -= 1
        if remaining:
            raise Exception("Simulated post failure")

        return httpx.Response(status_code=200, content=encrypted)

    mocker.patch("httpx.Client.post", side_effect=_fail_one_less_than_retry_count)

    protocol = SmartCameraProtocol("127.0.0.1", credentials=Credentials("user", "pass"))
    response = await protocol.query({}, retry_count=retry_count)
    assert response == {"great": "success"}


@pytest.mark.parametrize("log_level", [logging.WARNING, logging.DEBUG])
async def test_protocol_logging(mocker, caplog, log_level):
    caplog.set_level(log_level)
    logging.getLogger("kasa").setLevel(log_level)

    encrypted = b64encode(
        SmartCameraProtocol.encrypt('{"great":"success"}')[
            SmartCameraProtocol.BLOCK_SIZE :
        ]
    )

    def mock_response(*_, **__):
        return httpx.Response(status_code=200, content=encrypted)

    mocker.patch("httpx.Client.post", side_effect=mock_response)

    protocol = SmartCameraProtocol("127.0.0.1", credentials=Credentials("user", "pass"))
    response = await protocol.query({})
    assert response == {"great": "success"}
    if log_level == logging.DEBUG:
        assert "success" in caplog.text
    else:
        assert "success" not in caplog.text


async def test_protocol_b64_encodes_credential_password(mocker):
    session = mocker.spy(httpx.BasicAuth, "__init__")
    protocol = SmartCameraProtocol("127.0.0.1", credentials=Credentials("user", "pass"))
    await protocol._connect(timeout=5)
    session.assert_called_once_with(
        mocker.ANY, username="user", password=b64encode(b"pass")
    )
