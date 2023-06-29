import errno
import json
import logging
import struct
import sys
import secrets

import pytest

from ..exceptions import SmartDeviceException
from ..klapprotocol import TPLinkKLAP


from ..auth import Auth
import hashlib


def get_klap_proto_with_fake_endpoint(mocker, klap_endpoint):
    proto = TPLinkKLAP("127.0.0.1", Auth(klap_endpoint.device_username, klap_endpoint.device_password))

    mocker.patch.object(TPLinkKLAP, "handle_cookies")
    mocker.patch.object(TPLinkKLAP, "session_post", klap_endpoint.session_post) 
    mocker.patch.object(proto, "get_client_challenge", return_value=klap_endpoint.client_challenge)

    return proto

async def test_protocol_handshake(mocker, klap_endpoint):
    proto = get_klap_proto_with_fake_endpoint(mocker, klap_endpoint)
        
    await proto._handshake1(None)

    assert proto.handshake_done == False

    await proto._handshake2(None)

    assert proto.handshake_done



@pytest.mark.parametrize("retry_count", [1, 3, 5])
async def test_protocol_retries(mocker, retry_count, klap_endpoint):
    
    protocol = get_klap_proto_with_fake_endpoint(mocker, klap_endpoint)
    gs = '{"great":"success"}'
    encrypted = TPLinkKLAP.encrypt(gs, klap_endpoint.client_challenge, klap_endpoint.server_challenge, klap_endpoint.authentication.authenticator())
    klap_endpoint.set_request_response(encrypted)
    klap_endpoint.set_simulated_failure_count(retry_count - 1)
    

    response = await protocol.query({}, retry_count=retry_count)
    assert response == {"great": "success"}


@pytest.mark.parametrize("log_level", [logging.WARNING, logging.DEBUG])
async def test_protocol_logging(mocker, caplog, log_level, klap_endpoint):

    protocol = get_klap_proto_with_fake_endpoint(mocker, klap_endpoint)
    encrypted = TPLinkKLAP.encrypt('{"great":"success"}', klap_endpoint.client_challenge, klap_endpoint.server_challenge, klap_endpoint.authentication.authenticator())

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

    client_challenge = secrets.token_bytes(16)
    server_challenge = secrets.token_bytes(16)
    authenticator = Auth().authenticator()
    
    d = json.dumps({"foo": 1, "bar": 2})
    encrypted = TPLinkKLAP.encrypt(d, client_challenge, server_challenge, authenticator)

    decrypted = TPLinkKLAP.decrypt(encrypted,  client_challenge, server_challenge, authenticator)
    assert d == decrypted


def test_encrypt_unicode():
    d = "{'snowman': '\u2603'}"

   
    client_challenge = secrets.token_bytes(16)
    server_challenge = secrets.token_bytes(16)
    authenticator = Auth().authenticator()
    
    encrypted = TPLinkKLAP.encrypt(d, client_challenge, server_challenge, authenticator)

    decrypted = TPLinkKLAP.decrypt(encrypted,  client_challenge, server_challenge, authenticator)
    assert d == decrypted



