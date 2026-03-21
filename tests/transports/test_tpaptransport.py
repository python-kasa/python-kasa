from __future__ import annotations

import base64
import hashlib
import logging
import ssl
import struct
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
from yarl import URL

import kasa.transports.tpaptransport as tp
from kasa.credentials import Credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _ConnectionError,
    _RetryableError,
)


def _discover_response(
    *,
    mac: str = "AA:BB:CC:DD:EE:FF",
    tls: int = 2,
    port: int = 4567,
    pake: list[int] | None = None,
    user_hash_type: int | None = None,
    dac: bool = False,
) -> dict[str, Any]:
    tpap_info: dict[str, Any] = {
        "dac": dac,
        "tls": tls,
        "port": port,
        "pake": pake or [],
    }
    if user_hash_type is not None:
        tpap_info["user_hash_type"] = user_hash_type

    return {"error_code": 0, "result": {"mac": mac, "tpap": tpap_info}}


def _register_result(
    *,
    extra_crypt: dict[str, Any] | None = None,
    cipher_suites: int = 2,
    iterations: int = 100,
    encryption: str = "aes_128_ccm",
) -> dict[str, Any]:
    return {
        "dev_random": base64.b64encode(b"\x00" * 16).decode(),
        "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
        "dev_share": base64.b64encode(_p256_pub_uncompressed()).decode(),
        "cipher_suites": cipher_suites,
        "iterations": iterations,
        "encryption": encryption,
        "extra_crypt": extra_crypt or {},
    }


def _share_result(
    session: tp.TpapEncryptionSession,
    *,
    session_id: str = "STOK",
    start_seq: int = 7,
) -> dict[str, Any]:
    assert session._expected_dev_confirm is not None
    return {
        "dev_confirm": session._expected_dev_confirm.lower(),
        "sessionId": session_id,
        "start_seq": start_seq,
    }


def _make_discover_post(
    response: dict[str, Any],
) -> Any:
    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, data, headers, ssl
        assert json is not None
        assert json["params"]["sub_method"] == "discover"
        return 200, response

    return post


def _make_handshake_login(
    session: tp.TpapEncryptionSession,
    *,
    capture_register: dict[str, Any] | None = None,
    register_result: dict[str, Any] | None = None,
    session_id: str = "STOK",
    start_seq: int = 7,
) -> Any:
    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        if step_name == "pake_register":
            if capture_register is not None:
                capture_register.update(params)
            return register_result or _register_result()

        assert step_name == "pake_share"
        return _share_result(session, session_id=session_id, start_seq=start_seq)

    return fake_login


def _p256_pub_uncompressed() -> bytes:
    private_key = ec.derive_private_key(
        int.from_bytes(b"\x01" * 32, "big"),
        ec.SECP256R1(),
    )
    return private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )


def _establish_session(
    transport: tp.TpapTransport,
    session: tp.TpapEncryptionSession,
    *,
    session_id: str = "SID",
    start_seq: int = 10,
) -> None:
    key, base_nonce = tp.TpapEncryptionSession.key_nonce_from_shared(
        b"shared-secret", "aes_128_ccm"
    )
    session._cipher_id = "aes_128_ccm"
    session._key = key
    session._base_nonce = base_nonce
    session._session_id = session_id
    session._sequence = start_seq
    session._ds_url = URL(f"{transport._app_url}/stok={session_id}/ds")
    transport._state = tp.TransportState.ESTABLISHED


def _make_established_transport() -> tuple[tp.TpapTransport, tp.TpapEncryptionSession]:
    config = DeviceConfig("host")
    transport = tp.TpapTransport(config=config)
    session = transport._encryption_session
    _establish_session(transport, session)
    return transport, session


def _build_certificate(
    private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    subject_common_name: str,
    issuer_common_name: str,
    issuer_private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    *,
    is_ca: bool = False,
) -> x509.Certificate:
    now = datetime.now(UTC).replace(tzinfo=None)
    builder = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_common_name)])
        )
        .issuer_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_common_name)])
        )
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=is_ca, path_length=None),
            critical=True,
        )
    )
    return builder.sign(issuer_private_key, hashes.SHA256())


def test_session_cipher_helpers_roundtrip() -> None:
    aes_key, aes_nonce = tp.TpapEncryptionSession.key_nonce_from_shared(
        b"k" * 16, "aes_256_ccm"
    )
    aes_ct, aes_tag = tp.TpapEncryptionSession.sec_encrypt(
        "aes_256_ccm", aes_key, aes_nonce, b"hello", seq=3
    )
    assert (
        tp.TpapEncryptionSession.sec_decrypt(
            "aes_256_ccm",
            aes_key,
            aes_nonce,
            aes_ct,
            aes_tag,
            seq=3,
        )
        == b"hello"
    )

    chacha_key, chacha_nonce = tp.TpapEncryptionSession.key_nonce_from_shared(
        b"c" * 32, "chacha20_poly1305"
    )
    chacha_ct, chacha_tag = tp.TpapEncryptionSession.sec_encrypt(
        "chacha20_poly1305",
        chacha_key,
        chacha_nonce,
        b"world",
        seq=5,
    )
    assert (
        tp.TpapEncryptionSession.sec_decrypt(
            "chacha20_poly1305",
            chacha_key,
            chacha_nonce,
            chacha_ct,
            chacha_tag,
            seq=5,
        )
        == b"world"
    )


@pytest.mark.asyncio
async def test_session_encrypt_and_decrypt_roundtrip() -> None:
    transport, session = _make_established_transport()

    payload, seq = session.encrypt(b'{"ok": true}')
    assert seq == 10
    assert session._sequence == 11
    assert session.decrypt(payload, seq) == b'{"ok": true}'
    assert str(session.ds_url) == f"{transport._app_url}/stok=SID/ds"


@pytest.mark.asyncio
async def test_session_perform_handshake_updates_transport_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("handshake-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapTransport(config=config)
    session = transport._encryption_session
    captured_register: dict[str, Any] = {}

    transport._http_client.post = _make_discover_post(  # type: ignore[assignment]
        _discover_response(pake=[2], user_hash_type=0)
    )
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert captured_register["username"] == tp.TpapEncryptionSession._md5_hex("user")
    assert captured_register["encryption"] == ["aes_128_ccm"]
    assert captured_register["passcode_type"] == "userpw"
    assert transport._state is tp.TransportState.ESTABLISHED
    assert session.is_established is True
    assert session.tls_mode == 2
    assert str(transport._app_url) == "https://handshake-host:4567"
    assert str(session.ds_url) == "https://handshake-host:4567/stok=STOK/ds"


@pytest.mark.asyncio
async def test_session_perform_handshake_uses_sha256_username_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("handshake-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapTransport(config=config)
    session = transport._encryption_session
    captured_register: dict[str, Any] = {}

    transport._http_client.post = _make_discover_post(  # type: ignore[assignment]
        _discover_response(pake=[2], user_hash_type=1)
    )
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert captured_register["username"] == tp.TpapEncryptionSession._sha256_hex_upper(
        "user"
    )


@pytest.mark.asyncio
async def test_session_perform_handshake_uses_configured_username_hash_for_generic_tpap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("handshake-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapTransport(config=config)
    session = transport._encryption_session
    captured_register: dict[str, Any] = {}

    transport._http_client.post = _make_discover_post(  # type: ignore[assignment]
        _discover_response(tls=0, port=80)
    )
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert captured_register["username"] == tp.TpapEncryptionSession._md5_hex("user")
    assert captured_register["passcode_type"] == "default_userpw"
    assert session.tls_mode == 0
    assert transport._app_url.scheme == "http"
    assert transport._app_url.host == "handshake-host"
    assert transport._app_url.port == 80
    assert session.ds_url is not None
    assert session.ds_url.scheme == "http"
    assert session.ds_url.host == "handshake-host"
    assert session.ds_url.port == 80
    assert session.ds_url.path == "/stok=STOK/ds"


@pytest.mark.asyncio
async def test_smartcam_session_uses_fixed_admin_username_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    captured_register: dict[str, Any] = {}

    transport._http_client.post = _make_discover_post(  # type: ignore[assignment]
        _discover_response(pake=[2], user_hash_type=0)
    )
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert captured_register["username"] == tp.TpapEncryptionSession._md5_hex("admin")


@pytest.mark.asyncio
async def test_smartcam_session_builds_password_candidates_without_lat() -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [2]

    assert session._iter_spake_candidate_secrets() == [
        tp.TpapEncryptionSession._md5_hex("pass"),
        tp.TpapEncryptionSession._sha256_hex_upper("pass"),
    ]


@pytest.mark.asyncio
async def test_smartcam_session_retries_next_candidate_on_handshake_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    attempted_candidates: list[str] = []

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        return {}

    def fake_iter_candidates() -> list[str]:
        return ["first", "second"]

    def fake_process_register_result(
        register_result: dict[str, Any], credentials_string: str
    ) -> dict[str, Any]:
        del register_result
        attempted_candidates.append(credentials_string)
        return {}

    def fake_process_share_result(share_result: dict[str, Any]) -> None:
        del share_result
        if attempted_candidates[-1] == "first":
            raise KasaException("bad candidate")
        _establish_session(transport, session, session_id="CAM-SID", start_seq=4)

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session, "_iter_spake_candidate_secrets", fake_iter_candidates, raising=True
    )
    monkeypatch.setattr(
        session, "_process_register_result", fake_process_register_result, raising=True
    )
    monkeypatch.setattr(
        session, "_process_share_result", fake_process_share_result, raising=True
    )

    await session._perform_spake_handshake()

    assert attempted_candidates == ["first", "second"]
    assert session._session_id == "CAM-SID"


@pytest.mark.asyncio
async def test_smartcam_session_raises_when_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session

    monkeypatch.setattr(
        session, "_iter_spake_candidate_secrets", lambda: [], raising=True
    )

    with pytest.raises(AuthenticationError, match="no SPAKE2\\+ credential candidates"):
        await session._perform_spake_handshake()


@pytest.mark.asyncio
async def test_smartcam_session_reraises_last_candidate_error(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [2]

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        return {}

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session, "_iter_spake_candidate_secrets", lambda: ["only"], raising=True
    )
    monkeypatch.setattr(
        session,
        "_process_register_result",
        lambda register_result, credentials_string: {},
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_process_share_result",
        lambda share_result: (_ for _ in ()).throw(KasaException("last failure")),
        raising=True,
    )

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(KasaException, match="last failure"),
    ):
        await session._perform_spake_handshake()

    assert "all password-based SPAKE2+ smartcam candidates failed" in caplog.text


@pytest.mark.asyncio
async def test_generic_tpap_session_reraises_last_candidate_error_without_hint(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("tpap-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapTransport(config=config)
    session = transport._encryption_session

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        return {}

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session, "_iter_spake_candidate_secrets", lambda: ["only"], raising=True
    )
    monkeypatch.setattr(
        session,
        "_process_register_result",
        lambda register_result, credentials_string: {},
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_process_share_result",
        lambda share_result: (_ for _ in ()).throw(KasaException("last failure")),
        raising=True,
    )

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(KasaException, match="last failure"),
    ):
        await session._perform_spake_handshake()

    assert "all password-based SPAKE2+ smartcam candidates failed" not in caplog.text


@pytest.mark.asyncio
async def test_smartcam_session_propagates_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    attempts: list[str] = []

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        raise _RetryableError("retry me", error_code=SmartErrorCode.SESSION_EXPIRED)

    def fake_process_register_result(
        register_result: dict[str, Any], credentials_string: str
    ) -> dict[str, Any]:
        del register_result
        attempts.append(credentials_string)
        return {}

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session,
        "_iter_spake_candidate_secrets",
        lambda: ["first", "second"],
        raising=True,
    )
    monkeypatch.setattr(
        session, "_process_register_result", fake_process_register_result, raising=True
    )

    with pytest.raises(_RetryableError, match="retry me"):
        await session._perform_spake_handshake()

    assert attempts == ["first"]


@pytest.mark.asyncio
async def test_smartcam_session_adds_dac_nonce_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_tls = 0
    session._tpap_dac = True
    captured_share_params: dict[str, Any] | None = None

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        nonlocal captured_share_params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        captured_share_params = params.copy()
        return {}

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session, "_iter_spake_candidate_secrets", lambda: ["candidate"], raising=True
    )
    monkeypatch.setattr(
        session,
        "_process_register_result",
        lambda register_result, credentials_string: {},
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_process_share_result",
        lambda share_result: _establish_session(
            transport, session, session_id="DAC-SID", start_seq=2
        ),
        raising=True,
    )

    await session._perform_spake_handshake()

    assert captured_share_params is not None
    assert captured_share_params["dac_nonce"]
    assert session._session_id == "DAC-SID"


@pytest.mark.asyncio
async def test_smartcam_passcode_type_for_setup_code() -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [1]

    assert session._get_passcode_type() == "userpw"


@pytest.mark.asyncio
async def test_default_passcode_type_when_pake_contains_zero() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._tpap_pake = [0]

    assert session._get_passcode_type() == "default_userpw"


@pytest.mark.asyncio
async def test_smartcam_shared_token_passcode_type() -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [3]

    assert session._get_passcode_type() == "shared_token"


@pytest.mark.asyncio
async def test_smartcam_setup_code_candidate_uses_raw_password() -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [1]

    assert session._iter_spake_candidate_secrets() == ["pass"]


@pytest.mark.asyncio
async def test_smartcam_unknown_pake_has_no_candidates() -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [5]

    assert session._iter_spake_candidate_secrets() == []


@pytest.mark.asyncio
async def test_smartcam_shared_token_candidate_uses_md5_password() -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [3]

    assert session._iter_spake_candidate_secrets() == [
        tp.TpapEncryptionSession._md5_hex("pass")
    ]


@pytest.mark.asyncio
async def test_smartcam_candidate_builder_dedupes_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [2]
    monkeypatch.setattr(session, "_md5_hex", lambda value: "same", raising=False)
    monkeypatch.setattr(
        session, "_sha256_hex_upper", lambda value: "same", raising=False
    )

    assert session._iter_spake_candidate_secrets() == ["same"]


@pytest.mark.asyncio
async def test_smartcam_resolve_spake_credentials_applies_extra_crypt() -> None:
    config = DeviceConfig("cam-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapSmartCamTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [2]
    register_result = {
        "extra_crypt": {"type": "password_shadow", "params": {"passwd_id": 2}}
    }

    assert session._resolve_spake_credentials(register_result, "candidate") == (
        tp.TpapEncryptionSession._sha1_hex("candidate")
    )


@pytest.mark.asyncio
async def test_default_passcode_resolve_spake_credentials_returns_candidate() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._tpap_pake = [0]
    session._device_mac = "AA:BB:CC:DD:EE:FF"

    assert session._resolve_spake_credentials({}, "candidate") == "candidate"


@pytest.mark.asyncio
async def test_default_passcode_type_when_pake_is_missing() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._tpap_pake = []

    assert session._get_passcode_type() == "default_userpw"


@pytest.mark.asyncio
async def test_tls2_ssl_context_loads_noc_root_ca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_cert = _build_certificate(root_key, "root", "root", root_key, is_ca=True)
    root_pem = root_cert.public_bytes(serialization.Encoding.PEM).decode()

    monkeypatch.setattr(
        tp.TpapTransport,
        "TPAP_TLS2_NOC_ROOT_CA_PEM",
        root_pem,
        raising=True,
    )

    transport = tp.TpapTransport(config=DeviceConfig("tls-host"))
    transport._encryption_session._tpap_tls = 2
    context = transport._create_ssl_context()

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.get_ca_certs()


@pytest.mark.asyncio
async def test_tls2_ssl_context_can_disable_verification_with_env(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tls-host"))
    transport._encryption_session._tpap_tls = 2
    monkeypatch.setenv(tp.TpapTransport.TLS2_DISABLE_VERIFY_ENV, "1")

    with caplog.at_level(logging.WARNING):
        context = transport._create_ssl_context()

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE
    assert "TPAP TLS2 certificate verification disabled" in caplog.text


@pytest.mark.asyncio
async def test_dac_verification_checks_chain_and_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_cert = _build_certificate(root_key, "root", "root", root_key, is_ca=True)
    root_pem = root_cert.public_bytes(serialization.Encoding.PEM).decode()

    ica_key = ec.generate_private_key(ec.SECP256R1())
    ica_cert = _build_certificate(ica_key, "ica", "root", root_key, is_ca=True)
    dac_key = ec.generate_private_key(ec.SECP256R1())
    dac_cert = _build_certificate(dac_key, "dac", "ica", ica_key)

    monkeypatch.setattr(
        tp.TpapTransport,
        "TPAP_ROOT_CA_PEM",
        root_pem,
        raising=True,
    )

    transport = tp.TpapTransport(config=DeviceConfig("dac-host"))
    session = transport._encryption_session
    session._shared_key = b"shared-key"
    nonce = b"dac-nonce"
    session._dac_nonce_base64 = base64.b64encode(nonce).decode()

    proof = dac_key.sign(session._shared_key + nonce, ec.ECDSA(hashes.SHA256()))
    share_result = {
        "dac_ca": base64.b64encode(
            dac_cert.public_bytes(serialization.Encoding.PEM)
        ).decode(),
        "dac_ica": base64.b64encode(
            ica_cert.public_bytes(serialization.Encoding.PEM)
        ).decode(),
        "dac_proof": base64.b64encode(proof).decode(),
    }

    session._verify_dac(share_result)

    share_result["dac_proof"] = base64.b64encode(b"bad-proof").decode()
    with pytest.raises(KasaException, match="Invalid DAC proof signature"):
        session._verify_dac(share_result)


@pytest.mark.asyncio
async def test_transport_send_happy_path() -> None:
    transport, session = _make_established_transport()

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, bytes]:
        del url, json, headers, ssl
        assert data is not None
        return 200, data

    transport._http_client.post = post  # type: ignore[assignment]

    out = await transport.send('{"result": {"ok": true}}')

    assert out["result"]["ok"] is True
    assert session._sequence == 11


@pytest.mark.asyncio
async def test_transport_send_retries_after_session_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, session = _make_established_transport()
    request_calls = 0

    async def fake_handshake() -> None:
        _establish_session(transport, session, session_id="SID-RETRY", start_seq=20)

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any] | bytes]:
        nonlocal request_calls
        del url, json, headers, ssl
        request_calls += 1
        if request_calls == 1:
            return (200, {"error_code": SmartErrorCode.SESSION_EXPIRED.value})
        assert data is not None
        return 200, data

    transport._http_client.post = post  # type: ignore[assignment]
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)

    out = await transport.send('{"result": {"retry": true}}')

    assert out["result"]["retry"] is True
    assert request_calls == 2
    assert session._session_id == "SID-RETRY"
    assert session._sequence == 21


@pytest.mark.asyncio
async def test_transport_send_retries_connection_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, session = _make_established_transport()
    request_calls = 0

    async def fake_handshake() -> None:
        _establish_session(
            transport,
            session,
            session_id="SID-CONN",
            start_seq=30,
        )

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, bytes]:
        nonlocal request_calls
        del url, json, headers, ssl
        request_calls += 1
        if request_calls == 1:
            raise _ConnectionError("Connection reset by peer")
        assert data is not None
        return 200, data

    transport._http_client.post = post  # type: ignore[assignment]
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)

    out = await transport.send('{"result": {"retry": true}}')

    assert out["result"]["retry"] is True
    assert request_calls == 2
    assert session._session_id == "SID-CONN"
    assert session._sequence == 31


@pytest.mark.asyncio
async def test_transport_reset_clears_session_state() -> None:
    transport, session = _make_established_transport()

    await transport.reset()

    assert transport._state is tp.TransportState.NOT_ESTABLISHED
    assert session.is_established is False
    assert transport._app_url == transport._bootstrap_url
    with pytest.raises(KasaException, match="TPAP transport is not established"):
        session.encrypt(b"{}")


@pytest.mark.asyncio
async def test_transport_reset_preserves_discovered_transport_identity() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._device_mac = "AA:BB:CC:DD:EE:FF"
    session._tpap_tls = 2
    session._tpap_port = 4567
    session._tpap_dac = True
    session._tpap_pake = [0, 2]
    session._tpap_user_hash_type = 1
    transport._known_device_mac = session._device_mac
    transport._known_tpap_tls = session._tpap_tls
    transport._known_tpap_port = session._tpap_port
    transport._known_tpap_dac = session._tpap_dac
    transport._known_tpap_pake = list(session._tpap_pake)
    transport._known_tpap_user_hash_type = session._tpap_user_hash_type

    await transport.reset()

    assert transport._app_url == URL("https://tpap-host:4567")
    assert session.device_mac == "AA:BB:CC:DD:EE:FF"
    assert session.tls_mode == 2
    assert session._tpap_port == 4567
    assert session._tpap_dac is True
    assert session._tpap_pake == [0, 2]
    assert session._tpap_user_hash_type == 1


# --------------------------
# Discovery and Login
# --------------------------


@pytest.mark.asyncio
async def test_perform_handshake_is_noop_when_session_already_established() -> None:
    transport, session = _make_established_transport()

    await session.perform_handshake()

    assert transport._state is tp.TransportState.ESTABLISHED
    assert session.is_established is True


@pytest.mark.asyncio
async def test_discover_raises_on_bad_status_or_body() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("discover-host"))
    session = transport._encryption_session

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, bytes]:
        del url, json, data, headers, ssl
        return 500, b"bad"

    transport._http_client.post = post  # type: ignore[assignment]

    with pytest.raises(KasaException, match="_discover failed status/body"):
        await session._discover()


@pytest.mark.asyncio
async def test_discover_parses_invalid_numeric_fields_as_none() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("discover-host"))
    session = transport._encryption_session

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return (
            200,
            {
                "error_code": 0,
                "result": {
                    "mac": "AA:BB:CC:DD:EE:FF",
                    "tpap": {
                        "tls": "bad",
                        "port": "bad",
                        "dac": True,
                        "pake": [2],
                        "user_hash_type": "bad",
                    },
                },
            },
        )

    transport._http_client.post = post  # type: ignore[assignment]

    await session._discover()

    assert session.device_mac == "AA:BB:CC:DD:EE:FF"
    assert session.tls_mode is None
    assert session._tpap_port is None
    assert session._tpap_user_hash_type is None
    assert str(transport._app_url) == str(transport._bootstrap_url)


@pytest.mark.asyncio
async def test_discover_propagates_device_error_codes() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("discover-host"))
    session = transport._encryption_session

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return (
            200,
            {"error_code": SmartErrorCode.SESSION_EXPIRED.value},
        )

    transport._http_client.post = post  # type: ignore[assignment]

    with pytest.raises(_RetryableError):
        await session._discover()


@pytest.mark.asyncio
async def test_discover_requires_result_and_tpap_objects() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("discover-host"))
    session = transport._encryption_session

    async def post_without_result(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return 200, {"error_code": 0}

    transport._http_client.post = post_without_result  # type: ignore[assignment]

    with pytest.raises(KasaException, match="missing result object"):
        await session._discover()

    async def post_without_tpap(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return 200, {"error_code": 0, "result": {}}

    transport._http_client.post = post_without_tpap  # type: ignore[assignment]

    with pytest.raises(KasaException, match="missing tpap object"):
        await session._discover()


@pytest.mark.asyncio
async def test_login_raises_on_bad_status_or_body() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("login-host"))
    session = transport._encryption_session

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, bytes]:
        del url, json, data, headers, ssl
        return 500, b"bad"

    transport._http_client.post = post  # type: ignore[assignment]

    with pytest.raises(KasaException, match="pake_register bad status/body"):
        await session._login({}, step_name="pake_register")


@pytest.mark.asyncio
async def test_login_propagates_error_code_handling() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("login-host"))
    session = transport._encryption_session

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return (
            200,
            {"error_code": SmartErrorCode.LOGIN_ERROR.value},
        )

    transport._http_client.post = post  # type: ignore[assignment]

    with pytest.raises(AuthenticationError, match="TPAP pake_register failed"):
        await session._login({}, step_name="pake_register")

    async def post_without_result(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return 200, {"error_code": 0}

    transport._http_client.post = post_without_result  # type: ignore[assignment]
    with pytest.raises(KasaException, match="missing result object"):
        await session._login({}, step_name="pake_register")


@pytest.mark.asyncio
async def test_login_tls2_uses_post() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("login-host"))
    session = transport._encryption_session
    session._tpap_tls = 2
    session._update_transport_url()

    async def post(
        url: URL,
        *,
        params: dict[str, Any] | None = None,
        data: bytes | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies_dict: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del params, data, cookies_dict, ssl
        assert url == URL("https://login-host:4433/")
        assert json == {"method": "login", "params": {}}
        assert headers == transport.COMMON_HEADERS
        return 200, {"error_code": 0, "result": {}}

    transport._http_client.post = post  # type: ignore[assignment]

    assert await session._login({}, step_name="pake_register") == {}


@pytest.mark.asyncio
async def test_update_transport_url_uses_https_default_or_bootstrap_port() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session

    session._tpap_tls = 1
    session._tpap_port = None
    session._update_transport_url()
    assert transport._app_url == URL("https://tpap-host:4433")

    session._tpap_tls = 0
    session._tpap_port = None
    session._update_transport_url()
    assert str(transport._app_url) == "http://tpap-host"
    await transport.close()


@pytest.mark.asyncio
async def test_handle_response_error_code_covers_invalid_retry_auth_and_device() -> (
    None
):
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    reset_calls = 0

    def fake_reset() -> None:
        nonlocal reset_calls
        reset_calls += 1

    session.reset = fake_reset  # type: ignore[method-assign]

    with pytest.raises(DeviceError) as invalid_code:
        session.handle_response_error_code({"error_code": "not-an-int"}, "ignored")
    assert invalid_code.value.error_code is SmartErrorCode.INTERNAL_UNKNOWN_ERROR

    with pytest.raises(_RetryableError):
        session.handle_response_error_code(
            {"error_code": SmartErrorCode.SESSION_EXPIRED.value}, "retry"
        )

    with pytest.raises(AuthenticationError):
        session.handle_response_error_code(
            {"error_code": SmartErrorCode.LOGIN_ERROR.value}, "auth"
        )

    assert reset_calls == 1

    with pytest.raises(DeviceError):
        session.handle_response_error_code(
            {"error_code": SmartErrorCode.DEVICE_ERROR.value}, "device"
        )
    await transport.close()


# --------------------------
# Helper and Credential Functions
# --------------------------


def test_encode_w_and_hash_helpers_cover_edge_cases() -> None:
    assert tp.TpapEncryptionSession._encode_w(0) == b"\x00"
    assert tp.TpapEncryptionSession._encode_w(0x80) == b"\x00\x80"
    assert (
        tp.TpapEncryptionSession._hash("SHA512", b"data")
        == hashlib.sha512(b"data").digest()
    )
    assert len(tp.TpapEncryptionSession._cmac_aes(b"\x00" * 16, b"data")) == 16


def test_authkey_shadow_and_crypt_helpers() -> None:
    masked = tp.TpapEncryptionSession._authkey_mask("abc", "xy", "0123456789")
    assert len(masked) == 3
    assert (
        tp.TpapEncryptionSession._sha1_username_mac_shadow("", "AABBCCDDEEFF", "p")
        == "p"
    )
    assert tp.TpapEncryptionSession._sha1_username_mac_shadow(
        "user", "AABBCCDDEEFF", "p"
    ) == tp.TpapEncryptionSession._sha1_hex(
        tp.TpapEncryptionSession._md5_hex("user") + "_AA:BB:CC:DD:EE:FF"
    )
    assert tp.TpapEncryptionSession._md5_crypt("pass", "") is None
    assert tp.TpapEncryptionSession._md5_crypt("pass", "$1$salt$") is not None
    assert tp.TpapEncryptionSession._md5_crypt("pass", "$1$salt") is not None
    assert tp.TpapEncryptionSession._sha256_crypt("pass", "") is None
    assert (
        tp.TpapEncryptionSession._sha256_crypt("pass", "$5$rounds=oops$salt")
        is not None
    )
    assert (
        tp.TpapEncryptionSession._sha256_crypt(
            "pass", "$5$salt$", rounds_from_params=2000
        )
        is not None
    )
    assert (
        tp.TpapEncryptionSession._sha256_crypt(
            "pass",
            "$5$salt$",
            rounds_from_params=cast(Any, "bad-rounds"),
        )
        is not None
    )


@pytest.mark.parametrize(
    ("extra_crypt", "username", "passcode", "mac_no_colon", "expected"),
    [
        (None, "user", "pass", "AABBCCDDEEFF", "user/pass"),
        ({}, "", "pass", "AABBCCDDEEFF", "pass"),
        (
            {"type": "password_shadow", "params": {"passwd_id": 2}},
            "user",
            "pass",
            "AABBCCDDEEFF",
            tp.TpapEncryptionSession._sha1_hex("pass"),
        ),
        (
            {
                "type": "password_shadow",
                "params": {"passwd_id": 3},
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
            tp.TpapEncryptionSession._sha1_username_mac_shadow(
                "user", "AABBCCDDEEFF", "pass"
            ),
        ),
        (
            {
                "type": "password_authkey",
                "params": {
                    "authkey_tmpkey": "xy",
                    "authkey_dictionary": "0123456789",
                },
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
            tp.TpapEncryptionSession._authkey_mask("pass", "xy", "0123456789"),
        ),
        (
            {
                "type": "password_sha_with_salt",
                "params": {
                    "sha_name": 0,
                    "sha_salt": base64.b64encode(b"salt").decode(),
                },
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
            hashlib.sha256(b"adminsaltpass").hexdigest(),
        ),
        (
            {"type": "unknown", "params": {}},
            "user",
            "pass",
            "AABBCCDDEEFF",
            "user/pass",
        ),
    ],
)
def test_build_credentials_variants(
    extra_crypt: dict[str, Any] | None,
    username: str,
    passcode: str,
    mac_no_colon: str,
    expected: str,
) -> None:
    assert (
        tp.TpapEncryptionSession._build_credentials(
            extra_crypt, username, passcode, mac_no_colon
        )
        == expected
    )


def test_build_credentials_fallback_paths() -> None:
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {
                "type": "password_shadow",
                "params": {"passwd_id": 1, "passwd_prefix": "$1$salt$"},
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        != "pass"
    )
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {
                "type": "password_shadow",
                "params": {"passwd_id": 5, "passwd_prefix": "$5$salt$"},
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        is not None
    )
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {"type": "password_authkey", "params": {}},
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        == "pass"
    )
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {"type": "password_shadow", "params": {"passwd_id": 99}},
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        == "pass"
    )
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {"type": "password_shadow", "params": "not-a-dict"},
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        == "pass"
    )
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {"type": "password_shadow", "params": {"passwd_id": "bad"}},
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        == "pass"
    )
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {
                "type": "password_sha_with_salt",
                "params": {"sha_name": "bad", "sha_salt": "c2FsdA=="},
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        == "pass"
    )


def test_mac_pass_from_device_mac_validates_input() -> None:
    with pytest.raises(KasaException, match="Invalid device MAC"):
        tp.TpapEncryptionSession._mac_pass_from_device_mac("not-a-mac")

    with pytest.raises(KasaException, match="too short"):
        tp.TpapEncryptionSession._mac_pass_from_device_mac("AA:BB:CC:DD:EE")


# --------------------------
# Register, Share, and Suite Handling
# --------------------------


@pytest.mark.parametrize(
    ("suite_type", "curve_name"),
    [
        (3, "NIST384p"),
        (5, "NIST521p"),
    ],
)
def test_suite_parameters_support_additional_curves(
    suite_type: int, curve_name: str
) -> None:
    _, _, curve, _ = tp.TpapEncryptionSession._suite_parameters(suite_type)
    assert curve.name == curve_name


def test_suite_parameters_reject_unsupported_suite() -> None:
    with pytest.raises(KasaException, match="Unsupported SPAKE2\\+ suite type"):
        tp.TpapEncryptionSession._suite_parameters(999)


@pytest.mark.asyncio
async def test_process_register_result_requires_user_random() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session

    with pytest.raises(KasaException, match="user random not initialized"):
        session._process_register_result({}, "secret")


@pytest.mark.asyncio
async def test_process_register_result_validates_required_fields() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._user_random = base64.b64encode(b"\x01" * 16).decode()

    valid_register = {
        "dev_random": base64.b64encode(b"\x00" * 16).decode(),
        "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
        "dev_share": base64.b64encode(_p256_pub_uncompressed()).decode(),
        "cipher_suites": 2,
        "iterations": 100,
        "encryption": "aes_128_ccm",
    }

    with pytest.raises(KasaException, match="missing dev_random"):
        session._process_register_result({**valid_register, "dev_random": ""}, "secret")

    with pytest.raises(KasaException, match="missing dev_salt"):
        session._process_register_result({**valid_register, "dev_salt": ""}, "secret")

    with pytest.raises(KasaException, match="missing dev_share"):
        session._process_register_result({**valid_register, "dev_share": ""}, "secret")

    with pytest.raises(KasaException, match="has invalid cipher_suites"):
        session._process_register_result(
            {**valid_register, "cipher_suites": "bad"}, "secret"
        )

    with pytest.raises(KasaException, match="has invalid iterations"):
        session._process_register_result({**valid_register, "iterations": 0}, "secret")

    with pytest.raises(KasaException, match="Unsupported TPAP session cipher"):
        session._process_register_result(
            {**valid_register, "encryption": "bogus-cipher"}, "secret"
        )

    with pytest.raises(KasaException, match="missing encryption"):
        session._process_register_result({**valid_register, "encryption": ""}, "secret")


@pytest.mark.asyncio
async def test_process_register_result_uses_cmac_suites() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._user_random = base64.b64encode(b"\x01" * 16).decode()

    share_params = session._process_register_result(
        {
            "dev_random": base64.b64encode(b"\x00" * 16).decode(),
            "dev_salt": base64.b64encode(b"\x11" * 16).decode(),
            "dev_share": base64.b64encode(_p256_pub_uncompressed()).decode(),
            "cipher_suites": 8,
            "iterations": 100,
            "encryption": "aes_128_ccm",
        },
        "secret",
    )

    assert session._expected_dev_confirm is not None
    assert share_params["user_confirm"]


@pytest.mark.asyncio
async def test_verify_dac_returns_early_without_required_fields() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._verify_dac({})
    await transport.close()


@pytest.mark.asyncio
async def test_verify_dac_wraps_non_signature_errors() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._shared_key = b"shared"
    session._dac_nonce_base64 = base64.b64encode(b"nonce").decode()

    with pytest.raises(KasaException, match="DAC verification failed"):
        session._verify_dac({"dac_ca": "not-a-cert", "dac_proof": "not-b64"})
    await transport.close()


@pytest.mark.asyncio
async def test_verify_dac_rejects_invalid_proof_type_and_public_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._shared_key = b"shared"
    session._dac_nonce_base64 = base64.b64encode(b"nonce").decode()

    cert_key = ec.generate_private_key(ec.SECP256R1())
    cert = _build_certificate(cert_key, "root", "root", cert_key, is_ca=True)

    monkeypatch.setattr(
        transport,
        "_load_certificate_value",
        lambda value: cert,
        raising=True,
    )
    monkeypatch.setattr(
        transport,
        "_verify_dac_certificate_chain",
        lambda dac_ca_certificate, dac_ica_certificate: None,
        raising=True,
    )

    with pytest.raises(KasaException, match="Invalid DAC proof type"):
        session._verify_dac({"dac_ca": "cert", "dac_proof": 1})

    bad_cert = cast(Any, SimpleNamespace(public_key=lambda: object()))
    monkeypatch.setattr(
        transport,
        "_load_certificate_value",
        lambda value: bad_cert,
        raising=True,
    )
    with pytest.raises(KasaException, match="Unsupported DAC proof public key type"):
        session._verify_dac(
            {"dac_ca": "cert", "dac_proof": base64.b64encode(b"proof").decode()}
        )
    await transport.close()


@pytest.mark.asyncio
async def test_process_share_result_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._expected_dev_confirm = "expected"

    with pytest.raises(KasaException, match="missing dev_confirm"):
        session._process_share_result({})

    with pytest.raises(KasaException, match="confirmation mismatch"):
        session._process_share_result({"dev_confirm": "wrong"})

    monkeypatch.setattr(session, "_use_dac_certification", lambda: True, raising=True)
    verified: list[dict[str, Any]] = []
    monkeypatch.setattr(
        session, "_verify_dac", lambda share_result: verified.append(share_result)
    )
    session._shared_key = b"shared"
    session._process_share_result(
        {"dev_confirm": "expected", "stok": "STOK", "start_seq": 3}
    )
    assert verified
    assert session._session_id == "STOK"
    assert session._sequence == 3

    session._expected_dev_confirm = "expected"
    session._shared_key = b"shared"
    with pytest.raises(KasaException, match="Missing session fields"):
        session._process_share_result({"dev_confirm": "expected"})

    session._expected_dev_confirm = "expected"
    session._shared_key = b"shared"
    with pytest.raises(KasaException, match="Missing session fields"):
        session._process_share_result({"dev_confirm": "expected", "sessionId": "SID"})

    session._expected_dev_confirm = "expected"
    session._shared_key = b"shared"
    with pytest.raises(KasaException, match="Invalid session fields"):
        session._process_share_result(
            {
                "dev_confirm": "expected",
                "sessionId": "SID",
                "start_seq": "bad",
            }
        )

    session._expected_dev_confirm = "expected"
    session._shared_key = None
    with pytest.raises(KasaException, match="shared key was not derived"):
        session._process_share_result(
            {"dev_confirm": "expected", "sessionId": "SID", "start_seq": 1}
        )
    await transport.close()


# --------------------------
# Certificate and TLS Helpers
# --------------------------


def test_cipher_and_nonce_helpers() -> None:
    with pytest.raises(KasaException, match="Unsupported TPAP session cipher"):
        tp.TpapEncryptionSession._cipher_parameters("bogus")
    with pytest.raises(ValueError, match="base nonce too short"):
        tp.TpapEncryptionSession._nonce_from_base(b"\x00\x01\x02", 1)


def test_load_certificate_value_variants() -> None:
    cert_key = ec.generate_private_key(ec.SECP256R1())
    cert = _build_certificate(cert_key, "leaf", "leaf", cert_key)
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    der_b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()

    assert tp.TpapTransport._load_certificate_value(pem).subject == cert.subject
    assert tp.TpapTransport._load_certificate_value(der_b64).subject == cert.subject

    with pytest.raises(KasaException, match="Empty certificate value"):
        tp.TpapTransport._load_certificate_value("   ")
    with pytest.raises(KasaException, match="Invalid certificate value"):
        tp.TpapTransport._load_certificate_value("totally-invalid")


def test_verify_certificate_validity_handles_naive_datetimes() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    valid = SimpleNamespace(
        not_valid_before=now - timedelta(days=1),
        not_valid_after=now + timedelta(days=1),
    )
    tp.TpapTransport._verify_certificate_validity(cast(Any, valid))

    expired = SimpleNamespace(
        not_valid_before=now - timedelta(days=3),
        not_valid_after=now - timedelta(days=2),
    )
    with pytest.raises(KasaException, match="outside its validity period"):
        tp.TpapTransport._verify_certificate_validity(cast(Any, expired))


def test_verify_certificate_signature_variants() -> None:
    ec_root = ec.generate_private_key(ec.SECP256R1())
    ec_leaf = ec.generate_private_key(ec.SECP256R1())
    ec_cert = _build_certificate(ec_leaf, "leaf", "root", ec_root)
    ec_issuer = _build_certificate(ec_root, "root", "root", ec_root, is_ca=True)
    tp.TpapTransport._verify_certificate_signature(ec_cert, ec_issuer)

    rsa_root = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_leaf = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_cert = _build_certificate(rsa_leaf, "leaf", "root", rsa_root)
    rsa_issuer = _build_certificate(rsa_root, "root", "root", rsa_root, is_ca=True)
    tp.TpapTransport._verify_certificate_signature(rsa_cert, rsa_issuer)

    no_hash_cert = SimpleNamespace(signature_hash_algorithm=None)
    with pytest.raises(KasaException, match="hash algorithm is unavailable"):
        tp.TpapTransport._verify_certificate_signature(
            cast(Any, no_hash_cert),
            cast(Any, SimpleNamespace(public_key=lambda: ec_root.public_key())),
        )

    bad_issuer = SimpleNamespace(public_key=lambda: object())
    with pytest.raises(KasaException, match="Unsupported DAC issuer public key type"):
        tp.TpapTransport._verify_certificate_signature(ec_cert, cast(Any, bad_issuer))


def test_verify_dac_certificate_chain_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_cert = _build_certificate(root_key, "root", "root", root_key, is_ca=True)
    dac_key = ec.generate_private_key(ec.SECP256R1())
    dac_cert = _build_certificate(dac_key, "dac", "root", root_key)

    monkeypatch.setattr(
        tp.TpapTransport,
        "_load_root_ca_certificate",
        classmethod(lambda cls: root_cert),
        raising=True,
    )
    tp.TpapTransport._verify_dac_certificate_chain(dac_cert, None)

    monkeypatch.setattr(
        tp.TpapTransport,
        "_load_root_ca_certificate",
        classmethod(lambda cls: (_ for _ in ()).throw(ValueError("boom"))),
        raising=True,
    )
    with pytest.raises(
        KasaException, match="DAC certificate chain verification failed"
    ):
        tp.TpapTransport._verify_dac_certificate_chain(dac_cert, None)


# --------------------------
# Transport and Payload Handling
# --------------------------


@pytest.mark.asyncio
async def test_transport_properties_and_initial_url_helpers() -> None:
    config = DeviceConfig("tpap-host")
    config.credentials_hash = "hash"
    config.connection_type.http_port = 8080
    transport = tp.TpapTransport(config=config)
    transport._known_tpap_tls = 2

    assert transport.default_port == 8080
    assert transport.credentials_hash == "hash"
    assert transport._get_initial_app_url() == URL("https://tpap-host:4433")
    await transport.close()

    https_transport = tp.TpapTransport(config=DeviceConfig("secure-host"))
    https_transport._config.connection_type.https = True
    assert https_transport.default_port == tp.TpapTransport.DEFAULT_HTTPS_PORT
    await https_transport.close()


def test_should_retry_live_session_variants() -> None:
    assert tp.TpapTransport._should_retry_live_session(
        _ConnectionError("Connection reset by peer")
    )
    assert not tp.TpapTransport._should_retry_live_session(
        _ConnectionError("different connection issue")
    )
    assert not tp.TpapTransport._should_retry_live_session(KasaException("x"))
    assert not tp.TpapTransport._should_retry_live_session(
        _RetryableError("x", error_code=SmartErrorCode.LOGIN_ERROR)
    )


@pytest.mark.asyncio
async def test_get_ssl_context_caches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    created = 0

    def fake_create_ssl_context() -> bool:
        nonlocal created
        created += 1
        return False

    monkeypatch.setattr(transport, "_create_ssl_context", fake_create_ssl_context)

    assert await transport.get_ssl_context() is False
    assert await transport.get_ssl_context() is False
    assert created == 1


@pytest.mark.asyncio
async def test_create_ssl_context_for_tls0_and_tls1() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session

    session._tpap_tls = 0
    assert transport._create_ssl_context() is False

    session._tpap_tls = 1
    context = transport._create_ssl_context()
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE


def test_payload_and_sequence_helpers() -> None:
    key, base_nonce = tp.TpapEncryptionSession.key_nonce_from_shared(
        b"shared-secret", "aes_128_ccm"
    )
    session = object.__new__(tp.TpapEncryptionSession)
    session._cipher_id = "aes_128_ccm"
    session._sequence = 5
    session._ds_url = URL("https://tpap-host/stok=SID/ds")
    session._key = key
    session._base_nonce = base_nonce
    session._session_id = "SID"

    payload, seq = session.encrypt("hello")
    assert seq == 5

    session._sequence = 5
    session.advance(5)
    assert session._sequence == 6
    session.advance(3)
    assert session._sequence == 6

    with pytest.raises(KasaException, match="response too short"):
        session.decrypt(b"\x00\x00\x00\x01", 1)

    encrypted = tp.TpapEncryptionSession._encrypt_payload(
        "aes_128_ccm", key, base_nonce, b"world", 8
    )
    wrapped = struct.pack(">I", 8) + encrypted
    assert session.decrypt(wrapped, 7) == b"world"


@pytest.mark.asyncio
async def test_send_reraises_non_retryable_error() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))

    async def fake_send_once(request: str) -> dict[str, Any]:
        del request
        raise KasaException("boom")

    transport._send_once = fake_send_once  # type: ignore[assignment]

    with pytest.raises(KasaException, match="boom"):
        await transport.send("{}")


@pytest.mark.asyncio
async def test_send_once_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    transport, session = _make_established_transport()

    async def fake_handshake() -> None:
        session._ds_url = None

    transport._state = tp.TransportState.NOT_ESTABLISHED
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)
    with pytest.raises(KasaException, match="not established"):
        await transport._send_once("{}")

    _establish_session(transport, session)
    transport._send_lock = None  # type: ignore[assignment]

    async def post_bad_status(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, bytes]:
        del url, json, data, headers, ssl
        return 500, b"bad"

    transport._http_client.post = post_bad_status  # type: ignore[assignment]
    with pytest.raises(KasaException, match="unexpected status 500"):
        await transport._send_once("{}")
    assert transport._send_lock is not None

    async def post_dict_success(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return 200, {"error_code": 0, "result": {"ok": True}}

    transport._http_client.post = post_dict_success  # type: ignore[assignment]
    assert (await transport._send_once("{}"))["result"]["ok"] is True

    async def post_weird_type(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, int]:
        del url, json, data, headers, ssl
        return 200, 123

    transport._http_client.post = post_weird_type  # type: ignore[assignment]
    with pytest.raises(KasaException, match="Unexpected response body type"):
        await transport._send_once("{}")


@pytest.mark.asyncio
async def test_send_once_tls2_uses_post() -> None:
    transport, session = _make_established_transport()
    session._tpap_tls = 2

    async def post(
        url: URL,
        *,
        params: dict[str, Any] | None = None,
        data: bytes | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cookies_dict: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, bytes]:
        del params, json, cookies_dict, ssl
        assert url == session.ds_url
        assert headers == {"Content-Type": "application/octet-stream"}
        assert data is not None
        return 200, data

    transport._http_client.post = post  # type: ignore[assignment]

    out = await transport._send_once('{"result": {"ok": true}}')
    assert out["result"]["ok"] is True


@pytest.mark.asyncio
async def test_transport_close_resets_and_closes_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, session = _make_established_transport()
    closed = False

    async def fake_close() -> None:
        nonlocal closed
        closed = True

    monkeypatch.setattr(transport._http_client, "close", fake_close, raising=True)

    await transport.close()

    assert closed is True
    assert transport._state is tp.TransportState.NOT_ESTABLISHED
    assert session.is_established is False
    assert tp.TpapSmartCamTransport.USE_SMARTCAM_AUTH is True
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {
                "type": "password_sha_with_salt",
                "params": {"sha_name": 1, "sha_salt": "not-b64"},
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
        )
        == "pass"
    )


def test_transport_response_helpers_validate_dict_payloads() -> None:
    with pytest.raises(KasaException, match="Unexpected helper response body type"):
        tp.TpapTransport._require_response_dict(b"bad", context="helper")

    with pytest.raises(
        KasaException, match="Unexpected helper JSON response body type"
    ):
        tp.TpapTransport._load_json_dict(b"[]", context="helper")
