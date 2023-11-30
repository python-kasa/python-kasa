import errno
import json
import logging
import secrets
import struct
import sys
import time
from contextlib import nullcontext as does_not_raise

import httpx
import pytest

from ..credentials import Credentials
from ..exceptions import AuthenticationException, SmartDeviceException
from ..iotprotocol import TPLinkIotProtocol
from ..klaptransport import KlapEncryptionSession, TPLinkKlapTransport, _sha256


class _mock_response:
    def __init__(self, status_code, content: bytes):
        self.status_code = status_code
        self.content = content


@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries(mocker, retry_count):
    conn = mocker.patch.object(
        TPLinkKlapTransport, "client_post", side_effect=Exception("dummy exception")
    )
    with pytest.raises(SmartDeviceException):
        await TPLinkIotProtocol("127.0.0.1").query({}, retry_count=retry_count)

    assert conn.call_count == retry_count + 1


async def test_protocol_no_retry_on_connection_error(mocker):
    conn = mocker.patch.object(
        TPLinkKlapTransport,
        "client_post",
        side_effect=httpx.ConnectError("foo"),
    )
    with pytest.raises(SmartDeviceException):
        await TPLinkIotProtocol("127.0.0.1").query({}, retry_count=5)

    assert conn.call_count == 1


async def test_protocol_retry_recoverable_error(mocker):
    conn = mocker.patch.object(
        TPLinkKlapTransport,
        "client_post",
        side_effect=httpx.CloseError("foo"),
    )
    with pytest.raises(SmartDeviceException):
        await TPLinkIotProtocol("127.0.0.1").query({}, retry_count=5)

    assert conn.call_count == 6


@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_reconnect(mocker, retry_count):
    remaining = retry_count

    def _fail_one_less_than_retry_count(*_, **__):
        nonlocal remaining, encryption_session
        remaining -= 1
        if remaining:
            raise Exception("Simulated post failure")
        # Do the encrypt just before returning the value so the incrementing sequence number is correct
        encrypted, seq = encryption_session.encrypt('{"great":"success"}')
        return 200, encrypted

    seed = secrets.token_bytes(16)
    auth_hash = TPLinkKlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)
    protocol = TPLinkIotProtocol("127.0.0.1")
    protocol.transport.handshake_done = True
    protocol.transport.session_expire_at = time.time() + 86400
    protocol.transport.encryption_session = encryption_session
    mocker.patch.object(
        TPLinkKlapTransport, "client_post", side_effect=_fail_one_less_than_retry_count
    )

    response = await protocol.query({}, retry_count=retry_count)
    assert response == {"great": "success"}


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
    auth_hash = TPLinkKlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)
    protocol = TPLinkIotProtocol("127.0.0.1")

    protocol.transport.handshake_done = True
    protocol.transport.session_expire_at = time.time() + 86400
    protocol.transport.encryption_session = encryption_session
    mocker.patch.object(
        TPLinkKlapTransport, "client_post", side_effect=_return_encrypted
    )

    response = await protocol.query({})
    assert response == {"great": "success"}
    if log_level == logging.DEBUG:
        assert "success" in caplog.text
    else:
        assert "success" not in caplog.text


def test_encrypt():
    d = json.dumps({"foo": 1, "bar": 2})

    seed = secrets.token_bytes(16)
    auth_hash = TPLinkKlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    encrypted, seq = encryption_session.encrypt(d)

    assert d == encryption_session.decrypt(encrypted)


def test_encrypt_unicode():
    d = "{'snowman': '\u2603'}"

    seed = secrets.token_bytes(16)
    auth_hash = TPLinkKlapTransport.generate_auth_hash(Credentials("foo", "bar"))
    encryption_session = KlapEncryptionSession(seed, seed, auth_hash)

    encrypted, seq = encryption_session.encrypt(d)

    decrypted = encryption_session.decrypt(encrypted)

    assert d == decrypted


@pytest.mark.parametrize(
    "device_credentials, expectation",
    [
        (Credentials("foo", "bar"), does_not_raise()),
        (Credentials("", ""), does_not_raise()),
        (
            Credentials(
                TPLinkKlapTransport.KASA_SETUP_EMAIL,
                TPLinkKlapTransport.KASA_SETUP_PASSWORD,
            ),
            does_not_raise(),
        ),
        (
            Credentials("shouldfail", "shouldfail"),
            pytest.raises(AuthenticationException),
        ),
    ],
    ids=("client", "blank", "kasa_setup", "shouldfail"),
)
async def test_handshake1(mocker, device_credentials, expectation):
    async def _return_handshake1_response(url, params=None, data=None, *_, **__):
        nonlocal client_seed, server_seed, device_auth_hash

        client_seed = data
        client_seed_auth_hash = _sha256(data + device_auth_hash)

        return _mock_response(200, server_seed + client_seed_auth_hash)

    client_seed = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = TPLinkKlapTransport.generate_auth_hash(device_credentials)

    mocker.patch.object(
        httpx.AsyncClient, "post", side_effect=_return_handshake1_response
    )

    protocol = TPLinkIotProtocol("127.0.0.1", credentials=client_credentials)

    protocol.transport.http_client = httpx.AsyncClient()
    with expectation:
        (
            local_seed,
            device_remote_seed,
            auth_hash,
        ) = await protocol.transport.perform_handshake1()

        assert local_seed == client_seed
        assert device_remote_seed == server_seed
        assert device_auth_hash == auth_hash
    await protocol.close()


async def test_handshake(mocker):
    async def _return_handshake_response(url, params=None, data=None, *_, **__):
        nonlocal response_status, client_seed, server_seed, device_auth_hash

        if url == "http://127.0.0.1/app/handshake1":
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)

            return _mock_response(200, server_seed + client_seed_auth_hash)
        elif url == "http://127.0.0.1/app/handshake2":
            return _mock_response(response_status, b"")

    client_seed = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = TPLinkKlapTransport.generate_auth_hash(client_credentials)

    mocker.patch.object(
        httpx.AsyncClient, "post", side_effect=_return_handshake_response
    )

    protocol = TPLinkIotProtocol("127.0.0.1", credentials=client_credentials)
    protocol.transport.http_client = httpx.AsyncClient()

    response_status = 200
    await protocol.transport.perform_handshake()
    assert protocol.transport.handshake_done is True

    response_status = 403
    with pytest.raises(AuthenticationException):
        await protocol.transport.perform_handshake()
    assert protocol.transport.handshake_done is False
    await protocol.close()


async def test_query(mocker):
    async def _return_response(url, params=None, data=None, *_, **__):
        nonlocal client_seed, server_seed, device_auth_hash, protocol, seq

        if url == "http://127.0.0.1/app/handshake1":
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)

            return _mock_response(200, server_seed + client_seed_auth_hash)
        elif url == "http://127.0.0.1/app/handshake2":
            return _mock_response(200, b"")
        elif url == "http://127.0.0.1/app/request":
            encryption_session = KlapEncryptionSession(
                protocol.transport.encryption_session.local_seed,
                protocol.transport.encryption_session.remote_seed,
                protocol.transport.encryption_session.user_hash,
            )
            seq = params.get("seq")
            encryption_session._seq = seq - 1
            encrypted, seq = encryption_session.encrypt('{"great": "success"}')
            seq = seq
            return _mock_response(200, encrypted)

    client_seed = None
    last_seq = None
    seq = None
    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = TPLinkKlapTransport.generate_auth_hash(client_credentials)

    mocker.patch.object(httpx.AsyncClient, "post", side_effect=_return_response)

    protocol = TPLinkIotProtocol("127.0.0.1", credentials=client_credentials)

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
    async def _return_response(url, params=None, data=None, *_, **__):
        nonlocal client_seed, server_seed, device_auth_hash, response_status

        if url == "http://127.0.0.1/app/handshake1":
            client_seed = data
            client_seed_auth_hash = _sha256(data + device_auth_hash)

            return _mock_response(
                response_status[0], server_seed + client_seed_auth_hash
            )
        elif url == "http://127.0.0.1/app/handshake2":
            return _mock_response(response_status[1], b"")
        elif url == "http://127.0.0.1/app/request":
            return _mock_response(response_status[2], None)

    client_seed = None

    server_seed = secrets.token_bytes(16)
    client_credentials = Credentials("foo", "bar")
    device_auth_hash = TPLinkKlapTransport.generate_auth_hash(client_credentials)

    mocker.patch.object(httpx.AsyncClient, "post", side_effect=_return_response)

    protocol = TPLinkIotProtocol("127.0.0.1", credentials=client_credentials)

    with expectation:
        await protocol.query({})
