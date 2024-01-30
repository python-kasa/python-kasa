import json
import logging
import secrets
import time
from contextlib import nullcontext as does_not_raise

import aiohttp
import pytest
from yarl import URL

from ..aestransport import AesTransport
from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import (
    AuthenticationException,
    ConnectionException,
    RetryableException,
    SmartDeviceException,
    TimeoutException,
)
from ..httpclient import HttpClient
from ..iotprotocol import IotProtocol
from ..klaptransport import (
    KlapEncryptionSession,
    KlapTransport,
    KlapTransportV2,
    _sha256,
)
from ..protocol import DEFAULT_CREDENTIALS, get_default_credentials
from ..smartprotocol import SmartProtocol

DUMMY_QUERY = {"foobar": {"foo": "bar", "bar": "foo"}}


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
    "error, retry_expectation",
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
    mocker, retry_count, protocol_class, transport_class, error, retry_expectation
):
    host = "127.0.0.1"
    conn = mocker.patch.object(aiohttp.ClientSession, "post", side_effect=error)
    mocker.patch.object(protocol_class, "BACKOFF_SECONDS_AFTER_TIMEOUT", 0)

    config = DeviceConfig(host)
    with pytest.raises(SmartDeviceException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=retry_count
        )

    expected_count = retry_count + 1 if retry_expectation else 1
    assert conn.call_count == expected_count


@pytest.mark.parametrize(
    "error, retry_expectation",
    [
        (SmartDeviceException("dummy exception"), False),
        (RetryableException("dummy exception"), True),
        (TimeoutException("dummy exception"), True),
    ],
    ids=("SmartDeviceException", "RetryableException", "TimeoutException"),
)
@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries_via_httpclient(
    mocker, retry_count, protocol_class, transport_class, error, retry_expectation
):
    host = "127.0.0.1"
    conn = mocker.patch.object(HttpClient, "post", side_effect=error)
    mocker.patch.object(protocol_class, "BACKOFF_SECONDS_AFTER_TIMEOUT", 0)

    config = DeviceConfig(host)
    with pytest.raises(SmartDeviceException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=retry_count
        )

    expected_count = retry_count + 1 if retry_expectation else 1
    assert conn.call_count == expected_count


@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
async def test_protocol_no_retry_on_connection_error(
    mocker, protocol_class, transport_class
):
    host = "127.0.0.1"
    conn = mocker.patch.object(
        aiohttp.ClientSession,
        "post",
        side_effect=AuthenticationException("foo"),
    )
    mocker.patch.object(protocol_class, "BACKOFF_SECONDS_AFTER_TIMEOUT", 0)
    config = DeviceConfig(host)
    with pytest.raises(SmartDeviceException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=5
        )

    assert conn.call_count == 1


@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
async def test_protocol_retry_recoverable_error(
    mocker, protocol_class, transport_class
):
    host = "127.0.0.1"
    conn = mocker.patch.object(
        aiohttp.ClientSession,
        "post",
        side_effect=aiohttp.ClientOSError("foo"),
    )
    config = DeviceConfig(host)
    with pytest.raises(SmartDeviceException):
        await protocol_class(transport=transport_class(config=config)).query(
            DUMMY_QUERY, retry_count=5
        )

    assert conn.call_count == 6


@pytest.mark.parametrize("transport_class", [AesTransport, KlapTransport])
@pytest.mark.parametrize("protocol_class", [IotProtocol, SmartProtocol])
@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_reconnect(mocker, retry_count, protocol_class, transport_class):
    host = "127.0.0.1"
    remaining = retry_count
    mock_response = {"result": {"great": "success"}, "error_code": 0}

    def _fail_one_less_than_retry_count(*_, **__):
        nonlocal remaining
        remaining -= 1
        if remaining:
            raise ConnectionException("Simulated connection failure")

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
async def test_protocol_logging(mocker, caplog, log_level):
    caplog.set_level(log_level)
    logging.getLogger("kasa").setLevel(log_level)

    def _return_encrypted(*_, **__):
        nonlocal encryption_session
        # Do the encrypt just before returning the value so the incrementing sequence number is correct
        encrypted, seq = encryption_session.encrypt('{"great":"success"}')
        return 200, encrypted

    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    config = DeviceConfig("127.0.0.1")
    protocol = IotProtocol(transport=KlapTransport(config=config))

    protocol._transport._handshake_done = True
    protocol._transport._session_expire_at = time.time() + 86400
    protocol._transport._encryption_session = encryption_session
    mocker.patch.object(HttpClient, "post", side_effect=_return_encrypted)

    response = await protocol.query({})
    assert response == {"great": "success"}
    if log_level == logging.DEBUG:
        assert "success" in caplog.text
    else:
        assert "success" not in caplog.text


def test_encrypt():
    d = json.dumps({"foo": 1, "bar": 2})

    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    encrypted, seq = encryption_session.encrypt(d)

    assert d == encryption_session.decrypt(encrypted)


def test_encrypt_unicode():
    d = "{'snowman': '\u2603'}"

    seed = secrets.token_bytes(16)
    auth_hash = KlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    encrypted, seq = encryption_session.encrypt(d)

    decrypted = encryption_session.decrypt(encrypted)

    assert d == decrypted


@pytest.mark.parametrize(
    "device_credentials, expectation",
    [
        (Credentials("foo", "bar"), does_not_raise()),
        (Credentials(), does_not_raise()),
        (
            get_default_credentials(DEFAULT_CREDENTIALS["KASA"]),
            does_not_raise(),
        ),
        (
            Credentials("shouldfail", "shouldfail"),
            pytest.raises(AuthenticationException),
        ),
    ],
    ids=("client", "blank", "kasa_setup", "shouldfail"),
)
@pytest.mark.parametrize(
    "transport_class, seed_auth_hash_calc",
    [
        pytest.param(KlapTransport, lambda c, s, a: c + a, id="KLAP"),
        pytest.param(KlapTransportV2, lambda c, s, a: c + s + a, id="KLAPV2"),
    ],
)
async def test_handshake1(
    mocker, device_credentials, expectation, transport_class, seed_auth_hash_calc
):
    async def _return_handshake1_response(url, params=None, data=None, *_, **__):
        nonlocal client_seed, server_seed, device_auth_hash

        client_seed = data
        seed_auth_hash = _sha256(
            seed_auth_hash_calc(client_seed, server_seed, device_auth_hash)
        )
        return _mock_response(200, server_seed + seed_auth_hash)

    client_seed = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = transport_class.generate_auth_hash(device_credentials)

    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=_return_handshake1_response
    )

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    protocol = IotProtocol(transport=transport_class(config=config))

    with expectation:
        (
            local_seed,
            device_remote_seed,
            auth_hash,
        ) = await protocol._transport.perform_handshake1()

        assert local_seed == client_seed
        assert device_remote_seed == server_seed
        assert device_auth_hash == auth_hash
    await protocol.close()


@pytest.mark.parametrize(
    "transport_class, seed_auth_hash_calc1, seed_auth_hash_calc2",
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
    mocker, transport_class, seed_auth_hash_calc1, seed_auth_hash_calc2
):
    client_seed = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = transport_class.generate_auth_hash(client_credentials)

    async def _return_handshake_response(url: URL, params=None, data=None, *_, **__):
        nonlocal client_seed, server_seed, device_auth_hash

        if str(url) == "http://127.0.0.1/app/handshake1":
            client_seed = data
            seed_auth_hash = _sha256(
                seed_auth_hash_calc1(client_seed, server_seed, device_auth_hash)
            )

            return _mock_response(200, server_seed + seed_auth_hash)
        elif str(url) == "http://127.0.0.1/app/handshake2":
            seed_auth_hash = _sha256(
                seed_auth_hash_calc2(client_seed, server_seed, device_auth_hash)
            )
            assert data == seed_auth_hash
            return _mock_response(response_status, b"")

    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=_return_handshake_response
    )

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    protocol = IotProtocol(transport=transport_class(config=config))
    protocol._transport.http_client = aiohttp.ClientSession()

    response_status = 200
    await protocol._transport.perform_handshake()
    assert protocol._transport._handshake_done is True

    response_status = 403
    with pytest.raises(AuthenticationException):
        await protocol._transport.perform_handshake()
    assert protocol._transport._handshake_done is False
    await protocol.close()


async def test_query(mocker):
    client_seed = None
    last_seq = None
    seq = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = KlapTransport.generate_auth_hash(client_credentials)

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        nonlocal client_seed, server_seed, device_auth_hash, seq

        if str(url) == "http://127.0.0.1/app/handshake1":
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)

            return _mock_response(200, server_seed + client_seed_auth_hash)
        elif str(url) == "http://127.0.0.1/app/handshake2":
            return _mock_response(200, b"")
        elif str(url) == "http://127.0.0.1/app/request":
            encryption_session = KlapEncryptionSession(
                protocol._transport._encryption_session.local_seed,
                protocol._transport._encryption_session.remote_seed,
                protocol._transport._encryption_session.user_hash,
            )
            seq = params.get("seq")
            encryption_session._seq = seq - 1
            encrypted, seq = encryption_session.encrypt('{"great": "success"}')
            seq = seq
            return _mock_response(200, encrypted)

    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=_return_response)

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    protocol = IotProtocol(transport=KlapTransport(config=config))

    for _ in range(10):
        resp = await protocol.query({})
        assert resp == {"great": "success"}
        # Check the protocol is incrementing the sequence number
        assert last_seq is None or last_seq + 1 == seq
        last_seq = seq


@pytest.mark.parametrize(
    "response_status, expectation",
    [
        ((403, 403, 403), pytest.raises(AuthenticationException)),
        ((200, 403, 403), pytest.raises(AuthenticationException)),
        ((200, 200, 403), pytest.raises(AuthenticationException)),
        ((200, 200, 400), pytest.raises(SmartDeviceException)),
    ],
    ids=("handshake1", "handshake2", "request", "non_auth_error"),
)
async def test_authentication_failures(mocker, response_status, expectation):
    client_seed = None

    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = KlapTransport.generate_auth_hash(client_credentials)

    async def _return_response(url: URL, params=None, data=None, *_, **__):
        nonlocal client_seed, server_seed, device_auth_hash, response_status

        if str(url) == "http://127.0.0.1/app/handshake1":
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)

            return _mock_response(
                response_status[0], server_seed + client_seed_auth_hash
            )
        elif str(url) == "http://127.0.0.1/app/handshake2":
            return _mock_response(response_status[1], b"")
        elif str(url) == "http://127.0.0.1/app/request":
            return _mock_response(response_status[2], b"")

    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=_return_response)

    config = DeviceConfig("127.0.0.1", credentials=client_credentials)
    protocol = IotProtocol(transport=KlapTransport(config=config))

    with expectation:
        await protocol.query({})
