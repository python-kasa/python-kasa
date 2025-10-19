from __future__ import annotations

import base64
import hashlib
import json as jsonlib
import re
import struct

import aiohttp
import pytest
from ecdsa import NIST256p
from yarl import URL

from kasa.credentials import Credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from kasa.transports.tpaptransport import (
    _TAG_LEN,
    TpapTransport,
    _hkdf,
    _nonce,
    _SessionCipher,
)

# Transport tests are not designed for real devices
pytestmark = [pytest.mark.requires_dummy]

HOST = "127.0.0.1"


def test_len8le():
    b = b"abc"
    out = TpapTransport._len8le(b)
    assert len(out) == 8 + len(b)
    assert int.from_bytes(out[:8], "little") == len(b)
    assert out[8:] == b


def test_encode_w_rules():
    w = int.from_bytes(b"\x00\xff", "big")
    wb = TpapTransport._encode_w(w)
    assert wb == b"\xff"
    w2 = int.from_bytes(b"\x01\xff\xfe", "big")
    wb2 = TpapTransport._encode_w(w2)
    assert wb2 == b"\x01\xff\xfe"
    wb0 = TpapTransport._encode_w(0)
    assert wb0 == b"\x00"
    w3 = int.from_bytes(b"\x00\x01\x02\x03", "big")
    wb3 = TpapTransport._encode_w(w3)
    assert wb3 == b"\x01\x02\x03"
    assert len(wb3) == 3


def test_encode_w_forced_leading_zero():
    class ForcedInt(int):
        def bit_length(self):
            return 16

    w = ForcedInt(255)
    wb = TpapTransport._encode_w(w)
    assert wb == b"\xff"


def test_nonce_assembly():
    base = b"\x11" * 8 + b"\x00\x00\x00\x00"
    seq = 0xA5A5A5A5
    n = _nonce(base, seq)
    assert n[:-4] == base[:-4]
    assert n[-4:] == seq.to_bytes(4, "big")


def test_authkey_mask():
    out = TpapTransport._authkey_mask("abc", "XYZ", "0123456789abcdef")
    assert out == "9b9"


def test_sha1_username_mac_shadow():
    username = "user"
    mac12 = "aabbccddeeff"
    # codeql[py/weak-cryptographic-algorithm]:
    # Required by device firmware for credential compatibility.
    # Do not change.
    expected = hashlib.sha1(  # nosec B303  # noqa: S324
        (
            # codeql[py/weak-cryptographic-algorithm]:
            # Required by device firmware for credential compatibility.
            # Do not change.
            hashlib.md5(username.encode()).hexdigest() + "_" + "AA:BB:CC:DD:EE:FF"  # nosec B303  # noqa: S324
        ).encode()
    ).hexdigest()
    out = TpapTransport._sha1_username_mac_shadow(username, mac12, "ignored")
    assert out == expected
    assert TpapTransport._sha1_username_mac_shadow(username, "invalid", "pw") == "pw"


def test_password_shadow_variants():
    extra = {"type": "password_shadow", "params": {"passwd_id": 1}}
    out = TpapTransport._build_credentials(extra, "", "pw", "")
    # codeql[py/weak-cryptographic-algorithm]:
    # Required by device firmware for credential compatibility.
    # Do not change.
    assert out == hashlib.md5(b"pw").hexdigest()  # nosec B303  # noqa: S324
    extra = {"type": "password_shadow", "params": {"passwd_id": 2}}
    out = TpapTransport._build_credentials(extra, "", "pw", "")
    # codeql[py/weak-cryptographic-algorithm]:
    # Required by device firmware for credential compatibility.
    # Do not change.
    assert out == hashlib.sha1(b"pw").hexdigest()  # nosec B303  # noqa: S324
    extra = {
        "type": "password_shadow",
        "params": {"passwd_id": 5, "passwd_prefix": "x"},
    }
    out = TpapTransport._build_credentials(extra, "", "pw", "")
    assert out == "x$" + hashlib.sha256(b"pw").hexdigest()


def test_password_authkey_masking():
    extra = {
        "type": "password_authkey",
        "params": {"authkey_tmpkey": "a", "authkey_dictionary": "0123456789"},
    }
    out = TpapTransport._build_credentials(extra, "", "A", "")
    assert out == "2"


def test_password_sha_with_salt():
    salt = "SALT"
    salt_b64 = base64.b64encode(salt.encode()).decode()
    extra = {
        "type": "password_sha_with_salt",
        "params": {"sha_name": 0, "sha_salt": salt_b64},
    }
    out = TpapTransport._build_credentials(extra, "", "pw", "")
    expected = hashlib.sha256(("admin" + salt + "pw").encode()).hexdigest()
    assert out == expected


def test_password_sha_with_salt_bad_b64_falls_back():
    extra = {
        "type": "password_sha_with_salt",
        "params": {"sha_name": 0, "sha_salt": "***not-b64***"},
    }
    out = TpapTransport._build_credentials(extra, "", "pw", "")
    assert out == "pw"


def test_mac_pass_from_device_mac_shape():
    derived = TpapTransport._mac_pass_from_device_mac("AA:BB:CC:DD:EE:FF")
    assert isinstance(derived, str)
    assert len(derived) == 64
    assert re.fullmatch(r"[0-9A-F]{64}", derived) is not None


def test_hash_and_hmac_and_kdfs():
    data = b"abc"
    h256 = TpapTransport._hash("SHA256", data)
    h512 = TpapTransport._hash("SHA512", data)
    assert len(h256) == 32
    assert len(h512) == 64
    mac256 = TpapTransport._hmac("SHA256", b"k", data)
    mac512 = TpapTransport._hmac("SHA512", b"k", data)
    assert len(mac256) == 32
    assert len(mac512) == 64
    okm = TpapTransport._hkdf_expand("info", b"ikm", 42, "SHA256")
    assert len(okm) == 42
    okm2 = TpapTransport._hkdf_expand("info", b"ikm", 13, "SHA512")
    assert len(okm2) == 13
    out = _hkdf(b"ikm", salt=b"s", info=b"i", length=16, algo="SHA256")
    assert len(out) == 16


def test_pbkdf2_and_derive_ab():
    cred = b"cred"
    salt = b"salt"
    out = TpapTransport._pbkdf2_sha256(cred, salt, 100, 32)
    assert len(out) == 32
    a, b = TpapTransport._derive_ab(cred, salt, 10, 16)
    assert isinstance(a, int)
    assert isinstance(b, int)
    assert a > 0
    assert b > 0


def test_session_cipher_roundtrip_variants():
    shared_key = b"shared"
    for cipher_id in ("aes_128_ccm", "aes_256_ccm", "chacha20_poly1305"):
        c = _SessionCipher.from_shared_key(cipher_id, shared_key, hkdf_hash="SHA256")
        pt = b"hello world"
        ct = c.encrypt(pt, 1)
        assert c.decrypt(ct, 1) == pt


def test_rand_scalar_rejects_zero(mocker):
    order = NIST256p.order
    mocker.patch("kasa.transports.tpaptransport.secrets.randbelow", side_effect=[0, 5])
    assert TpapTransport._rand_scalar(order) == 5


@pytest.mark.asyncio
async def test_get_ssl_context_cached():
    transport = TpapTransport(config=DeviceConfig(HOST))
    ctx1 = await transport._get_ssl_context()
    ctx2 = await transport._get_ssl_context()
    assert ctx1 is ctx2
    assert ctx1.verify_mode.name == "CERT_NONE"
    assert transport._ssl_context is ctx1


@pytest.mark.asyncio
async def test_create_ssl_context():
    transport = TpapTransport(config=DeviceConfig(HOST))
    ctx = transport._create_ssl_context()
    assert ctx.check_hostname is False
    assert ctx.verify_mode.name == "CERT_NONE"


@pytest.mark.asyncio
async def test_perform_discover_success(mocker):
    device = MockTpapDevice(
        HOST, discover_mac="AA:BB:CC:DD:EE:FF", discover_suites=[2, 1]
    )
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    transport = TpapTransport(config=DeviceConfig(HOST))
    await transport._perform_discover()
    assert transport._discover_mac == "AA:BB:CC:DD:EE:FF"
    assert transport._discover_suites == [2, 1]
    await transport._perform_discover()
    assert transport._discover_mac == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_perform_discover_bad_status_and_body(mocker):
    device = MockTpapDevice(HOST, status_code=500)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    transport = TpapTransport(config=DeviceConfig(HOST))
    await transport._perform_discover()
    assert transport._discover_mac is None
    assert transport._discover_suites is None
    mocker.patch.object(transport._http_client, "post", return_value=(200, b"not-json"))
    await transport._perform_discover()
    assert transport._discover_mac is None
    assert transport._discover_suites is None


@pytest.mark.asyncio
async def test_perform_discover_suites_malformed(mocker):
    device = MockTpapDevice(HOST, malformed_suites=True)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    transport = TpapTransport(config=DeviceConfig(HOST))
    await transport._perform_discover()
    assert transport._discover_mac == "AA:BB:CC:DD:EE:FF"
    assert transport._discover_suites is None


@pytest.mark.asyncio
async def test_perform_handshake_requires_mac_suite0(mocker):
    device = MockTpapDevice(HOST, discover_suites=[0], discover_mac=None)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    with pytest.raises(AuthenticationError, match="requires MAC-derived passcode"):
        await transport.perform_handshake()


@pytest.mark.asyncio
async def test_perform_handshake_suite0_uses_mac_passcode(mocker):
    device = MockTpapDevice(
        HOST,
        discover_suites=[0],
        discover_mac="AA:BB:CC:DD:EE:FF",
        share_dev_confirm="00" * 32,
        share_stok="MAC",
        share_start_seq=2,
    )
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    mocker.patch.object(TpapTransport, "_hmac", return_value=b"\x00" * 32)
    mac_fn = mocker.patch.object(
        TpapTransport,
        "_mac_pass_from_device_mac",
        wraps=TpapTransport._mac_pass_from_device_mac,
    )
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    await transport.perform_handshake()
    assert transport._state is transport._state.ESTABLISHED
    assert transport._session_id == "MAC"
    assert transport._seq == 2
    assert mac_fn.called


@pytest.mark.asyncio
async def test_perform_handshake_success_minimal(mocker):
    def _fake_hmac(alg, key, data):
        return b"\x00" * (64 if alg.upper() == "SHA512" else 32)

    mocker.patch.object(TpapTransport, "_hmac", side_effect=_fake_hmac)
    device = MockTpapDevice(
        HOST,
        discover_suites=[1],
        discover_mac=None,
        share_dev_confirm="00" * 32,
        share_stok="TEST",
        share_start_seq=9,
    )
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    await transport.perform_handshake()
    assert transport._state is transport._state.ESTABLISHED
    assert transport._session_id == "TEST"
    assert transport._seq == 9
    assert transport._cipher is not None
    assert transport._cipher.cipher_id == "aes_128_ccm"
    assert transport._ds_url is not None

    class CT:
        pass

    transport._config.connection_type = CT()
    transport._config.connection_type.http_port = 5555
    assert transport.default_port == 5555


@pytest.mark.asyncio
async def test_perform_handshake_dev_confirm_mismatch(mocker):
    mocker.patch.object(TpapTransport, "_hmac", return_value=b"\x00" * 32)
    device = MockTpapDevice(
        HOST,
        discover_suites=[1],
        discover_mac=None,
        share_dev_confirm="ff",
        share_stok="TEST",
        share_start_seq=1,
    )
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    with pytest.raises(KasaException, match="confirmation mismatch"):
        await transport.perform_handshake()


@pytest.mark.asyncio
async def test_perform_handshake_missing_session_fields(mocker):
    mocker.patch.object(TpapTransport, "_hmac", return_value=b"\x00" * 32)
    device = MockTpapDevice(
        HOST,
        discover_suites=[1],
        discover_mac=None,
        share_dev_confirm="00" * 32,
        share_stok=None,
        share_start_seq=9,
    )
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=device.post)
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    with pytest.raises(KasaException, match="Missing session fields"):
        await transport.perform_handshake()


@pytest.mark.asyncio
async def test_post_login_paths(mocker):
    transport = TpapTransport(config=DeviceConfig(HOST))
    mocker.patch.object(transport._http_client, "post", return_value=(500, b"x"))
    with pytest.raises(KasaException, match="bad status/body"):
        await transport._post_login({"sub_method": "x"}, step_name="register")
    mocker.patch.object(transport._http_client, "post", return_value=(200, b"x"))
    with pytest.raises(KasaException, match="bad status/body"):
        await transport._post_login({"sub_method": "x"}, step_name="register")
    mocker.patch.object(
        transport._http_client,
        "post",
        return_value=(200, {"error_code": SmartErrorCode.LOGIN_ERROR.value}),
    )
    with pytest.raises(AuthenticationError):
        await transport._post_login({"sub_method": "x"}, step_name="register")
    mocker.patch.object(
        transport._http_client,
        "post",
        return_value=(200, {"error_code": SmartErrorCode.UNSPECIFIC_ERROR.value}),
    )
    with pytest.raises(_RetryableError):
        await transport._post_login({"sub_method": "x"}, step_name="register")
    mocker.patch.object(
        transport._http_client,
        "post",
        return_value=(200, {"error_code": SmartErrorCode.DEVICE_BLOCKED.value}),
    )
    with pytest.raises(DeviceError):
        await transport._post_login({"sub_method": "x"}, step_name="register")
    mocker.patch.object(
        transport._http_client,
        "post",
        return_value=(200, {"error_code": 0, "result": {"ok": 1}}),
    )
    res = await transport._post_login({"sub_method": "x"}, step_name="register")
    assert res == {"ok": 1}


@pytest.mark.asyncio
async def test_handle_response_error_code_success():
    transport = TpapTransport(config=DeviceConfig(HOST))
    transport._handle_response_error_code({"error_code": 0}, "msg")
    transport._handle_response_error_code({"error_code": "not-int"}, "msg")


@pytest.mark.asyncio
async def test_send_success_aes128(mocker):
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    shared_key = b"shared-key-material-for-tests"
    cipher = _SessionCipher.from_shared_key(
        "aes_128_ccm", shared_key, hkdf_hash="SHA256"
    )
    transport._cipher = cipher
    transport._seq = 1
    transport._ds_url = URL(f"https://{HOST}:4433/stok=TEST/ds")
    transport._state = transport._state.ESTABLISHED
    req_obj = {"method": "get_info", "params": {"x": 1}}
    req_str = jsonlib.dumps(req_obj)

    def _mock_post(url, *, json=None, data=None, headers=None, ssl=None, params=None):
        assert url == transport._ds_url
        assert isinstance(data, bytes | bytearray)
        raw = bytes(data)
        rseq = struct.unpack(">I", raw[:4])[0]
        plaintext = cipher.decrypt(raw[4:], rseq).decode()
        assert jsonlib.loads(plaintext) == req_obj
        resp_obj = {"result": {"ok": True}, "error_code": 0}
        resp_ct = cipher.encrypt(jsonlib.dumps(resp_obj).encode(), rseq)
        return 200, struct.pack(">I", rseq) + resp_ct

    mocker.patch.object(transport._http_client, "post", side_effect=_mock_post)
    resp = await transport.send(req_str)
    assert resp == {"result": {"ok": True}, "error_code": 0}


@pytest.mark.asyncio
async def test_send_success_chacha(mocker):
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    shared_key = b"another-shared-key"
    cipher = _SessionCipher.from_shared_key(
        "chacha20_poly1305", shared_key, hkdf_hash="SHA256"
    )
    transport._cipher = cipher
    transport._seq = 7
    transport._ds_url = URL(f"https://{HOST}:4433/stok=TEST/ds")
    transport._state = transport._state.ESTABLISHED
    req_str = jsonlib.dumps({"method": "dummy", "params": None})

    def _mock_post(url, *, json=None, data=None, headers=None, ssl=None, params=None):
        raw = bytes(data)
        rseq = struct.unpack(">I", raw[:4])[0]
        resp_obj = {"ok": 1}
        resp_ct = cipher.encrypt(jsonlib.dumps(resp_obj).encode(), rseq)
        return 200, struct.pack(">I", rseq) + resp_ct

    mocker.patch.object(transport._http_client, "post", side_effect=_mock_post)
    resp = await transport.send(req_str)
    assert resp == {"ok": 1}


@pytest.mark.asyncio
async def test_send_unexpected_status(mocker):
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    transport._cipher = _SessionCipher.from_shared_key(
        "aes_128_ccm", b"x", hkdf_hash="SHA256"
    )
    transport._seq = 1
    transport._ds_url = URL(f"https://{HOST}:4433/stok=TEST/ds")
    transport._state = transport._state.ESTABLISHED
    mocker.patch.object(transport._http_client, "post", return_value=(500, b""))
    with pytest.raises(KasaException, match="unexpected status 500"):
        await transport.send(jsonlib.dumps({"m": 1}))


@pytest.mark.asyncio
async def test_send_response_too_short(mocker):
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )
    transport._cipher = _SessionCipher.from_shared_key(
        "aes_128_ccm", b"x", hkdf_hash="SHA256"
    )
    transport._seq = 1
    transport._ds_url = URL(f"https://{HOST}:4433/stok=TEST/ds")
    transport._state = transport._state.ESTABLISHED
    too_short = b"\x00\x00\x00\x01" + b"\x00" * (_TAG_LEN - 1)
    mocker.patch.object(transport._http_client, "post", return_value=(200, too_short))
    with pytest.raises(KasaException, match="response too short"):
        await transport.send(jsonlib.dumps({"m": 1}))


@pytest.mark.asyncio
async def test_send_not_established_raises(mocker):
    transport = TpapTransport(config=DeviceConfig(HOST))
    transport._state = transport._state.ESTABLISHED
    with pytest.raises(KasaException, match="not established"):
        await transport.send("{}")


@pytest.mark.asyncio
async def test_send_dict_response_passthrough(mocker):
    transport = TpapTransport(
        config=DeviceConfig(HOST, credentials=Credentials("u", "p"))
    )

    async def _fake_handshake():
        transport._cipher = _SessionCipher.from_shared_key(
            "aes_128_ccm", b"x", hkdf_hash="SHA256"
        )
        transport._seq = 1
        transport._ds_url = URL(f"https://{HOST}:4433/stok=TEST/ds")
        transport._state = transport._state.ESTABLISHED

    mocker.patch.object(transport, "perform_handshake", side_effect=_fake_handshake)
    mocker.patch.object(
        transport._http_client,
        "post",
        return_value=(200, {"error_code": 0, "result": {"foo": "bar"}}),
    )
    resp = await transport.send(jsonlib.dumps({"m": 1}))
    assert resp == {"error_code": 0, "result": {"foo": "bar"}}


@pytest.mark.asyncio
async def test_reset_and_close(mocker):
    transport = TpapTransport(config=DeviceConfig(HOST))
    transport._state = transport._state.ESTABLISHED
    transport._session_id = "stok"
    transport._seq = 1
    transport._cipher = _SessionCipher.from_shared_key(
        "aes_128_ccm", b"x", hkdf_hash="SHA256"
    )
    transport._ds_url = URL(f"https://{HOST}:4433/stok=TEST/ds")
    await transport.reset()
    assert transport._state is transport._state.HANDSHAKE_REQUIRED
    assert transport._session_id is None
    assert transport._seq is None
    assert transport._cipher is None
    assert transport._ds_url is None

    async def _noop_close():
        return None

    mocker.patch.object(transport._http_client, "close", side_effect=_noop_close)
    await transport.close()


@pytest.mark.asyncio
async def test_credentials_hash_is_none():
    assert TpapTransport(config=DeviceConfig(HOST)).credentials_hash is None


def test_build_credentials_pid3_via_extra_crypt():
    extra = {"type": "password_shadow", "params": {"passwd_id": 3}}
    username = "user"
    mac12 = "aabbccddeeff"
    passcode = "pw"
    out = TpapTransport._build_credentials(extra, username, passcode, mac12)
    expected = TpapTransport._sha1_username_mac_shadow(username, mac12, passcode)
    assert out == expected


def test_build_credentials_password_shadow_default_passthrough():
    extra = {"type": "password_shadow", "params": {"passwd_id": 999}}
    assert TpapTransport._build_credentials(extra, "", "pw", "") == "pw"


def test_build_credentials_unknown_type_fallback():
    extra = {"type": "totally_unknown", "params": {}}
    assert TpapTransport._build_credentials(extra, "", "pw", "") == "pw"


class MockTpapDevice:
    """
    Minimal TPAP device mock to exercise discover and handshake flows via HttpClient.

    For register/share, we don't implement the full SPAKE2+ responder.
    Tests patch TpapTransport._hmac to deterministic output so we can control dev_confirm.
    """

    class _mock_response:
        def __init__(self, status: int, payload: dict | bytes):
            self.status = status
            self._payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_t, exc_v, exc_tb):
            pass

        async def read(self):
            if isinstance(self._payload, dict):
                return jsonlib.dumps(self._payload).encode()
            return self._payload

    def __init__(
        self,
        host: str,
        *,
        status_code: int = 200,
        discover_suites: list[int] | None = None,
        discover_mac: str | None = "AA:BB:CC:DD:EE:FF",
        share_dev_confirm: str = "00" * 32,
        share_stok: str | None = "TEST",
        share_start_seq: int = 9,
        malformed_suites: bool = False,
        force_non_json: bool = False,
    ):
        self.host = host
        self.status_code = status_code
        self.discover_suites = [2, 1] if discover_suites is None else discover_suites
        self.discover_mac = discover_mac
        self.share_dev_confirm = share_dev_confirm
        self.share_stok = share_stok
        self.share_start_seq = share_start_seq
        self.malformed_suites = malformed_suites
        self.force_non_json = force_non_json

    async def post(
        self, url: URL, *, headers=None, params=None, json=None, data=None, **__
    ):
        if url == URL(f"https://{self.host}:4433/"):
            if self.status_code != 200:
                return self._mock_response(self.status_code, b"err")
            if self.force_non_json:
                return self._mock_response(200, b"not-json")
            sub_method = (json or {}).get("params", {}).get("sub_method")
            if sub_method == "discover":
                pake = "bad-shape" if self.malformed_suites else self.discover_suites
                body = {
                    "error_code": 0,
                    "result": {
                        "mac": self.discover_mac,
                        "tpap": {"pake": pake},
                    },
                }
                return self._mock_response(200, body)
            if sub_method == "pake_register":
                body = {
                    "error_code": 0,
                    "result": {
                        "dev_random": "00" * 16,
                        "dev_salt": "00" * 16,
                        "dev_share": TpapTransport.P256_N_COMP.hex(),
                        "cipher_suites": 1,
                        "iterations": 1,
                        "encryption": "aes_128_ccm",
                        "extra_crypt": {},
                    },
                }
                return self._mock_response(200, body)
            if sub_method == "pake_share":
                body = {
                    "error_code": 0,
                    "result": {
                        "dev_confirm": self.share_dev_confirm,
                        "stok": self.share_stok,
                        "start_seq": self.share_start_seq,
                    },
                }
                return self._mock_response(200, body)
        return self._mock_response(200, b"")
