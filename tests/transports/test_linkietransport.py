import base64

import pytest

from kasa.credentials import DEFAULT_CREDENTIALS, Credentials, get_default_credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import KasaException
from kasa.transports.linkietransport import LinkieTransportV2

KASACAM_REQUEST_PLAINTEXT = '{"smartlife.cam.ipcamera.dateTime":{"get_status":{}}}'
KASACAM_RESPONSE_ENCRYPTED = "0PKG74LnnfKc+dvhw5bCgaycqZOjk7Gdv96syaiKsJLTvtupwKPC7aPGse632KrB48/tiPiX9JzDsNW2lK6fqZCgmKuZoZGh3A=="
KASACAM_RESPONSE_ERROR = '{"smartlife.cam.ipcamera.cloud": {"get_inf": {"err_code": -10008, "err_msg": "Unsupported API call."}}}'


async def test_working(mocker):
    transport_no_creds = LinkieTransportV2(config=DeviceConfig("127.0.0.1"))
    mocker.patch.object(
        transport_no_creds._http_client,
        "post",
        side_effect=post_custom_return(200, KASACAM_RESPONSE_ENCRYPTED),
    )
    # Expected response
    # '{"timezone": "UTC-05:00", "area": "America/New_York", "epoch_sec": 1690832800}'
    response = await transport_no_creds.send(KASACAM_REQUEST_PLAINTEXT)
    assert response["epoch_sec"] == 1690832800


async def test_credentials_hash(mocker):
    # Test without credentials input
    out_headers_no_creds = {}
    transport_no_creds = LinkieTransportV2(config=DeviceConfig("127.0.0.1"))
    mocker.patch.object(
        transport_no_creds._http_client,
        "post",
        side_effect=create_post_get_auth_header(out_headers_no_creds),
    )
    await transport_no_creds.send(KASACAM_REQUEST_PLAINTEXT)
    assert (
        out_headers_no_creds["Authorization"]
        == f"Basic {_generate_kascam_basic_auth()}"
    )

    # Test with credentials input
    out_headers_with_creds = {}
    transport_with_creds = LinkieTransportV2(
        config=DeviceConfig("127.0.0.1", credentials=Credentials("Admin", "password"))
    )
    mocker.patch.object(
        transport_with_creds._http_client,
        "post",
        side_effect=create_post_get_auth_header(out_headers_with_creds),
    )
    await transport_with_creds.send(KASACAM_REQUEST_PLAINTEXT)
    assert (
        out_headers_with_creds["Authorization"]
        == f"Basic {_generate_kascam_basic_auth()}"
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
    transport = LinkieTransportV2(config=DeviceConfig("127.0.0.1"))
    mocker.patch.object(
        transport._http_client,
        "post",
        side_effect=post_custom_return(return_status, return_data),
    )
    with pytest.raises(KasaException) as ex:
        await transport.send(KASACAM_REQUEST_PLAINTEXT)
    # Unpack original error from Retryable
    assert expected in str(ex.value.__context__)


def _generate_kascam_basic_auth():
    creds = get_default_credentials(DEFAULT_CREDENTIALS["KASACAMERA"])
    creds_combined = f"{creds.username}:{creds.password}"
    return base64.b64encode(creds_combined.encode()).decode()


def create_post_get_auth_header(out_headers: dict):
    """Place the Authorization header inside `out_headers`.

    Then, return a method that can be used to override Httpclient.post.
    """

    async def post_get_auth_header(*_, headers, **__):
        out_headers["Authorization"] = headers.get("Authorization")
        return (200, KASACAM_RESPONSE_ENCRYPTED)

    return post_get_auth_header


def post_custom_return(ret_code: int, ret_data: bytes):
    async def _post(*_, **__):
        return (ret_code, ret_data)

    return _post
