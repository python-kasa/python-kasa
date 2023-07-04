import errno
import json
import logging
import struct
import sys
import secrets

import pytest

from kasa import SmartDevice
from ..exceptions import SmartDeviceException
from ..klapprotocol import TPLinkKlap, KlapEncryptionSession


from ..auth import AuthCredentials
import hashlib


def get_klap_proto_with_fake_endpoint(mocker, klap_endpoint):
    proto = TPLinkKlap(
        "127.0.0.1",
        AuthCredentials(klap_endpoint.device_username, klap_endpoint.device_password),
    )

    mocker.patch.object(TPLinkKlap, "handle_cookies")
    mocker.patch.object(proto, "clear_cookies")
    mocker.patch.object(TPLinkKlap, "session_post", klap_endpoint.session_post)
    mocker.patch.object(proto, "get_local_seed", return_value=klap_endpoint.local_seed)

    return proto


async def test_protocol_query_physical_device(dev):
    if not isinstance(dev.protocol, TPLinkKlap):
        pytest.skip(f"skipping klap test for non-klap device")
    else:
        for rng in range(10):
            dev.protocol.handshake_done = False
            for rng2 in range(5):
                res = await dev.protocol.query(dev.protocol.DISCOVERY_QUERY, 3)
                assert res is not None


async def test_protocol_handshake(mocker, klap_endpoint):
    proto = get_klap_proto_with_fake_endpoint(mocker, klap_endpoint)

    await proto.perform_handshake1(None)

    assert proto.handshake_done == False

    await proto.perform_handshake2(None)

    assert proto.handshake_done


@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries(mocker, retry_count, klap_endpoint):
    protocol = get_klap_proto_with_fake_endpoint(mocker, klap_endpoint)
    gs = '{"great":"success"}'

    # await protocol.perform_handshake(None, new_local_seed = klap_endpoint.local_seed)

    es = KlapEncryptionSession(
        klap_endpoint.local_seed,
        klap_endpoint.remote_seed,
        TPLinkKlap.generate_auth_hash(klap_endpoint.authentication),
    )

    # Call the encryption function multiple times so the internal sequence number increments according to the retries
    for i in range(0, retry_count):
        encrypted = es.encrypt(gs)[0]

    klap_endpoint.set_request_response(encrypted)
    klap_endpoint.set_simulated_failure_count(retry_count - 1)

    response = await protocol.query({}, retry_count=retry_count)
    assert response == {"great": "success"}


@pytest.mark.parametrize("log_level", [logging.WARNING, logging.DEBUG])
async def test_protocol_logging(mocker, caplog, log_level, klap_endpoint):
    protocol = get_klap_proto_with_fake_endpoint(mocker, klap_endpoint)

    gs = '{"great":"success"}'
    es = KlapEncryptionSession(
        klap_endpoint.local_seed,
        klap_endpoint.remote_seed,
        TPLinkKlap.generate_auth_hash(klap_endpoint.authentication),
    )
    encrypted = es.encrypt(gs)[0]

    caplog.set_level(log_level)

    logging.getLogger("kasa").setLevel(log_level)

    klap_endpoint.set_request_response(encrypted)

    response = await protocol.query({})
    assert response == {"great": "success"}
    if log_level == logging.DEBUG:
        assert "success" in caplog.text
    else:
        assert "success" not in caplog.text


async def test_encrypt():
    local_seed = secrets.token_bytes(16)
    remote_seed = secrets.token_bytes(16)
    auth = AuthCredentials()

    d = json.dumps({"foo": 1, "bar": 2})

    es = KlapEncryptionSession(
        local_seed, remote_seed, TPLinkKlap.generate_auth_hash(auth)
    )

    encrypted = es.encrypt(d)[0]
    decrypted = es.decrypt(encrypted)
    assert d == decrypted

    # Repeate encryption to ensure that the sequence numbering is working
    encrypted = es.encrypt(d)[0]
    decrypted = es.decrypt(encrypted)
    assert d == decrypted


def test_encrypt_unicode():
    d = "{'snowman': '\u2603'}"

    local_seed = secrets.token_bytes(16)
    remote_seed = secrets.token_bytes(16)
    auth = AuthCredentials()

    es = KlapEncryptionSession(
        local_seed, remote_seed, TPLinkKlap.generate_auth_hash(auth)
    )
    encrypted = es.encrypt(d)[0]

    decrypted = es.decrypt(encrypted)
    assert d == decrypted
