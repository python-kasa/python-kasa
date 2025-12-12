from __future__ import annotations

import base64
import hashlib
import logging
import os
import ssl
from dataclasses import dataclass
from datetime import UTC
from typing import Any, cast

import pytest
from yarl import URL

import kasa.transports.tpaptransport as tp
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)


def _make_self_signed_cert_and_key() -> tuple[str, str]:
    from datetime import datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


def _make_rsa_key_pem() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _make_ec_cert_and_key() -> tuple[str, bytes, object]:
    from datetime import datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    priv = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Dev NOC")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(priv.public_key())
        .serial_number(1)
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .sign(priv, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM).decode()
    pub_uncompressed = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return cert_pem, pub_uncompressed, priv


# --------------------------
# _SessionCipher unit tests
# --------------------------


@pytest.mark.asyncio
async def test_session_cipher_all():
    with pytest.raises(ValueError, match="base nonce too short"):
        tp._SessionCipher._nonce_from_base(b"\x00\x01\x02", 1)

    c1 = tp._SessionCipher.from_shared_key("aes_128_ccm", b"shared-aes")
    msg = b"hello"
    ct = c1.encrypt(msg, 7)
    assert c1.decrypt(ct, 7) == msg

    c2 = tp._SessionCipher.from_shared_key("chacha20_poly1305", b"shared-chacha")
    m2 = b"world"
    ct2 = c2.encrypt(m2, 9)
    assert c2.decrypt(ct2, 9) == m2

    key, nonce = tp._SessionCipher.key_nonce_from_shared(b"k" * 16, "aes_256_ccm")
    cts, tag = tp._SessionCipher.sec_encrypt("aes_256_ccm", key, nonce, b"data", seq=3)
    out = tp._SessionCipher.sec_decrypt("aes_256_ccm", key, nonce, cts, tag, seq=3)
    assert out == b"data"

    keyc, noncec = tp._SessionCipher.key_nonce_from_shared(
        b"c" * 32, "chacha20_poly1305"
    )
    ctc, tagc = tp._SessionCipher.sec_encrypt(
        "chacha20_poly1305", keyc, noncec, b"x", seq=2
    )
    outc = tp._SessionCipher.sec_decrypt(
        "chacha20_poly1305", keyc, noncec, ctc, tagc, seq=2
    )
    assert outc == b"x"

    k512, n512 = tp._SessionCipher.key_nonce_from_shared(
        b"s" * 32, "aes_128_ccm", hkdf_hash="SHA512"
    )
    assert len(k512) == 16
    assert len(n512) == 12


def test_sessioncipher_hkdf_sha512_branch():
    c = tp._SessionCipher.from_shared_key(
        "aes_128_ccm", b"shared-secret", hkdf_hash="SHA512"
    )
    pt = b"hello-sha512"
    ct = c.encrypt(pt, 1)
    assert c.decrypt(ct, 1) == pt


# --------------------------
# NOCClient tests
# --------------------------


def _install_requests_stubs_for_noc(
    monkeypatch, cert_user: str, inter_pem: str, root_pem: str
):
    def fake_post(url: str, **kwargs):
        class FakeResp:
            def __init__(self, payload: dict[str, Any], status: int = 200):
                self._p = payload
                self._s = status

            def raise_for_status(self):
                if self._s != 200:
                    raise RuntimeError(f"HTTP {self._s}")

            def json(self) -> dict[str, Any]:
                return self._p

        if url.endswith("/"):
            return FakeResp({"result": {"token": "tok", "accountId": "acc"}})
        if "getAppServiceUrlById" in url:
            return FakeResp(
                {"result": {"serviceList": [{"serviceUrl": "https://svc"}]}}
            )
        if url.endswith("/v1/certificate/noc/app/apply"):
            chain = inter_pem + root_pem
            return FakeResp(
                {"result": {"certificate": cert_user, "certificateChain": chain}}
            )
        return FakeResp({}, 404)

    monkeypatch.setattr(tp.requests, "post", fake_post)


@pytest.mark.asyncio
async def test_nocclient_apply_get_and_split_success(monkeypatch, tmp_path):
    cert_user, _ = _make_self_signed_cert_and_key()
    inter_pem, _ = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()
    _install_requests_stubs_for_noc(monkeypatch, cert_user, inter_pem, root_pem)

    client = tp.NOCClient()
    data = client.apply("user@example.com", os.getenv("KASA_TEST_PW", "pwd123"))  # noqa: S106
    assert data.nocPrivateKey
    assert data.nocCertificate
    assert data.nocIntermediateCertificate
    assert data.nocRootCertificate

    again = client.get()
    assert again.nocCertificate == data.nocCertificate

    again2 = client.apply("user@example.com", "pwd")
    assert again2.nocCertificate == data.nocCertificate

    inter2, root2 = tp.NOCClient._split_chain(inter_pem + root_pem)  # type: ignore[attr-defined]
    assert inter2.endswith("-----END CERTIFICATE-----")
    assert isinstance(root2, str)


def test_nocclient_get_raises_when_empty_cache():
    client = tp.NOCClient()
    with pytest.raises(KasaException, match="No NOC materials"):
        client.get()


def test_nocclient_apply_exception_logs_and_raises(monkeypatch):
    """Force an exception in apply() to cover the except/log/re-raise path."""
    client = tp.NOCClient()

    def fake_login(self, username, password):  # noqa: ARG001
        raise RuntimeError("login boom")

    monkeypatch.setattr(tp.NOCClient, "_login", fake_login, raising=True)
    with pytest.raises(KasaException, match="TPLink Cloud NOC apply failed") as excinfo:
        client.apply("u", "p")
    cause = excinfo.value.__cause__
    assert isinstance(cause, Exception)
    assert "login boom" in str(cause)


# --------------------------
# BaseAuthContext tests
# --------------------------


@pytest.mark.asyncio
async def test_baseauth_login_and_tslp_success_and_errors(monkeypatch):
    class DummyHTTP:
        def __init__(self, ok=True):
            self.ok = ok

        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            if self.ok:
                return 200, {"error_code": 0, "result": {"ok": True}}
            return 500, b"x"

    class DummyTransport:
        def __init__(self, ok=True):
            self._http_client = DummyHTTP(ok=ok)
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self, ok=True):
            self._transport = DummyTransport(ok=ok)

        def _handle_response_error_code(self, resp, msg):
            return None

    ctx = tp.BaseAuthContext(DummyAuth())
    r = await ctx._login({"a": 1}, step_name="s")
    assert r == {"ok": True}
    r2 = await ctx._login({"b": 2}, step_name="t")
    assert r2 == {"ok": True}

    ctx_bad = tp.BaseAuthContext(DummyAuth(ok=False))
    with pytest.raises(KasaException, match="bad status/body"):
        await ctx_bad._login({}, step_name="x")


@pytest.mark.asyncio
async def test_baseauth_login_200_but_not_dict():
    class DummyHTTP:
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            return 200, b"x"

    class DummyTransport:
        def __init__(self):
            self._http_client = DummyHTTP()
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()

        def _handle_response_error_code(self, resp, msg):
            return None

    ctx = tp.BaseAuthContext(DummyAuth())
    with pytest.raises(KasaException, match="bad status/body"):
        await ctx._login({"a": 1}, step_name="s")


@pytest.mark.asyncio
async def test_baseauth_login_missing_result_returns_empty():
    class DummyHTTP:
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            return 200, {"error_code": 0}

    class DummyTransport:
        def __init__(self):
            self._http_client = DummyHTTP()
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()

        def _handle_response_error_code(self, resp, msg):
            return None

    ctx = tp.BaseAuthContext(DummyAuth())
    assert await ctx._login({"x": 1}, step_name="s") == {}
    assert await ctx._login({"y": 2}, step_name="t") == {}


# TSLP wrapping/parsing and TSLP-specific login were removed; tests adapted


# --------------------------
# NocAuthContext tests
# --------------------------


def test_nocauth_init_raises_when_no_noc():
    class DummyTransport:
        def __init__(self):
            self._http_client = None
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"
            self._username = "user"

        async def _get_ssl_context(self):
            return False

    bad_auth = type(
        "A",
        (),
        {
            "_transport": DummyTransport(),
            "_noc_data": None,
            "_ensure_noc": lambda self: None,
        },
    )()
    with pytest.raises(KasaException, match="NOC materials unavailable"):
        tp.NocAuthContext(bad_auth)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_nocauth_flow_success_and_errors(monkeypatch):
    @dataclass
    class TlaSessionCompat(tp.TlaSession):  # type: ignore[misc]
        weakCipher: bool = False

    monkeypatch.setattr(tp, "TlaSession", TlaSessionCompat, raising=True)

    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyHTTP:
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            json_mod = __import__("json")
            param_json = json if json is not None else None
            j = param_json or {}
            if not j and data:
                try:
                    if isinstance(data, bytes | bytearray) and len(data) >= 24:
                        try:
                            length = int.from_bytes(data[4:8], "big")
                            payload = bytes(data[24 : 24 + length])
                            j = json_mod.loads(payload.decode("utf-8"))
                        except Exception:
                            j = {}
                except Exception:
                    j = {}
            p = j.get("params", {})
            if p and p.get("sub_method") == "noc_kex":
                return 200, {
                    "error_code": 0,
                    "result": {
                        "dev_pk": base64.b64encode(b"\x04" + b"\x01" * 64).decode(),
                        "encryption": "aes_128_ccm",
                        "expired": 99,
                    },
                }
            if p and p.get("sub_method") == "noc_proof":
                return 200, {
                    "error_code": 0,
                    "result": {
                        "dev_proof_encrypt": base64.b64encode(b"\x00").decode(),
                        "tag": base64.b64encode(b"\x00" * 16).decode(),
                        "sessionId": "SID",
                        "start_seq": 5,
                        "expired": 123,
                    },
                }
            return 200, {"error_code": 0, "result": {}}

    class DummyTransport:
        def __init__(self):
            self._http_client = DummyHTTP()
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"
            self._username = "user"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()
            self._noc_data = tp.TpapNOCData(
                nocPrivateKey=key_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            )

        def _handle_response_error_code(self, resp, msg):
            return None

        def _ensure_noc(self):
            return None

    ctx = tp.NocAuthContext(DummyAuth())
    monkeypatch.setattr(
        ctx, "_derive_shared_secret", lambda *_: b"shared", raising=True
    )
    monkeypatch.setattr(ctx, "_sign_user_proof", lambda *a, **k: b"SIGN", raising=True)
    monkeypatch.setattr(
        tp._SessionCipher,
        "sec_decrypt",
        classmethod(lambda cls, *args, **kwargs: b'{"dev_noc":"X","proof":"ab"}'),
        raising=True,
    )
    monkeypatch.setattr(ctx, "_verify_device_proof", lambda *a, **k: None, raising=True)

    out = await ctx.start()
    assert isinstance(out, tp.TlaSession)
    assert out.sessionId == ""
    assert out.startSequence == 5
    assert out.sessionType == "NOC"

    class DummyHTTPMissingDevPk:
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            json_mod = __import__("json")
            param_json = json if json is not None else None
            j = param_json or {}
            if not j and data:
                try:
                    if isinstance(data, bytes | bytearray) and len(data) >= 24:
                        try:
                            length = int.from_bytes(data[4:8], "big")
                            payload = bytes(data[24 : 24 + length])
                            j = json_mod.loads(payload.decode("utf-8"))
                        except Exception:
                            j = {}
                except Exception:
                    j = {}
            p = j.get("params", {})
            if p and p.get("sub_method") == "noc_kex":
                return 200, {"error_code": 0, "result": {"encryption": "aes_128_ccm"}}
            return 200, {"error_code": 0, "result": {}}

    ctx2 = tp.NocAuthContext(DummyAuth())
    ctx2._transport._http_client = DummyHTTPMissingDevPk()  # type: ignore[attr-defined]
    with pytest.raises(KasaException, match="missing dev_pk"):
        await ctx2.start()

    class DummyHTTPNoDevProof(DummyHTTP):
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            json_mod = __import__("json")
            param_json = json if json is not None else None
            j = param_json or {}
            if not j and data:
                try:
                    if isinstance(data, bytes | bytearray) and len(data) >= 24:
                        try:
                            length = int.from_bytes(data[4:8], "big")
                            payload = bytes(data[24 : 24 + length])
                            j = json_mod.loads(payload.decode("utf-8"))
                        except Exception:
                            j = {}
                except Exception:
                    j = {}
            p = j.get("params", {})
            if p and p.get("sub_method") == "noc_kex":
                return await super().post(
                    url, json=json, data=data, headers=headers, ssl=ssl
                )
            if p and p.get("sub_method") == "noc_proof":
                return 200, {"error_code": 0, "result": {"sessionId": "SID"}}
            return 200, {"error_code": 0, "result": {}}

    ctx3 = tp.NocAuthContext(DummyAuth())
    ctx3._transport._http_client = DummyHTTPNoDevProof()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        ctx3, "_derive_shared_secret", lambda *_: b"shared", raising=True
    )
    with pytest.raises(KasaException, match="missing device proof"):
        await ctx3.start()

    ctx4 = tp.NocAuthContext(DummyAuth())
    monkeypatch.setattr(
        ctx4, "_derive_shared_secret", lambda *_: b"shared", raising=True
    )

    def bad_sec_dec(cls, *a, **k):  # noqa: ARG001
        raise ValueError("bad tag")

    monkeypatch.setattr(
        tp._SessionCipher, "sec_decrypt", classmethod(bad_sec_dec), raising=True
    )
    monkeypatch.setattr(ctx4, "_sign_user_proof", lambda *a, **k: b"SIGN", raising=True)
    with pytest.raises(ValueError, match="bad tag"):
        await ctx4.start()

    ctx5 = tp.NocAuthContext(DummyAuth())
    ctx5._dev_pub_bytes = b"\x04" + b"\x01" * 64
    ctx5._ephemeral_pub_bytes = b"\x04" + b"\x02" * 64
    with pytest.raises(KasaException, match="Device proof missing fields"):
        ctx5._verify_device_proof({})  # type: ignore[arg-type]

    dev_cert_pem, dev_key_pem = _make_self_signed_cert_and_key()
    inter_pem, _ = _make_self_signed_cert_and_key()
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import ec as _ec

    dev_key = _ser.load_pem_private_key(dev_key_pem.encode(), password=None)
    bad_sig = dev_key.sign(b"wrong message", _ec.ECDSA(tp.hashes.SHA256()))
    ctx_verify = tp.NocAuthContext(DummyAuth())
    ctx_verify._dev_pub_bytes = b"\x04" + b"\x03" * 64
    ctx_verify._ephemeral_pub_bytes = b"\x04" + b"\x04" * 64
    with pytest.raises(KasaException, match="Invalid NOC device proof signature"):
        ctx_verify._verify_device_proof(
            {
                "dev_noc": dev_cert_pem,
                "dev_icac": inter_pem,
                "proof": base64.b64encode(bad_sig).decode(),
            }
        )


@pytest.mark.asyncio
async def test_nocauth_derive_shared_success_and_missing_pubkeys():
    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyAuthOK:
        def __init__(self):
            class DT:
                def __init__(self):
                    self._http_client = None
                    self._app_url = URL("https://h:4433")
                    self.COMMON_HEADERS = {"Content-Type": "application/json"}
                    self._host = "h"
                    self._username = "user"

                async def _get_ssl_context(self):
                    return False

            self._transport = DT()
            self._noc_data = tp.TpapNOCData(
                nocPrivateKey=key_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            )

        def _ensure_noc(self):
            return None

        def _handle_response_error_code(self, resp, msg):
            return None

    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import ec as _ec

    ctx_ok = tp.NocAuthContext(DummyAuthOK())
    first = ctx_ok._gen_ephemeral()
    second = ctx_ok._gen_ephemeral()
    assert first == second
    dev_priv = _ec.generate_private_key(_ec.SECP256R1())
    dev_pub_bytes = dev_priv.public_key().public_bytes(
        encoding=_ser.Encoding.X962, format=_ser.PublicFormat.UncompressedPoint
    )
    shared = ctx_ok._derive_shared_secret(dev_pub_bytes)
    assert isinstance(shared, bytes)
    assert len(shared) > 0

    ctx_missing = tp.NocAuthContext(DummyAuthOK())
    bad_dev_cert, _ = _make_self_signed_cert_and_key()
    with pytest.raises(KasaException, match="Missing public keys"):
        ctx_missing._verify_device_proof({"dev_noc": bad_dev_cert, "proof": "00"})


@pytest.mark.asyncio
async def test_nocauth_unknown_encryption_and_alt_session_fields(monkeypatch):
    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyHTTP:
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            json_mod = __import__("json")
            param_json = json if json is not None else None
            j = param_json or {}
            if not j and data:
                try:
                    if isinstance(data, bytes | bytearray) and len(data) >= 24:
                        try:
                            length = int.from_bytes(data[4:8], "big")
                            payload = bytes(data[24 : 24 + length])
                            j = json_mod.loads(payload.decode("utf-8"))
                        except Exception:
                            j = {}
                except Exception:
                    j = {}
            p = j.get("params", {})
            if p and p.get("sub_method") == "noc_kex":
                return 200, {
                    "error_code": 0,
                    "result": {
                        "dev_pk": base64.b64encode(b"\x04" + b"\x02" * 64).decode(),
                        "encryption": "unknown",
                        "expired": 7,
                    },
                }
            if p and p.get("sub_method") == "noc_proof":
                return 200, {
                    "error_code": 0,
                    "result": {
                        "dev_proof_encrypt": base64.b64encode(b"\x00").decode(),
                        "stok": "STK",
                        "startSeq": 3,
                        "sessionExpired": 321,
                    },
                }
            return 200, {"error_code": 0, "result": {}}

    class DummyTransport:
        def __init__(self):
            self._http_client = DummyHTTP()
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"
            self._username = "user"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()
            self._noc_data = tp.TpapNOCData(
                nocPrivateKey=key_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            )

        def _handle_response_error_code(self, resp, msg):
            return None

        def _ensure_noc(self):
            return None

    ctx = tp.NocAuthContext(DummyAuth())
    monkeypatch.setattr(
        ctx, "_derive_shared_secret", lambda *_: b"shared", raising=True
    )
    monkeypatch.setattr(ctx, "_sign_user_proof", lambda *a, **k: b"SIGN", raising=True)
    monkeypatch.setattr(
        tp._SessionCipher,
        "sec_decrypt",
        classmethod(lambda cls, *args, **kwargs: b'{"dev_noc":"X","proof":"aa"}'),
        raising=True,
    )
    monkeypatch.setattr(ctx, "_verify_device_proof", lambda *a, **k: None, raising=True)

    out = await ctx.start()
    assert isinstance(out, tp.TlaSession)
    assert out.sessionId == "STK"
    assert out.startSequence == 1
    assert out.sessionExpired == 0
    assert out.sessionCipher.cipher_id == "aes_128_ccm"


@pytest.mark.asyncio
async def test_nocauth_no_tag_in_dev_proof(monkeypatch):
    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyHTTP:
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            json_mod = __import__("json")
            param_json = json if json is not None else None
            j = param_json or {}
            if not j and data:
                try:
                    if isinstance(data, bytes | bytearray) and len(data) >= 24:
                        try:
                            length = int.from_bytes(data[4:8], "big")
                            payload = bytes(data[24 : 24 + length])
                            j = json_mod.loads(payload.decode("utf-8"))
                        except Exception:
                            j = {}
                except Exception:
                    j = {}
            p = j.get("params", {})
            if p and p.get("sub_method") == "noc_kex":
                return 200, {
                    "error_code": 0,
                    "result": {
                        "dev_pk": base64.b64encode(b"\x04" + b"\x03" * 64).decode(),
                        "encryption": "aes_128_ccm",
                        "expired": 1,
                    },
                }
            if p and p.get("sub_method") == "noc_proof":
                return 200, {
                    "error_code": 0,
                    "result": {
                        # This test covers the case where the response has a
                        # non-encrypted `dev_proof` field; keep it base64 for
                        # realism, but the transport expects `dev_proof_encrypt`.
                        "dev_proof": base64.b64encode(b"\x00").decode(),
                        "sessionId": "SIDN",
                        "start_seq": 2,
                        "expired": 5,
                    },
                }
            return 200, {"error_code": 0, "result": {}}

    class DummyTransport:
        def __init__(self):
            self._http_client = DummyHTTP()
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"
            self._username = "user"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()
            self._noc_data = tp.TpapNOCData(
                nocPrivateKey=key_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            )

        def _handle_response_error_code(self, resp, msg):
            return None

        def _ensure_noc(self):
            return None

    ctx = tp.NocAuthContext(DummyAuth())
    monkeypatch.setattr(
        ctx, "_derive_shared_secret", lambda *_: b"shared", raising=True
    )
    monkeypatch.setattr(ctx, "_sign_user_proof", lambda *a, **k: b"SIGN", raising=True)
    monkeypatch.setattr(
        tp._SessionCipher,
        "sec_decrypt",
        classmethod(lambda cls, *args, **kwargs: b'{"dev_noc":"X","proof":"aa"}'),
        raising=True,
    )
    monkeypatch.setattr(ctx, "_verify_device_proof", lambda *a, **k: None, raising=True)

    with pytest.raises(KasaException, match="NOC proof response missing device proof"):
        await ctx.start()


@pytest.mark.asyncio
async def test_nocauth_alt_session_id_and_defaults(monkeypatch):
    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyHTTP:
        async def post(self, url, *, json=None, data=None, headers=None, ssl=None):
            json_mod = __import__("json")
            param_json = json if json is not None else None
            j = param_json or {}
            if not j and data:
                try:
                    if isinstance(data, bytes | bytearray) and len(data) >= 24:
                        try:
                            length = int.from_bytes(data[4:8], "big")
                            payload = bytes(data[24 : 24 + length])
                            j = json_mod.loads(payload.decode("utf-8"))
                        except Exception:
                            j = {}
                except Exception:
                    j = {}
            p = (j or {}).get("params", {})
            if p.get("sub_method") == "noc_kex":
                return 200, {
                    "error_code": 0,
                    "result": {
                        "dev_pk": base64.b64encode(b"\x04" + b"\x05" * 64).decode(),
                        "encryption": "aes_128_ccm",
                        "expired": 42,
                    },
                }
            if p.get("sub_method") == "noc_proof":
                return 200, {
                    "error_code": 0,
                    "result": {
                        "dev_proof_encrypt": base64.b64encode(b"\x00").decode(),
                        "session_id": "SID_ALT",
                    },
                }
            return 200, {"error_code": 0, "result": {}}

    class DummyTransport:
        def __init__(self):
            self._http_client = DummyHTTP()
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"
            self._username = "user"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()
            self._noc_data = tp.TpapNOCData(
                nocPrivateKey=key_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            )

        def _handle_response_error_code(self, resp, msg):
            return None

        def _ensure_noc(self):
            return None

    ctx = tp.NocAuthContext(DummyAuth())
    monkeypatch.setattr(
        ctx, "_derive_shared_secret", lambda *_: b"shared", raising=True
    )
    monkeypatch.setattr(ctx, "_sign_user_proof", lambda *a, **k: b"SIGN", raising=True)
    monkeypatch.setattr(
        tp._SessionCipher,
        "sec_decrypt",
        classmethod(lambda cls, *args, **kwargs: b'{"dev_noc":"X","proof":"aa"}'),
        raising=True,
    )
    monkeypatch.setattr(ctx, "_verify_device_proof", lambda *a, **k: None, raising=True)

    out = await ctx.start()
    assert out.sessionId == ""
    assert out.startSequence == 1
    assert out.sessionExpired == 0


def test_nocauth_sign_proof_with_non_ec_key(monkeypatch):
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import rsa

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pem = rsa_key.private_bytes(
        encoding=_ser.Encoding.PEM,
        format=_ser.PrivateFormat.PKCS8,
        encryption_algorithm=_ser.NoEncryption(),
    ).decode()

    cert_pem, _ = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyTransport:
        def __init__(self):
            self._http_client = None
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"
            self._username = "user"

        async def _get_ssl_context(self):
            return False

    auth = type(
        "A",
        (),
        {
            "_transport": DummyTransport(),
            "_noc_data": tp.TpapNOCData(
                nocPrivateKey=rsa_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            ),
            "_ensure_noc": lambda self: None,
        },
    )()
    ctx = tp.NocAuthContext(auth)  # type: ignore[arg-type]
    with pytest.raises(KasaException, match="NOC user proof signing failed"):
        ctx._sign_user_proof(b"A", b"B", b"C", b"D")


def test_nocauth_sign_user_proof_non_ec_key_raises():
    rsa_pem = _make_rsa_key_pem()
    cert_pem, _, _ = _make_ec_cert_and_key()
    root_pem, _, _ = _make_ec_cert_and_key()

    class DummyTransport:
        _username = "user"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()
            self._noc_data = tp.TpapNOCData(
                nocPrivateKey=rsa_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            )

        def _handle_response_error_code(self, resp, msg):
            return None

        def _ensure_noc(self):
            return None

    ctx = tp.NocAuthContext(DummyAuth())
    with pytest.raises(KasaException, match="user proof signing failed"):
        ctx._sign_user_proof(b"A", b"B", b"C", b"D")


def test_nocauth_verify_device_proof_invalid_signature():
    cert_pem, dev_pub_uncompressed, priv = _make_ec_cert_and_key()

    class DummyTransport:
        _username = "user"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()
            self._noc_data = tp.TpapNOCData("K", cert_pem, "", cert_pem)

        def _handle_response_error_code(self, resp, msg):
            return None

        def _ensure_noc(self):
            return None

    ctx = tp.NocAuthContext(DummyAuth())
    ctx._dev_pub_bytes = dev_pub_uncompressed  # type: ignore[attr-defined]
    ctx._ephemeral_pub_bytes = b"\x04" + b"\x02" * 64  # type: ignore[attr-defined]

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    wrong_message = b"not-the-expected-message"
    bad_sig = priv.sign(wrong_message, ec.ECDSA(hashes.SHA256()))
    dev_proof_obj = {"dev_noc": cert_pem, "proof": base64.b64encode(bad_sig).decode()}
    with pytest.raises(KasaException, match="Invalid NOC device proof signature"):
        ctx._verify_device_proof(dev_proof_obj)


def test_nocauth_verify_device_proof_generic_error_nonhex():
    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyTransport:
        def __init__(self):
            self._http_client = None
            self._app_url = URL("https://h:4433")
            self.COMMON_HEADERS = {"Content-Type": "application/json"}
            self._host = "h"
            self._username = "user"

        async def _get_ssl_context(self):
            return False

    auth = type(
        "A",
        (),
        {
            "_transport": DummyTransport(),
            "_noc_data": tp.TpapNOCData(
                nocPrivateKey=key_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            ),
            "_ensure_noc": lambda self: None,
        },
    )()
    ctx = tp.NocAuthContext(auth)  # type: ignore[arg-type]
    ctx._dev_pub_bytes = b"\x04" + b"\x11" * 64
    ctx._ephemeral_pub_bytes = b"\x04" + b"\x22" * 64
    with pytest.raises(KasaException, match="NOC device proof verification failed"):
        ctx._verify_device_proof({"dev_noc": cert_pem, "proof": "not-hex"})


# --------------------------
# Spake2pAuthContext tests
# --------------------------


@pytest.mark.asyncio
async def test_spake2p_helpers_and_process(monkeypatch):
    K = tp.Spake2pAuthContext
    assert K._len8le(b"a") == (1).to_bytes(8, "little") + b"a"
    assert (K._encode_w(0) == b"\x00") or K._encode_w(0x0102).startswith(b"\x01")
    assert K._hash("SHA256", b"x") == hashlib.sha256(b"x").digest()
    assert K._hash("SHA512", b"x") == hashlib.sha512(b"x").digest()
    assert K._md5_hex("a") == hashlib.md5(b"a").hexdigest()  # noqa: S324
    assert K._sha1_hex("a") == hashlib.sha1(b"a").hexdigest()  # noqa: S324
    assert isinstance(K._sha256_crypt("p", "X"), str)
    assert isinstance(K._authkey_mask("pass", "tmp", "ABC"), str)
    assert K._sha1_username_mac_shadow("", "AA" * 6, "pwd") == "pwd"
    assert len(K._sha1_username_mac_shadow("user", "AABBCCDDEEFF", "pwd")) == 40
    assert K._build_credentials(None, "u", "p", "MAC") == "u/p"
    out_md5 = K._build_credentials(
        {
            "type": "password_shadow",
            "params": {"passwd_id": 1, "passwd_prefix": "$1$abcd"},
        },
        "",
        "p",
        "",
    )
    assert isinstance(out_md5, str)
    assert out_md5.startswith("$1$")
    assert (
        len(
            K._build_credentials(
                {"type": "password_shadow", "params": {"passwd_id": 2}}, "", "p", ""
            )
        )
        == 40
    )
    assert (
        len(
            K._build_credentials(
                {"type": "password_shadow", "params": {"passwd_id": 3}},
                "u",
                "p",
                "AABBCCDDEEFF",
            )
        )
        == 40
    )
    out_s5 = K._build_credentials(
        {"type": "password_shadow", "params": {"passwd_id": 5, "passwd_prefix": "X"}},
        "",
        "p",
        "",
    )
    assert isinstance(out_s5, str)
    assert out_s5.startswith("$5$")
    assert K._build_credentials(
        {
            "type": "password_authkey",
            "params": {"authkey_tmpkey": "aa", "authkey_dictionary": "AB"},
        },
        "",
        "p",
        "",
    )
    assert (
        K._build_credentials(
            {
                "type": "password_sha_with_salt",
                "params": {"sha_name": 0, "sha_salt": base64.b64encode(b"S").decode()},
            },
            "",
            "p",
            "",
        )
        != ""
    )
    assert isinstance(K._mac_pass_from_device_mac("AA:BB:CC:DD:EE:FF"), str)

    ctx_suite = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    assert ctx_suite._suite_hash_name(2) == "SHA512"  # type: ignore[attr-defined]
    assert ctx_suite._suite_hash_name(1) == "SHA256"  # type: ignore[attr-defined]
    assert ctx_suite._suite_mac_is_cmac(8) is True  # type: ignore[attr-defined]
    assert ctx_suite._suite_mac_is_cmac(2) is False  # type: ignore[attr-defined]

    ctx = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    ctx._curve = tp.NIST256p  # type: ignore[attr-defined]
    ctx._generator = ctx._curve.generator  # type: ignore[attr-defined]
    ctx._G = ctx._generator  # type: ignore[attr-defined]
    ctx._order = ctx._generator.order()  # type: ignore[attr-defined]
    Mx, My = K._sec1_to_xy(K.P256_M_COMP)
    Nx, Ny = K._sec1_to_xy(K.P256_N_COMP)
    ctx._M = tp.ellipticcurve.Point(ctx._curve.curve, Mx, My, ctx._order)  # type: ignore[attr-defined]
    ctx._N = tp.ellipticcurve.Point(ctx._curve.curve, Nx, Ny, ctx._order)  # type: ignore[attr-defined]
    ctx._hkdf_hash = "SHA512"
    ctx.user_random = base64.b64encode(b"\x00" * 16).decode()  # type: ignore[attr-defined]
    ctx.discover_suites = [1, 2]  # type: ignore[attr-defined]
    ctx.discover_mac = "AA:BB:CC:DD:EE:FF"  # type: ignore[attr-defined]
    ctx.username = "u"  # type: ignore[attr-defined]
    ctx.passcode = "p"  # type: ignore[attr-defined]
    ctx._authenticator = type("A", (), {"_tpap_tls": 1, "_tpap_dac": False})()  # type: ignore[attr-defined]

    reg = {
        "dev_random": base64.b64encode(b"\x00" * 16).decode(),
        "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
        "dev_share": base64.b64encode(tp.Spake2pAuthContext.P256_N_COMP).decode(),
        "cipher_suites": 2,
        "iterations": 100,
        "encryption": "aes_128_ccm",
        "extra_crypt": {},
    }
    share_params = tp.Spake2pAuthContext.process_register_result(ctx, reg)  # type: ignore[misc]
    assert share_params["sub_method"] == "pake_share"
    share = {
        "dev_confirm": (ctx._expected_dev_confirm or "").lower(),  # type: ignore[attr-defined]
        "sessionId": "STOK",
        "start_seq": 7,
        "sessionExpired": 0,
    }
    tla = tp.Spake2pAuthContext.process_share_result(ctx, share)  # type: ignore[misc]
    assert isinstance(tla, tp.TlaSession)
    assert tla.sessionId == "STOK"
    assert tla.startSequence == 7

    ctx2 = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    ctx2._curve = ctx._curve  # type: ignore[attr-defined]
    ctx2._generator = ctx._generator  # type: ignore[attr-defined]
    ctx2._G = ctx._G  # type: ignore[attr-defined]
    ctx2._order = ctx._order  # type: ignore[attr-defined]
    ctx2._M = ctx._M  # type: ignore[attr-defined]
    ctx2._N = ctx._N  # type: ignore[attr-defined]
    ctx2.user_random = base64.b64encode(b"\x00" * 16).decode()  # type: ignore[attr-defined]
    ctx2.discover_suites = [0]  # type: ignore[attr-defined]
    ctx2.discover_mac = ""  # type: ignore[attr-defined]
    ctx2._hkdf_hash = "SHA256"
    ctx2.username = "u"  # type: ignore[attr-defined]
    ctx2.passcode = "p"  # type: ignore[attr-defined]
    ctx2._authenticator = type("A", (), {"_tpap_tls": 0, "_tpap_dac": True})()  # type: ignore[attr-defined]
    share_params3 = tp.Spake2pAuthContext.process_register_result(ctx2, reg)  # type: ignore[misc]
    assert share_params3["sub_method"] == "pake_share"
    assert isinstance(share_params3["user_share"], str)

    ctx3 = ctx
    ctx3._authenticator = type("A", (), {"_tpap_tls": 0, "_tpap_dac": True})()  # type: ignore[attr-defined]
    ctx3._shared_key = b"K" * 32  # type: ignore[attr-defined]
    ctx3._hkdf_hash = "SHA256"  # type: ignore[attr-defined]
    ctx3._chosen_cipher = "aes_128_ccm"  # type: ignore[attr-defined]
    ctx3._expected_dev_confirm = ctx._expected_dev_confirm  # type: ignore[attr-defined]
    from datetime import datetime, timedelta

    from cryptography import x509 as _x509
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    from cryptography.x509.oid import NameOID as _NameOID

    ctx3._dac_nonce_hex = "00" * 32  # type: ignore[attr-defined]
    key = _ec.generate_private_key(_ec.SECP256R1())
    subject = issuer = _x509.Name([_x509.NameAttribute(_NameOID.COMMON_NAME, "DAC CA")])
    cert = (
        _x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .sign(key, _hashes.SHA256())
    )
    cert_pem = cert.public_bytes(encoding=_ser.Encoding.PEM)
    msg = ctx3._shared_key + bytes.fromhex(ctx3._dac_nonce_hex)  # type: ignore[attr-defined]
    sig = key.sign(msg, _ec.ECDSA(_hashes.SHA256()))
    share_with_dac = {
        "dev_confirm": (ctx3._expected_dev_confirm or "").lower(),  # type: ignore[attr-defined]
        "sessionId": "STOK2",
        "start_seq": 9,
        "sessionExpired": 1,
        "dac_ca": base64.b64encode(cert_pem).decode(),
        "dac_proof": sig.hex(),
    }
    tla2 = tp.Spake2pAuthContext.process_share_result(ctx3, share_with_dac)  # type: ignore[misc]
    assert isinstance(tla2, tp.TlaSession)
    assert tla2.sessionId == "STOK2"

    with pytest.raises(KasaException, match="SPAKE\\+?2\\+ confirmation mismatch"):
        tp.Spake2pAuthContext.process_share_result(
            ctx, {"dev_confirm": "dead", "sessionId": "X", "start_seq": 1}
        )  # type: ignore[misc]
    with pytest.raises(KasaException, match="Missing session fields"):
        tp.Spake2pAuthContext.process_share_result(
            ctx, {"dev_confirm": (ctx._expected_dev_confirm or "").lower()}
        )  # type: ignore[misc]


def test_build_credentials_sha_with_salt_invalid_b64_returns_passcode():
    out = tp.Spake2pAuthContext._build_credentials(  # type: ignore[misc]
        {
            "type": "password_sha_with_salt",
            "params": {"sha_name": 0, "sha_salt": "***not-b64***"},
        },
        "",
        "PASS",
        "",
    )
    assert out == "PASS"


@pytest.mark.asyncio
async def test_spake2p_start_covers_both_tls_modes(monkeypatch):
    class DummyAuth:
        def __init__(self, tls, dac):
            self._transport = type(
                "T",
                (),
                {
                    "_app_url": URL("https://h:4433"),
                    "_host": "h",
                    "COMMON_HEADERS": {"Content-Type": "application/json"},
                    "_http_client": type(
                        "H",
                        (),
                        {
                            "post": lambda *a, **k: (
                                200,
                                {"error_code": 0, "result": {}},
                            )
                        },
                    )(),
                    "_get_ssl_context": lambda *a, **k: False,
                    "_config": DeviceConfig("h"),
                },
            )()
            self._tpap_tls = tls
            self._tpap_dac = dac
            self._tpap_pake = [1, 2]
            self._device_mac = "AA:BB:CC:DD:EE:FF"

        def _handle_response_error_code(self, resp, msg):
            return None

    ctx = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    tp.Spake2pAuthContext.__init__(ctx, DummyAuth(1, False))  # type: ignore[misc]

    calls = {"share_params": None}

    async def fake_login(params, *, step_name):
        if step_name == "pake_register":
            return {
                "dev_random": base64.b64encode(b"\x00" * 16).decode(),
                "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
                "dev_share": base64.b64encode(
                    tp.Spake2pAuthContext.P256_N_COMP
                ).decode(),
                "cipher_suites": 2,
                "iterations": 100,
                "encryption": "aes_128_ccm",
                "extra_crypt": {},
            }
        if step_name == "pake_share":
            calls["share_params"] = params
            return {
                "dev_confirm": (ctx._expected_dev_confirm or "").lower(),  # type: ignore[attr-defined]
                "sessionId": "SIDX",
                "start_seq": 4,
                "sessionExpired": 0,
            }
        return {}

    monkeypatch.setattr(ctx, "_login", fake_login, raising=True)
    out = await tp.Spake2pAuthContext.start(ctx)  # type: ignore[misc]
    assert isinstance(out, tp.TlaSession)
    assert calls["share_params"] is not None
    assert "dac_nonce" not in calls["share_params"]

    ctx2 = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    tp.Spake2pAuthContext.__init__(ctx2, DummyAuth(0, True))  # type: ignore[misc]
    calls2 = {"share_params": None}

    async def fake_login2(params, *, step_name):
        if step_name == "pake_register":
            return {
                "dev_random": base64.b64encode(b"\x00" * 16).decode(),
                "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
                "dev_share": base64.b64encode(
                    tp.Spake2pAuthContext.P256_N_COMP
                ).decode(),
                "cipher_suites": 2,
                "iterations": 100,
                "encryption": "aes_128_ccm",
                "extra_crypt": {},
            }
        if step_name == "pake_share":
            calls2["share_params"] = params
            return {
                "dev_confirm": (ctx2._expected_dev_confirm or "").lower(),  # type: ignore[attr-defined]
                "sessionId": "SIDY",
                "start_seq": 6,
                "sessionExpired": 0,
            }
        return {}

    monkeypatch.setattr(ctx2, "_login", fake_login2, raising=True)
    out2 = await tp.Spake2pAuthContext.start(ctx2)  # type: ignore[misc]
    assert isinstance(out2, tp.TlaSession)
    assert "dac_nonce" in (calls2["share_params"] or {})


def test_spake2p_encode_w_trims_leading_zero():
    class FakeInt(int):
        def to_bytes(self, length, byteorder, signed=False):  # noqa: ARG002
            return b"\x00\x10"

    out = tp.Spake2pAuthContext._encode_w(FakeInt(5))
    assert out == b"\x10"


def test_build_credentials_shadow_unknown_pid_and_unknown_type():
    K = tp.Spake2pAuthContext
    out1 = K._build_credentials(
        {"type": "password_shadow", "params": {"passwd_id": 4}}, "u", "p", ""
    )
    assert out1 == "p"
    out2 = K._build_credentials({"type": "xyz", "params": {}}, "u", "p", "AA")
    assert out2 == "u/p"


def test_spake2p_verify_dac_errors():
    ctx = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    ctx._shared_key = b"S" * 32  # type: ignore[attr-defined]
    ctx._dac_nonce_hex = "00" * 32  # type: ignore[attr-defined]

    from datetime import datetime, timedelta

    from cryptography import x509 as _x509
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    from cryptography.x509.oid import NameOID as _NameOID

    key = _ec.generate_private_key(_ec.SECP256R1())
    subject = issuer = _x509.Name([_x509.NameAttribute(_NameOID.COMMON_NAME, "C")])
    cert = (
        _x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .sign(key, _hashes.SHA256())
    )
    cert_pem = cert.public_bytes(encoding=_ser.Encoding.PEM)
    wrong_sig = key.sign(b"bad", _ec.ECDSA(_hashes.SHA256()))
    with pytest.raises(KasaException, match="Invalid DAC proof signature"):
        tp.Spake2pAuthContext._verify_dac(  # type: ignore[misc]
            ctx,
            {
                "dac_ca": base64.b64encode(cert_pem).decode(),
                "dac_proof": wrong_sig.hex(),
            },
        )
    with pytest.raises(KasaException, match="DAC verification failed"):
        tp.Spake2pAuthContext._verify_dac(  # type: ignore[misc]
            ctx, {"dac_ca": base64.b64encode(cert_pem).decode(), "dac_proof": "not-hex"}
        )


def test_spake2p_verify_dac_early_return():
    ctx = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    tp.Spake2pAuthContext._verify_dac(ctx, {"dac_ca": ""})  # type: ignore[misc]


def test_spake2p_process_register_uses_mac_pass_when_suite0_with_mac():
    ctx = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    ctx._curve = tp.NIST256p  # type: ignore[attr-defined]
    ctx._generator = ctx._curve.generator  # type: ignore[attr-defined]
    ctx._G = ctx._generator  # type: ignore[attr-defined]
    ctx._order = ctx._generator.order()  # type: ignore[attr-defined]
    Mx, My = tp.Spake2pAuthContext._sec1_to_xy(tp.Spake2pAuthContext.P256_M_COMP)
    Nx, Ny = tp.Spake2pAuthContext._sec1_to_xy(tp.Spake2pAuthContext.P256_N_COMP)
    ctx._M = tp.ellipticcurve.Point(ctx._curve.curve, Mx, My, ctx._order)  # type: ignore[attr-defined]
    ctx._N = tp.ellipticcurve.Point(ctx._curve.curve, Nx, Ny, ctx._order)  # type: ignore[attr-defined]
    ctx.user_random = base64.b64encode(b"\x00" * 16).decode()  # type: ignore[attr-defined]
    ctx.discover_suites = [0]  # type: ignore[attr-defined]
    ctx.discover_mac = "AA:BB:CC:DD:EE:FF"  # type: ignore[attr-defined]
    ctx._hkdf_hash = "SHA256"
    ctx.username = "u"  # type: ignore[attr-defined]
    ctx.passcode = "p"  # type: ignore[attr-defined]
    ctx._authenticator = type("A", (), {"_tpap_tls": 1, "_tpap_dac": False})()  # type: ignore[attr-defined]

    reg = {
        "dev_random": base64.b64encode(b"\x00" * 16).decode(),
        "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
        "dev_share": base64.b64encode(tp.Spake2pAuthContext.P256_N_COMP).decode(),
        "cipher_suites": 2,
        "iterations": 100,
        "encryption": "aes_128_ccm",
        "extra_crypt": {},
    }
    params = tp.Spake2pAuthContext.process_register_result(ctx, reg)  # type: ignore[misc]
    assert params["sub_method"] == "pake_share"


@pytest.mark.asyncio
async def test_spake2p_cmac_branch_in_register():
    ctx = tp.Spake2pAuthContext.__new__(tp.Spake2pAuthContext)  # type: ignore[misc]
    ctx._curve = tp.NIST256p  # type: ignore[attr-defined]
    ctx._generator = ctx._curve.generator  # type: ignore[attr-defined]
    ctx._G = ctx._generator  # type: ignore[attr-defined]
    ctx._order = ctx._generator.order()  # type: ignore[attr-defined]
    Mx, My = tp.Spake2pAuthContext._sec1_to_xy(tp.Spake2pAuthContext.P256_M_COMP)
    Nx, Ny = tp.Spake2pAuthContext._sec1_to_xy(tp.Spake2pAuthContext.P256_N_COMP)
    ctx._M = tp.ellipticcurve.Point(ctx._curve.curve, Mx, My, ctx._order)  # type: ignore[attr-defined]
    ctx._N = tp.ellipticcurve.Point(ctx._curve.curve, Nx, Ny, ctx._order)  # type: ignore[attr-defined]
    ctx.user_random = base64.b64encode(b"\x00" * 16).decode()  # type: ignore[attr-defined]
    ctx.discover_suites = [8]  # type: ignore[attr-defined]
    ctx.discover_mac = ""  # type: ignore[attr-defined]
    ctx._hkdf_hash = "SHA256"
    ctx.username = "u"  # type: ignore[attr-defined]
    ctx.passcode = "p"  # type: ignore[attr-defined]
    ctx._authenticator = type("A", (), {"_tpap_tls": 1, "_tpap_dac": False})()  # type: ignore[attr-defined]
    reg = {
        "dev_random": base64.b64encode(b"\x00" * 16).decode(),
        "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
        "dev_share": base64.b64encode(tp.Spake2pAuthContext.P256_N_COMP).decode(),
        "cipher_suites": 8,  # triggers CMAC
        "iterations": 100,
        "encryption": "aes_128_ccm",
        "extra_crypt": {},
    }
    params = tp.Spake2pAuthContext.process_register_result(ctx, reg)  # type: ignore[misc]
    assert params["sub_method"] == "pake_share"
    assert isinstance(params["user_confirm"], str)


def test_spake2p_passlib_md5_and_sha256():
    """Cover passlib-based helpers: MD5-crypt and SHA256-crypt behavior."""
    K = tp.Spake2pAuthContext
    assert K._md5_crypt("p", "") is None
    assert K._md5_crypt("p", "nope") is None
    out = K._md5_crypt("p", "$1$abcd")
    assert isinstance(out, str)
    assert out.startswith("$1$")
    long_pw = "x" * 30001
    assert K._md5_crypt(long_pw, "$1$abcd") is None
    out_extra = K._md5_crypt("p", "$1$abcd$extra")
    assert out_extra == out
    assert K._sha256_crypt("p", "") is None
    out2 = K._sha256_crypt("p", "$5$rounds=2000$mysalt")
    assert isinstance(out2, str)
    assert out2.startswith("$5$")
    out3 = K._sha256_crypt("p", "$5$mysalt", rounds_from_params=10)
    assert isinstance(out3, str)
    assert "rounds=1000" in out3
    out_bad = K._sha256_crypt("p", "$5$rounds=bad$mysalt")
    assert isinstance(out_bad, str)
    assert out_bad.startswith("$5$mysalt$") or "rounds=5000" in out_bad


# --------------------------
# Authenticator and Transport tests
# --------------------------


@pytest.mark.asyncio
async def test_authenticator_discover_establish_and_cached(monkeypatch):
    monkeypatch.setattr(
        tp.NOCClient, "apply", lambda self, u, p: tp.TpapNOCData("K", "C", "I", "R")
    )

    tr = tp.TpapTransport(config=DeviceConfig("1.2.3.4"))

    async def post_discover(url, *, json=None, data=None, headers=None, ssl=None):
        return 200, {
            "error_code": 0,
            "result": {
                "mac": "AA:BB:CC:DD:EE:FF",
                "tpap": {"noc": True, "dac": False, "tls": 1, "pake": [1, 2]},
            },
        }

    tr._http_client.post = post_discover  # type: ignore[assignment]

    class NocCtxDummy:
        def __init__(self, auth):
            pass

        async def start(self):
            c = tp._SessionCipher.from_shared_key("aes_128_ccm", b"shared")
            return tp.TlaSession("SID", 0, "NOC", c, 1)

    monkeypatch.setattr(tp, "NocAuthContext", NocCtxDummy, raising=True)

    await tr._authenticator.ensure_authenticator()
    assert tr._authenticator._session_id == "SID"
    assert tr._authenticator._seq == 1
    assert isinstance(tr._authenticator._ds_url, URL)

    await tr._authenticator.ensure_authenticator()
    assert tr._authenticator._seq == 1

    a = tr._authenticator
    retry_code = next(iter(SMART_RETRYABLE_ERRORS))
    auth_code = next(iter(SMART_AUTHENTICATION_ERRORS))
    other_code = next(
        c
        for c in SmartErrorCode
        if c not in SMART_RETRYABLE_ERRORS
        and c not in SMART_AUTHENTICATION_ERRORS
        and c is not SmartErrorCode.SUCCESS
    )
    with pytest.raises(_RetryableError):
        a._handle_response_error_code({"error_code": retry_code.value}, "m")
    with pytest.raises(AuthenticationError):
        a._handle_response_error_code({"error_code": auth_code.value}, "m")
    with pytest.raises(DeviceError):
        a._handle_response_error_code({"error_code": other_code.value}, "m")

    tr2 = tp.TpapTransport(config=DeviceConfig("1.2.3.5"))

    async def post_discover2(url, *, json=None, data=None, headers=None, ssl=None):
        return 200, {
            "error_code": 0,
            "result": {
                "mac": "AA:BB:CC:DD:EE:FF",
                "tpap": {"noc": False, "dac": False, "tls": 1, "pake": [1, 2]},
            },
        }

    tr2._http_client.post = post_discover2  # type: ignore[assignment]

    class SpakeCtxDummy:
        def __init__(self, auth):
            pass

        async def start(self):
            c = tp._SessionCipher.from_shared_key("aes_128_ccm", b"shared")
            return tp.TlaSession("SID2", 0, "SPAKE2+", c, 2)

    monkeypatch.setattr(tp, "Spake2pAuthContext", SpakeCtxDummy, raising=True)
    await tr2._authenticator.ensure_authenticator()
    assert tr2._authenticator._session_id == "SID2"
    assert tr2._authenticator._seq == 2


@pytest.mark.asyncio
async def test_authenticator_discover_and_establish_failures(monkeypatch, caplog):
    monkeypatch.setattr(
        tp.NOCClient, "apply", lambda self, u, p: tp.TpapNOCData("K", "C", "I", "R")
    )
    tr = tp.TpapTransport(config=DeviceConfig("2.3.4.5"))

    async def post_500(url, *, json=None, data=None, headers=None, ssl=None):
        return 500, b"x"

    tr._http_client.post = post_500  # type: ignore[assignment]
    with pytest.raises(KasaException, match="_discover failed status: 500"):
        await tr._authenticator.ensure_authenticator()

    async def post_ok(url, *, json=None, data=None, headers=None, ssl=None):
        return 200, {
            "error_code": 0,
            "result": {
                "mac": "AA:BB:CC:DD:EE:FF",
                "tpap": {"noc": True, "dac": False, "tls": 1, "pake": [1, 2]},
            },
        }

    tr._http_client.post = post_ok  # type: ignore[assignment]

    class BoomNoc:
        def __init__(self, auth):
            pass

        async def start(self):
            raise RuntimeError("noc boom")

    class BoomSpake:
        def __init__(self, auth):
            pass

        async def start(self):
            return None

    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(tp, "NocAuthContext", BoomNoc, raising=True)
    monkeypatch.setattr(tp, "Spake2pAuthContext", BoomSpake, raising=True)
    with pytest.raises(KasaException, match="failed to establish session"):
        await tr._authenticator.ensure_authenticator()
    assert any("NOC attempt failed" in m for m in caplog.messages) or caplog.messages


@pytest.mark.asyncio
async def test_authenticator_ensure_noc_applies_when_none(monkeypatch):
    tr = tp.TpapTransport(config=DeviceConfig("host"))
    tr._username = "user"
    tr._password = "pass"  # noqa: S105

    called = {}

    def fake_apply(self, u, p):
        called["ran"] = (u, p)
        return tp.TpapNOCData("K", "C", "I", "R")

    tr._authenticator._noc_data = None
    monkeypatch.setattr(tp.NOCClient, "apply", fake_apply, raising=True)
    tr._authenticator._ensure_noc()
    assert called["ran"] == ("user", "pass")
    assert tr._authenticator._noc_data is not None


@pytest.mark.asyncio
async def test_authenticator_set_session_from_tla_branches():
    tr = tp.TpapTransport(config=DeviceConfig("host2"))
    tr._authenticator._cached_session = None
    tr._authenticator._set_session_from_tla()
    assert tr._authenticator._session_id is None
    assert tr._authenticator._seq is None
    assert tr._authenticator._cipher is None
    assert tr._authenticator._ds_url is None

    c = tp._SessionCipher.from_shared_key("aes_128_ccm", b"shared")
    tr._authenticator._cached_session = tp.TlaSession("SIDX", 0, "NOC", c, 3)
    tr._authenticator._set_session_from_tla()
    assert tr._authenticator._session_id == "SIDX"
    assert tr._authenticator._seq == 3
    assert tr._authenticator._cipher is c
    assert str(tr._authenticator._ds_url).endswith("/stok=SIDX/ds")


@pytest.mark.asyncio
async def test_authenticator_handle_response_error_code_nonint():
    tr = tp.TpapTransport(config=DeviceConfig("host9"))
    tr._authenticator._handle_response_error_code({"error_code": "bad"}, "msg")


@pytest.mark.asyncio
async def test_authenticator_noc_returns_none_falls_back_to_spake(monkeypatch):
    tr = tp.TpapTransport(config=DeviceConfig("host-fallback"))

    async def post_ok(url, *, json=None, data=None, headers=None, ssl=None):
        return 200, {
            "error_code": 0,
            "result": {
                "mac": "AA:BB:CC:DD:EE:FF",
                "tpap": {"noc": True, "dac": False, "tls": 1, "pake": [1, 2]},
            },
        }

    tr._http_client.post = post_ok  # type: ignore[assignment]

    class NocNone:
        def __init__(self, a):
            pass

        async def start(self):
            return None

    class SpakeOk:
        def __init__(self, a):
            pass

        async def start(self):
            c = tp._SessionCipher.from_shared_key("aes_128_ccm", b"shared")
            return tp.TlaSession("SIDF", 0, "SPAKE2+", c, 7)

    monkeypatch.setattr(tp, "NocAuthContext", NocNone, raising=True)
    monkeypatch.setattr(tp, "Spake2pAuthContext", SpakeOk, raising=True)

    await tr._authenticator.ensure_authenticator()
    assert tr._authenticator._session_id == "SIDF"
    assert tr._authenticator._seq == 7


# --------------------------
# SSL/TLS and send() tests
# --------------------------


@pytest.mark.asyncio
async def test_transport_ssl_context_variants_and_cleanup(monkeypatch):
    monkeypatch.setattr(
        tp.NOCClient, "apply", lambda self, u, p: tp.TpapNOCData("K", "C", "I", "R")
    )
    tr = tp.TpapTransport(config=DeviceConfig("host3"))

    assert tr.default_port == 4433
    tr._config.connection_type.http_port = 12345  # type: ignore[attr-defined]
    assert tr.default_port == 12345
    tr._config.credentials_hash = "abc"  # type: ignore[attr-defined]
    assert tr.credentials_hash == "abc"

    tr._authenticator._tpap_tls = 0
    assert tr._create_ssl_context() is False

    tr._authenticator._tpap_tls = 1
    ctx1 = tr._create_ssl_context()
    assert isinstance(ctx1, ssl.SSLContext)
    assert ctx1.verify_mode == ssl.CERT_NONE

    tr._authenticator._tpap_tls = None  # type: ignore[assignment]
    ctx_none = tr._create_ssl_context()
    assert isinstance(ctx_none, ssl.SSLContext)
    assert ctx_none.verify_mode == ssl.CERT_NONE

    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()
    tr._authenticator._tpap_tls = 2
    tr._authenticator._noc_data = tp.TpapNOCData(key_pem, cert_pem, "", root_pem)
    ctx2 = tr._create_ssl_context()
    assert isinstance(ctx2, ssl.SSLContext)
    assert ctx2.verify_mode == ssl.CERT_REQUIRED

    tr2 = tp.TpapTransport(config=DeviceConfig("host4"))
    tr2._authenticator._tpap_tls = 2
    tr2._authenticator._noc_data = None

    def raise_ensure():
        raise RuntimeError("boom")

    monkeypatch.setattr(tr2._authenticator, "_ensure_noc", raise_ensure, raising=True)
    ctx3 = tr2._create_ssl_context()
    assert isinstance(ctx3, ssl.SSLContext)
    assert ctx3.verify_mode == ssl.CERT_REQUIRED

    tr._authenticator._tpap_tls = 2
    tr._authenticator._noc_data = tp.TpapNOCData(key_pem, cert_pem, "", root_pem)
    unlinked: list[str] = []

    def fake_unlink(p: str):
        unlinked.append(p)

    real_verify = tp.ssl.SSLContext.load_verify_locations
    real_chain = tp.ssl.SSLContext.load_cert_chain

    def ok_verify(self, *a, **k):  # noqa: ARG001
        return None

    def bad_chain(self, *a, **k):  # noqa: ARG001
        raise RuntimeError("bad chain")

    monkeypatch.setattr(tp.os, "unlink", fake_unlink, raising=True)
    monkeypatch.setattr(
        tp.ssl.SSLContext, "load_verify_locations", ok_verify, raising=True
    )
    monkeypatch.setattr(tp.ssl.SSLContext, "load_cert_chain", bad_chain, raising=True)
    ctx_err = tr._create_ssl_context()
    assert isinstance(ctx_err, ssl.SSLContext)
    assert unlinked

    tr3 = tp.TpapTransport(config=DeviceConfig("host5"))
    tr3._authenticator._tpap_tls = 2
    tr3._authenticator._noc_data = tp.TpapNOCData(key_pem, cert_pem, "", root_pem)

    def fail_verify(self, *a, **k):  # noqa: ARG001
        raise RuntimeError("verify locations failed")

    unlinked2: list[str] = []
    monkeypatch.setattr(tp.os, "unlink", lambda p: unlinked2.append(p), raising=True)
    monkeypatch.setattr(
        tp.ssl.SSLContext, "load_verify_locations", fail_verify, raising=True
    )
    ctx_fail = tr3._create_ssl_context()
    assert isinstance(ctx_fail, ssl.SSLContext)
    assert ctx_fail.verify_mode == ssl.CERT_REQUIRED
    assert unlinked2 == []

    monkeypatch.setattr(
        tp.ssl.SSLContext, "load_verify_locations", real_verify, raising=True
    )
    monkeypatch.setattr(tp.ssl.SSLContext, "load_cert_chain", real_chain, raising=True)


@pytest.mark.asyncio
async def test_transport_ssl_context_tls_mode_unknown_skips_tls2_block():
    tr = tp.TpapTransport(config=DeviceConfig("host-tls3"))
    tr._authenticator._tpap_tls = 3
    ctx = tr._create_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.asyncio
async def test_transport_send_happy_and_error_paths(monkeypatch):
    monkeypatch.setattr(
        tp.NOCClient, "apply", lambda self, u, p: tp.TpapNOCData("K", "C", "I", "R")
    )
    tr = tp.TpapTransport(config=DeviceConfig("host6"))

    class FakeCipher:
        def encrypt(self, plaintext: bytes, seq: int) -> bytes:  # noqa: ARG002
            return plaintext + (b"\x00" * tp._SessionCipher.TAG_LEN)

        def decrypt(self, ciphertext_and_tag: bytes, seq: int) -> bytes:  # noqa: ARG002
            return b'{"error_code":0,"result":{"ok":true}}'

    tr._authenticator._session_id = "SID"
    tr._authenticator._seq = 10
    tr._authenticator._cipher = cast(tp._SessionCipher, FakeCipher())
    tr._authenticator._ds_url = URL(f"{str(tr._app_url)}/stok=SID/ds")
    tr._state = tp.TransportState.ESTABLISHED

    async def post_bytes(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 200, data

    tr._http_client.post = post_bytes  # type: ignore[assignment]
    out = await tr.send('{"m":"g"}')
    assert out["result"]["ok"] is True

    async def post_dict(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 200, {"error_code": 0, "result": {"ok": True}}

    tr._http_client.post = post_dict  # type: ignore[assignment]
    out2 = await tr.send('{"m":"g"}')
    assert out2["result"]["ok"] is True

    async def post_bad_type(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 200, 123

    tr._http_client.post = post_bad_type  # type: ignore[assignment]
    with pytest.raises(KasaException, match="Unexpected response body type"):
        await tr.send('{"m":"g"}')

    async def post_500(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 500, b"ignored"

    tr._http_client.post = post_500  # type: ignore[assignment]
    with pytest.raises(KasaException, match="responded with unexpected status 500"):
        await tr.send('{"m":"g"}')

    async def post_short(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 200, b"\x00\x00\x00\x0a" + b"\x00" * (tp._SessionCipher.TAG_LEN - 1)

    tr._http_client.post = post_short  # type: ignore[assignment]
    with pytest.raises(KasaException, match="TPAP response too short"):
        await tr.send('{"m":"g"}')

    async def post_mismatch(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        payload = (
            (999).to_bytes(4, "big") + b"{}" + (b"\x00" * tp._SessionCipher.TAG_LEN)
        )
        return 200, payload

    tr._http_client.post = post_mismatch  # type: ignore[assignment]
    out3 = await tr.send('{"m":"g"}')
    assert out3["result"]["ok"] is True

    retry_code = next(iter(SMART_RETRYABLE_ERRORS))

    async def post_retry(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 200, {"error_code": retry_code.value}

    tr._http_client.post = post_retry  # type: ignore[assignment]
    with pytest.raises(_RetryableError):
        await tr.send('{"m":"g"}')

    auth_code = next(iter(SMART_AUTHENTICATION_ERRORS))

    async def post_auth(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 200, {"error_code": auth_code.value}

    tr._http_client.post = post_auth  # type: ignore[assignment]
    with pytest.raises(AuthenticationError):
        await tr.send('{"m":"g"}')

    other_code = next(
        c
        for c in SmartErrorCode
        if c not in SMART_RETRYABLE_ERRORS
        and c not in SMART_AUTHENTICATION_ERRORS
        and c is not SmartErrorCode.SUCCESS
    )

    async def post_other(url, *, json=None, data=None, headers=None, ssl=None):  # noqa: ARG001
        return 200, {"error_code": other_code.value}

    tr._http_client.post = post_other  # type: ignore[assignment]
    with pytest.raises(DeviceError):
        await tr.send('{"m":"g"}')

    tr._http_client.post = post_bytes  # type: ignore[assignment]
    tr._authenticator._seq = 20
    tr._send_lock = None  # trigger creation branch

    async def noop_ensure():
        return None

    monkeypatch.setattr(
        tr._authenticator, "ensure_authenticator", noop_ensure, raising=True
    )

    out4 = await tr.send('{"m":"g"}')
    assert out4["result"]["ok"] is True
    assert tr._authenticator.seq == 21

    original_prop = tp.Authenticator.seq
    try:
        monkeypatch.setattr(
            tp.Authenticator, "seq", property(lambda self: 30), raising=True
        )
        tr._authenticator._seq = None
        out4b = await tr.send('{"m":"g"}')
        assert out4b["result"]["ok"] is True
        assert tr._authenticator._seq is None
    finally:
        monkeypatch.setattr(tp.Authenticator, "seq", original_prop, raising=True)

    tr2 = tp.TpapTransport(config=DeviceConfig("host7"))

    class FakeCipher2:
        def encrypt(self, plaintext: bytes, seq: int) -> bytes:  # noqa: ARG002
            return plaintext + (b"\x00" * tp._SessionCipher.TAG_LEN)

        def decrypt(self, ciphertext_and_tag: bytes, seq: int) -> bytes:  # noqa: ARG002
            return b'{"error_code":0,"result":{"ok":true}}'

    async def ensure():
        tr2._authenticator._session_id = "SIDAE"
        tr2._authenticator._seq = 1
        tr2._authenticator._cipher = cast(tp._SessionCipher, FakeCipher2())
        tr2._authenticator._ds_url = URL(f"{str(tr2._app_url)}/stok=SIDAE/ds")
        tr2._state = tp.TransportState.ESTABLISHED

    tr2._http_client.post = post_bytes  # type: ignore[assignment]
    monkeypatch.setattr(
        tr2._authenticator, "ensure_authenticator", ensure, raising=True
    )
    tr2._state = tp.TransportState.NOT_ESTABLISHED
    out5 = await tr2.send('{"m":"g"}')
    assert out5["result"]["ok"] is True
    assert tr2._authenticator.seq == 2
    assert tr2._authenticator.cipher is not None
    assert isinstance(tr2._authenticator.ds_url, URL)

    tr3 = tp.TpapTransport(config=DeviceConfig("host8"))
    tr3._state = tp.TransportState.ESTABLISHED
    with pytest.raises(KasaException, match="TPAP transport is not established"):
        await tr3.send('{"m":"g"}')

    tr3._authenticator._seq = 1
    tr3._authenticator._ds_url = URL(f"{str(tr3._app_url)}/stok=SID/ds")
    tr3._http_client.post = post_bytes  # type: ignore[assignment]
    with pytest.raises(
        KasaException, match="TPAP transport AEAD cipher not initialized"
    ):
        await tr3.send('{"m":"g"}')

    await tr.reset()
    await tr.close()


@pytest.mark.asyncio
async def test_tls2_verify_locations_raises_no_unlink(monkeypatch):
    monkeypatch.setattr(
        tp.NOCClient, "apply", lambda self, u, p: tp.TpapNOCData("K", "C", "I", "R")
    )
    tr = tp.TpapTransport(config=DeviceConfig("host10"))
    cert_pem = "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----\n"
    key_pem = "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"
    root_pem = cert_pem
    tr._authenticator._tpap_tls = 2
    tr._authenticator._noc_data = tp.TpapNOCData(
        nocPrivateKey=key_pem,
        nocCertificate=cert_pem,
        nocIntermediateCertificate="",
        nocRootCertificate=root_pem,
    )

    def fail_verify(self, *a, **k):  # noqa: ARG001
        raise RuntimeError("verify locations failed")

    unlinks: list[str] = []
    monkeypatch.setattr(
        tp.ssl.SSLContext, "load_verify_locations", fail_verify, raising=True
    )
    monkeypatch.setattr(tp.os, "unlink", lambda p: unlinks.append(p), raising=True)
    ctx = tr._create_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert unlinks == []


# --------------------------
# Additional coverage for missing/partial lines
# --------------------------


def test_spake2p_cmac_direct_call():
    key = hashlib.sha256(b"k").digest()
    out = tp.Spake2pAuthContext._cmac_aes(key, b"data")
    assert isinstance(out, bytes)
    assert len(out) > 0


@pytest.mark.asyncio
async def test_nocauth_derive_shared_raises_when_no_ephemeral():
    cert_pem, key_pem = _make_self_signed_cert_and_key()
    root_pem, _ = _make_self_signed_cert_and_key()

    class DummyTransport:
        _username = "user"

        async def _get_ssl_context(self):
            return False

    class DummyAuth:
        def __init__(self):
            self._transport = DummyTransport()
            self._noc_data = tp.TpapNOCData(
                nocPrivateKey=key_pem,
                nocCertificate=cert_pem,
                nocIntermediateCertificate="",
                nocRootCertificate=root_pem,
            )

        def _handle_response_error_code(self, resp, msg):
            return None

        def _ensure_noc(self):
            return None

    ctx = tp.NocAuthContext(DummyAuth())
    with pytest.raises(KasaException, match="Ephemeral private key not generated"):
        ctx._derive_shared_secret(b"\x04" + b"\x01" * 64)


@pytest.mark.asyncio
async def test_create_ssl_context_tls2_no_noc_materials_logging_branch(monkeypatch):
    tr = tp.TpapTransport(config=DeviceConfig("host-ensure-fail"))
    tr._authenticator._tpap_tls = 2
    tr._authenticator._noc_data = None

    def raise_ensure():
        raise RuntimeError("boom")

    monkeypatch.setattr(tr._authenticator, "_ensure_noc", raise_ensure, raising=True)
    ctx = tr._create_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
