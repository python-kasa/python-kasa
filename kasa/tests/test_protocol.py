import asyncio
import errno
import importlib
import inspect
import json
import logging
import pkgutil
import struct
import sys

import pytest

from ..aestransport import AesTransport
from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import SmartDeviceException
from ..klaptransport import KlapTransport, KlapTransportV2
from ..protocol import (
    BaseTransport,
    TPLinkProtocol,
    TPLinkSmartHomeProtocol,
    _XorTransport,
)


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
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(SmartDeviceException):
        await TPLinkSmartHomeProtocol(transport=_XorTransport(config=config)).query(
            {}, retry_count=retry_count
        )

    assert conn.call_count == retry_count + 1


async def test_protocol_no_retry_on_unreachable(mocker):
    conn = mocker.patch(
        "asyncio.open_connection",
        side_effect=OSError(errno.EHOSTUNREACH, "No route to host"),
    )
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(SmartDeviceException):
        await TPLinkSmartHomeProtocol(transport=_XorTransport(config=config)).query(
            {}, retry_count=5
        )

    assert conn.call_count == 1


async def test_protocol_no_retry_connection_refused(mocker):
    conn = mocker.patch(
        "asyncio.open_connection",
        side_effect=ConnectionRefusedError,
    )
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(SmartDeviceException):
        await TPLinkSmartHomeProtocol(transport=_XorTransport(config=config)).query(
            {}, retry_count=5
        )

    assert conn.call_count == 1


async def test_protocol_retry_recoverable_error(mocker):
    conn = mocker.patch(
        "asyncio.open_connection",
        side_effect=OSError(errno.ECONNRESET, "Connection reset by peer"),
    )
    config = DeviceConfig("127.0.0.1")
    with pytest.raises(SmartDeviceException):
        await TPLinkSmartHomeProtocol(transport=_XorTransport(config=config)).query(
            {}, retry_count=5
        )

    assert conn.call_count == 6


@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_reconnect(mocker, retry_count):
    remaining = retry_count
    encrypted = TPLinkSmartHomeProtocol.encrypt('{"great":"success"}')[
        TPLinkSmartHomeProtocol.BLOCK_SIZE :
    ]

    def _fail_one_less_than_retry_count(*_):
        nonlocal remaining
        remaining -= 1
        if remaining:
            raise Exception("Simulated write failure")

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == TPLinkSmartHomeProtocol.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted

        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        mocker.patch.object(writer, "write", _fail_one_less_than_retry_count)
        mocker.patch.object(reader, "readexactly", _mock_read)
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = TPLinkSmartHomeProtocol(transport=_XorTransport(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    response = await protocol.query({}, retry_count=retry_count)
    assert response == {"great": "success"}


async def test_protocol_handles_cancellation_during_write(mocker):
    attempts = 0
    encrypted = TPLinkSmartHomeProtocol.encrypt('{"great":"success"}')[
        TPLinkSmartHomeProtocol.BLOCK_SIZE :
    ]

    def _cancel_first_attempt(*_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.CancelledError("Simulated task cancel")

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == TPLinkSmartHomeProtocol.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted

        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        mocker.patch.object(writer, "write", _cancel_first_attempt)
        mocker.patch.object(reader, "readexactly", _mock_read)
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = TPLinkSmartHomeProtocol(transport=_XorTransport(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    with pytest.raises(asyncio.CancelledError):
        await protocol.query({})
    assert protocol.writer is None
    response = await protocol.query({})
    assert response == {"great": "success"}


async def test_protocol_handles_cancellation_during_connection(mocker):
    attempts = 0
    encrypted = TPLinkSmartHomeProtocol.encrypt('{"great":"success"}')[
        TPLinkSmartHomeProtocol.BLOCK_SIZE :
    ]

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == TPLinkSmartHomeProtocol.BLOCK_SIZE:
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
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = TPLinkSmartHomeProtocol(transport=_XorTransport(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    with pytest.raises(asyncio.CancelledError):
        await protocol.query({})
    assert protocol.writer is None
    response = await protocol.query({})
    assert response == {"great": "success"}


@pytest.mark.parametrize("log_level", [logging.WARNING, logging.DEBUG])
async def test_protocol_logging(mocker, caplog, log_level):
    caplog.set_level(log_level)
    logging.getLogger("kasa").setLevel(log_level)
    encrypted = TPLinkSmartHomeProtocol.encrypt('{"great":"success"}')[
        TPLinkSmartHomeProtocol.BLOCK_SIZE :
    ]

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == TPLinkSmartHomeProtocol.BLOCK_SIZE:
            return struct.pack(">I", len(encrypted))
        if byte_count == len(encrypted):
            return encrypted
        raise ValueError(f"No mock for {byte_count}")

    def aio_mock_writer(_, __):
        reader = mocker.patch("asyncio.StreamReader")
        writer = mocker.patch("asyncio.StreamWriter")
        mocker.patch.object(reader, "readexactly", _mock_read)
        return reader, writer

    config = DeviceConfig("127.0.0.1")
    protocol = TPLinkSmartHomeProtocol(transport=_XorTransport(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    response = await protocol.query({})
    assert response == {"great": "success"}
    if log_level == logging.DEBUG:
        assert "success" in caplog.text
    else:
        assert "success" not in caplog.text


@pytest.mark.parametrize("custom_port", [123, None])
async def test_protocol_custom_port(mocker, custom_port):
    encrypted = TPLinkSmartHomeProtocol.encrypt('{"great":"success"}')[
        TPLinkSmartHomeProtocol.BLOCK_SIZE :
    ]

    async def _mock_read(byte_count):
        nonlocal encrypted
        if byte_count == TPLinkSmartHomeProtocol.BLOCK_SIZE:
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
        return reader, writer

    config = DeviceConfig("127.0.0.1", port_override=custom_port)
    protocol = TPLinkSmartHomeProtocol(transport=_XorTransport(config=config))
    mocker.patch("asyncio.open_connection", side_effect=aio_mock_writer)
    response = await protocol.query({})
    assert response == {"great": "success"}


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


def _get_subclasses(of_class):
    import kasa

    package = sys.modules["kasa"]
    subclasses = set()
    for _, modname, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module("." + modname, package="kasa")
        module = sys.modules["kasa." + modname]
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, of_class):
                subclasses.add((name, obj))
    return subclasses


@pytest.mark.parametrize(
    "class_name_obj", _get_subclasses(TPLinkProtocol), ids=lambda t: t[0]
)
def test_protocol_init_signature(class_name_obj):
    params = list(inspect.signature(class_name_obj[1].__init__).parameters.values())

    assert len(params) == 2
    assert (
        params[0].name == "self"
        and params[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert (
        params[1].name == "transport"
        and params[1].kind == inspect.Parameter.KEYWORD_ONLY
    )


@pytest.mark.parametrize(
    "class_name_obj", _get_subclasses(BaseTransport), ids=lambda t: t[0]
)
def test_transport_init_signature(class_name_obj):
    params = list(inspect.signature(class_name_obj[1].__init__).parameters.values())

    assert len(params) == 2
    assert (
        params[0].name == "self"
        and params[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert (
        params[1].name == "config" and params[1].kind == inspect.Parameter.KEYWORD_ONLY
    )


@pytest.mark.parametrize(
    "transport_class", [AesTransport, KlapTransport, KlapTransportV2, _XorTransport]
)
async def test_transport_credentials_hash(mocker, transport_class):
    host = "127.0.0.1"

    credentials = Credentials("Foo", "Bar")
    config = DeviceConfig(host, credentials=credentials)
    transport = transport_class(config=config)
    credentials_hash = transport.credentials_hash
    config = DeviceConfig(host, credentials_hash=credentials_hash)
    transport = transport_class(config=config)

    assert transport.credentials_hash == credentials_hash
