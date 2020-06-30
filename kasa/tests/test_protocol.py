import json

import pytest

from ..exceptions import SmartDeviceException
from ..protocol import TPLinkSmartHomeProtocol
from .conftest import pytestmark


@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries(mocker, retry_count):
    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")

        mocker.patch(
            "asyncio.StreamWriter.write", side_effect=Exception("dummy exception")
        )

        return reader, writer

    conn = mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    with pytest.raises(SmartDeviceException):
        await TPLinkSmartHomeProtocol.query("127.0.0.1", {}, retry_count=retry_count)

    assert conn.call_count == retry_count + 1


def test_encrypt():
    d = json.dumps({"foo": 1, "bar": 2})
    encrypted = TPLinkSmartHomeProtocol.encrypt(d)
    # encrypt adds a 4 byte header
    encrypted = encrypted[4:]
    assert d == TPLinkSmartHomeProtocol.decrypt(encrypted)


def test_encrypt_unicode():
    d = "{'snowman': '\u2603'}"

    e = bytes(
        [
            208,
            247,
            132,
            234,
            133,
            242,
            159,
            254,
            144,
            183,
            141,
            173,
            138,
            104,
            240,
            115,
            84,
            41,
        ]
    )

    encrypted = TPLinkSmartHomeProtocol.encrypt(d)
    # encrypt adds a 4 byte header
    encrypted = encrypted[4:]

    assert e == encrypted


def test_decrypt_unicode():
    e = bytes(
        [
            208,
            247,
            132,
            234,
            133,
            242,
            159,
            254,
            144,
            183,
            141,
            173,
            138,
            104,
            240,
            115,
            84,
            41,
        ]
    )

    d = "{'snowman': '\u2603'}"

    assert d == TPLinkSmartHomeProtocol.decrypt(e)
