from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
import secrets
import ssl
import struct
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

import aiohttp
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from ecdsa import ellipticcurve
from pytest_mock import MockerFixture
from yarl import URL

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
    TpapParameters,
)
from kasa.exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.protocols import IotProtocol, SmartCamProtocol, SmartProtocol
from kasa.smart import SmartDevice
from kasa.transports import KlapTransportV2, SslAesTransport
from kasa.transports.sslcontext import get_ssl_context as get_shared_ssl_context
from kasa.transports.tpap import cert, crypto
from kasa.transports.tpaptransport import TpapEncryptionSession, TpapTransport

from .tpap.certificates import build_certificate, mac_name

HOST = "127.0.0.1"
MOCK_USER = "mock@example.com"
MOCK_PWD = "correct_pwd"  # noqa: S105
SECRET_PWD = "secret-pass"  # noqa: S105
MOCK_MAC = "AA:BB:CC:DD:EE:FF"
MOCK_STOK = "MOCKSTOK"
CREDENTIALS = Credentials(MOCK_USER, MOCK_PWD)
DUMMY_QUERY = {"foobar": {"foo": "bar", "bar": "foo"}}
DEVICE_RESPONSE = {"error_code": 0, "result": {"great": "success"}}
PASSWORD_SHADOW = {"type": "password_shadow", "params": {"passwd_id": 2}}
LOCKED = {
    "error_code": SmartErrorCode.ACCOUNT_ERROR.value,
    "error_info": {"lockedMinute": 30, "failedAttempts": 15, "remainAttempts": 0},
}
CAMERAS = (DeviceFamily.SmartIpCamera, DeviceFamily.SmartTapoDoorbell)
#: A reply field the mock device leaves out
ABSENT = object()


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode()


class DacChain:
    """A device attestation certificate, its optional intermediate and root."""

    def __init__(self, *, with_ica: bool = False) -> None:
        root_key = ec.generate_private_key(ec.SECP256R1())
        self.root = build_certificate(root_key, "root", "root", root_key, is_ca=True)
        issuer_key, issuer_name = root_key, "root"
        self.ica = None
        if with_ica:
            ica_key = ec.generate_private_key(ec.SECP256R1())
            self.ica = build_certificate(ica_key, "ica", "root", root_key, is_ca=True)
            issuer_key, issuer_name = ica_key, "ica"
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.dac = build_certificate(self.key, "dac", issuer_name, issuer_key)

    def attest(self, message: bytes) -> dict[str, str]:
        der = serialization.Encoding.DER
        return {
            "dac_ca": _b64(self.dac.public_bytes(der)),
            "dac_ica": _b64(self.ica.public_bytes(der)) if self.ica else "",
            "dac_proof": _b64(self.key.sign(message, ec.ECDSA(hashes.SHA256()))),
        }


@pytest.fixture
def dac_chain(monkeypatch: pytest.MonkeyPatch) -> DacChain:
    chain = DacChain()
    monkeypatch.setattr(
        cert,
        "TPAP_ROOT_CA_PEM",
        chain.root.public_bytes(serialization.Encoding.PEM).decode(),
    )
    return chain


class _Suite:
    """The curve, hash and MAC of a SPAKE2+ cipher suite, for the device side."""

    def __init__(self, suite_type: int) -> None:
        m_comp, n_comp, nist, self.ec_curve = crypto._suite_parameters(suite_type)
        self.curve = nist.curve
        self.g = nist.generator
        self.order = int(self.g.order())
        self.order_len = (self.order.bit_length() + 7) // 8
        self.m = self.point(m_comp)
        self.n = self.point(n_comp)
        self.hash_name = crypto._suite_hash_name(suite_type)
        self.cmac = crypto._suite_mac_is_cmac(suite_type)
        self.digest_len = 64 if self.hash_name == "SHA512" else 32
        # Confirmation keys as long as the MAC output, as in the Tapo app
        self.mac_len = 16 if self.cmac else self.digest_len

    def point(self, sec1: bytes) -> Any:
        x, y = crypto._sec1_to_xy(sec1, self.ec_curve)
        return ellipticcurve.Point(self.curve, x, y, self.order)

    def encode(self, point: Any) -> bytes:
        return crypto._xy_to_uncompressed(point.x(), point.y(), self.ec_curve)

    def mac(self, key: bytes, data: bytes) -> bytes:
        if self.cmac:
            return crypto._cmac_aes(key, data)
        return crypto._hmac(self.hash_name, key, data)


class MockTpapDevice:
    """A TPAP device: the in-band discover, the device side of SPAKE2+, and /ds.

    The device holds one encoded passcode for each passcode type, as a device
    holds its registration records, and refuses a login that does not prove it.
    """

    class _mock_response:
        def __init__(self, status: int, body: Any) -> None:
            self.status = status
            self._body = body

        async def __aenter__(self) -> MockTpapDevice._mock_response:
            return self

        async def __aexit__(self, exc_t: Any, exc_v: Any, exc_tb: Any) -> None:
            pass

        async def read(self) -> bytes:
            if isinstance(self._body, bytes):
                return self._body
            return json_dumps(self._body).encode()

    def __init__(
        self,
        family: DeviceFamily = DeviceFamily.SmartTapoPlug,
        *,
        tls: int | None = 0,
        port: int | None = 80,
        pake: Sequence[int] | None = (2,),
        dac: bool = False,
        mac: str = MOCK_MAC,
        password: str = MOCK_PWD,
        passcodes: dict[str, str] | None = None,
        extra_crypt: Any = ABSENT,
        suite: int = 1,
        cipher: str = "aes_128_ccm",
        start_seq: int = 1,
        dac_chain: DacChain | None = None,
        replies: dict[str, Any] | None = None,
        register: dict[str, Any] | None = None,
        share: dict[str, Any] | None = None,
        ds_replies: list[tuple[int, Any]] | None = None,
        response: Any = None,
        camera: bool | None = None,
    ) -> None:
        camera = family in CAMERAS if camera is None else camera
        if extra_crypt is ABSENT:
            extra_crypt = None if camera else PASSWORD_SHADOW
        self.extra_crypt = extra_crypt
        hashed = crypto.md5_hex(password) if camera else crypto._sha1_hex(password)
        self.passcodes = passcodes or {"userpw": hashed, "shared_token": hashed}
        # Only a device that attests itself holds the default passcode as it is
        self.attested = not camera and tls == 0 and dac and 0 in (pake or ())
        self.tpap = {
            "tls": tls,
            "port": port,
            "pake": None if pake is None else list(pake),
            "dac": int(dac),
        }
        self.mac = mac
        self.suite = suite
        self.cipher = cipher
        self.start_seq = start_seq
        self.dac_chain = dac_chain
        self.replies = replies or {}
        self.register = register or {}
        self.share = share or {}
        self.ds_replies = list(ds_replies or [])
        self.response = DEVICE_RESPONSE if response is None else response
        self.failed_attempts = 0
        self.calls: Counter[str] = Counter()
        self.params: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        self.urls: list[URL] = []
        self.ssl: list[Any] = []

    async def post(
        self,
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        ssl: Any = None,
        **_: Any,
    ) -> MockTpapDevice._mock_response:
        await asyncio.sleep(0)  # let other requests run, as on a network
        self.urls.append(url)
        self.ssl.append(ssl)
        if json is None:
            assert data is not None
            self.calls["request"] += 1
            if self.ds_replies:
                return self._mock_response(*self.ds_replies.pop(0))
            return self._mock_response(200, self._request(url, data))

        step = json["params"]["sub_method"]
        self.calls[step] += 1
        self.params[step].append(json["params"])
        if (reply := self.replies.get(step)) is not None:
            if isinstance(reply, tuple):
                return self._mock_response(*reply)
            return self._mock_response(200, reply)
        handler = {
            "discover": self._discover,
            "pake_register": self._pake_register,
            "pake_share": self._pake_share,
        }[step]
        return self._mock_response(200, handler(json["params"]))

    @staticmethod
    def _apply(result: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
        for key, value in changes.items():
            if value is ABSENT:
                result.pop(key, None)
            elif callable(value):
                result[key] = value(result[key])
            else:
                result[key] = value
        return result

    def _discover(self, params: dict[str, Any]) -> dict[str, Any]:
        tpap = {key: value for key, value in self.tpap.items() if value is not None}
        return {"error_code": 0, "result": {"mac": self.mac, "tpap": tpap}}

    def _pake_register(self, params: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "cipher_suites": self.suite,
            "iterations": 100,
            "encryption": self.cipher,
        }
        if self.extra_crypt is not None:
            result["extra_crypt"] = self.extra_crypt
        iterations = self.register.get("iterations", 100)
        if not isinstance(iterations, int) or not 0 < iterations <= 100_000:
            iterations = 10_000

        suite = self._suite = _Suite(self.suite)
        passcode = self.passcodes.get(params["passcode_type"])
        if passcode is None and params["passcode_type"] == "default_userpw":
            passcode = crypto.mac_pass_from_device_mac(self.mac)
            if not self.attested:
                passcode = crypto.build_credentials(
                    self.extra_crypt, "", passcode, self.mac.replace(":", "")
                )
        salt = secrets.token_bytes(16)
        w0, w1 = crypto._derive_ab((passcode or "").encode(), salt, iterations, 32)
        self._w0, self._w1 = w0 % suite.order, w1 % suite.order
        self._y = secrets.randbelow(suite.order - 1) + 1
        self._dev_share = self._y * suite.g + self._w0 * suite.n
        self._user_random = base64.b64decode(params["user_random"])
        self._dev_random = secrets.token_bytes(32)
        result["dev_random"] = _b64(self._dev_random)
        result["dev_salt"] = _b64(salt)
        result["dev_share"] = _b64(suite.encode(self._dev_share))
        return {"error_code": 0, "result": self._apply(result, self.register)}

    def _pake_share(self, params: dict[str, Any]) -> dict[str, Any]:
        suite = self._suite
        user_share = suite.point(base64.b64decode(params["user_share"]))
        z = self._y * (user_share + (-(self._w0 * suite.m)))
        v = self._y * (self._w1 * suite.g)
        context = crypto._hash(
            suite.hash_name,
            crypto.PAKE_CONTEXT_TAG + self._user_random + self._dev_random,
        )
        transcript = b"".join(
            crypto._len8le(part)
            for part in (
                context,
                b"",
                b"",
                suite.encode(suite.m),
                suite.encode(suite.n),
                suite.encode(user_share),
                suite.encode(self._dev_share),
                suite.encode(z),
                suite.encode(v),
                crypto._encode_w(self._w0, suite.order_len),
            )
        )
        transcript_hash = crypto._hash(suite.hash_name, transcript)
        keys = crypto._hkdf_expand(
            "ConfirmationKeys", transcript_hash, suite.mac_len * 2, suite.hash_name
        )
        shared_key = crypto._hkdf_expand(
            "SharedKey", transcript_hash, suite.digest_len, suite.hash_name
        )
        expected = suite.mac(keys[: suite.mac_len], suite.encode(self._dev_share))
        if not hmac.compare_digest(expected, base64.b64decode(params["user_confirm"])):
            self.failed_attempts += 1
            return {
                "error_code": SmartErrorCode.STAT_ACCESS_ERROR.value,
                "error_info": {
                    "lockedMinute": 0,
                    "failedAttempts": self.failed_attempts,
                    "remainAttempts": 15 - self.failed_attempts,
                },
            }

        dev_confirm = suite.mac(keys[suite.mac_len :], suite.encode(user_share))
        result: dict[str, Any] = {
            "dev_confirm": _b64(dev_confirm),
            "stok": MOCK_STOK,
            "start_seq": self.start_seq,
        }
        if "dac_nonce" in params and self.dac_chain:
            nonce = base64.b64decode(params["dac_nonce"])
            result.update(self.dac_chain.attest(shared_key + nonce))
        key, self._base_nonce = TpapEncryptionSession.key_nonce_from_shared(
            shared_key, self.cipher
        )
        self._aead: AESCCM | ChaCha20Poly1305 = (
            AESCCM(key, tag_length=16)
            if self.cipher.startswith("aes")
            else ChaCha20Poly1305(key)
        )
        return {"error_code": 0, "result": self._apply(result, self.share)}

    def _request(self, url: URL, data: bytes) -> bytes:
        assert url.path == f"/stok={MOCK_STOK}/ds"
        nonce = self._base_nonce[:-4] + data[:4]
        self.last_request = json_loads(self._aead.decrypt(nonce, data[4:], None))
        body = self.response
        plaintext = body if isinstance(body, bytes) else json_dumps(body).encode()
        return data[:4] + self._aead.encrypt(nonce, plaintext, None)


def _patch(mocker: MockerFixture, device: MockTpapDevice) -> MockTpapDevice:
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    return device


def _transport(
    family: DeviceFamily = DeviceFamily.SmartTapoPlug,
    *,
    https: bool | None = None,
    tpap: TpapParameters | None = None,
    credentials: Credentials | None = CREDENTIALS,
    credentials_hash: str | None = None,
    http_port: int | None = None,
    port_override: int | None = None,
) -> TpapTransport:
    config = DeviceConfig(
        HOST,
        credentials=credentials,
        credentials_hash=credentials_hash,
        port_override=port_override,
        connection_type=DeviceConnectionParameters(
            device_family=family,
            encryption_type=DeviceEncryptionType.Tpap,
            https=family in CAMERAS if https is None else https,
            http_port=http_port,
            tpap=tpap,
        ),
    )
    return TpapTransport(config=config)


def _discovered(
    tls: int = 0,
    *,
    port: int | None = 80,
    pake: list[int] | None = None,
    dac: bool = False,
    mac: str | None = MOCK_MAC,
    user_hash_type: int | None = None,
    owner: str | None = None,
) -> TpapParameters:
    """Return the values of a UDP discovery reply's tpap object."""
    return TpapParameters(
        tls=tls,
        port=port,
        pake=[2] if pake is None else pake,
        dac=dac,
        mac=mac,
        user_hash_type=user_hash_type,
        owner=owner,
    )


# --------------------------
# Session
# --------------------------


@pytest.mark.parametrize("cipher", ["aes_128_ccm", "aes_256_ccm", "chacha20_poly1305"])
def test_encrypt(cipher: str) -> None:
    session = TpapEncryptionSession(cipher, b"shared-key", 3)

    payload, seq = session.encrypt('{"method": "foobar"}')

    assert seq == 3
    assert payload[:4] == struct.pack(">I", 3)
    assert session.decrypt(payload, seq) == b'{"method": "foobar"}'
    assert session.encrypt(b"{}")[1] == 4


def test_decrypt_uses_the_sequence_of_the_reply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = TpapEncryptionSession("aes_128_ccm", b"shared-key", 7)
    payload, _ = session.encrypt(b"reply")

    with caplog.at_level(logging.DEBUG):
        assert session.decrypt(payload, 6) == b"reply"

    assert "unexpected rseq 7 (expected 6)" in caplog.text
    with pytest.raises(KasaException, match="response too short"):
        session.decrypt(b"\x00\x00\x00\x07", 7)


def test_unsupported_session_cipher() -> None:
    with pytest.raises(KasaException, match="Unsupported TPAP session cipher: rc4"):
        TpapEncryptionSession("rc4", b"shared-key", 1)


def test_session_keys_use_hkdf_sha256() -> None:
    """The key and nonce use HKDF-SHA256 whatever the hash of the SPAKE2+ suite."""

    def hkdf(salt: bytes, info: bytes, length: int) -> bytes:
        return HKDF(hashes.SHA256(), length, salt, info).derive(b"shared-key")

    session = TpapEncryptionSession("aes_128_ccm", b"shared-key", 1)

    assert session._key == hkdf(
        b"tp-kdf-salt-aes128-key", b"tp-kdf-info-aes128-key", 16
    )
    assert session._base_nonce == hkdf(
        b"tp-kdf-salt-aes128-iv", b"tp-kdf-info-aes128-iv", 12
    )


# --------------------------
# Login
# --------------------------


@pytest.mark.parametrize(
    ("family", "discovers"),
    [
        pytest.param(DeviceFamily.SmartTapoPlug, 1, id="plug"),
        pytest.param(DeviceFamily.SmartKasaPlug, 1, id="kasa-plug"),
        pytest.param(DeviceFamily.SmartTapoHub, 1, id="hub"),
        pytest.param(DeviceFamily.SmartTapoRobovac, 1, id="robovac"),
        pytest.param(DeviceFamily.IotSmartBulb, 1, id="kasa-iot-bulb"),
        pytest.param(DeviceFamily.IotSmartPlugSwitch, 1, id="kasa-iot-plug"),
        # Cameras refuse the in-band discover, so they get the camera defaults
        pytest.param(DeviceFamily.SmartIpCamera, 0, id="camera"),
        pytest.param(DeviceFamily.SmartTapoDoorbell, 0, id="doorbell"),
    ],
)
async def test_handshake(
    mocker: MockerFixture, family: DeviceFamily, discovers: int
) -> None:
    device = _patch(mocker, MockTpapDevice(family))
    transport = _transport(family)

    await transport.perform_handshake()

    assert transport._encryption_session is not None
    assert device.calls == Counter(
        {"discover": discovers, "pake_register": 1, "pake_share": 1}
    )
    register = device.params["pake_register"][0]
    assert register["username"] == crypto.md5_hex("admin")
    assert register["passcode_type"] == "userpw"
    assert register["cipher_suites"] == [1]
    assert "stok" not in register
    assert "dac_nonce" not in device.params["pake_share"][0]
    assert await transport.send(json_dumps(DUMMY_QUERY)) == DEVICE_RESPONSE
    assert device.last_request == DUMMY_QUERY


@pytest.mark.parametrize(
    ("family", "https", "http_port", "port_override", "tpap", "url"),
    [
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            False,
            80,
            None,
            _discovered(0, port=80),
            "http://127.0.0.1:80/",
            id="p115-plug",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            False,
            80,
            None,
            _discovered(1, port=None),
            "https://127.0.0.1:4433/",
            id="plug-tls-without-port",
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac,
            True,
            4433,
            None,
            _discovered(2, port=4433),
            "https://127.0.0.1:4433/",
            id="rv50-robovac",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            True,
            None,
            None,
            _discovered(1, port=443),
            "https://127.0.0.1:443/",
            id="c510w-camera",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            True,
            None,
            None,
            _discovered(1, port=None),
            "https://127.0.0.1:443/",
            id="camera-without-port",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            True,
            None,
            None,
            _discovered(0, port=None),
            "https://127.0.0.1:443/",
            id="camera-is-always-https",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            False,
            8080,
            None,
            _discovered(0, port=None),
            "http://127.0.0.1:8080/",
            id="plug-without-port-takes-http-port",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            False,
            80,
            8080,
            _discovered(0, port=None),
            "http://127.0.0.1:8080/",
            id="plug-without-port-keeps-port-override",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            True,
            8443,
            None,
            _discovered(0, port=None),
            "http://127.0.0.1:80/",
            id="plug-without-port-over-https-takes-80",
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac,
            True,
            None,
            None,
            _discovered(0, port=None),
            "http://127.0.0.1:443/",
            id="robovac-without-any-port-takes-443",
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac,
            True,
            4433,
            None,
            _discovered(0, port=None),
            "http://127.0.0.1:4433/",
            id="robovac-without-port-takes-http-port",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            False,
            None,
            None,
            _discovered(1, port=None),
            "https://127.0.0.1:443/",
            id="camera-without-any-port-takes-443",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            True,
            8443,
            None,
            _discovered(1, port=None),
            "https://127.0.0.1:8443/",
            id="camera-without-port-takes-http-port",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            False,
            80,
            None,
            _discovered(0, port=80),
            "http://127.0.0.1:80/",
            id="kl420l5-kasa-iot",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            False,
            9999,
            None,
            _discovered(1, port=None),
            "https://127.0.0.1:80/",
            id="kasa-iot-tls-without-port",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            False,
            9999,
            None,
            _discovered(2, port=4433),
            "https://127.0.0.1:4433/",
            id="kasa-iot-tls-port",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            False,
            9999,
            None,
            _discovered(3, port=None),
            "https://127.0.0.1:80/",
            id="kasa-iot-any-tls-but-0-is-https",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            False,
            9999,
            8080,
            _discovered(0, port=None),
            "http://127.0.0.1:8080/",
            id="kasa-iot-keeps-port-override",
        ),
    ],
)
async def test_handshake_from_discovery_values(
    mocker: MockerFixture,
    family: DeviceFamily,
    https: bool,
    http_port: int | None,
    port_override: int | None,
    tpap: TpapParameters,
    url: str,
) -> None:
    """With the values from UDP discovery the transport logs in straight away."""
    device = _patch(mocker, MockTpapDevice(family))
    transport = _transport(
        family,
        https=https,
        http_port=http_port,
        port_override=port_override,
        tpap=tpap,
    )

    await transport.perform_handshake()
    # A new login after a reset does not ask the device either
    await transport.reset()
    await transport.perform_handshake()

    assert device.calls["discover"] == 0
    assert device.calls["pake_share"] == 2
    assert {str(url) for url in device.urls} == {str(URL(url))}


async def test_handshake_from_in_band_discover(mocker: MockerFixture) -> None:
    """The in-band discover gives the URL, passcode type and MAC to log in with."""
    device = _patch(
        mocker,
        MockTpapDevice(DeviceFamily.IotSmartBulb, tls=1, port=0, pake=(0, 2), dac=True),
    )
    transport = _transport(DeviceFamily.IotSmartBulb, http_port=9999)

    await transport.perform_handshake()

    assert str(device.urls[0]) == str(URL("http://127.0.0.1:9999/"))
    assert {str(url) for url in device.urls[1:]} == {str(URL("https://127.0.0.1:80/"))}
    assert device.params["pake_register"][0]["passcode_type"] == "userpw"
    assert transport._device_mac == MOCK_MAC


async def test_discover_over_https_answering_tls_0_stays_on_tls_2(
    mocker: MockerFixture,
) -> None:
    """The RV50 Pro Omni answers the in-band discover over TLS with tls 0."""
    device = _patch(
        mocker, MockTpapDevice(DeviceFamily.SmartTapoRobovac, tls=0, port=4433)
    )
    transport = _transport(DeviceFamily.SmartTapoRobovac, https=True)

    await transport.perform_handshake()

    assert {str(url) for url in device.urls} == {str(URL("https://127.0.0.1:4433/"))}
    assert device.ssl[0] is await get_shared_ssl_context()
    assert all(context.verify_mode == ssl.CERT_REQUIRED for context in device.ssl[1:])


async def test_discover_with_values_of_the_wrong_type(mocker: MockerFixture) -> None:
    reply = {
        "error_code": 0,
        "result": {
            "mac": MOCK_MAC,
            "tpap": {"tls": "bad", "port": "bad", "pake": [2], "user_hash_type": "x"},
        },
    }
    device = _patch(mocker, MockTpapDevice(replies={"discover": reply}))
    transport = _transport()

    await transport.perform_handshake()

    assert {str(url) for url in device.urls} == {str(URL("http://127.0.0.1:80/"))}
    assert transport._encryption_session is not None


async def test_stored_config_reconnects_without_discover(mocker: MockerFixture) -> None:
    """A config saved after discovery logs in with its values, as HA's does."""
    device = _patch(mocker, MockTpapDevice())
    transport = _transport(tpap=_discovered(0, port=80))
    stored = transport._config.to_dict_control_credentials(
        credentials_hash=transport.credentials_hash
    )
    transport = TpapTransport(config=DeviceConfig.from_dict(stored))

    await transport.perform_handshake()

    assert device.calls["discover"] == 0
    assert transport._encryption_session is not None


@pytest.mark.parametrize(
    ("family", "pake", "expected"),
    [
        pytest.param(
            DeviceFamily.SmartIpCamera, [1], "setupcode", id="camera-setup-code"
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera, [0, 1], "setupcode", id="camera-one-before-zero"
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera, [1, 2], "userpw", id="camera-two-before-one"
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera, [0, 2], "userpw", id="camera-two-before-zero"
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera, [3], "shared_token", id="camera-token"
        ),
        pytest.param(DeviceFamily.SmartIpCamera, [], None, id="camera-empty-pake"),
        pytest.param(DeviceFamily.SmartIpCamera, None, None, id="camera-no-pake"),
        pytest.param(DeviceFamily.SmartTapoPlug, [0], "default_userpw", id="pake-0"),
        pytest.param(DeviceFamily.SmartTapoPlug, [1], "default_userpw", id="pake-1"),
        pytest.param(DeviceFamily.SmartTapoPlug, [5], "userpw", id="pake-5"),
        pytest.param(DeviceFamily.SmartTapoPlug, [2, 3], "userpw", id="two-before-3"),
        pytest.param(
            DeviceFamily.SmartTapoPlug, [0, 2], "default_userpw", id="zero-before-2"
        ),
        pytest.param(DeviceFamily.SmartTapoPlug, [], "default_userpw", id="empty-pake"),
        pytest.param(DeviceFamily.SmartTapoPlug, None, None, id="no-pake"),
        pytest.param(DeviceFamily.SmartTapoBulb, [5], "userpw", id="bulb-pake-5"),
        pytest.param(DeviceFamily.SmartTapoHub, [2], "userpw", id="hub"),
        pytest.param(DeviceFamily.IotSmartBulb, [2], "userpw", id="kasa-iot-pake-2"),
        pytest.param(
            DeviceFamily.IotSmartPlugSwitch, [0, 2], "userpw", id="kasa-iot-two-first"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [2, 3], "userpw", id="kasa-iot-two-before-3"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [3], "shared_token", id="kasa-iot-token"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [0], "default_userpw", id="kasa-iot-pake-0"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [1], "default_userpw", id="kasa-iot-pake-1"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [5], "default_userpw", id="kasa-iot-pake-5"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [], "default_userpw", id="kasa-iot-empty"
        ),
        pytest.param(DeviceFamily.IotSmartBulb, None, None, id="kasa-iot-no-pake"),
        pytest.param(
            DeviceFamily.SmartTapoRobovac, [2, 3], "userpw", id="robot-two-before-3"
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac, [5], "default_userpw", id="robot-pake-5"
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac, [9], "default_userpw", id="robot-unknown"
        ),
        pytest.param(DeviceFamily.SmartTapoRobovac, None, None, id="robot-no-pake"),
    ],
)
async def test_passcode_type(
    mocker: MockerFixture,
    family: DeviceFamily,
    pake: list[int] | None,
    expected: str | None,
) -> None:
    """The passcode type follows the passcode types the device announces."""
    # The device refuses the registration: only the request matters here
    refused = {"error_code": SmartErrorCode.UNKNOWN_METHOD_ERROR.value}
    device = _patch(mocker, MockTpapDevice(family, replies={"pake_register": refused}))
    transport = _transport(
        family,
        tpap=TpapParameters(tls=int(family in CAMERAS), pake=pake, mac=MOCK_MAC),
    )

    if expected is None:
        with pytest.raises(AuthenticationError, match="no supported passcode type"):
            await transport.perform_handshake()
        assert not device.calls
        return

    with pytest.raises(DeviceError, match="UNKNOWN_METHOD_ERROR"):
        await transport.perform_handshake()
    assert {p["passcode_type"] for p in device.params["pake_register"]} == {expected}


async def test_no_pake_from_in_band_discover_refuses_before_logging_in(
    mocker: MockerFixture,
) -> None:
    device = _patch(mocker, MockTpapDevice(pake=None))
    transport = _transport()

    with pytest.raises(AuthenticationError, match="no supported passcode type"):
        await transport.perform_handshake()

    assert device.calls == Counter({"discover": 1})


@pytest.mark.parametrize(
    ("family", "tls", "dac", "pake", "asked"),
    [
        pytest.param(DeviceFamily.SmartTapoPlug, 0, True, [0], True, id="tapo-pake-0"),
        pytest.param(DeviceFamily.SmartTapoPlug, 0, True, [5], True, id="tapo-pake-5"),
        pytest.param(
            DeviceFamily.SmartKasaPlug, 0, True, [2], False, id="tapo-pake-2-kp125m"
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug, 0, True, [0, 2], True, id="tapo-pake-0-2"
        ),
        pytest.param(DeviceFamily.SmartTapoPlug, 0, False, [0], False, id="no-dac"),
        pytest.param(DeviceFamily.SmartTapoPlug, 1, True, [0], False, id="tls"),
        pytest.param(DeviceFamily.IotSmartBulb, 0, True, [0], True, id="kasa-pake-0"),
        pytest.param(DeviceFamily.IotSmartBulb, 0, True, [5], False, id="kasa-pake-5"),
        pytest.param(
            DeviceFamily.IotSmartBulb, 0, True, [2], False, id="kasa-pake-2-kl420l5"
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac, 0, True, [0], True, id="robot-pake-0"
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac, 0, True, [5], False, id="robot-pake-5"
        ),
        pytest.param(DeviceFamily.SmartIpCamera, 0, True, [0], False, id="camera"),
    ],
)
async def test_dac(
    mocker: MockerFixture,
    dac_chain: DacChain,
    family: DeviceFamily,
    tls: int,
    dac: bool,
    pake: list[int],
    asked: bool,
) -> None:
    """The device proves itself with its attestation certificate where asked to."""
    device = _patch(
        mocker,
        MockTpapDevice(family, tls=tls, dac=dac, pake=pake, dac_chain=dac_chain),
    )
    transport = _transport(family, tpap=_discovered(tls, dac=dac, pake=pake))

    await transport.perform_handshake()

    assert ("dac_nonce" in device.params["pake_share"][0]) is asked
    assert transport._encryption_session is not None


async def test_dac_with_intermediate_certificate(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    chain = DacChain(with_ica=True)
    root = chain.root.public_bytes(serialization.Encoding.PEM).decode()
    monkeypatch.setattr(cert, "TPAP_ROOT_CA_PEM", root)
    _patch(mocker, MockTpapDevice(dac=True, pake=[0], dac_chain=chain))
    transport = _transport(tpap=_discovered(dac=True, pake=[0]))

    await transport.perform_handshake()

    assert transport._encryption_session is not None


@pytest.mark.parametrize(
    ("share", "match"),
    [
        pytest.param({"dac_ca": ABSENT}, "no DAC certificate or proof", id="no-cert"),
        pytest.param(
            {"dac_proof": ABSENT}, "no DAC certificate or proof", id="no-proof"
        ),
        pytest.param({"dac_proof": 1}, "Invalid DAC proof type", id="proof-not-text"),
        pytest.param(
            {"dac_proof": _b64(b"\x30\x06\x02\x01\x01\x02\x01\x01")},
            "Invalid DAC proof signature",
            id="wrong-signature",
        ),
        pytest.param(
            {"dac_ca": "not a certificate"},
            "Invalid certificate value",
            id="bad-certificate",
        ),
    ],
)
async def test_dac_failures(
    mocker: MockerFixture,
    dac_chain: DacChain,
    share: dict[str, Any],
    match: str,
) -> None:
    """An attestation that was asked for must be there and must check out."""
    _patch(mocker, MockTpapDevice(dac=True, pake=[0], dac_chain=dac_chain, share=share))
    transport = _transport(tpap=_discovered(dac=True, pake=[0]))

    with pytest.raises(KasaException, match=match):
        await transport.perform_handshake()

    assert transport._encryption_session is None


async def test_dac_from_another_root(mocker: MockerFixture) -> None:
    """A DAC that TP-Link's device root CA did not issue fails the login."""
    _patch(mocker, MockTpapDevice(dac=True, pake=[0], dac_chain=DacChain()))
    transport = _transport(tpap=_discovered(dac=True, pake=[0]))

    with pytest.raises(KasaException, match="DAC certificate chain verification"):
        await transport.perform_handshake()


@pytest.mark.parametrize(
    ("accepted", "shares"),
    [
        pytest.param(crypto.md5_hex(MOCK_PWD), 1, id="md5"),
        pytest.param(crypto.sha256_hex_upper(MOCK_PWD), 2, id="sha256"),
    ],
)
async def test_camera_tries_each_password_hash(
    mocker: MockerFixture, accepted: str, shares: int
) -> None:
    device = _patch(
        mocker,
        MockTpapDevice(DeviceFamily.SmartIpCamera, passcodes={"userpw": accepted}),
    )
    transport = _transport(DeviceFamily.SmartIpCamera)

    await transport.perform_handshake()

    assert device.calls["pake_share"] == shares
    assert transport._encryption_session is not None


@pytest.mark.parametrize(
    ("tpap", "url", "username"),
    [
        pytest.param(
            None, "https://127.0.0.1:443/", crypto.md5_hex("admin"), id="defaults"
        ),
        pytest.param(
            _discovered(0, port=None, dac=True, user_hash_type=1),
            "https://127.0.0.1:443/",
            crypto.sha256_hex_upper("admin"),
            id="discovery-values",
        ),
    ],
)
async def test_camera_hub_logs_in_as_a_camera(
    mocker: MockerFixture, tpap: TpapParameters | None, url: str, username: str
) -> None:
    """H200 and H500 hubs, SMART.TAPOHUB over https, follow the camera rules."""
    device = _patch(
        mocker,
        MockTpapDevice(
            DeviceFamily.SmartTapoHub,
            camera=True,
            passcodes={"userpw": crypto.sha256_hex_upper(MOCK_PWD)},
        ),
    )
    transport = _transport(DeviceFamily.SmartTapoHub, https=True, tpap=tpap)

    await transport.perform_handshake()

    # No in-band discover, https on the camera port, the camera user name,
    # md5 then sha256 of the password, and no attestation
    assert device.calls == Counter({"pake_register": 2, "pake_share": 2})
    assert {str(u) for u in device.urls} == {str(URL(url))}
    assert {p["username"] for p in device.params["pake_register"]} == {username}
    assert all("dac_nonce" not in p for p in device.params["pake_share"])
    assert transport._encryption_session is not None


async def test_camera_setup_code_uses_the_default_passcode(
    mocker: MockerFixture,
) -> None:
    """On the LAN a camera's setup code is not known, as in the Tapo app."""
    device = _patch(
        mocker,
        MockTpapDevice(
            DeviceFamily.SmartIpCamera,
            pake=[1],
            passcodes={"setupcode": crypto.mac_pass_from_device_mac(MOCK_MAC)},
        ),
    )
    transport = _transport(DeviceFamily.SmartIpCamera, tpap=_discovered(1, pake=[1]))

    await transport.perform_handshake()

    register = device.params["pake_register"][0]
    assert register["passcode_type"] == "setupcode"
    assert "auth_type" not in register
    assert device.calls["pake_share"] == 1
    assert transport._encryption_session is not None


async def test_camera_with_the_wrong_password(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    device = _patch(mocker, MockTpapDevice(DeviceFamily.SmartIpCamera))
    transport = _transport(
        DeviceFamily.SmartIpCamera, credentials=Credentials(MOCK_USER, "wrong")
    )

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(AuthenticationError, match="credentials rejected"),
    ):
        await transport.perform_handshake()

    assert device.calls["pake_share"] == 2
    assert "all password-based camera candidates failed" in caplog.text


OTHER_OWNER = crypto.md5_hex("other@example.com")


@pytest.mark.parametrize(
    ("username", "owner", "pake", "logs_in"),
    [
        pytest.param(MOCK_USER, crypto.md5_hex(MOCK_USER), [2], True, id="owner"),
        pytest.param(
            MOCK_USER, crypto.md5_hex(MOCK_USER).upper(), [2], True, id="hex-case"
        ),
        pytest.param(
            f" {MOCK_USER.upper()}", crypto.md5_hex(MOCK_USER), [2], True, id="email"
        ),
        pytest.param(
            "5550100", crypto.md5_hex("5550100@tplink.id"), [2], True, id="phone"
        ),
        pytest.param(MOCK_USER, None, [2], True, id="no-owner"),
        pytest.param(MOCK_USER, OTHER_OWNER, [0], True, id="default-passcode"),
        pytest.param(MOCK_USER, OTHER_OWNER, [2], False, id="other-account"),
        pytest.param(MOCK_USER, OTHER_OWNER, [3], False, id="other-account-token"),
    ],
)
async def test_owner(
    mocker: MockerFixture,
    username: str,
    owner: str | None,
    pake: list[int],
    logs_in: bool,
) -> None:
    """The account is only tried on a device it owns, as in the Tapo app."""
    device = _patch(mocker, MockTpapDevice(pake=pake))
    transport = _transport(
        credentials=Credentials(username, MOCK_PWD),
        tpap=_discovered(pake=pake, owner=owner),
    )

    if not logs_in:
        with pytest.raises(AuthenticationError, match="owned by another"):
            await transport.perform_handshake()
        assert not device.calls
        return

    await transport.perform_handshake()
    assert transport._encryption_session is not None


@pytest.mark.parametrize(
    ("family", "user_hash_type", "username"),
    [
        pytest.param(
            DeviceFamily.SmartIpCamera, 1, crypto.sha256_hex_upper("admin"), id="sha256"
        ),
        pytest.param(DeviceFamily.SmartIpCamera, 0, crypto.md5_hex("admin"), id="md5"),
        pytest.param(
            DeviceFamily.SmartIpCamera, None, crypto.md5_hex("admin"), id="not-set"
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug, 1, crypto.md5_hex("admin"), id="only-on-cameras"
        ),
    ],
)
async def test_register_user_name(
    mocker: MockerFixture,
    family: DeviceFamily,
    user_hash_type: int | None,
    username: str,
) -> None:
    device = _patch(mocker, MockTpapDevice(family))
    transport = _transport(
        family, tpap=_discovered(int(family in CAMERAS), user_hash_type=user_hash_type)
    )

    await transport.perform_handshake()

    assert device.params["pake_register"][0]["username"] == username


@pytest.mark.parametrize(
    ("family", "pake", "extra_crypt", "passcode"),
    [
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            [2],
            None,
            f"{MOCK_USER}/{MOCK_PWD}",
            id="user-and-password",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            [2],
            {"type": "password_shadow", "params": {"passwd_id": 3}},
            crypto._sha1_hex(crypto.md5_hex(MOCK_USER) + "_" + MOCK_MAC),
            id="user-and-mac-shadow",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            [2],
            PASSWORD_SHADOW,
            crypto._sha1_hex(crypto.md5_hex(MOCK_PWD)),
            id="camera-encodes-the-hash",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            [0],
            PASSWORD_SHADOW,
            crypto._sha1_hex(crypto.mac_pass_from_device_mac(MOCK_MAC)),
            id="default-passcode-encoded",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            [0],
            {"type": "password_shadow", "params": {"passwd_id": 3}},
            crypto.mac_pass_from_device_mac(MOCK_MAC),
            id="default-passcode-has-no-user",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            [0],
            PASSWORD_SHADOW,
            crypto._sha1_hex(crypto.mac_pass_from_device_mac(MOCK_MAC)),
            id="camera-default-passcode-encoded",
        ),
    ],
)
async def test_passcode_encoding(
    mocker: MockerFixture,
    family: DeviceFamily,
    pake: list[int],
    extra_crypt: dict[str, Any] | None,
    passcode: str,
) -> None:
    """The passcode is encoded as the device's extra_crypt says."""
    passcode_type = "default_userpw" if pake == [0] else "userpw"
    _patch(
        mocker,
        MockTpapDevice(
            family, extra_crypt=extra_crypt, passcodes={passcode_type: passcode}
        ),
    )
    transport = _transport(family, tpap=_discovered(int(family in CAMERAS), pake=pake))

    await transport.perform_handshake()

    assert transport._encryption_session is not None


async def test_default_passcode_as_is_with_the_attestation(
    mocker: MockerFixture, dac_chain: DacChain
) -> None:
    """A device that attests itself takes the default passcode unencoded."""
    raw = crypto.mac_pass_from_device_mac(MOCK_MAC)
    device = _patch(
        mocker,
        MockTpapDevice(
            pake=[0], dac=True, dac_chain=dac_chain, passcodes={"default_userpw": raw}
        ),
    )
    transport = _transport(tpap=_discovered(0, pake=[0], dac=True))

    await transport.perform_handshake()

    assert "dac_nonce" in device.params["pake_share"][0]
    assert transport._encryption_session is not None


@pytest.mark.parametrize(
    ("family", "pake", "credentials", "mac"),
    [
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            [2],
            Credentials(MOCK_USER, ""),
            MOCK_MAC,
            id="no-password",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            [2],
            Credentials(MOCK_USER, ""),
            MOCK_MAC,
            id="camera-no-password",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug, [0], CREDENTIALS, None, id="default-without-mac"
        ),
    ],
)
async def test_nothing_to_log_in_with(
    mocker: MockerFixture,
    family: DeviceFamily,
    pake: list[int],
    credentials: Credentials,
    mac: str | None,
) -> None:
    """Each try is a login the device counts, so an empty passcode is never sent."""
    device = _patch(mocker, MockTpapDevice(family))
    transport = _transport(
        family,
        credentials=credentials,
        tpap=_discovered(int(family in CAMERAS), pake=pake, mac=mac),
    )

    with pytest.raises(AuthenticationError, match="no credential candidates"):
        await transport.perform_handshake()

    assert not device.calls


@pytest.mark.parametrize("suite", [1, 2, 3, 4, 5, 8, 9])
async def test_cipher_suites(mocker: MockerFixture, suite: int) -> None:
    """The login works with each SPAKE2+ suite the device may answer with."""
    _patch(mocker, MockTpapDevice(suite=suite))
    transport = _transport()

    assert await transport.send(json_dumps(DUMMY_QUERY)) == DEVICE_RESPONSE


@pytest.mark.parametrize("cipher", ["aes_128_ccm", "aes_256_ccm", "chacha20_poly1305"])
async def test_session_ciphers(mocker: MockerFixture, cipher: str) -> None:
    _patch(mocker, MockTpapDevice(cipher=cipher))
    transport = _transport()

    assert await transport.send(json_dumps(DUMMY_QUERY)) == DEVICE_RESPONSE


@pytest.mark.parametrize(
    "iterations",
    [pytest.param(None, id="null"), pytest.param(ABSENT, id="absent")],
)
async def test_default_iterations(mocker: MockerFixture, iterations: Any) -> None:
    """Without an iteration count, both sides use 10000."""
    _patch(mocker, MockTpapDevice(register={"iterations": iterations}))
    transport = _transport()

    await transport.perform_handshake()

    assert transport._encryption_session is not None


@pytest.mark.parametrize(
    ("device_kwargs", "error", "match"),
    [
        pytest.param(
            {"replies": {"discover": (500, b"")}},
            KasaException,
            "TPAP discover failed",
            id="discover-status",
        ),
        pytest.param(
            {"replies": {"discover": {"error_code": -40401}}},
            _RetryableError,
            "SESSION_EXPIRED",
            id="discover-retryable",
        ),
        pytest.param(
            {"replies": {"discover": {"error_code": -1501}}},
            AuthenticationError,
            "LOGIN_ERROR",
            id="discover-authentication",
        ),
        pytest.param(
            {"replies": {"discover": {"error_code": -1002}}},
            DeviceError,
            "UNKNOWN_METHOD_ERROR",
            id="discover-device-error",
        ),
        pytest.param(
            {"replies": {"discover": {"error_code": "x"}}},
            DeviceError,
            "INTERNAL_UNKNOWN_ERROR",
            id="discover-unknown-code",
        ),
        pytest.param(
            {"replies": {"discover": {"error_code": 0}}},
            KasaException,
            "missing result object",
            id="discover-no-result",
        ),
        pytest.param(
            {"replies": {"discover": {"error_code": 0, "result": {}}}},
            KasaException,
            "missing tpap object",
            id="discover-no-tpap",
        ),
        pytest.param(
            {"replies": {"pake_register": (500, b"")}},
            KasaException,
            "TPAP pake_register failed",
            id="register-status",
        ),
        pytest.param(
            {"register": {"dev_random": ""}},
            KasaException,
            "missing dev_random",
            id="register-no-dev-random",
        ),
        pytest.param(
            {"register": {"dev_salt": ABSENT}},
            KasaException,
            "missing dev_salt",
            id="register-no-dev-salt",
        ),
        pytest.param(
            {"register": {"dev_share": ""}},
            KasaException,
            "missing dev_share",
            id="register-no-dev-share",
        ),
        pytest.param(
            {"register": {"cipher_suites": "bad"}},
            KasaException,
            "invalid cipher_suites",
            id="register-bad-suite",
        ),
        pytest.param(
            {"register": {"cipher_suites": None}},
            KasaException,
            "invalid cipher_suites",
            id="register-no-suite",
        ),
        pytest.param(
            {"register": {"cipher_suites": 6}},
            KasaException,
            "Unsupported TPAP suite type: 6",
            id="register-unsupported-suite",
        ),
        pytest.param(
            {"register": {"iterations": 0}},
            KasaException,
            "invalid iterations",
            id="register-no-iterations",
        ),
        pytest.param(
            {"register": {"iterations": "bad"}},
            KasaException,
            "invalid iterations",
            id="register-bad-iterations",
        ),
        pytest.param(
            {"register": {"iterations": 1_000_000}},
            KasaException,
            "invalid iterations",
            id="register-too-many-iterations",
        ),
        pytest.param(
            {"register": {"encryption": "bogus-cipher"}},
            KasaException,
            "Unsupported TPAP session cipher",
            id="register-unsupported-cipher",
        ),
        pytest.param(
            {"register": {"encryption": ""}},
            KasaException,
            "missing encryption",
            id="register-no-cipher",
        ),
        pytest.param(
            {
                "extra_crypt": {
                    "type": "password_shadow",
                    "params": {"passwd_id": 5, "passwd_prefix": "$5$rounds=999999$s"},
                }
            },
            KasaException,
            "too many passwd_prefix rounds",
            id="register-too-many-crypt-rounds",
        ),
        pytest.param(
            {"password": "other"},
            AuthenticationError,
            r"credentials rejected by device \(STAT_ACCESS_ERROR\), 14 attempts left",
            id="share-wrong-password",
        ),
        pytest.param(
            {"replies": {"pake_share": {"error_code": -1501}}},
            AuthenticationError,
            r"credentials rejected by device \(LOGIN_ERROR\)",
            id="share-authentication",
        ),
        pytest.param(
            {"replies": {"pake_share": {"error_code": -40401}}},
            DeviceError,
            r"SESSION_EXPIRED\(-40401\)",
            id="share-other-code",
        ),
        pytest.param(
            {"share": {"dev_confirm": ABSENT}},
            KasaException,
            "missing dev_confirm",
            id="share-no-confirmation",
        ),
        pytest.param(
            {"share": {"dev_confirm": "wrong"}},
            KasaException,
            "confirmation mismatch",
            id="share-wrong-confirmation",
        ),
        pytest.param(
            {"share": {"dev_confirm": str.swapcase}},
            KasaException,
            "confirmation mismatch",
            id="share-confirmation-in-other-case",
        ),
        pytest.param(
            {"share": {"stok": ABSENT}},
            KasaException,
            "Missing session fields",
            id="share-no-session",
        ),
        pytest.param(
            {"share": {"start_seq": ABSENT}},
            KasaException,
            "Missing session fields",
            id="share-no-sequence",
        ),
        pytest.param(
            {"share": {"start_seq": "bad"}},
            KasaException,
            "Invalid session fields",
            id="share-bad-sequence",
        ),
    ],
)
async def test_login_errors(
    mocker: MockerFixture,
    device_kwargs: dict[str, Any],
    error: type[Exception],
    match: str,
) -> None:
    _patch(mocker, MockTpapDevice(**device_kwargs))
    transport = _transport()

    with pytest.raises(error, match=match):
        await transport.perform_handshake()

    assert transport._encryption_session is None


@pytest.mark.parametrize(
    ("reply", "match"),
    [
        pytest.param(LOCKED, "retry in 30 minutes", id="locked-minutes"),
        pytest.param(
            {
                "error_code": -2101,
                "error_info": {"lockedMinute": 0, "remainAttempts": 0},
            },
            r"device blocked after failed logins \(error_code",
            id="no-attempts-left",
        ),
    ],
)
@pytest.mark.parametrize("step", ["discover", "pake_register", "pake_share"])
async def test_locked_device(
    mocker: MockerFixture, step: str, reply: dict[str, Any], match: str
) -> None:
    """A locked device stops the login at once, at any step, and is not retried."""
    device = _patch(mocker, MockTpapDevice(replies={step: reply}))
    protocol = SmartProtocol(transport=_transport())

    with pytest.raises(DeviceError, match=match) as exc_info:
        await protocol.query(DUMMY_QUERY)

    assert exc_info.value.error_code is SmartErrorCode.DEVICE_BLOCKED
    assert device.calls[step] == 1


async def test_locked_camera_tries_no_other_password_hash(
    mocker: MockerFixture,
) -> None:
    device = _patch(
        mocker,
        MockTpapDevice(DeviceFamily.SmartIpCamera, replies={"pake_share": LOCKED}),
    )
    transport = _transport(DeviceFamily.SmartIpCamera)

    with pytest.raises(DeviceError, match="device blocked"):
        await transport.perform_handshake()

    assert device.calls["pake_share"] == 1


@pytest.mark.parametrize(
    ("family", "device_kwargs", "protocol_class", "shares"),
    [
        pytest.param(
            DeviceFamily.SmartTapoHub,
            {"password": "other"},
            SmartProtocol,
            1,
            id="wrong-password",
        ),
        pytest.param(
            DeviceFamily.SmartTapoHub,
            {"replies": {"pake_share": {"error_code": -40401}}},
            SmartProtocol,
            1,
            id="retryable-code",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            {"password": "other"},
            SmartCamProtocol,
            2,
            id="camera-wrong-password",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            {"password": "other"},
            IotProtocol,
            1,
            id="kasa-iot-wrong-password",
        ),
    ],
)
async def test_refused_login_is_not_repeated(
    mocker: MockerFixture,
    family: DeviceFamily,
    device_kwargs: dict[str, Any],
    protocol_class: type[SmartProtocol] | type[IotProtocol],
    shares: int,
) -> None:
    """The device counts each refused login, so neither layer repeats one."""
    device = _patch(mocker, MockTpapDevice(family, **device_kwargs))
    protocol = protocol_class(transport=_transport(family))

    with pytest.raises(KasaException):
        await protocol.query(DUMMY_QUERY)

    assert device.calls["pake_share"] == shares


async def test_retryable_error_at_register_stops_the_candidates(
    mocker: MockerFixture,
) -> None:
    """A retryable error goes to the protocol before any other password hash."""
    retryable = {"error_code": SmartErrorCode.SESSION_EXPIRED.value}
    device = _patch(
        mocker,
        MockTpapDevice(
            DeviceFamily.SmartIpCamera, replies={"pake_register": retryable}
        ),
    )
    transport = _transport(DeviceFamily.SmartIpCamera)

    with pytest.raises(_RetryableError):
        await transport.perform_handshake()

    assert device.calls["pake_register"] == 1


# --------------------------
# Requests
# --------------------------


async def test_send(mocker: MockerFixture) -> None:
    device = _patch(mocker, MockTpapDevice(start_seq=7))
    transport = _transport()

    assert await transport.send(json_dumps(DUMMY_QUERY)) == DEVICE_RESPONSE
    assert await transport.send(json_dumps({"other": {}})) == DEVICE_RESPONSE

    assert device.calls["request"] == 2
    assert device.calls["pake_share"] == 1
    assert device.last_request == {"other": {}}


async def test_concurrent_requests_log_in_once(mocker: MockerFixture) -> None:
    device = _patch(mocker, MockTpapDevice())
    transport = _transport()

    await asyncio.gather(
        transport.send(json_dumps(DUMMY_QUERY)),
        transport.send(json_dumps(DUMMY_QUERY)),
    )

    assert device.calls["pake_share"] == 1
    assert device.calls["request"] == 2


@pytest.mark.parametrize(
    ("family", "protocol_class", "response"),
    [
        pytest.param(DeviceFamily.SmartTapoPlug, SmartProtocol, None, id="smart"),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            SmartCamProtocol,
            {
                "error_code": 0,
                "result": {
                    "responses": [
                        {"method": "foobar", "error_code": 0, "result": {"a": 1}}
                    ]
                },
            },
            id="smartcam",
        ),
        pytest.param(DeviceFamily.IotSmartBulb, IotProtocol, None, id="iot"),
    ],
)
async def test_query(
    mocker: MockerFixture,
    family: DeviceFamily,
    protocol_class: type[SmartProtocol] | type[IotProtocol],
    response: dict[str, Any] | None,
) -> None:
    device = _patch(mocker, MockTpapDevice(family, response=response))
    protocol = protocol_class(transport=_transport(family))

    assert await protocol.query(DUMMY_QUERY)

    assert device.calls["request"] == 1


DROPPED_SESSION = [
    pytest.param(500, b'{"error_code": -40420}', id="http-40420"),
    pytest.param(500, b'{"error_code": -40421}', id="http-40421"),
    pytest.param(500, b'{"err_code": -2402}', id="http-err_code-2402"),
    pytest.param(500, b'{"error_code": -2101}', id="http-2101"),
    pytest.param(200, {"error_code": -2402}, id="plain-reply-2402"),
    pytest.param(500, b'{"error_code": -40401}', id="http-40401"),
    pytest.param(200, {"error_code": -40401}, id="plain-reply-40401"),
]


@pytest.mark.parametrize(("status", "body"), DROPPED_SESSION)
async def test_dropped_session_is_retryable(
    mocker: MockerFixture, status: int, body: Any
) -> None:
    """A dropped session is reset and raised as retryable, for the protocol."""
    device = _patch(mocker, MockTpapDevice(ds_replies=[(status, body)]))
    transport = _transport()
    await transport.perform_handshake()

    with pytest.raises(_RetryableError, match="dropped the session"):
        await transport.send(json_dumps(DUMMY_QUERY))

    assert transport._encryption_session is None
    assert device.calls["request"] == 1


@pytest.mark.parametrize(("status", "body"), DROPPED_SESSION)
@pytest.mark.parametrize("protocol_class", [SmartProtocol, IotProtocol])
async def test_protocol_logs_in_again_after_a_dropped_session(
    mocker: MockerFixture,
    protocol_class: type[SmartProtocol] | type[IotProtocol],
    status: int,
    body: Any,
) -> None:
    mocker.patch.object(protocol_class, "BACKOFF_SECONDS_AFTER_TIMEOUT", 0)
    device = _patch(mocker, MockTpapDevice(ds_replies=[(status, body)]))
    protocol = protocol_class(transport=_transport())

    assert await protocol.query(DUMMY_QUERY)

    assert device.calls["pake_share"] == 2
    assert device.calls["request"] == 2


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b'{"error_code": -1}', id="other-code"),
        pytest.param(b"not json", id="not-json"),
        pytest.param(b"[1]", id="json-not-an-object"),
        pytest.param(b"", id="empty"),
    ],
)
async def test_request_failed(mocker: MockerFixture, body: bytes) -> None:
    """Other failures keep the session."""
    _patch(mocker, MockTpapDevice(ds_replies=[(500, body)]))
    transport = _transport()
    await transport.perform_handshake()

    with pytest.raises(KasaException, match="status 500"):
        await transport.send(json_dumps(DUMMY_QUERY))

    assert transport._encryption_session is not None


@pytest.mark.parametrize(
    ("device_kwargs", "error", "match"),
    [
        pytest.param(
            {"ds_replies": [(200, {"error_code": -40413})]},
            _RetryableError,
            "INVALID_NONCE",
            id="plain-retryable",
        ),
        pytest.param(
            {"ds_replies": [(200, {"error_code": -1002})]},
            DeviceError,
            "UNKNOWN_METHOD_ERROR",
            id="plain-device-error",
        ),
        pytest.param(
            {"ds_replies": [(200, b"\x00\x00\x00\x01")]},
            KasaException,
            "response too short",
            id="too-short",
        ),
        pytest.param(
            {"ds_replies": [(200, b"\x00\x00\x00\x01" + bytes(32))]},
            KasaException,
            "could not be decrypted",
            id="not-decryptable",
        ),
        pytest.param(
            {"response": b"[1]"},
            KasaException,
            "Unexpected TPAP JSON response body type",
            id="not-an-object",
        ),
    ],
)
async def test_request_errors(
    mocker: MockerFixture,
    device_kwargs: dict[str, Any],
    error: type[Exception],
    match: str,
) -> None:
    _patch(mocker, MockTpapDevice(**device_kwargs))
    transport = _transport()

    with pytest.raises(error, match=match):
        await transport.send(json_dumps(DUMMY_QUERY))


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param({"error_code": 0, "result": {"plain": True}}, id="success"),
        pytest.param({"result": {"plain": True}}, id="no-error-code"),
    ],
)
async def test_plain_reply_is_not_the_answer(
    mocker: MockerFixture, reply: dict[str, Any]
) -> None:
    """Only an encrypted reply is the device's answer."""
    _patch(mocker, MockTpapDevice(ds_replies=[(200, reply)]))
    transport = _transport()

    with pytest.raises(KasaException, match="was not encrypted"):
        await transport.send(json_dumps(DUMMY_QUERY))

    assert transport._encryption_session is not None


async def test_authentication_error_drops_the_session(mocker: MockerFixture) -> None:
    device = _patch(mocker, MockTpapDevice(ds_replies=[(200, {"error_code": -1501})]))
    transport = _transport()
    await transport.perform_handshake()

    with pytest.raises(AuthenticationError, match="LOGIN_ERROR"):
        await transport.send(json_dumps(DUMMY_QUERY))
    assert transport._encryption_session is None

    assert await transport.send(json_dumps(DUMMY_QUERY)) == DEVICE_RESPONSE
    assert device.calls["pake_share"] == 2


async def test_request_waiting_while_the_session_drops(mocker: MockerFixture) -> None:
    """A request that waited while another one lost the session is not sent."""
    device = _patch(
        mocker, MockTpapDevice(ds_replies=[(500, b'{"error_code": -2402}')])
    )
    transport = _transport()
    await transport.perform_handshake()

    results: list[Any] = await asyncio.gather(
        transport.send(json_dumps(DUMMY_QUERY)),
        transport.send(json_dumps(DUMMY_QUERY)),
        return_exceptions=True,
    )
    first, second = results

    assert isinstance(first, _RetryableError)
    assert isinstance(second, KasaException)
    assert "not established" in str(second)
    assert device.calls["request"] == 1


async def test_reset_keeps_the_login_values(mocker: MockerFixture) -> None:
    device = _patch(mocker, MockTpapDevice(tls=2, port=4567))
    transport = _transport()
    await transport.perform_handshake()

    await transport.reset()

    assert transport._encryption_session is None
    assert str(transport._app_url) == "https://127.0.0.1:4567"
    await transport.perform_handshake()
    assert str(device.urls[-1]) == str(URL("https://127.0.0.1:4567/"))


async def test_close(mocker: MockerFixture) -> None:
    _patch(mocker, MockTpapDevice())
    transport = _transport()
    await transport.perform_handshake()
    close = mocker.patch.object(HttpClient, "close")

    await transport.close()

    assert transport._encryption_session is None
    close.assert_awaited_once()


async def test_connection_logs_each_step(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Like KLAP, the debug log shows every step of a connection, no secrets."""
    _patch(mocker, MockTpapDevice(password=SECRET_PWD))
    transport = _transport(credentials=Credentials(MOCK_USER, SECRET_PWD))

    with caplog.at_level(logging.DEBUG, logger="kasa.transports.tpaptransport"):
        await transport.send(json_dumps(DUMMY_QUERY))

    messages = [record.getMessage() for record in caplog.records]
    expected = [
        "Starting handshake with 127.0.0.1",
        "Discover posted at",
        "Using the TPAP login from the in-band discover for 127.0.0.1: tls 0, "
        "port 80, pake [2], dac False",
        "pake_register posted at",
        "pake_register success at",
        "pake_share posted at",
        "pake_share confirmation matches the expected credentials (candidate 1/1)",
        "Handshake with 127.0.0.1 complete",
        "Device 127.0.0.1 query posted Host is 127.0.0.1, Sequence is 1",
        "Device 127.0.0.1 query response received",
    ]
    for text in expected:
        assert any(text in message for message in messages), text
    assert "Response status is 200" in caplog.text
    assert SECRET_PWD not in caplog.text
    assert MOCK_MAC not in caplog.text


# --------------------------
# Credentials
# --------------------------


async def test_credentials_hash() -> None:
    transport = _transport()

    credentials_hash = transport.credentials_hash

    assert credentials_hash is not None
    assert json.loads(base64.b64decode(credentials_hash)) == {
        "un": MOCK_USER,
        "pwd": MOCK_PWD,
    }


async def test_login_from_credentials_hash(mocker: MockerFixture) -> None:
    _patch(mocker, MockTpapDevice())
    credentials_hash = _transport().credentials_hash
    transport = _transport(credentials=None, credentials_hash=credentials_hash)

    await transport.perform_handshake()

    assert transport._config.credentials == CREDENTIALS
    assert transport.credentials_hash == credentials_hash


async def test_malformed_credentials_hash() -> None:
    transport = _transport(credentials=None, credentials_hash="not-base64-json")

    assert transport._config.credentials is None
    assert transport.credentials_hash is None


async def test_credentials_hash_from_ssl_aes() -> None:
    """A camera moving from SslAesTransport to TPAP keeps its credentials."""
    config = DeviceConfig(HOST, credentials=CREDENTIALS)
    config.connection_type.device_family = DeviceFamily.SmartIpCamera
    config.connection_type.https = True
    ssl_aes_hash = SslAesTransport(config=config).credentials_hash

    transport = _transport(
        DeviceFamily.SmartIpCamera, credentials=None, credentials_hash=ssl_aes_hash
    )

    assert transport._config.credentials == CREDENTIALS


async def test_credentials_hash_from_klap(mocker: MockerFixture) -> None:
    """A KLAP hash is one way, so update() refuses before any request."""
    device = _patch(mocker, MockTpapDevice())
    klap_hash = KlapTransportV2(
        config=DeviceConfig(HOST, credentials=CREDENTIALS)
    ).credentials_hash
    transport = _transport(credentials=None, credentials_hash=klap_hash)
    dev = SmartDevice(HOST, protocol=SmartProtocol(transport=transport))

    with pytest.raises(AuthenticationError):
        await dev.update()

    assert transport.credentials_hash is None
    assert not device.calls


# --------------------------
# Ports and TLS
# --------------------------


@pytest.mark.parametrize(
    ("family", "https", "http_port", "port"),
    [
        pytest.param(DeviceFamily.SmartTapoPlug, False, None, 80, id="http"),
        pytest.param(DeviceFamily.SmartTapoPlug, False, 8080, 8080, id="http-port"),
        pytest.param(DeviceFamily.SmartTapoRobovac, True, None, 4433, id="https"),
        pytest.param(DeviceFamily.SmartIpCamera, True, None, 443, id="camera"),
        pytest.param(
            DeviceFamily.SmartIpCamera, False, None, 443, id="camera-without-https"
        ),
        pytest.param(DeviceFamily.SmartTapoHub, True, None, 443, id="camera-hub"),
        pytest.param(DeviceFamily.SmartTapoHub, False, None, 80, id="hub"),
    ],
)
async def test_default_port(
    family: DeviceFamily, https: bool, http_port: int | None, port: int
) -> None:
    assert _transport(family, https=https, http_port=http_port).default_port == port


async def test_tls_0_is_plain_http(mocker: MockerFixture) -> None:
    device = _patch(mocker, MockTpapDevice())
    transport = _transport(tpap=_discovered(0))

    await transport.send(json_dumps(DUMMY_QUERY))

    assert device.ssl == [False, False, False]


async def test_tls_1_uses_the_shared_context(mocker: MockerFixture) -> None:
    """Unverified TLS uses the context the other https transports share."""
    device = _patch(mocker, MockTpapDevice())
    transport = _transport(tpap=_discovered(1, port=4433))

    await transport.send(json_dumps(DUMMY_QUERY))

    shared = await get_shared_ssl_context()
    assert device.ssl == [shared, shared, shared]
    enabled = {c["name"] for c in shared.get_ciphers()}
    assert {"ECDHE-ECDSA-AES128-SHA", "ECDHE-ECDSA-AES256-SHA"} <= enabled


@pytest.mark.parametrize("mac", [MOCK_MAC, None])
async def test_tls_2_context(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture, mac: str | None
) -> None:
    """ECDSA suites only, TP-Link's root CA, and the MAC check when it is known."""
    device = _patch(mocker, MockTpapDevice())
    transport = _transport(tpap=_discovered(2, port=4433, mac=mac, pake=[2]))

    with caplog.at_level(logging.DEBUG):
        await transport.send(json_dumps(DUMMY_QUERY))

    context = device.ssl[0]
    assert device.ssl == [context] * 3
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.get_ca_certs()
    tls12 = [c["name"] for c in context.get_ciphers() if c["protocol"] == "TLSv1.2"]
    assert tls12
    assert all(name.startswith("ECDHE-ECDSA-") for name in tls12)
    assert (context.sslobject_class is ssl.SSLObject) is (mac is None)
    assert ("No device MAC to check" in caplog.text) is (mac is None)


def _tls_handshake(client_ctx: ssl.SSLContext, server_ctx: ssl.SSLContext) -> None:
    """Run a TLS handshake in memory, raising what the client raises."""
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_ctx.wrap_bio(client_in, client_out)
    server = server_ctx.wrap_bio(server_in, server_out, server_side=True)
    client_done = server_done = False
    for _ in range(10):
        if not client_done:
            try:
                client.do_handshake()
                client_done = True
            except ssl.SSLWantReadError:
                pass
        server_in.write(client_out.read())
        if not server_done:
            try:
                server.do_handshake()
                server_done = True
            except ssl.SSLWantReadError:
                pass
        client_in.write(server_out.read())
        if client_done and server_done:
            return
    raise AssertionError("handshake did not finish")


@pytest.mark.parametrize(
    ("cert_mac", "matches"),
    [
        pytest.param(b"AABBCCDDEEFF", True, id="device-mac"),
        pytest.param(b"112233445566", False, id="other-device"),
    ],
)
async def test_tls_2_handshake_requires_the_device_mac(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, cert_mac: bytes, matches: bool
) -> None:
    """A real TLS handshake fails unless the certificate names the device MAC."""
    root_key = ec.generate_private_key(ec.SECP256R1())
    root = build_certificate(root_key, "test root", "test root", root_key, is_ca=True)
    device_key = ec.generate_private_key(ec.SECP256R1())
    device = build_certificate(
        device_key,
        "device",
        "test root",
        root_key,
        subject_alt_names=[mac_name(cert_mac)],
    )
    cert_file, key_file = tmp_path / "device.pem", tmp_path / "device.key"
    cert_file.write_bytes(device.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        device_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert_file, key_file)
    monkeypatch.setattr(
        cert, "TPAP_ROOT_CA_PEM", root.public_bytes(serialization.Encoding.PEM).decode()
    )
    transport = _transport(
        DeviceFamily.SmartTapoRobovac,
        https=True,
        tpap=_discovered(2, port=4433, mac="AA-BB-CC-DD-EE-FF"),
    )
    client_ctx = await transport.get_ssl_context()
    assert isinstance(client_ctx, ssl.SSLContext)

    if matches:
        _tls_handshake(client_ctx, server_ctx)
    else:
        with pytest.raises(ssl.SSLCertVerificationError, match="device MAC"):
            _tls_handshake(client_ctx, server_ctx)
