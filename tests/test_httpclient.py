import logging
import re
from types import SimpleNamespace

import aiohttp
import pytest
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
        "Exception",
        "ServerFingerprintMismatch",
    ),
)
@pytest.mark.parametrize("mock_read", [False, True], ids=("post", "read"))
async def test_httpclient_errors(mocker, error, error_raises, error_message, mock_read):
    class _mock_response:
        def __init__(self, status, error):
            self.status = status
            self.error = error
            self.call_count = 0
            self.connection = None
            self._protocol = None

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
    try:
        # Exceptions with parameters print with double quotes, without use single quotes
        full_msg = (
            re.escape("(")
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
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_post_with_info_logs_host_when_error_response_is_not_json(mocker, caplog):
    class _mock_response:
        status = 500
        connection = None
        _protocol = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_t, exc_v, exc_tb):
            pass

        async def read(self):
            return b"not-json"

    async def _post(url, *_, **__):
        del url
        return _mock_response()

    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=_post)
    client = HttpClient(DeviceConfig("127.0.0.1"))
    try:
        with caplog.at_level(logging.DEBUG):
            status, response_data, _ = await client.post_with_info(
                URL("http://foobar"),
                json={"method": "test"},
            )

        assert status == 500
        assert response_data == b"not-json"
        assert "Device 127.0.0.1 response could not be parsed as json" in caplog.text
    finally:
        await client.close()


def test_get_peer_cert_der_reads_from_connection():
    expected = b"peer-cert"

    class _SslObject:
        def getpeercert(self, *, binary_form):
            assert binary_form is True
            return expected

    class _Transport:
        def get_extra_info(self, name):
            assert name == "ssl_object"
            return _SslObject()

    resp = SimpleNamespace(connection=SimpleNamespace(transport=_Transport()))

    assert HttpClient._get_peer_cert_der(resp) == expected


def test_get_peer_cert_der_returns_none_without_transport():
    resp = SimpleNamespace(connection=None)

    assert HttpClient._get_peer_cert_der(resp) is None


def test_get_peer_cert_der_returns_none_without_ssl_object():
    class _Transport:
        def get_extra_info(self, name):
            assert name == "ssl_object"
            return None

    resp = SimpleNamespace(connection=SimpleNamespace(transport=_Transport()))

    assert HttpClient._get_peer_cert_der(resp) is None


def test_get_peer_cert_der_returns_none_when_getpeercert_fails():
    class _SslObject:
        def getpeercert(self, *, binary_form):
            assert binary_form is True
            raise RuntimeError("boom")

    class _Transport:
        def get_extra_info(self, name):
            assert name == "ssl_object"
            return _SslObject()

    resp = SimpleNamespace(connection=SimpleNamespace(transport=_Transport()))

    assert HttpClient._get_peer_cert_der(resp) is None
