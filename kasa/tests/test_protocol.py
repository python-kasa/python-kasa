import asyncio
import errno
import importlib
import inspect
import json
import logging
import os
import pkgutil
import struct
import sys
from typing import cast
from unittest.mock import AsyncMock

import pytest

from kasa.iot import IotDevice

from ..aestransport import AesTransport
from ..credentials import Credentials
from ..device import Device
from ..deviceconfig import DeviceConfig
from ..exceptions import KasaException
from ..iotprotocol import IotProtocol, _deprecated_TPLinkSmartHomeProtocol
from ..klaptransport import KlapTransport, KlapTransportV2
from ..protocol import (
    BaseProtocol,
    BaseTransport,
    mask_mac,
    redact_data,
)
from ..xortransport import XorEncryption, XorTransport
from .conftest import device_iot
from .fakeprotocol_iot import FakeIotTransport


@pytest.mark.parametrize(
    ("protocol_class", "transport_class"),
    [
        (_deprecated_TPLinkSmartHomeProtocol, XorTransport),
        (IotProtocol, XorTransport),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries(mocker, retry_count, protocol_class, transport_class):
    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")

        mocker.patch(
            "asyncio.StreamWriter.write", side_effect=Exception("dummy exception")
        )

        return reader, writer

    conn = mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            {}, retry_count=retry_count
        )

    assert conn.call_count == retry_count + 1


@pytest.mark.parametrize(
    ("protocol_class", "transport_class"),
    [
        (_deprecated_TPLinkSmartHomeProtocol, XorTransport),
        (IotProtocol, XorTransport),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
async def test_protocol_no_retry_on_unreachable(
    mocker, protocol_class, transport_class
):
    conn = mocker.patch(
        "asyncio.open_connection",
        side_effect=OSError(errno.EHOSTUNREACH, "No route to host"),
    )
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            {}, retry_count=5
        )

    assert conn.call_count == 1


@pytest.mark.parametrize(
    ("protocol_class", "transport_class"),
    [
        (_deprecated_TPLinkSmartHomeProtocol, XorTransport),
        (IotProtocol, XorTransport),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
async def test_protocol_no_retry_connection_refused(
    mocker, protocol_class, transport_class
):
    conn = mocker.patch(
        "asyncio.open_connection",
        side_effect=ConnectionRefusedError,
    )
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            {}, retry_count=5
        )

    assert conn.call_count == 1


@pytest.mark.parametrize(
    ("protocol_class", "transport_class"),
    [
        (_deprecated_TPLinkSmartHomeProtocol, XorTransport),
        (IotProtocol, XorTransport),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
async def test_protocol_retry_recoverable_error(
    mocker, protocol_class, transport_class
):
    conn = mocker.patch(
        "asyncio.open_connection",
        side_effect=OSError(errno.ECONNRESET, "Connection reset by peer"),
    )
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            {}, retry_count=5
        )

    assert conn.call_count == 6


@pytest.mark.parametrize(
    ("protocol_class", "transport_class", "encryption_class"),
    [
        (
            _deprecated_TPLinkSmartHomeProtocol,
            XorTransport,
            _deprecated_TPLinkSmartHomeProtocol,
        ),
        (IotProtocol, XorTransport, XorEncryption),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_reconnect(
    mocker, retry_count, protocol_class, transport_class, encryption_class
):
    remaining = retry_count
    encrypted = encryption_class.encrypt('{"great":"success"}')[
        transport_class.BLOCK_SIZE :
    ]

    def _fail_one_less_than_retry_count(*_):
        nonlocal remaining
        remaining -= 1
        if remaining:
            raise Exception("Simulated write failure")

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == transport_class.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted

        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        mocker.patch.object(writer, "write", _fail_one_less_than_retry_count)
        mocker.patch.object(reader, "readexactly", _mock_read)
        mocker.patch.object(writer, "drain", new_callable=AsyncMock)
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = protocol_class(transport=transport_class(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    response = await protocol.query({}, retry_count=retry_count)
    assert response == {"great": "success"}


@pytest.mark.parametrize(
    ("protocol_class", "transport_class", "encryption_class"),
    [
        (
            _deprecated_TPLinkSmartHomeProtocol,
            XorTransport,
            _deprecated_TPLinkSmartHomeProtocol,
        ),
        (IotProtocol, XorTransport, XorEncryption),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
async def test_protocol_handles_cancellation_during_write(
    mocker, protocol_class, transport_class, encryption_class
):
    attempts = 0
    encrypted = encryption_class.encrypt('{"great":"success"}')[
        transport_class.BLOCK_SIZE :
    ]

    def _cancel_first_attempt(*_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.CancelledError("Simulated task cancel")

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == transport_class.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted

        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        mocker.patch.object(writer, "write", _cancel_first_attempt)
        mocker.patch.object(reader, "readexactly", _mock_read)
        mocker.patch.object(writer, "drain", new_callable=AsyncMock)
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = protocol_class(transport=transport_class(config=config))
    conn_mock = mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    with pytest.raises(asyncio.CancelledError):
        await protocol.query({})
    writer_obj = protocol if hasattr(protocol, "writer") else protocol._transport
    assert writer_obj.writer is None
    conn_mock.assert_awaited_once()
    response = await protocol.query({})
    assert response == {"great": "success"}


@pytest.mark.parametrize(
    ("protocol_class", "transport_class", "encryption_class"),
    [
        (
            _deprecated_TPLinkSmartHomeProtocol,
            XorTransport,
            _deprecated_TPLinkSmartHomeProtocol,
        ),
        (IotProtocol, XorTransport, XorEncryption),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
async def test_protocol_handles_cancellation_during_connection(
    mocker, protocol_class, transport_class, encryption_class
):
    attempts = 0
    encrypted = encryption_class.encrypt('{"great":"success"}')[
        transport_class.BLOCK_SIZE :
    ]

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == transport_class.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted

        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, __):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.CancelledError("Simulated task cancel")
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        mocker.patch.object(reader, "readexactly", _mock_read)
        mocker.patch.object(writer, "drain", new_callable=AsyncMock)
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = protocol_class(transport=transport_class(config=config))
    conn_mock = mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    with pytest.raises(asyncio.CancelledError):
        await protocol.query({})

    writer_obj = protocol if hasattr(protocol, "writer") else protocol._transport
    assert writer_obj.writer is None
    conn_mock.assert_awaited_once()
    response = await protocol.query({})
    assert response == {"great": "success"}


@pytest.mark.parametrize(
    ("protocol_class", "transport_class", "encryption_class"),
    [
        (
            _deprecated_TPLinkSmartHomeProtocol,
            XorTransport,
            _deprecated_TPLinkSmartHomeProtocol,
        ),
        (IotProtocol, XorTransport, XorEncryption),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
@pytest.mark.parametrize("log_level", [logging.WARNING, logging.DEBUG])
async def test_protocol_logging(
    mocker, caplog, log_level, protocol_class, transport_class, encryption_class
):
    caplog.set_level(log_level)
    logging.getLogger("kasa").setLevel(log_level)
    encrypted = encryption_class.encrypt('{"great":"success"}')[
        transport_class.BLOCK_SIZE :
    ]

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == transport_class.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted
        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        mocker.patch.object(reader, "readexactly", _mock_read)
        mocker.patch.object(writer, "drain", new_callable=AsyncMock)
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = protocol_class(transport=transport_class(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    response = await protocol.query({})
    assert response == {"great": "success"}
    if log_level == logging.DEBUG:
        assert "success" in caplog.text
    else:
        assert "success" not in caplog.text


@pytest.mark.parametrize(
    ("protocol_class", "transport_class", "encryption_class"),
    [
        (
            _deprecated_TPLinkSmartHomeProtocol,
            XorTransport,
            _deprecated_TPLinkSmartHomeProtocol,
        ),
        (IotProtocol, XorTransport, XorEncryption),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
@pytest.mark.parametrize("custom_port", [123, None])
async def test_protocol_custom_port(
    mocker, custom_port, protocol_class, transport_class, encryption_class
):
    encrypted = encryption_class.encrypt('{"great":"success"}')[
        transport_class.BLOCK_SIZE :
    ]

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == transport_class.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted
        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, port):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        if custom_port is None:
            assert port == 9999
        else:
            assert port == custom_port
        mocker.patch.object(reader, "readexactly", _mock_read)
        mocker.patch.object(writer, "drain", new_callable=AsyncMock)
        return reader, writer

    config = DeviceConfig("127.0.0.1", port_override=custom_port)
    protocol = protocol_class(transport=transport_class(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    response = await protocol.query({})
    assert response == {"great": "success"}


@pytest.mark.parametrize(
    "encrypt_class",
    [_deprecated_TPLinkSmartHomeProtocol, XorEncryption],
)
@pytest.mark.parametrize(
    "decrypt_class",
    [_deprecated_TPLinkSmartHomeProtocol, XorEncryption],
)
def test_encrypt(encrypt_class, decrypt_class):
    d = json.dumps({"foo": 1, "bar": 2})
    encrypted = encrypt_class.encrypt(d)
    # encrypt adds a 4 byte header
    encrypted = encrypted[4:]
    assert d == decrypt_class.decrypt(encrypted)


@pytest.mark.parametrize(
    "encrypt_class",
    [_deprecated_TPLinkSmartHomeProtocol, XorEncryption],
)
def test_encrypt_unicode(encrypt_class):
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

    encrypted = encrypt_class.encrypt(d)
    # encrypt adds a 4 byte header
    encrypted = encrypted[4:]

    assert e == encrypted


@pytest.mark.parametrize(
    "decrypt_class",
    [_deprecated_TPLinkSmartHomeProtocol, XorEncryption],
)
def test_decrypt_unicode(decrypt_class):
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

    assert d == decrypt_class.decrypt(e)


def _get_subclasses(of_class):
    package = sys.modules["kasa"]
    subclasses = set()
    for _, modname, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module("." + modname, package="kasa")
        module = sys.modules["kasa." + modname]
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, of_class)
                and name != "_deprecated_TPLinkSmartHomeProtocol"
            ):
                subclasses.add((name, obj))
    return sorted(subclasses)


@pytest.mark.parametrize(
    "class_name_obj", _get_subclasses(BaseProtocol), ids=lambda t: t[0]
)
def test_protocol_init_signature(class_name_obj):
    if class_name_obj[0].startswith("_"):
        pytest.skip("Skipping internal protocols")
        return
    params = list(inspect.signature(class_name_obj[1].__init__).parameters.values())

    assert len(params) == 2
    assert params[0].name == "self"
    assert params[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[1].name == "transport"
    assert params[1].kind == inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize(
    "class_name_obj", _get_subclasses(BaseTransport), ids=lambda t: t[0]
)
def test_transport_init_signature(class_name_obj):
    params = list(inspect.signature(class_name_obj[1].__init__).parameters.values())

    assert len(params) == 2
    assert params[0].name == "self"
    assert params[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[1].name == "config"
    assert params[1].kind == inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize(
    ("transport_class", "login_version", "expected_hash"),
    [
        pytest.param(
            AesTransport,
            1,
            "eyJwYXNzd29yZCI6IlFtRnkiLCJ1c2VybmFtZSI6Ik1qQXhZVFppTXpBMU0yTmpNVFF5TW1ReVl6TTJOekJpTmpJMk1UWXlNakZrTWpJNU1Ea3lPUT09In0=",
            id="aes-lv-1",
        ),
        pytest.param(
            AesTransport,
            2,
            "eyJwYXNzd29yZDIiOiJaVFE1Tm1aa01qQXhNelprTkdKaU56Z3lPR1ZpWWpCaFlqa3lOV0l4WW1RNU56Y3lNRGhsTkE9PSIsInVzZXJuYW1lIjoiTWpBeFlUWmlNekExTTJOak1UUXlNbVF5WXpNMk56QmlOakkyTVRZeU1qRmtNakk1TURreU9RPT0ifQ==",
            id="aes-lv-2",
        ),
        pytest.param(KlapTransport, 1, "xBhMRGYWStVCVk9aSD8/6Q==", id="klap-lv-1"),
        pytest.param(KlapTransport, 2, "xBhMRGYWStVCVk9aSD8/6Q==", id="klap-lv-2"),
        pytest.param(
            KlapTransportV2,
            1,
            "tEmiensOcZkP9twDEZKwU3JJl3asmseKCP7N9sfatVo=",
            id="klapv2-lv-1",
        ),
        pytest.param(
            KlapTransportV2,
            2,
            "tEmiensOcZkP9twDEZKwU3JJl3asmseKCP7N9sfatVo=",
            id="klapv2-lv-2",
        ),
        pytest.param(XorTransport, None, None, id="xor"),
    ],
)
@pytest.mark.parametrize(
    ("credentials", "expected_blank"),
    [
        pytest.param(Credentials("Foo", "Bar"), False, id="credentials"),
        pytest.param(None, True, id="no-credentials"),
        pytest.param(Credentials(None, "Bar"), True, id="no-username"),  # type: ignore[arg-type]
    ],
)
async def test_transport_credentials_hash(
    mocker, transport_class, login_version, expected_hash, credentials, expected_blank
):
    """Test that the actual hashing doesn't break and empty credential returns an empty hash."""
    host = "127.0.0.1"

    params = Device.ConnectionParameters(
        device_family=Device.Family.SmartTapoPlug,
        encryption_type=Device.EncryptionType.Xor,
        login_version=login_version,
    )
    config = DeviceConfig(host, credentials=credentials, connection_type=params)
    transport = transport_class(config=config)

    credentials_hash = transport.credentials_hash

    expected = None if expected_blank else expected_hash
    assert credentials_hash == expected


@pytest.mark.parametrize(
    "transport_class",
    [AesTransport, KlapTransport, KlapTransportV2, XorTransport],
)
async def test_transport_credentials_hash_from_config(mocker, transport_class):
    """Test that credentials_hash provided via config sets correctly."""
    host = "127.0.0.1"

    credentials = Credentials("Foo", "Bar")
    config = DeviceConfig(host, credentials=credentials)
    transport = transport_class(config=config)
    credentials_hash = transport.credentials_hash
    config = DeviceConfig(host, credentials_hash=credentials_hash)
    transport = transport_class(config=config)

    assert transport.credentials_hash == credentials_hash


@pytest.mark.parametrize(
    ("error", "retry_expectation"),
    [
        (ConnectionRefusedError("dummy exception"), False),
        (OSError(errno.EHOSTDOWN, os.strerror(errno.EHOSTDOWN)), False),
        (OSError(errno.ECONNRESET, os.strerror(errno.ECONNRESET)), True),
        (Exception("dummy exception"), True),
    ],
    ids=("ConnectionRefusedError", "OSErrorNoRetry", "OSErrorRetry", "Exception"),
)
@pytest.mark.parametrize(
    ("protocol_class", "transport_class"),
    [
        (_deprecated_TPLinkSmartHomeProtocol, XorTransport),
        (IotProtocol, XorTransport),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
async def test_protocol_will_retry_on_connect(
    mocker, protocol_class, transport_class, error, retry_expectation
):
    retry_count = 2
    conn = mocker.patch("asyncio.open_connection", side_effect=error)
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            {}, retry_count=retry_count
        )

    assert conn.call_count == (retry_count + 1 if retry_expectation else 1)


@pytest.mark.parametrize(
    ("error", "retry_expectation"),
    [
        (ConnectionRefusedError("dummy exception"), True),
        (OSError(errno.EHOSTDOWN, os.strerror(errno.EHOSTDOWN)), True),
        (OSError(errno.ECONNRESET, os.strerror(errno.ECONNRESET)), True),
        (Exception("dummy exception"), True),
    ],
    ids=("ConnectionRefusedError", "OSErrorNoRetry", "OSErrorRetry", "Exception"),
)
@pytest.mark.parametrize(
    ("protocol_class", "transport_class"),
    [
        (_deprecated_TPLinkSmartHomeProtocol, XorTransport),
        (IotProtocol, XorTransport),
    ],
    ids=("_deprecated_TPLinkSmartHomeProtocol", "IotProtocol-XorTransport"),
)
async def test_protocol_will_retry_on_write(
    mocker, protocol_class, transport_class, error, retry_expectation
):
    retry_count = 2
    writer = mocker.patch("asyncio.StreamWriter")
    write_mock = mocker.patch.object(writer, "write", side_effect=error)

    def aio_mock_writer(_, __):
        nonlocal writer
        reader = mocker.patch("asyncio.StreamReader")

        return reader, writer

    conn = mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    write_mock = mocker.patch("asyncio.StreamWriter.write", side_effect=error)
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            {}, retry_count=retry_count
        )

    expected_call_count = retry_count + 1 if retry_expectation else 1
    assert conn.call_count == expected_call_count
    assert write_mock.call_count == expected_call_count


def test_deprecated_protocol():
    with pytest.deprecated_call():
        from kasa import TPLinkSmartHomeProtocol

        with pytest.raises(KasaException, match="host or transport must be supplied"):
            proto = TPLinkSmartHomeProtocol()
        host = "127.0.0.1"
        proto = TPLinkSmartHomeProtocol(host=host)
        assert proto.config.host == host


@device_iot
async def test_iot_queries_redaction(dev: IotDevice, caplog: pytest.LogCaptureFixture):
    """Test query sensitive info redaction."""
    device_id = "123456789ABCDEF"
    cast(FakeIotTransport, dev.protocol._transport).proto["system"]["get_sysinfo"][
        "deviceId"
    ] = device_id

    # Info no message logging
    caplog.set_level(logging.INFO)
    await dev.update()
    assert device_id not in caplog.text

    caplog.set_level(logging.DEBUG, logger="kasa")
    # The fake iot protocol also logs so disable it
    test_logger = logging.getLogger("kasa.tests.fakeprotocol_iot")
    test_logger.setLevel(logging.INFO)

    # Debug no redaction
    caplog.clear()
    cast(IotProtocol, dev.protocol)._redact_data = False
    await dev.update()
    assert device_id in caplog.text

    # Debug redaction
    caplog.clear()
    cast(IotProtocol, dev.protocol)._redact_data = True
    await dev.update()
    assert device_id not in caplog.text
    assert "REDACTED_" + device_id[9::] in caplog.text


async def test_redact_data():
    """Test redact data function."""
    data = {
        "device_id": "123456789ABCDEF",
        "owner": "0987654",
        "mac": "12:34:56:78:90:AB",
        "ip": "192.168.1",
        "no_val": None,
    }
    excpected_data = {
        "device_id": "REDACTED_ABCDEF",
        "owner": "**REDACTED**",
        "mac": "12:34:56:00:00:00",
        "ip": "**REDACTEX**",
        "no_val": None,
    }
    REDACTORS = {
        "device_id": lambda x: "REDACTED_" + x[9::],
        "owner": None,
        "mac": mask_mac,
        "ip": lambda x: "127.0.0." + x.split(".")[3],
    }

    redacted_data = redact_data(data, REDACTORS)

    assert redacted_data == excpected_data
