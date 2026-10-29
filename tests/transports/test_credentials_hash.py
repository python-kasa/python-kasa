"""Tests for credentials_hash handling across transports.

A credentials_hash is transport specific. Devices can change their encryption
type without the credentials changing, for example when Third-Party
Compatibility is toggled on a Tapo device, so a transport can be handed a hash
that a different transport produced. It must not treat that as a bad password.
"""

from __future__ import annotations

import base64

import pytest

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.json import dumps as json_dumps
from kasa.transports.aestransport import AesTransport
from kasa.transports.klaptransport import KlapTransportV2
from kasa.transports.sslaestransport import SslAesTransport
from kasa.transports.ssltransport import SslTransport

pytestmark = [pytest.mark.requires_dummy]

CREDENTIALS = Credentials("user@example.com", "great_password")

# The aes hash depends on the login version, so pin it rather than relying
# on the DeviceConfig default.
AES_LV2 = DeviceConnectionParameters(
    device_family=DeviceFamily.SmartTapoPlug,
    encryption_type=DeviceEncryptionType.Aes,
    login_version=2,
)


def klap_hash(credentials: Credentials) -> str:
    """Build a KLAP v2 credentials_hash: base64 of a raw sha256 digest."""
    return base64.b64encode(KlapTransportV2.generate_auth_hash(credentials)).decode()


def aes_hash(credentials: Credentials) -> str:
    """Build an AES credentials_hash: base64 json of sha1'd credentials."""
    un, pw = AesTransport.hash_credentials(True, credentials)
    return base64.b64encode(
        json_dumps({"password2": pw, "username": un}).encode()
    ).decode()


def plaintext_hash(credentials: Credentials) -> str:
    """Build a TPAP or SSL-AES credentials_hash: base64 json of plaintext."""
    return base64.b64encode(
        json_dumps({"un": credentials.username, "pwd": credentials.password}).encode()
    ).decode()


async def test_klap_ignores_an_aes_credentials_hash():
    """KLAP must not build an auth hash out of another transport's hash."""
    transport = KlapTransportV2(
        config=DeviceConfig("127.0.0.1", credentials_hash=aes_hash(CREDENTIALS))
    )

    assert transport._local_auth_hash == KlapTransportV2.generate_auth_hash(
        Credentials()
    )
    assert transport.credentials_hash is None


async def test_aes_ignores_a_klap_credentials_hash():
    """AES must not crash or authenticate on another transport's hash."""
    transport = AesTransport(
        config=DeviceConfig(
            "127.0.0.1",
            credentials_hash=klap_hash(CREDENTIALS),
            connection_type=AES_LV2,
        )
    )

    assert transport._login_params == AesTransport._get_login_params(
        transport, Credentials()
    )
    assert transport.credentials_hash is None


async def test_klap_keeps_its_own_credentials_hash():
    """A hash the transport itself produced is still used."""
    credentials_hash = klap_hash(CREDENTIALS)
    transport = KlapTransportV2(
        config=DeviceConfig("127.0.0.1", credentials_hash=credentials_hash)
    )

    assert transport.credentials_hash == credentials_hash


async def test_aes_keeps_its_own_credentials_hash():
    """A hash the transport itself produced is still used."""
    credentials_hash = aes_hash(CREDENTIALS)
    transport = AesTransport(
        config=DeviceConfig(
            "127.0.0.1",
            credentials_hash=credentials_hash,
            connection_type=AES_LV2,
        )
    )

    assert transport.credentials_hash == credentials_hash


async def test_klap_recovers_credentials_from_a_plaintext_hash():
    """A TPAP or SSL-AES hash carries plaintext, so KLAP can rederive its own."""
    transport = KlapTransportV2(
        config=DeviceConfig("127.0.0.1", credentials_hash=plaintext_hash(CREDENTIALS))
    )

    assert transport.credentials_hash == klap_hash(CREDENTIALS)


async def test_aes_recovers_credentials_from_a_plaintext_hash():
    """A TPAP or SSL-AES hash carries plaintext, so AES can rederive its own."""
    transport = AesTransport(
        config=DeviceConfig(
            "127.0.0.1",
            credentials_hash=plaintext_hash(CREDENTIALS),
            connection_type=AES_LV2,
        )
    )

    assert transport.credentials_hash == aes_hash(CREDENTIALS)


async def test_sslaes_ignores_a_klap_credentials_hash():
    """SSL-AES must not crash on another transport's hash."""
    transport = SslAesTransport(
        config=DeviceConfig("127.0.0.1", credentials_hash=klap_hash(CREDENTIALS))
    )

    assert transport._username is None
    assert transport._password is None
    assert transport.credentials_hash is None


async def test_sslaes_keeps_its_own_credentials_hash():
    """A hash the transport itself produced is still used."""
    credentials_hash = plaintext_hash(CREDENTIALS)
    transport = SslAesTransport(
        config=DeviceConfig("127.0.0.1", credentials_hash=credentials_hash)
    )

    assert transport.credentials_hash == credentials_hash


async def test_ssl_ignores_a_klap_credentials_hash():
    """The ssl transport must not crash on another transport's hash."""
    transport = SslTransport(
        config=DeviceConfig("127.0.0.1", credentials_hash=klap_hash(CREDENTIALS))
    )

    assert transport._login_params == SslTransport._get_login_params(
        transport, Credentials()
    )


async def test_ssl_recovers_credentials_from_a_plaintext_hash():
    """A TPAP or SSL-AES hash carries plaintext, so ssl can rederive its own."""
    transport = SslTransport(
        config=DeviceConfig("127.0.0.1", credentials_hash=plaintext_hash(CREDENTIALS))
    )

    assert transport._login_params == SslTransport._get_login_params(
        transport, CREDENTIALS
    )


async def test_klap_ignores_a_malformed_credentials_hash():
    """A hash that is not even base64 is treated as absent."""
    transport = KlapTransportV2(
        config=DeviceConfig("127.0.0.1", credentials_hash="not!valid!base64!")
    )

    assert transport._local_auth_hash == KlapTransportV2.generate_auth_hash(
        Credentials()
    )
    assert transport.credentials_hash is None


async def test_klap_ignores_a_hash_that_is_not_a_json_object():
    """Recovery only applies to a json object, not to any decodable json."""
    credentials_hash = base64.b64encode(json_dumps(["user", "pass"]).encode()).decode()
    transport = KlapTransportV2(
        config=DeviceConfig("127.0.0.1", credentials_hash=credentials_hash)
    )

    assert transport._local_auth_hash == KlapTransportV2.generate_auth_hash(
        Credentials()
    )


async def test_klap_prefers_credentials_over_a_foreign_hash():
    """Configured credentials win, so nothing is recovered from the hash."""
    other = Credentials("other@example.com", "other_password")
    transport = KlapTransportV2(
        config=DeviceConfig(
            "127.0.0.1",
            credentials=CREDENTIALS,
            credentials_hash=plaintext_hash(other),
        )
    )

    assert transport.credentials_hash == klap_hash(CREDENTIALS)


async def test_aes_prefers_credentials_over_a_foreign_hash():
    """Configured credentials win, so nothing is recovered from the hash."""
    other = Credentials("other@example.com", "other_password")
    transport = AesTransport(
        config=DeviceConfig(
            "127.0.0.1",
            credentials=CREDENTIALS,
            credentials_hash=plaintext_hash(other),
            connection_type=AES_LV2,
        )
    )

    assert transport.credentials_hash == aes_hash(CREDENTIALS)
