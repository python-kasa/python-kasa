import base64
from unittest.mock import ANY

import aiohttp
import pytest
from yarl import URL

from kasa.credentials import DEFAULT_CREDENTIALS, Credentials, get_default_credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import KasaException
from kasa.httpclient import HttpClient
from kasa.json import dumps as json_dumps
from kasa.transports.linkietransport import LinkieTransportV2

KASACAM_REQUEST_PLAINTEXT = '{"smartlife.cam.ipcamera.dateTime":{"get_status":{}}}'
KASACAM_RESPONSE_ENCRYPTED = "0PKG74LnnfKc+dvhw5bCgaycqZOjk7Gdv96syaiKsJLTvtupwKPC7aPGse632KrB48/tiPiX9JzDsNW2lK6fqZCgmKuZoZGh3A=="
KASACAM_RESPONSE_ERROR = '{"smartlife.cam.ipcamera.cloud": {"get_inf": {"err_code": -10008, "err_msg": "Unsupported API call."}}}'
KASA_DEFAULT_CREDENTIALS_HASH = "YWRtaW46MjEyMzJmMjk3YTU3YTVhNzQzODk0YTBlNGE4MDFmYzM="


async def test_working(mocker):
    """No errors with an expected request/response."""
    host = "127.0.0.1"
    mock_linkie_device = MockLinkieDevice(host)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_linkie_device.post
    )
    transport_no_creds = LinkieTransportV2(config=DeviceConfig(host))

    response = await transport_no_creds.send(KASACAM_REQUEST_PLAINTEXT)
    assert response == {
        "timezone": "UTC-05:00",
        "area": "America/New_York",
        "epoch_sec": 1690832800,
    }


async def test_credentials_hash(mocker):
    """Ensure the default credentials are always passed as Basic Auth."""
    # Test without credentials input

    host = "127.0.0.1"
    mock_linkie_device = MockLinkieDevice(host)
    mock_post = mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_linkie_device.post
    )
    transport_no_creds = LinkieTransportV2(config=DeviceConfig(host))
    await transport_no_creds.send(KASACAM_REQUEST_PLAINTEXT)
    mock_post.assert_called_once_with(
        URL(f"https://{host}:10443/data/LINKIE2.json"),
        params=None,
        data=ANY,
        json=None,
        timeout=ANY,
        cookies=None,
        headers={
            "Authorization": "Basic " + _generate_kascam_basic_auth(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        ssl=ANY,
    )

    assert transport_no_creds.credentials_hash == KASA_DEFAULT_CREDENTIALS_HASH
    # Test with credentials input

    transport_with_creds = LinkieTransportV2(
        config=DeviceConfig(host, credentials=Credentials("Admin", "password"))
    )
    mock_post.reset_mock()

    await transport_with_creds.send(KASACAM_REQUEST_PLAINTEXT)
    mock_post.assert_called_once_with(
        URL(f"https://{host}:10443/data/LINKIE2.json"),
        params=None,
        data=ANY,
        json=None,
        timeout=ANY,
        cookies=None,
        headers={
            "Authorization": "Basic " + _generate_kascam_basic_auth(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        ssl=ANY,
    )


@pytest.mark.parametrize(
    ("return_status", "return_data", "expected"),
    [
        (500, KASACAM_RESPONSE_ENCRYPTED, "500"),
        (200, "AAAAAAAAAAAAAAAAAAAAAAAA", "Unable to read response"),
        (200, KASACAM_RESPONSE_ERROR, "Unsupported API call"),
    ],
)
async def test_exceptions(mocker, return_status, return_data, expected):
    """Test a variety of possible responses from the device."""
    host = "127.0.0.1"
    transport = LinkieTransportV2(config=DeviceConfig(host))
    mock_linkie_device = MockLinkieDevice(
        host, status_code=return_status, response=return_data
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_linkie_device.post
    )

    with pytest.raises(KasaException, match=expected):
        await transport.send(KASACAM_REQUEST_PLAINTEXT)


def _generate_kascam_basic_auth():
    creds = get_default_credentials(DEFAULT_CREDENTIALS["KASACAMERA"])
    creds_combined = f"{creds.username}:{creds.password}"
    return base64.b64encode(creds_combined.encode()).decode()


class MockLinkieDevice:
    """Based on MockSslDevice."""

    class _mock_response:
        def __init__(self, status, request: dict):
            self.status = status
            self._json = request

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_t, exc_v, exc_tb):
            pass

        async def read(self):
            if isinstance(self._json, dict):
                return json_dumps(self._json).encode()
            return self._json

    def __init__(self, host, *, status_code=200, response=KASACAM_RESPONSE_ENCRYPTED):
        self.host = host
        self.http_client = HttpClient(DeviceConfig(self.host))
        self.status_code = status_code
        self.response = response

    async def post(
        self, url: URL, *, headers=None, params=None, json=None, data=None, **__
    ):
        return self._mock_response(self.status_code, self.response)
