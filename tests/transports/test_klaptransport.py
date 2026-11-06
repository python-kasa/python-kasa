from __future__ import annotations

import json
import logging
import re
import secrets
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from contextlib import nullcontext as does_not_raise

import aiohttp
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from pytest_mock import MockerFixture
from yarl import URL

from kasa.credentials import DEFAULT_CREDENTIALS, Credentials, get_default_credentials
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.exceptions import (
    AuthenticationError,
    KasaException,
    TimeoutError,
    _ConnectionError,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.iot import IotBulb, IotDevice, IotPlug, IotWallSwitch
from kasa.protocols import IotProtocol, SmartProtocol
from kasa.transports.aestransport import AesTransport
from kasa.transports.klaptransport import (
    PACK_SIGNED_LONG,
    KlapEncryptionSession,
    KlapTransport,
    KlapTransportV2,
    _sha256,
)

from ..device_fixtures import device_iot, parametrize

DUMMY_QUERY = {"foobar": {"foo": "bar", "bar": "foo"}}

KLAP_CONNECTION = DeviceConnectionParameters(
    DeviceFamily.IotSmartPlugSwitch, DeviceEncryptionType.Klap, login_version=2
)

ks200m_iot = parametrize("ks200m", model_filter={"KS200M"}, protocol_filter={"IOT"})

# Transport tests are not designed for real devices
pytestmark = [pytest.mark.requires_dummy]


class _mock_response:
    def __init__(self, status, content: bytes):
        self.status = status
        self.content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_t, exc_v, exc_tb):
        pass

    async def read(self):
        return self.content


@pytest.mark.parametrize(
    ("error", "retry_expectation"),
    [
        (Exception("dummy exception"), False),
        (aiohttp.ServerTimeoutError("dummy exception"), True),
        (aiohttp.ServerDisconnectedError("dummy exception"), True),
        (aiohttp.ClientOSError("dummy exception"), True),
    ],
    ids=("Exception", "ServerTimeoutError", "ServerDisconnectedError", "ClientOSError"),
)
@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries_via_client_session(
    mocker: MockerFixture,
    retry_count: int,
    protocol_class: type,
    transport_class: type,
    error: Exception,
    retry_expectation: bool,
) -> None:
    host = "127.0.0.1"
    conn = mocker.patch.object(aiohttp.ClientSession, "post", side_effect=error)

    config = DeviceConfig(host)
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=retry_count
        )

    expected_count = retry_count + 1 if retry_expectation else 1
    assert conn.call_count == expected_count


@pytest.mark.parametrize(
    ("error", "retry_expectation"),
    [
        (KasaException("dummy exception"), False),
        (_RetryableError("dummy exception"), True),
        (TimeoutError("dummy exception"), True),
    ],
    ids=("KasaException", "_RetryableError", "TimeoutError"),
)
@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries_via_httpclient(
    mocker: MockerFixture,
    retry_count: int,
    protocol_class: type,
    transport_class: type,
    error: Exception,
    retry_expectation: bool,
) -> None:
    host = "127.0.0.1"
    conn = mocker.patch.object(HttpClient, "post", side_effect=error)
    mocker.patch.object(protocol_class, "BACKOFF_SECONDS_AFTER_TIMEOUT", 0)

    config = DeviceConfig(host)
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=retry_count
        )

    expected_count = retry_count + 1 if retry_expectation else 1
    assert conn.call_count == expected_count


@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
async def test_protocol_no_retry_on_connection_error(
    mocker: MockerFixture, protocol_class: type, transport_class: type
) -> None:
    host = "127.0.0.1"
    conn = mocker.patch.object(
        aiohttp.ClientSession,
        "post",
        side_effect=AuthenticationError("foo"),
    )
    mocker.patch.object(protocol_class, "BACKOFF_SECONDS_AFTER_TIMEOUT", 0)
    config = DeviceConfig(host)
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=5
        )

    assert conn.call_count == 1


@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
async def test_protocol_retry_recoverable_error(
    mocker: MockerFixture, protocol_class: type, transport_class: type
) -> None:
    host = "127.0.0.1"
    conn = mocker.patch.object(
        aiohttp.ClientSession,
        "post",
        side_effect=aiohttp.ClientOSError("foo"),
    )

    config = DeviceConfig(host)
    with pytest.raises(KasaException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=5
        )

    assert conn.call_count == 6


@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_reconnect(
    mocker: MockerFixture, retry_count: int, protocol_class: type, transport_class: type
) -> None:
    host = "127.0.0.1"
    remaining = retry_count
    mock_response = {"result": {"great": "success"}, "error_code": 0}

    def _fail_one_less_than_retry_count(*_, **__):
        nonlocal remaining
        remaining -= 1
        if remaining:
            raise _ConnectionError("Simulated connection failure")

        return mock_response

    mocker.patch.object(transport_class, "perform_handshake")
    if hasattr(transport_class, "perform_login"):
        mocker.patch.object(transport_class, "perform_login")

    send_mock = mocker.patch.object(
        transport_class,
        "send",
        side_effect=_fail_one_less_than_retry_count,
    )

    config = DeviceConfig(host)
    response = await protocol_class(transport=transport_class(config=config)).query(
        DUMMY_QUERY, retry_count=retry_count
    )
    assert "result" in response or "foobar" in response
    assert send_mock.call_count == retry_count


@pytest.mark.parametrize("log_level", [logging.WARNING, logging.DEBUG])
@pytest.mark.xdist_group(name="caplog")
async def test_protocol_logging(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture, log_level: int
) -> None:
    caplog.set_level(log_level)
    caplog.set_level(log_level, logger="kasa")

    def _return_encrypted(*_, **__):
        # Devices sign the response for the sequence number of the request
        encryption_session._seq -= 1
        encrypted, seq = encryption_session.encrypt('{"great":"success"}')
        return 200, encrypted

    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    config = DeviceConfig("127.0.0.1")
    transport = KlapTransport(config=config)
    protocol = IotProtocol(transport=transport)

    transport._handshake_done = True
    transport._session_expire_at = time.time() + 86400
    transport._encryption_session = encryption_session
    mocker.patch.object(HttpClient, "post", side_effect=_return_encrypted)

    response = await protocol.query({})
    assert response == {"great": "success"}
    if log_level == logging.DEBUG:
        assert "success" in caplog.text
    else:
        assert "success" not in caplog.text


def test_encrypt() -> None:
    d = json.dumps({"foo": 1, "bar": 2})

    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    encrypted, seq = encryption_session.encrypt(d)

    assert d == encryption_session.decrypt(encrypted)


def test_encrypt_unicode() -> None:
    d = "{'snowman': '\u2603'}"

    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    encrypted, seq = encryption_session.encrypt(d)

    decrypted = encryption_session.decrypt(encrypted)

    assert d == decrypted


async def test_transport_decrypt(mocker: MockerFixture) -> None:
    """Test transport decryption."""
    d = {"great": "success"}

    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    transport = KlapTransport(config=DeviceConfig(host="127.0.0.1"))
    transport._handshake_done = True
    transport._session_expire_at = time.monotonic() + 60
    transport._encryption_session = encryption_session

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        assert transport._encryption_session is not None
        encryption_session = KlapEncryptionSession(
            transport._encryption_session.local_seed,
            transport._encryption_session.remote_seed,
            transport._encryption_session.user_hash,
        )
        seq = params.get("seq")
        encryption_session._seq = seq - 1
        encrypted, seq = encryption_session.encrypt(json.dumps(d))
        seq = seq
        return 200, encrypted

    mocker.patch.object(HttpClient, "post", side_effect=_return_response)

    resp = await transport.send(json.dumps({}))
    assert d == resp


def _logged_in_transport() -> KlapTransport:
    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))

    transport = KlapTransport(config=DeviceConfig(host="127.0.0.1"))
    transport._handshake_done = True
    transport._session_expire_at = time.monotonic() + 60
    transport._encryption_session = KlapEncryptionSession(seed, seed, auth_hash)
    return transport


@pytest.mark.parametrize("mismatch", ["key", "seq"])
async def test_transport_signature_error(mocker: MockerFixture, mismatch: str) -> None:
    """Test that a response not signed for the request raises a kasa exception."""
    transport = _logged_in_transport()

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        assert transport._encryption_session is not None
        encryption_session = KlapEncryptionSession(
            secrets.token_bytes(16)
            if mismatch == "key"
            else transport._encryption_session.local_seed,
            transport._encryption_session.remote_seed,
            transport._encryption_session.user_hash,
        )
        seq = params.get("seq")
        encryption_session._seq = seq - 1 if mismatch == "key" else seq
        encrypted, _seq = encryption_session.encrypt(json.dumps({"great": "success"}))
        return 200, encrypted

    mocker.patch.object(HttpClient, "post", side_effect=_return_response)

    with pytest.raises(
        KasaException,
        match=re.escape(
            "Device 127.0.0.1 sent a response with an invalid signature "
            "for request with seq"
        ),
    ):
        await transport.send(json.dumps({}))


async def test_transport_decrypt_error(mocker: MockerFixture) -> None:
    """Test that a signed response that fails to decrypt raises a kasa exception."""
    transport = _logged_in_transport()

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        session = transport._encryption_session
        assert session is not None
        seq = PACK_SIGNED_LONG(params.get("seq"))
        # A block that decrypts to zeros, which is not valid PKCS7 padding
        encryptor = Cipher(session._aes, modes.CBC(session._iv + seq)).encryptor()
        ciphertext = encryptor.update(bytes(16)) + encryptor.finalize()
        return 200, _sha256(session._sig + seq + ciphertext) + ciphertext

    mocker.patch.object(HttpClient, "post", side_effect=_return_response)

    with pytest.raises(
        KasaException,
        match=re.escape("Error trying to decrypt device 127.0.0.1 response:"),
    ):
        await transport.send(json.dumps({}))


HTML_PAGE = b"<html><body><center>200 OK</center></body></html>"


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(HTML_PAGE, id="html-page"),
        pytest.param(b"", id="empty"),
        pytest.param(secrets.token_bytes(32), id="signature-only"),
        pytest.param(secrets.token_bytes(32 + 17), id="partial-block"),
    ],
)
async def test_transport_invalid_response(
    mocker: MockerFixture, response: bytes
) -> None:
    """Test that a response that is not a KLAP message raises a kasa exception."""
    transport = _logged_in_transport()
    mocker.patch.object(HttpClient, "post", return_value=(200, response))

    with pytest.raises(
        KasaException,
        match=re.escape(
            "Device 127.0.0.1 sent a response that is not a KLAP message "
            f"({len(response)} bytes): {response[:64]!r}"
        ),
    ):
        await transport.send(json.dumps({}))


@pytest.mark.parametrize("transport_class", [KlapTransport, KlapTransportV2])
async def test_protocol_invalid_response(
    mocker: MockerFixture, transport_class: type[KlapTransport]
) -> None:
    """Test that an invalid response is not retried and resets the session."""
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = transport_class.generate_auth_hash(client_credentials)
    handshakes = 0
    requests = 0

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        nonlocal handshakes, requests

        if url == URL("http://127.0.0.1:80/app/handshake1"):
            handshakes += 1
            seed_auth_hash = _sha256(
                data + server_seed + device_auth_hash
                if transport_class is KlapTransportV2
                else data + device_auth_hash
            )
            return _mock_response(200, server_seed + seed_auth_hash)
        elif url == URL("http://127.0.0.1:80/app/handshake2"):
            return _mock_response(200, b"")
        elif url == URL("http://127.0.0.1:80/app/request"):
            requests += 1
            if requests == 1:
                return _mock_response(200, HTML_PAGE)
            assert transport._encryption_session is not None
            encryption_session = KlapEncryptionSession(
                transport._encryption_session.local_seed,
                transport._encryption_session.remote_seed,
                transport._encryption_session.user_hash,
            )
            encryption_session._seq = params.get("seq") - 1
            encrypted, _seq = encryption_session.encrypt('{"great": "success"}')
            return _mock_response(200, encrypted)

    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=_return_response)

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    transport = transport_class(config=config)
    protocol = IotProtocol(transport=transport)

    with pytest.raises(KasaException, match="is not a KLAP message"):
        await protocol.query(DUMMY_QUERY)
    assert requests == 1
    assert handshakes == 1
    assert transport._handshake_done is False

    assert await protocol.query(DUMMY_QUERY) == {"great": "success"}
    assert requests == 2
    assert handshakes == 2


@pytest.mark.parametrize(
    ("device_credentials", "expectation"),
    [
        (Credentials("foo", "bar"), does_not_raise()),
        (Credentials(), does_not_raise()),
        (
            get_default_credentials(DEFAULT_CREDENTIALS["KASA"]),
            does_not_raise(),
        ),
        (
            Credentials("shouldfail", "shouldfail"),
            pytest.raises(AuthenticationError),
        ),
    ],
    ids=("client", "blank", "kasa_setup", "shouldfail"),
)
@pytest.mark.parametrize(
    ("transport_class", "seed_auth_hash_calc"),
    [
        pytest.param(KlapTransport, lambda c, s, a: c + a, id="KLAP"),
        pytest.param(KlapTransportV2, lambda c, s, a: c + s + a, id="KLAPV2"),
    ],
)
async def test_handshake1(
    mocker: MockerFixture,
    device_credentials: Credentials,
    expectation: AbstractContextManager,
    transport_class: type[KlapTransport],
    seed_auth_hash_calc: Callable[..., bytes],
) -> None:
    client_seed = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = transport_class.generate_auth_hash(device_credentials)

    async def _return_handshake1_response(url, params=None, data=None, *_, **__):
        nonlocal client_seed

        client_seed = data
        seed_auth_hash = _sha256(
            seed_auth_hash_calc(client_seed, server_seed, device_auth_hash)
        )
        return _mock_response(200, server_seed + seed_auth_hash)

    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=_return_handshake1_response
    )

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    transport = transport_class(config=config)
    protocol = IotProtocol(transport=transport)

    with expectation:
        (
            local_seed,
            device_remote_seed,
            auth_hash,
        ) = await transport.perform_handshake1()

        assert local_seed == client_seed
        assert device_remote_seed == server_seed
        assert device_auth_hash == auth_hash
    await protocol.close()


@pytest.mark.parametrize(
    ("transport_class", "seed_auth_hash_calc1", "seed_auth_hash_calc2"),
    [
        pytest.param(
            KlapTransport, lambda c, s, a: c + a, lambda c, s, a: s + a, id="KLAP"
        ),
        pytest.param(
            KlapTransportV2,
            lambda c, s, a: c + s + a,
            lambda c, s, a: s + c + a,
            id="KLAPV2",
        ),
    ],
)
async def test_handshake(
    mocker: MockerFixture,
    transport_class: type[KlapTransport],
    seed_auth_hash_calc1: Callable[..., bytes],
    seed_auth_hash_calc2: Callable[..., bytes],
) -> None:
    client_seed = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = transport_class.generate_auth_hash(client_credentials)

    async def _return_handshake_response(url: URL, params=None, data=None, *_, **__):
        nonlocal client_seed

        if url == URL("http://127.0.0.1:80/app/handshake1"):
            client_seed = data
            seed_auth_hash = _sha256(
                seed_auth_hash_calc1(client_seed, server_seed, device_auth_hash)
            )

            return _mock_response(200, server_seed + seed_auth_hash)
        elif url == URL("http://127.0.0.1:80/app/handshake2"):
            seed_auth_hash = _sha256(
                seed_auth_hash_calc2(client_seed, server_seed, device_auth_hash)
            )
            assert data == seed_auth_hash
            return _mock_response(response_status, b"")

    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=_return_handshake_response
    )

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    transport = transport_class(config=config)
    protocol = IotProtocol(transport=transport)

    response_status = 200
    await transport.perform_handshake()
    assert transport._handshake_done is True

    response_status = 403
    with pytest.raises(KasaException):
        await transport.perform_handshake()
    assert transport._handshake_done is False
    await protocol.close()


@pytest.mark.xdist_group(name="caplog")
async def test_handshake_debug_logging(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Both handshake steps are logged when debug logging is enabled."""
    caplog.set_level(logging.DEBUG, logger="kasa")
    server_seed = secrets.token_bytes(16)
    credentials = Credentials("foo", "bar")
    device_auth_hash = KlapTransport.generate_auth_hash(credentials)

    async def _return_handshake_response(url: URL, params=None, data=None, *_, **__):
        if url == URL("http://127.0.0.1:80/app/handshake1"):
            seed_auth_hash = _sha256(data + device_auth_hash)
            return _mock_response(200, server_seed + seed_auth_hash)
        return _mock_response(200, b"")

    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=_return_handshake_response
    )
    transport = KlapTransport(config=DeviceConfig("127.0.0.1", credentials=credentials))

    await transport.perform_handshake()
    assert "Handshake1 posted" in caplog.text
    assert "Handshake1 success" in caplog.text
    assert "Handshake2 posted" in caplog.text
    await transport.close()


async def test_query(mocker: MockerFixture) -> None:
    client_seed = None
    last_seq = None
    seq = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = KlapTransport.generate_auth_hash(client_credentials)

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        nonlocal client_seed, seq

        if url == URL("http://127.0.0.1:80/app/handshake1"):
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)

            return _mock_response(200, server_seed + client_seed_auth_hash)
        elif url == URL("http://127.0.0.1:80/app/handshake2"):
            return _mock_response(200, b"")
        elif url == URL("http://127.0.0.1:80/app/request"):
            assert transport._encryption_session is not None
            encryption_session = KlapEncryptionSession(
                transport._encryption_session.local_seed,
                transport._encryption_session.remote_seed,
                transport._encryption_session.user_hash,
            )
            seq = params.get("seq")
            encryption_session._seq = seq - 1
            encrypted, seq = encryption_session.encrypt('{"great": "success"}')
            seq = seq
            return _mock_response(200, encrypted)

    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=_return_response)

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    transport = KlapTransport(config=config)
    protocol = IotProtocol(transport=transport)

    for _ in range(10):
        resp = await protocol.query({})
        assert resp == {"great": "success"}
        # Check the protocol is incrementing the sequence number
        assert last_seq is None or last_seq + 1 == seq
        last_seq = seq


@pytest.mark.parametrize(
    ("response_status", "credentials_match", "expectation"),
    [
        pytest.param(
            (403, 403, 403),
            True,
            pytest.raises(KasaException),
            id="handshake1-403-status",
        ),
        pytest.param(
            (200, 403, 403),
            True,
            pytest.raises(KasaException),
            id="handshake2-403-status",
        ),
        pytest.param(
            (200, 200, 403),
            True,
            pytest.raises(_RetryableError),
            id="request-403-status",
        ),
        pytest.param(
            (200, 200, 400),
            True,
            pytest.raises(KasaException),
            id="request-400-status",
        ),
        pytest.param(
            (200, 200, 200),
            False,
            pytest.raises(AuthenticationError),
            id="handshake1-wrong-auth",
        ),
        pytest.param(
            (200, 200, 200),
            secrets.token_bytes(16),
            pytest.raises(KasaException),
            id="handshake1-bad-auth-length",
        ),
    ],
)
async def test_authentication_failures(
    mocker: MockerFixture,
    response_status: tuple[int, ...],
    credentials_match: bool | bytes,
    expectation: AbstractContextManager,
) -> None:
    client_seed = None

    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_credentials = (
        client_credentials if credentials_match else Credentials("bar", "foo")
    )
    device_auth_hash = KlapTransport.generate_auth_hash(device_credentials)

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        nonlocal client_seed

        if url == URL("http://127.0.0.1:80/app/handshake1"):
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)
            if credentials_match is not False and credentials_match is not True:
                client_seed_auth_hash += credentials_match
            return _mock_response(
                response_status[0], server_seed + client_seed_auth_hash
            )
        elif url == URL("http://127.0.0.1:80/app/handshake2"):
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)
            return _mock_response(
                response_status[1], server_seed + client_seed_auth_hash
            )
        elif url == URL("http://127.0.0.1:80/app/request"):
            return _mock_response(response_status[2], b"")

    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=_return_response)

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    protocol = IotProtocol(transport=KlapTransport(config=config))

    with expectation:
        await protocol.query({})


async def test_port_override() -> None:
    """Test that port override sets the app_url."""
    host = "127.0.0.1"
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), port_override=12345
    )
    transport = KlapTransport(config=config)

    assert str(transport._app_url) == "http://127.0.0.1:12345/app"


@device_iot
async def test_max_device_response_size_klap(
    dev: IotDevice, mocker: MockerFixture
) -> None:
    """Test that devices other than bulbs use a smaller budget over KLAP."""
    is_bulb = isinstance(dev, IotBulb)
    assert dev.max_device_response_size == (4096 if is_bulb else 16 * 1024)

    mocker.patch.object(dev.config, "connection_type", KLAP_CONNECTION)
    expected = 4096 if is_bulb else 2048
    assert dev.max_device_response_size == expected
    for child in dev.children:
        assert child.max_device_response_size == expected


def test_max_device_response_size_before_update() -> None:
    """Test that the budget follows the connection settings before an update."""
    assert IotPlug("127.0.0.1").max_device_response_size == 16 * 1024

    config = DeviceConfig("127.0.0.1", connection_type=KLAP_CONNECTION)
    assert IotPlug("127.0.0.1", config=config).max_device_response_size == 2048


@ks200m_iot
async def test_ks200m_update_split_klap(
    dev: IotWallSwitch, mocker: MockerFixture
) -> None:
    """Check that a KS200M update over KLAP is split into smaller requests."""
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    assert spy.call_count == 1

    mocker.patch.object(dev.config, "connection_type", KLAP_CONNECTION)
    spy.reset_mock()
    await dev.update()

    assert [sorted(call.args[0]) for call in spy.call_args_list] == [
        ["schedule", "system"],
        ["schedule"],
        ["anti_theft", "cnCloud", "smartlife.iot.LAS", "smartlife.iot.PIR", "time"],
    ]
