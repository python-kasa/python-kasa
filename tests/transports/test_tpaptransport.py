from __future__ import annotations

import base64
import hashlib
import json
import logging
import ssl
import struct
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.x509.oid import NameOID
from yarl import URL

import kasa.transports.tpaptransport as tp
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
    _ConnectionError,
    _RetryableError,
)
from kasa.protocols import SmartProtocol
from kasa.smart import SmartDevice
from kasa.transports import KlapTransportV2, SslAesTransport


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
        "dev_confirm": session._expected_dev_confirm,
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


def _make_established_transport() -> tuple[tp.TpapTransport, tp.TpapEncryptionSession]:
    transport = _make_tpap_transport("host")
    session = transport._encryption_session
    _establish_session(transport, session)
    return transport, session


def _make_tpap_transport(
    host: str = "tpap-host",
    *,
    family: DeviceFamily | None = None,
    credentials: Credentials | None = None,
) -> tp.TpapTransport:
    config = DeviceConfig(host)
    if family is not None:
        config.connection_type.device_family = family
    if credentials is not None:
        config.credentials = credentials
    return tp.TpapTransport(config=config)


def _make_camera_tpap_transport(host: str = "cam-host") -> tp.TpapTransport:
    return _make_tpap_transport(
        host,
        family=DeviceFamily.SmartIpCamera,
        credentials=Credentials("user", "pass"),
    )


def _build_certificate(
    private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    subject_common_name: str,
    issuer_common_name: str,
    issuer_private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    *,
    is_ca: bool = False,
    subject_alt_names: list[x509.GeneralName] | None = None,
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
    if subject_alt_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(subject_alt_names),
            critical=False,
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


async def test_session_encrypt_and_decrypt_roundtrip() -> None:
    transport, session = _make_established_transport()

    payload, seq = session.encrypt(b'{"ok": true}')
    assert seq == 10
    assert session._sequence == 11
    assert session.decrypt(payload, seq) == b'{"ok": true}'
    assert str(session.ds_url) == f"{transport._app_url}/stok=SID/ds"


@pytest.mark.parametrize(
    (
        "family",
        "discover_response",
        "expected_username",
        "expected_passcode_type",
        "expected_tls_mode",
        "expected_scheme",
        "expected_port",
    ),
    [
        pytest.param(
            None,
            _discover_response(pake=[2], user_hash_type=0),
            tp.TpapEncryptionSession._md5_hex("admin"),
            "userpw",
            2,
            "https",
            4567,
            id="iot-md5",
        ),
        pytest.param(
            None,
            _discover_response(pake=[2], user_hash_type=1),
            tp.TpapEncryptionSession._md5_hex("admin"),
            "userpw",
            2,
            "https",
            4567,
            id="iot-ignores-user-hash-type",
        ),
        pytest.param(
            None,
            _discover_response(tls=0, port=80),
            tp.TpapEncryptionSession._md5_hex("admin"),
            "default_userpw",
            0,
            "http",
            80,
            id="generic-http",
        ),
        pytest.param(
            DeviceFamily.SmartTapoHub,
            _discover_response(tls=0, port=80, pake=[2], user_hash_type=0, dac=True),
            tp.TpapEncryptionSession._md5_hex("admin"),
            "userpw",
            0,
            "http",
            80,
            id="tapo-hub-http-userpw",
        ),
    ],
)
async def test_session_perform_handshake_registers_expected_auth_values(
    monkeypatch: pytest.MonkeyPatch,
    family: DeviceFamily | None,
    discover_response: dict[str, Any],
    expected_username: str,
    expected_passcode_type: str,
    expected_tls_mode: int,
    expected_scheme: str,
    expected_port: int,
) -> None:
    transport = _make_tpap_transport(
        "handshake-host",
        family=family,
        credentials=Credentials("user", "pass"),
    )
    session = transport._encryption_session
    captured_register: dict[str, Any] = {}

    transport._http_client.post = _make_discover_post(  # type: ignore[assignment]
        discover_response
    )
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert captured_register["username"] == expected_username
    assert captured_register["encryption"] == ["aes_128_ccm"]
    assert captured_register["passcode_type"] == expected_passcode_type
    # Like the app, no stok is sent when there is no session to reuse
    assert "stok" not in captured_register
    assert session.is_established is True
    assert session.tls_mode == expected_tls_mode
    assert transport._app_url.scheme == expected_scheme
    assert transport._app_url.host == "handshake-host"
    assert transport._app_url.port == expected_port
    assert session.ds_url is not None
    assert session.ds_url.scheme == expected_scheme
    assert session.ds_url.host == "handshake-host"
    assert session.ds_url.port == expected_port
    assert session.ds_url.path == "/stok=STOK/ds"


async def test_session_camera_auth_uses_device_family() -> None:
    camera_transport = _make_camera_tpap_transport()

    hub_transport = _make_tpap_transport("hub-host", family=DeviceFamily.SmartTapoHub)
    robot_transport = _make_tpap_transport(
        "robot-host", family=DeviceFamily.SmartTapoRobovac
    )
    iot_transport = _make_tpap_transport()

    assert camera_transport._encryption_session._uses_camera_auth is True
    assert hub_transport._encryption_session._uses_camera_auth is False
    assert robot_transport._encryption_session._uses_camera_auth is False
    assert robot_transport._encryption_session._uses_robot_tpap_auth is True
    assert iot_transport._encryption_session._uses_camera_auth is False


async def test_smartcam_session_builds_password_candidates_without_lat() -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [2]

    assert session._get_candidate_secrets() == [
        tp.TpapEncryptionSession._md5_hex("pass"),
        tp.TpapEncryptionSession._sha256_hex_upper("pass"),
    ]


@pytest.mark.asyncio
async def test_smartcam_session_retries_next_candidate_on_handshake_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [2]
    attempted_candidates: list[str] = []

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        return {}

    def fake_iter_candidates() -> list[str]:
        return ["first", "second"]

    def fake_build_share_params(
        register_result: dict[str, Any], credentials_string: str
    ) -> dict[str, Any]:
        del register_result
        attempted_candidates.append(credentials_string)
        return {}

    def fake_establish_session(share_result: dict[str, Any]) -> None:
        del share_result
        if attempted_candidates[-1] == "first":
            raise KasaException("bad candidate")
        _establish_session(transport, session, session_id="CAM-SID", start_seq=4)

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session, "_get_candidate_secrets", fake_iter_candidates, raising=True
    )
    monkeypatch.setattr(
        session,
        "_build_share_params_from_register",
        fake_build_share_params,
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_establish_session_from_share_result",
        fake_establish_session,
        raising=True,
    )

    await session._perform_auth_handshake()

    assert attempted_candidates == ["first", "second"]
    assert session._session_id == "CAM-SID"


@pytest.mark.asyncio
async def test_smartcam_session_raises_when_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [2]

    monkeypatch.setattr(session, "_get_candidate_secrets", lambda: [], raising=True)

    with pytest.raises(AuthenticationError, match="no credential candidates"):
        await session._perform_auth_handshake()


@pytest.mark.asyncio
async def test_smartcam_session_raises_when_no_supported_passcode_type() -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [9]

    with pytest.raises(AuthenticationError, match="no supported passcode type"):
        await session._perform_auth_handshake()


@pytest.mark.asyncio
async def test_smartcam_session_reraises_last_candidate_error(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [2]

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        return {}

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session, "_get_candidate_secrets", lambda: ["only"], raising=True
    )
    monkeypatch.setattr(
        session,
        "_build_share_params_from_register",
        lambda register_result, credentials_string: {},
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_establish_session_from_share_result",
        lambda share_result: (_ for _ in ()).throw(KasaException("last failure")),
        raising=True,
    )

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(KasaException, match="last failure"),
    ):
        await session._perform_auth_handshake()

    assert "all password-based camera candidates failed" in caplog.text


@pytest.mark.asyncio
async def test_generic_tpap_session_reraises_last_candidate_error_without_hint(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = DeviceConfig("tpap-host")
    config.credentials = Credentials("user", "pass")
    transport = tp.TpapTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [2]

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        return {}

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session, "_get_candidate_secrets", lambda: ["only"], raising=True
    )
    monkeypatch.setattr(
        session,
        "_build_share_params_from_register",
        lambda register_result, credentials_string: {},
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_establish_session_from_share_result",
        lambda share_result: (_ for _ in ()).throw(KasaException("last failure")),
        raising=True,
    )

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(KasaException, match="last failure"),
    ):
        await session._perform_auth_handshake()

    assert "all password-based camera candidates failed" not in caplog.text


@pytest.mark.asyncio
async def test_smartcam_session_propagates_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [2]
    attempts: list[str] = []

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        del params
        if step_name == "pake_register":
            return {"extra_crypt": {}}
        raise _RetryableError("retry me", error_code=SmartErrorCode.SESSION_EXPIRED)

    def fake_build_share_params(
        register_result: dict[str, Any], credentials_string: str
    ) -> dict[str, Any]:
        del register_result
        attempts.append(credentials_string)
        return {}

    monkeypatch.setattr(session, "_login", fake_login, raising=True)
    monkeypatch.setattr(
        session,
        "_get_candidate_secrets",
        lambda: ["first", "second"],
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_build_share_params_from_register",
        fake_build_share_params,
        raising=True,
    )

    with pytest.raises(_RetryableError, match="retry me"):
        await session._perform_auth_handshake()

    assert attempts == ["first"]


@pytest.mark.asyncio
async def test_iot_session_adds_dac_nonce_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _make_tpap_transport(
        family=DeviceFamily.SmartTapoPlug,
        credentials=Credentials("user", "pass"),
    )
    session = transport._encryption_session
    session._tpap_pake = [5]
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
        session, "_get_candidate_secrets", lambda: ["candidate"], raising=True
    )
    monkeypatch.setattr(
        session,
        "_build_share_params_from_register",
        lambda register_result, credentials_string: {},
        raising=True,
    )
    monkeypatch.setattr(
        session,
        "_establish_session_from_share_result",
        lambda share_result: _establish_session(
            transport, session, session_id="DAC-SID", start_seq=2
        ),
        raising=True,
    )

    await session._perform_auth_handshake()

    assert captured_share_params is not None
    assert captured_share_params["dac_nonce"]
    assert len(base64.b64decode(captured_share_params["dac_nonce"])) == 32
    assert session._session_id == "DAC-SID"


@pytest.mark.parametrize(
    ("tls", "dac", "pake", "expected"),
    [
        pytest.param(0, True, [2], True, id="plain-tpap-dac"),
        pytest.param(0, False, [2], False, id="plain-tpap-no-dac"),
        pytest.param(1, True, [2], False, id="tls-tpap-dac"),
    ],
)
async def test_use_dac_certification_uses_discovered_dac_support(
    tls: int, dac: bool, pake: list[int], expected: bool
) -> None:
    transport = _make_tpap_transport("tpap-host")
    session = transport._encryption_session
    session._tpap_pake = pake
    session._tpap_tls = tls
    session._tpap_dac = dac

    assert session._use_dac_certification() is expected


@pytest.mark.parametrize(
    ("family", "pake", "expected"),
    [
        pytest.param(
            DeviceFamily.SmartIpCamera,
            [1],
            "userpw",
            id="camera-setup-code",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            [0, 2],
            "userpw",
            id="camera-pake-two-before-zero",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug, [0], "default_userpw", id="default-pake-zero"
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug, [1], "default_userpw", id="iot-pake-one"
        ),
        pytest.param(DeviceFamily.SmartTapoPlug, [5], "userpw", id="iot-pake-five"),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            [2, 3],
            "userpw",
            id="iot-userpw-before-shared-token",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            [0, 2],
            "default_userpw",
            id="iot-default-before-userpw",
        ),
        pytest.param(DeviceFamily.IotSmartBulb, [2], "userpw", id="kasa-iot-pake-two"),
        pytest.param(
            DeviceFamily.IotSmartPlugSwitch,
            [0, 2],
            "userpw",
            id="kasa-iot-userpw-before-default",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            [2, 3],
            "userpw",
            id="kasa-iot-userpw-before-shared-token",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [3], "shared_token", id="kasa-iot-shared-token"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [0], "default_userpw", id="kasa-iot-pake-zero"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [1], "default_userpw", id="kasa-iot-pake-one"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [5], "default_userpw", id="kasa-iot-pake-five"
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb, [], "default_userpw", id="kasa-iot-empty-pake"
        ),
        pytest.param(DeviceFamily.SmartTapoHub, [2], "userpw", id="hub-userpw"),
        pytest.param(
            DeviceFamily.SmartTapoRobovac,
            [2, 3],
            "userpw",
            id="robot-userpw-before-shared-token",
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac,
            [5],
            "default_userpw",
            id="robot-pake-five-default",
        ),
        pytest.param(DeviceFamily.SmartTapoBulb, [5], "userpw", id="bulb-pake-five"),
        pytest.param(
            DeviceFamily.SmartTapoRobovac,
            [9],
            "default_userpw",
            id="robot-unknown-pake",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            [3],
            "shared_token",
            id="camera-shared-token",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug, [], "default_userpw", id="default-empty-pake"
        ),
        pytest.param(DeviceFamily.SmartIpCamera, [], None, id="camera-empty-pake"),
        # Like the app, no announced passcode types means nothing to log in with
        pytest.param(DeviceFamily.SmartTapoPlug, None, None, id="default-no-pake"),
        pytest.param(DeviceFamily.IotSmartBulb, None, None, id="kasa-iot-no-pake"),
        pytest.param(DeviceFamily.SmartTapoRobovac, None, None, id="robot-no-pake"),
        pytest.param(DeviceFamily.SmartIpCamera, None, None, id="camera-no-pake"),
    ],
)
async def test_get_passcode_type(
    family: DeviceFamily | None, pake: list[int] | None, expected: str | None
) -> None:
    transport = _make_tpap_transport("tpap-host", family=family)
    session = transport._encryption_session
    session._tpap_pake = pake

    assert session._get_passcode_type() == expected


@pytest.mark.parametrize(
    ("pake", "expected"),
    [
        pytest.param([1], ["pass"], id="setup-code-uses-raw-password"),
        pytest.param(
            [3], [tp.TpapEncryptionSession._md5_hex("pass")], id="shared-token"
        ),
        pytest.param([9], [], id="unknown-pake"),
        pytest.param([], [], id="missing-pake"),
    ],
)
async def test_camera_candidate_secrets(pake: list[int], expected: list[str]) -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = pake

    assert session._get_candidate_secrets() == expected


async def test_smartcam_candidate_builder_dedupes_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [2]
    monkeypatch.setattr(session, "_md5_hex", lambda value: "same", raising=False)
    monkeypatch.setattr(
        session, "_sha256_hex_upper", lambda value: "same", raising=False
    )

    assert session._get_candidate_secrets() == ["same"]


async def test_smartcam_resolve_credentials_applies_extra_crypt() -> None:
    transport = _make_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [2]
    register_result = {
        "extra_crypt": {"type": "password_shadow", "params": {"passwd_id": 2}}
    }

    assert session._resolve_credentials(register_result, "candidate") == (
        tp.TpapEncryptionSession._sha1_hex("candidate")
    )


async def test_default_passcode_resolve_credentials_returns_candidate() -> None:
    transport = _make_tpap_transport()
    session = transport._encryption_session
    session._tpap_pake = [0]
    session._device_mac = "AA:BB:CC:DD:EE:FF"

    assert session._resolve_credentials({}, "candidate") == "candidate"


async def test_tls2_ssl_context_loads_root_ca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_cert = _build_certificate(root_key, "root", "root", root_key, is_ca=True)

    monkeypatch.setattr(
        tp.TpapTransport,
        "TPAP_ROOT_CA_PEM",
        root_cert.public_bytes(serialization.Encoding.PEM).decode(),
        raising=True,
    )

    transport = tp.TpapTransport(config=DeviceConfig("tls-host"))
    transport._encryption_session._tpap_tls = 2
    context = transport._create_ssl_context()

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.get_ca_certs()


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

    session._verify_dac_proof(share_result)

    share_result["dac_proof"] = base64.b64encode(b"bad-proof").decode()
    with pytest.raises(KasaException, match="Invalid DAC proof signature"):
        session._verify_dac_proof(share_result)


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


@pytest.mark.parametrize(
    ("first_failure", "session_id", "start_seq"),
    [
        pytest.param("session-expired", "SID-RETRY", 20, id="session-expired"),
        pytest.param("connection-reset", "SID-CONN", 30, id="connection-reset"),
    ],
)
async def test_transport_send_retries_live_session_failures(
    monkeypatch: pytest.MonkeyPatch,
    first_failure: str,
    session_id: str,
    start_seq: int,
) -> None:
    transport, session = _make_established_transport()
    request_calls = 0

    async def fake_handshake() -> None:
        _establish_session(
            transport, session, session_id=session_id, start_seq=start_seq
        )

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
            if first_failure == "session-expired":
                return 200, {"error_code": SmartErrorCode.SESSION_EXPIRED.value}
            raise _ConnectionError("Connection reset by peer")
        assert data is not None
        return 200, data

    transport._http_client.post = post  # type: ignore[assignment]
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)

    out = await transport.send('{"result": {"retry": true}}')

    assert out["result"]["retry"] is True
    assert request_calls == 2
    assert session._session_id == session_id
    assert session._sequence == start_seq + 1


def _dropping_post(
    replies: list[tuple[int, Any]],
) -> tuple[Any, list[int]]:
    """Answer /ds requests with the given replies, then echo the payload."""
    calls: list[int] = []

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, Any]:
        del url, json, headers, ssl
        calls.append(len(calls))
        if len(calls) <= len(replies):
            return replies[len(calls) - 1]
        return 200, data

    return post, calls


@pytest.mark.parametrize(
    ("status", "body"),
    [
        pytest.param(500, b'{"error_code": -40420}', id="http-40420"),
        pytest.param(500, b'{"error_code": -40421}', id="http-40421"),
        pytest.param(500, b'{"err_code": -2402}', id="http-err_code-2402"),
        pytest.param(500, b'{"error_code": -2101}', id="http-2101"),
        pytest.param(200, {"error_code": -2402}, id="reply-2402"),
    ],
)
async def test_send_logs_in_again_once_when_session_dropped(
    monkeypatch: pytest.MonkeyPatch, status: int, body: Any
) -> None:
    """Like the app, a dropped session gets one new login and one resend."""
    transport, session = _make_established_transport()
    handshakes = 0

    async def fake_handshake() -> None:
        nonlocal handshakes
        handshakes += 1
        _establish_session(transport, session, session_id="SID-NEW", start_seq=40)

    post, calls = _dropping_post([(status, body)])
    transport._http_client.post = post  # type: ignore[assignment]
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)

    out = await transport.send('{"result": {"ok": true}}')

    assert out["result"]["ok"] is True
    assert len(calls) == 2
    assert handshakes == 1
    assert session._session_id == "SID-NEW"


async def test_send_logs_in_again_when_fresh_session_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry also applies when this call made the first login."""
    transport, session = _make_established_transport()
    await transport.reset()
    handshakes = 0

    async def fake_handshake() -> None:
        nonlocal handshakes
        handshakes += 1
        _establish_session(transport, session, session_id=f"SID-{handshakes}")

    post, calls = _dropping_post([(500, b'{"error_code": -2402}')])
    transport._http_client.post = post  # type: ignore[assignment]
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)

    out = await transport.send('{"result": {"ok": true}}')

    assert out["result"]["ok"] is True
    assert (len(calls), handshakes) == (2, 2)


async def test_send_gives_up_when_session_dropped_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new login and resend happen once only."""
    transport, session = _make_established_transport()
    handshakes = 0

    async def fake_handshake() -> None:
        nonlocal handshakes
        handshakes += 1
        _establish_session(transport, session)

    dropped = (500, b'{"error_code": -2402}')
    post, calls = _dropping_post([dropped, dropped, dropped])
    transport._http_client.post = post  # type: ignore[assignment]
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)

    with pytest.raises(DeviceError, match="device dropped the session"):
        await transport.send('{"result": {"ok": true}}')

    assert (len(calls), handshakes) == (2, 1)
    assert not session.is_established


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b'{"error_code": -1}', id="other-code"),
        pytest.param(b"<html>bad gateway</html>", id="not-json"),
        pytest.param(b"[]", id="json-not-an-object"),
        pytest.param(b"", id="empty"),
    ],
)
async def test_send_does_not_log_in_again_for_other_http_errors(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    transport, session = _make_established_transport()
    handshakes = 0

    async def fake_handshake() -> None:
        nonlocal handshakes
        handshakes += 1

    post, calls = _dropping_post([(500, body)])
    transport._http_client.post = post  # type: ignore[assignment]
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)

    with pytest.raises(KasaException, match="status 500"):
        await transport.send('{"result": {"ok": true}}')

    assert (len(calls), handshakes) == (1, 0)


@pytest.mark.asyncio
async def test_transport_reset_clears_session_state() -> None:
    transport, session = _make_established_transport()

    await transport.reset()

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

    assert session.is_established is True


@pytest.mark.asyncio
async def test_perform_handshake_restarts_when_session_was_invalidated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, session = _make_established_transport()
    session._invalidate_session()
    discover_called = False

    async def fake_discover() -> None:
        nonlocal discover_called
        discover_called = True

    async def fake_auth_handshake() -> None:
        _establish_session(transport, session, session_id="SID-NEW", start_seq=14)

    monkeypatch.setattr(session, "_discover", fake_discover, raising=True)
    monkeypatch.setattr(
        session, "_perform_auth_handshake", fake_auth_handshake, raising=True
    )

    await session.perform_handshake()

    assert discover_called is True
    assert session.is_established is True
    assert session._session_id == "SID-NEW"


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

    with pytest.raises(KasaException, match="TPAP discover failed"):
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
async def test_discover_tls0_over_https_does_not_downgrade_to_http() -> None:
    """RV50 Pro Omni answers the in-band discover over TLS with tls=0."""
    config = DeviceConfig("tpap-host")
    config.connection_type.https = True
    config.connection_type.http_port = 4433
    transport = tp.TpapTransport(config=config)
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
        return 200, _discover_response(tls=0, port=4433, pake=[2], dac=True)

    transport._http_client.post = post  # type: ignore[assignment]

    await session._discover()
    session._update_transport_url()

    assert transport._app_url == URL("https://tpap-host:4433")
    assert session.tls_mode == 2
    assert transport._known_tpap_tls == 2
    assert not session._use_dac_certification()
    await transport.close()


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

    with pytest.raises(KasaException, match="TPAP pake_register failed"):
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


@pytest.mark.parametrize(
    ("step_name", "expected"),
    [
        pytest.param("pake_share", AuthenticationError, id="share-auth-error"),
        pytest.param("pake_register", DeviceError, id="register-device-error"),
    ],
)
@pytest.mark.asyncio
async def test_login_stat_access_error_on_share_is_authentication_error(
    step_name: str, expected: type[Exception]
) -> None:
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
        return 200, {"error_code": SmartErrorCode.STAT_ACCESS_ERROR.value}

    transport._http_client.post = post  # type: ignore[assignment]

    with pytest.raises(expected) as exc_info:
        await session._login({}, step_name=step_name)
    assert exc_info.value.error_code is SmartErrorCode.STAT_ACCESS_ERROR  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_send_wrong_password_fails_once_without_retry() -> None:
    """A rejected passcode must not trigger the live-session retry."""
    transport = _make_tpap_transport(
        "hub-host",
        family=DeviceFamily.SmartKasaHub,
        credentials=Credentials("user@example.com", "wrong"),
    )
    share_attempts = 0

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        nonlocal share_attempts
        del url, data, headers, ssl
        assert json is not None
        sub_method = json["params"]["sub_method"]
        if sub_method == "discover":
            return 200, _discover_response(tls=0, port=80, pake=[2])
        if sub_method == "pake_register":
            return 200, {
                "error_code": 0,
                "result": _register_result(
                    extra_crypt={"type": "password_shadow", "params": {"passwd_id": 2}},
                    cipher_suites=1,
                ),
            }
        assert sub_method == "pake_share"
        share_attempts += 1
        return 200, {"error_code": SmartErrorCode.STAT_ACCESS_ERROR.value}

    transport._http_client.post = post  # type: ignore[assignment]

    with pytest.raises(AuthenticationError, match="credentials rejected"):
        await transport.send('{"method": "get_device_info"}')
    assert share_attempts == 1
    assert not transport._encryption_session.is_established


def _fake_login_device(
    transport: tp.TpapTransport,
    *,
    discover: dict[str, Any] | None = None,
    pake_register: dict[str, Any] | None = None,
    pake_share: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Answer the login steps with the given replies and count each step."""
    counts = {"discover": 0, "pake_register": 0, "pake_share": 0}
    replies = {
        "discover": discover or _discover_response(tls=0, port=80, pake=[2]),
        "pake_register": pake_register
        or {
            "error_code": 0,
            "result": _register_result(
                extra_crypt={"type": "password_shadow", "params": {"passwd_id": 2}},
                cipher_suites=1,
            ),
        },
        "pake_share": pake_share or {"error_code": 0},
    }

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
        sub_method = json["params"]["sub_method"]
        counts[sub_method] += 1
        return 200, replies[sub_method]

    transport._http_client.post = post  # type: ignore[assignment]
    return counts


@pytest.mark.parametrize(
    ("family", "error_code", "expected", "logins"),
    [
        pytest.param(
            DeviceFamily.SmartKasaHub,
            SmartErrorCode.STAT_ACCESS_ERROR,
            AuthenticationError,
            1,
            id="hub-wrong-password",
        ),
        pytest.param(
            DeviceFamily.SmartKasaHub,
            SmartErrorCode.SESSION_EXPIRED,
            DeviceError,
            1,
            id="hub-retryable-code",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            SmartErrorCode.STAT_ACCESS_ERROR,
            AuthenticationError,
            2,
            id="camera-wrong-password",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            SmartErrorCode.SESSION_EXPIRED,
            DeviceError,
            2,
            id="camera-retryable-code",
        ),
    ],
)
async def test_rejected_login_is_sent_once_per_candidate(
    mocker: Any,
    family: DeviceFamily,
    error_code: SmartErrorCode,
    expected: type[KasaException],
    logins: int,
) -> None:
    """A rejected pake_share is not repeated by the transport or the protocol.

    Cameras try two password hashes, every other device one password.
    """
    mocker.patch("asyncio.sleep")
    transport = _make_tpap_transport(
        "login-host", family=family, credentials=Credentials("user", "wrong")
    )
    counts = _fake_login_device(transport, pake_share={"error_code": error_code.value})
    protocol = SmartProtocol(transport=transport)

    with pytest.raises(expected) as exc_info:
        await protocol.query({"get_device_info": None})

    assert type(exc_info.value) is expected
    assert exc_info.value.error_code is error_code  # type: ignore[attr-defined]
    assert counts["pake_share"] == logins
    # Cameras go straight to pake_register, like the app
    is_camera = family in tp.TpapTransport.CAMERA_AUTH_DEVICE_FAMILIES
    assert counts["discover"] == (0 if is_camera else 1)


async def test_rejected_login_reports_attempts_left() -> None:
    transport = _make_tpap_transport(
        "login-host",
        family=DeviceFamily.SmartKasaHub,
        credentials=Credentials("user", "wrong"),
    )
    _fake_login_device(
        transport,
        pake_share={
            "error_code": SmartErrorCode.STAT_ACCESS_ERROR.value,
            "error_info": {
                "lockedMinute": 0,
                "failedAttempts": 3,
                "remainAttempts": 12,
            },
        },
    )

    with pytest.raises(AuthenticationError, match="12 attempts left"):
        await transport.send('{"method": "get_device_info"}')


@pytest.mark.parametrize(
    ("family", "step", "error_info", "message"),
    [
        pytest.param(
            DeviceFamily.SmartKasaHub,
            "discover",
            {"lockedMinute": 25, "failedAttempts": 15, "remainAttempts": 0},
            "retry in 25 minutes",
            id="discover-locked",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            "pake_share",
            {"lockedMinute": 30, "failedAttempts": 5, "remainAttempts": 0},
            "retry in 30 minutes",
            id="share-locked",
        ),
        pytest.param(
            DeviceFamily.SmartKasaHub,
            "pake_register",
            {"failedAttempts": 15, "remainAttempts": 0},
            r"device blocked after failed logins \(",
            id="register-no-attempts-left",
        ),
    ],
)
async def test_locked_device_is_reported_as_blocked(
    mocker: Any,
    family: DeviceFamily,
    step: str,
    error_info: dict[str, int],
    message: str,
) -> None:
    """A locked device stops the login at once and is not retried.

    A locked KH100 answers every step, even discover, with ACCOUNT_ERROR and
    error_info.
    """
    mocker.patch("asyncio.sleep")
    transport = _make_tpap_transport(
        "login-host", family=family, credentials=Credentials("user", "pw")
    )
    reply = {"error_code": SmartErrorCode.ACCOUNT_ERROR.value, "error_info": error_info}
    counts = _fake_login_device(transport, **{step: reply})
    protocol = SmartProtocol(transport=transport)

    with pytest.raises(DeviceError, match=message) as exc_info:
        await protocol.query({"get_device_info": None})

    assert exc_info.value.error_code is SmartErrorCode.DEVICE_BLOCKED
    assert counts[step] == 1
    assert counts["pake_share"] == (1 if step == "pake_share" else 0)


async def test_send_does_not_retry_failed_handshake() -> None:
    """send() retries a live session, not a handshake that never completed."""
    transport = _make_tpap_transport(
        "login-host",
        family=DeviceFamily.SmartKasaHub,
        credentials=Credentials("user", "pw"),
    )
    counts = _fake_login_device(
        transport, pake_register={"error_code": SmartErrorCode.SESSION_EXPIRED.value}
    )

    with pytest.raises(_RetryableError):
        await transport.send('{"method": "get_device_info"}')

    assert counts == {"discover": 1, "pake_register": 1, "pake_share": 0}


@pytest.mark.asyncio
async def test_login_tls2_uses_post() -> None:
    transport = _make_tpap_transport("login-host", family=DeviceFamily.SmartTapoPlug)
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
    transport = _make_tpap_transport(family=DeviceFamily.SmartTapoPlug)
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
async def test_private_handle_response_error_code_covers_invalid_retry_auth_and_device() -> (
    None
):
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._tpap_tls = 2
    session._tpap_port = 4567
    transport._app_url = URL("https://tpap-host:4567")
    _establish_session(transport, session, session_id="SID-AUTH", start_seq=4)

    with pytest.raises(DeviceError) as invalid_code:
        session._handle_response_error_code({"error_code": "not-an-int"}, "ignored")
    assert invalid_code.value.error_code is SmartErrorCode.INTERNAL_UNKNOWN_ERROR

    with pytest.raises(_RetryableError):
        session._handle_response_error_code(
            {"error_code": SmartErrorCode.SESSION_EXPIRED.value}, "retry"
        )
    with pytest.raises(DeviceError):
        session._handle_response_error_code(
            {"error_code": SmartErrorCode.STAT_ACCESS_ERROR.value}, "retry"
        )

    with pytest.raises(AuthenticationError):
        session._handle_response_error_code(
            {"error_code": SmartErrorCode.LOGIN_ERROR.value}, "auth"
        )

    assert session.is_established is False
    assert session.tls_mode == 2
    assert session._tpap_port == 4567
    assert transport._app_url == URL("https://tpap-host:4567")

    with pytest.raises(DeviceError):
        session._handle_response_error_code(
            {"error_code": SmartErrorCode.DEVICE_ERROR.value}, "device"
        )
    await transport.close()


# --------------------------
# Helper and Credential Functions
# --------------------------


def test_encode_w_and_hash_helpers_cover_edge_cases() -> None:
    assert tp.TpapEncryptionSession._encode_w(0, 32) == bytes(32)
    assert tp.TpapEncryptionSession._encode_w(0x80, 32) == bytes(31) + b"\x80"
    # 31 significant bytes with the top bit clear: the old minimal encoding
    # dropped the leading zero byte here.
    assert tp.TpapEncryptionSession._encode_w(1 << 240, 32) == (1 << 240).to_bytes(
        32, "big"
    )
    assert (
        tp.TpapEncryptionSession._hash("SHA512", b"data")
        == hashlib.sha512(b"data").digest()
    )
    assert len(tp.TpapEncryptionSession._cmac_aes(b"\x00" * 16, b"data")) == 16


@pytest.mark.parametrize(
    "register_overrides",
    [
        pytest.param({"iterations": None}, id="null"),
        pytest.param({}, id="absent"),
    ],
)
async def test_share_params_default_iterations(
    monkeypatch: pytest.MonkeyPatch, register_overrides: dict[str, Any]
) -> None:
    """Without iterations, PBKDF2 uses the app's default of 10000."""
    transport = _make_tpap_transport()
    session = transport._encryption_session
    session._user_random = session._base64(b"\x01" * 32)
    used: list[int] = []

    def derive_ab(credentials: bytes, salt: bytes, iterations: int, hash_len: int):
        used.append(iterations)
        return 5, 7

    monkeypatch.setattr(session, "_derive_ab", derive_ab)
    register_result = _register_result(cipher_suites=1)
    register_result.pop("iterations")
    register_result.update(register_overrides)

    session._build_share_params_from_register(register_result, "secret")

    assert used == [10000]


async def test_session_keys_use_sha256_for_sha512_suites() -> None:
    """The session key and nonce use HKDF-SHA256 even when the suite hash is SHA512."""
    transport = _make_tpap_transport()
    session = transport._encryption_session
    session._hkdf_hash = "SHA512"
    session._cipher_id = "aes_128_ccm"
    session._shared_key = b"shared-key"
    session._expected_dev_confirm = "expected"

    session._establish_session_from_share_result(
        {"dev_confirm": "expected", "stok": "STOK", "start_seq": 1}
    )

    def hkdf(algorithm: hashes.HashAlgorithm, salt: bytes, info: bytes, n: int):
        return HKDF(algorithm=algorithm, length=n, salt=salt, info=info).derive(
            b"shared-key"
        )

    key_labels = (b"tp-kdf-salt-aes128-key", b"tp-kdf-info-aes128-key", 16)
    iv_labels = (b"tp-kdf-salt-aes128-iv", b"tp-kdf-info-aes128-iv", 12)
    assert session._key == hkdf(hashes.SHA256(), *key_labels)
    assert session._base_nonce == hkdf(hashes.SHA256(), *iv_labels)
    assert session._key != hkdf(hashes.SHA512(), *key_labels)


async def test_share_params_encode_w0_at_curve_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """w0 keeps its leading zero bytes in the transcript, as the app writes it."""
    transport = _make_tpap_transport()
    session = transport._encryption_session
    session._user_random = session._base64(b"\x01" * 32)
    small_w0 = 0x1234
    monkeypatch.setattr(session, "_derive_ab", lambda *args, **kwargs: (small_w0, 7))
    hashed: list[bytes] = []
    real_hash = tp.TpapEncryptionSession._hash

    def capture(algorithm: str, data: bytes) -> bytes:
        hashed.append(data)
        return real_hash(algorithm, data)

    monkeypatch.setattr(session, "_hash", capture)

    session._build_share_params_from_register(
        _register_result(cipher_suites=1), "secret"
    )

    w0_element = (32).to_bytes(8, "little") + small_w0.to_bytes(32, "big")
    assert any(data.endswith(w0_element) for data in hashed)


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


# The test vectors of https://www.akkadia.org/drepper/SHA-crypt.txt, which
# `openssl passwd -5` also produces.
@pytest.mark.parametrize(
    ("password", "prefix", "expected"),
    [
        pytest.param(
            "Hello world!",
            "$5$saltstring",
            "$5$saltstring$5B8vYYiY.CVt1RlTTf8KbXBH3hsxY/GNooZaBBGWEc5",
            id="default-rounds",
        ),
        pytest.param(
            "Hello world!",
            "$5$rounds=10000$saltstringsaltstring",
            "$5$rounds=10000$saltstringsaltst$3xv.VbSHBb41AL9AvLeujZkZRBAwqFMz2.opqey6IcA",
            id="rounds-in-prefix",
        ),
        pytest.param(
            "This is just a test",
            "$5$rounds=5000$toolongsaltstring",
            "$5$rounds=5000$toolongsaltstrin$Un/5jzAHMgOGZ5.mWJpuVolil07guHPvOW8mGRcvxa5",
            id="explicit-default-rounds-kept",
        ),
        pytest.param(
            "a very much longer text to encrypt.  "
            "This one even stretches over morethan one line.",
            "$5$rounds=1400$anotherlongsaltstring",
            "$5$rounds=1400$anotherlongsalts$Rx.j8H.h8HjEDGomFU8bDkXm3XIUnzyxf12oP84Bnq1",
            id="long-password",
        ),
        pytest.param(
            "we have a short salt string but not a short password",
            "$5$rounds=77777$short",
            "$5$rounds=77777$short$JiO1O3ZpDAxGJeaDIuqCoEFysAe1mZNJRs3pw0KQRd/",
            id="short-salt",
        ),
        pytest.param(
            "the minimum number is still observed",
            "$5$rounds=10$roundstoolow",
            "$5$rounds=1000$roundstoolow$yfvwcWrQ8l/K0DAWyuPMDNHpIVlTQebY9l/gL972bIC",
            id="rounds-below-minimum",
        ),
    ],
)
def test_sha256_crypt_shadow(password: str, prefix: str, expected: str) -> None:
    assert tp.TpapEncryptionSession._sha256_crypt(password, prefix) == expected


def test_sha256_crypt_shadow_ignores_passwd_rounds() -> None:
    """Like the app, only passwd_prefix sets the rounds; passwd_rounds is unused."""
    extra_crypt = {
        "type": "password_shadow",
        "params": {
            "passwd_id": 5,
            "passwd_prefix": "$5$saltstring",
            "passwd_rounds": 10000,
        },
    }
    assert (
        tp.TpapEncryptionSession._build_credentials(
            extra_crypt, "", "Hello world!", "AABBCCDDEEFF"
        )
        == "$5$saltstring$5B8vYYiY.CVt1RlTTf8KbXBH3hsxY/GNooZaBBGWEc5"
    )


# Produced by `openssl passwd -1`.
@pytest.mark.parametrize(
    ("password", "prefix", "expected"),
    [
        pytest.param("pass", "$1$saltsalt$", "$1$saltsalt$hZR.9zfJXcVTsa9iTxnQR1"),
        pytest.param("pass", "$1$salt", "$1$salt$M6xQvx9eSlM4zTu69di5B/"),
        pytest.param(
            "correct horse battery staple",
            "$1$longersaltstring$",
            "$1$longersa$COeekwSWUn4OO9X02U7s21",
            id="salt-truncated",
        ),
        pytest.param("", "$1$TFsy6I", "$1$TFsy6I$uDeFAJQ.oIhIuUsAK14Zf1", id="empty"),
    ],
)
def test_md5_crypt_shadow(password: str, prefix: str, expected: str) -> None:
    assert tp.TpapEncryptionSession._md5_crypt(password, prefix) == expected


def test_sha256_crypt_rejects_too_many_rounds() -> None:
    """The prefix rounds come from an unauthenticated reply and are hashed on the loop."""
    with pytest.raises(KasaException, match="too many passwd_prefix rounds"):
        tp.TpapEncryptionSession._sha256_crypt("pass", "$5$rounds=100001$salt$")


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


@pytest.mark.parametrize(
    ("extra_crypt", "expected"),
    [
        pytest.param(
            {
                "type": "password_shadow",
                "params": {"passwd_id": 1, "passwd_prefix": "$1$salt$"},
            },
            "not-pass",
            id="shadow-md5-prefix",
        ),
        pytest.param(
            {
                "type": "password_shadow",
                "params": {"passwd_id": 5, "passwd_prefix": "$5$salt$"},
            },
            "not-none",
            id="shadow-sha256-prefix",
        ),
        pytest.param(
            {"type": "password_authkey", "params": {}},
            "pass",
            id="authkey-missing-params",
        ),
        pytest.param(
            {"type": "password_shadow", "params": {"passwd_id": 99}},
            "pass",
            id="shadow-unknown-id",
        ),
        pytest.param(
            {"type": "password_shadow", "params": "not-a-dict"},
            "user/pass",
            id="shadow-invalid-params",
        ),
        pytest.param(
            {"type": "password_shadow"}, "user/pass", id="shadow-without-params"
        ),
        pytest.param(
            {"type": "password_authkey"}, "user/pass", id="authkey-without-params"
        ),
        pytest.param(
            {"type": "password_sha_with_salt"},
            "user/pass",
            id="sha-with-salt-without-params",
        ),
        pytest.param(
            {"type": "password_shadow", "params": {"passwd_id": "bad"}},
            "pass",
            id="shadow-invalid-passwd-id",
        ),
        pytest.param(
            {
                "type": "password_sha_with_salt",
                "params": {"sha_name": "bad", "sha_salt": "c2FsdA=="},
            },
            "pass",
            id="sha-with-salt-invalid-sha-name",
        ),
    ],
)
def test_build_credentials_fallback_paths(
    extra_crypt: dict[str, Any], expected: str
) -> None:
    result = tp.TpapEncryptionSession._build_credentials(
        extra_crypt,
        "user",
        "pass",
        "AABBCCDDEEFF",
    )

    if expected == "not-pass":
        assert result != "pass"
    elif expected == "not-none":
        assert result is not None
    else:
        assert result == expected


def test_build_credentials_without_params_or_username() -> None:
    """Without params and without a username the app uses the password alone."""
    assert (
        tp.TpapEncryptionSession._build_credentials(
            {"type": "password_shadow"}, "", "pass", "AABBCCDDEEFF"
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
    with pytest.raises(KasaException, match="Unsupported TPAP suite type"):
        tp.TpapEncryptionSession._suite_parameters(999)


async def test_build_share_params_from_register_requires_user_random() -> None:
    transport = _make_tpap_transport()
    session = transport._encryption_session

    with pytest.raises(KasaException, match="user random not initialized"):
        session._build_share_params_from_register({}, "secret")


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        pytest.param({"dev_random": ""}, "missing dev_random", id="missing-dev-random"),
        pytest.param({"dev_salt": ""}, "missing dev_salt", id="missing-dev-salt"),
        pytest.param({"dev_share": ""}, "missing dev_share", id="missing-dev-share"),
        pytest.param(
            {"cipher_suites": "bad"},
            "has invalid cipher_suites",
            id="invalid-cipher-suites-str",
        ),
        pytest.param(
            {"cipher_suites": None},
            "has invalid cipher_suites",
            id="invalid-cipher-suites-none",
        ),
        pytest.param(
            {"iterations": 0}, "has invalid iterations", id="invalid-iterations-0"
        ),
        pytest.param(
            {"iterations": "bad"},
            "has invalid iterations",
            id="invalid-iterations-str",
        ),
        pytest.param(
            {"encryption": "bogus-cipher"},
            "Unsupported TPAP session cipher",
            id="unsupported-cipher",
        ),
        pytest.param({"encryption": ""}, "missing encryption", id="missing-encryption"),
    ],
)
async def test_build_share_params_from_register_validates_required_fields(
    overrides: dict[str, Any], match: str
) -> None:
    transport = _make_tpap_transport()
    session = transport._encryption_session
    session._user_random = base64.b64encode(b"\x01" * 16).decode()

    with pytest.raises(KasaException, match=match):
        session._build_share_params_from_register(
            {**_register_result(), **overrides},
            "secret",
        )


async def test_build_share_params_from_register_uses_cmac_suites() -> None:
    transport = _make_tpap_transport()
    session = transport._encryption_session
    session._user_random = base64.b64encode(b"\x01" * 16).decode()

    share_params = session._build_share_params_from_register(
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
async def test_verify_dac_proof_returns_early_without_required_fields() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._verify_dac_proof({})
    await transport.close()


@pytest.mark.asyncio
async def test_verify_dac_proof_wraps_non_signature_errors() -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._shared_key = b"shared"
    session._dac_nonce_base64 = base64.b64encode(b"nonce").decode()

    with pytest.raises(KasaException, match="DAC verification failed"):
        session._verify_dac_proof({"dac_ca": "not-a-cert", "dac_proof": "not-b64"})
    await transport.close()


@pytest.mark.asyncio
async def test_verify_dac_proof_rejects_invalid_proof_type_and_public_key(
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
        session._verify_dac_proof({"dac_ca": "cert", "dac_proof": 1})

    bad_cert = cast(Any, SimpleNamespace(public_key=lambda: object()))
    monkeypatch.setattr(
        transport,
        "_load_certificate_value",
        lambda value: bad_cert,
        raising=True,
    )
    with pytest.raises(KasaException, match="Unsupported DAC proof public key type"):
        session._verify_dac_proof(
            {"dac_ca": "cert", "dac_proof": base64.b64encode(b"proof").decode()}
        )
    await transport.close()


@pytest.mark.asyncio
async def test_establish_session_from_share_result_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = tp.TpapTransport(config=DeviceConfig("tpap-host"))
    session = transport._encryption_session
    session._expected_dev_confirm = "expected"

    with pytest.raises(KasaException, match="missing dev_confirm"):
        session._establish_session_from_share_result({})

    with pytest.raises(KasaException, match="confirmation mismatch"):
        session._establish_session_from_share_result({"dev_confirm": "wrong"})

    # compare_digest rejects non-ASCII str with a TypeError
    with pytest.raises(KasaException, match="confirmation mismatch"):
        session._establish_session_from_share_result({"dev_confirm": "wröng"})

    # base64 is case-sensitive: a value differing only in case does not match
    session._expected_dev_confirm = "AbCdEf=="
    with pytest.raises(KasaException, match="confirmation mismatch"):
        session._establish_session_from_share_result({"dev_confirm": "abcdef=="})
    session._expected_dev_confirm = "expected"

    monkeypatch.setattr(session, "_use_dac_certification", lambda: True, raising=True)
    verified: list[dict[str, Any]] = []
    monkeypatch.setattr(
        session, "_verify_dac_proof", lambda share_result: verified.append(share_result)
    )
    session._shared_key = b"shared"
    session._establish_session_from_share_result(
        {"dev_confirm": "expected", "stok": "STOK", "start_seq": 3}
    )
    assert verified
    assert session._session_id == "STOK"
    assert session._sequence == 3

    session._expected_dev_confirm = "expected"
    session._shared_key = b"shared"
    with pytest.raises(KasaException, match="Missing session fields"):
        session._establish_session_from_share_result({"dev_confirm": "expected"})

    session._expected_dev_confirm = "expected"
    session._shared_key = b"shared"
    with pytest.raises(KasaException, match="Missing session fields"):
        session._establish_session_from_share_result(
            {"dev_confirm": "expected", "sessionId": "SID"}
        )

    session._expected_dev_confirm = "expected"
    session._shared_key = b"shared"
    with pytest.raises(KasaException, match="Invalid session fields"):
        session._establish_session_from_share_result(
            {
                "dev_confirm": "expected",
                "sessionId": "SID",
                "start_seq": "bad",
            }
        )

    session._expected_dev_confirm = "expected"
    session._shared_key = None
    with pytest.raises(KasaException, match="shared key was not derived"):
        session._establish_session_from_share_result(
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
    config.connection_type.device_family = DeviceFamily.SmartTapoPlug
    config.credentials_hash = "hash"
    config.connection_type.http_port = 8080
    transport = tp.TpapTransport(config=config)
    transport._known_tpap_tls = 2

    assert transport.default_port == 8080
    # Not the shape TPAP stores, so it is dropped
    assert transport.credentials_hash is None
    assert transport._get_initial_app_url() == URL("https://tpap-host:4433")
    await transport.close()

    https_transport = tp.TpapTransport(config=DeviceConfig("secure-host"))
    https_transport._config.connection_type.https = True
    assert https_transport.default_port == tp.TpapTransport.DEFAULT_HTTPS_PORT
    await https_transport.close()


@pytest.mark.asyncio
async def test_transport_credentials_hash_encodes_live_credentials() -> None:
    transport = tp.TpapTransport(
        config=DeviceConfig("tpap-host", credentials=Credentials("user", "pass"))
    )

    credentials_hash = transport.credentials_hash

    assert credentials_hash is not None
    decoded_hash = json.loads(base64.b64decode(credentials_hash.encode()).decode())
    assert decoded_hash == {"un": "user", "pwd": "pass"}
    await transport.close()


@pytest.mark.asyncio
async def test_transport_decodes_credentials_hash_for_tpap_handshake() -> None:
    seed_transport = tp.TpapTransport(
        config=DeviceConfig("tpap-host", credentials=Credentials("user", "pass"))
    )
    credentials_hash = seed_transport.credentials_hash
    assert credentials_hash is not None

    config = DeviceConfig("tpap-host", credentials_hash=credentials_hash)
    transport = tp.TpapTransport(config=config)
    session = transport._encryption_session
    session._tpap_pake = [2]

    assert transport._credentials == Credentials("user", "pass")
    assert config.credentials == transport._credentials
    assert session._get_candidate_secrets() == ["pass"]
    await seed_transport.close()
    await transport.close()


@pytest.mark.asyncio
async def test_transport_ignores_malformed_credentials_hash() -> None:
    transport = tp.TpapTransport(
        config=DeviceConfig("tpap-host", credentials_hash="not-valid-base64-json")
    )

    assert transport._credentials is None
    assert transport._config.credentials is None
    assert transport.credentials_hash is None
    await transport.close()


@pytest.mark.asyncio
async def test_transport_drops_credentials_hash_from_klap() -> None:
    """A KLAP hash is one way, so TPAP is left without credentials."""
    klap = KlapTransportV2(
        config=DeviceConfig("tpap-host", credentials=Credentials("user", "pass"))
    )
    klap_hash = klap.credentials_hash
    assert klap_hash
    transport = tp.TpapTransport(
        config=DeviceConfig("tpap-host", credentials_hash=klap_hash)
    )

    assert transport._credentials is None
    assert transport.credentials_hash is None
    await klap.close()
    await transport.close()


@pytest.mark.asyncio
async def test_transport_takes_credentials_from_ssl_aes_hash() -> None:
    """A camera moving from SslAesTransport to TPAP keeps its credentials."""
    config = DeviceConfig("cam-host", credentials=Credentials("user", "pass"))
    config.connection_type.device_family = DeviceFamily.SmartIpCamera
    config.connection_type.https = True
    ssl_aes = SslAesTransport(config=config)
    ssl_aes_hash = ssl_aes.credentials_hash
    assert ssl_aes_hash
    transport = tp.TpapTransport(
        config=DeviceConfig("cam-host", credentials_hash=ssl_aes_hash)
    )

    assert transport._credentials == Credentials("user", "pass")
    await ssl_aes.close()
    await transport.close()


@pytest.mark.asyncio
async def test_update_without_credentials_does_not_log_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the KLAP hash dropped, update() refuses before any request."""
    klap = KlapTransportV2(
        config=DeviceConfig("tpap-host", credentials=Credentials("user", "pass"))
    )
    klap_hash = klap.credentials_hash
    assert klap_hash
    transport = tp.TpapTransport(
        config=DeviceConfig("tpap-host", credentials_hash=klap_hash)
    )
    post = AsyncMock()
    monkeypatch.setattr(transport._http_client, "post", post)
    dev = SmartDevice("tpap-host", protocol=SmartProtocol(transport=transport))

    with pytest.raises(AuthenticationError):
        await dev.update()

    post.assert_not_called()
    await klap.close()
    await dev.disconnect()


@pytest.mark.parametrize(
    "family",
    [
        pytest.param(None, id="iot"),
        pytest.param(DeviceFamily.SmartIpCamera, id="camera"),
    ],
)
async def test_no_password_gives_no_candidates(family: DeviceFamily | None) -> None:
    """An empty password is never sent; every candidate is a counted login."""
    transport = _make_tpap_transport(family=family, credentials=Credentials("user", ""))
    session = transport._encryption_session
    session._tpap_pake = [2]

    assert session._get_candidate_secrets() == []
    with pytest.raises(AuthenticationError, match="no credential candidates"):
        await session._perform_auth_handshake()
    await transport.close()


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        pytest.param(
            _ConnectionError("Connection reset by peer"),
            True,
            id="connection-reset",
        ),
        pytest.param(
            _ConnectionError("different connection issue"),
            False,
            id="other-connection-error",
        ),
        pytest.param(KasaException("x"), False, id="generic-kasa"),
        pytest.param(
            _RetryableError("x", error_code=SmartErrorCode.LOGIN_ERROR),
            False,
            id="retryable-non-session-error",
        ),
        pytest.param(
            _RetryableError("x", error_code=SmartErrorCode.STAT_ACCESS_ERROR),
            False,
            id="stat-access-error",
        ),
    ],
)
def test_should_retry_live_session_variants(exc: Exception, expected: bool) -> None:
    assert tp.TpapTransport._should_retry_live_session(exc) is expected


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

    session._invalidate_session()
    monkeypatch.setattr(session, "perform_handshake", fake_handshake, raising=True)
    with pytest.raises(KasaException, match="not established"):
        await transport._send_once("{}")

    _establish_session(transport, session)

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
    with pytest.raises(KasaException, match="secure request failed.*status 500"):
        await transport._send_once("{}")

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
    with pytest.raises(KasaException, match="Unexpected TPAP response body type"):
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
    assert session.is_established is False
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


def test_transport_response_helpers_validate_json_payloads() -> None:
    with pytest.raises(KasaException, match="Unexpected TPAP JSON response body type"):
        tp.TpapTransport._load_json_dict(b"[]")


class _NotAnInt:
    """An integer that is not an int, like the gmpy2.mpz ecdsa returns when gmpy2 is installed."""

    def __init__(self, value: int) -> None:
        self._value = value

    def __index__(self) -> int:
        return self._value

    __int__ = __index__


def test_xy_to_uncompressed_accepts_non_int_coordinates() -> None:
    curve = ec.SECP256R1()
    numbers = ec.generate_private_key(curve).public_key().public_numbers()
    expected = numbers.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    encoded = tp.TpapEncryptionSession._xy_to_uncompressed(
        _NotAnInt(numbers.x),  # type: ignore[arg-type]
        _NotAnInt(numbers.y),  # type: ignore[arg-type]
        curve,
    )
    assert encoded == expected


class _GeneratorWithNonIntOrder:
    """A generator whose order() is not an int, as with ecdsa on gmpy2."""

    def __init__(self, generator: Any) -> None:
        self._generator = generator

    def order(self) -> _NotAnInt:
        return _NotAnInt(int(self._generator.order()))

    def __rmul__(self, other: int) -> Any:
        return other * self._generator


async def test_build_share_params_accepts_non_int_curve_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m_comp, n_comp, nist, crypto_curve = tp.TpapEncryptionSession._suite_parameters(2)
    fake_nist = SimpleNamespace(
        curve=nist.curve, generator=_GeneratorWithNonIntOrder(nist.generator)
    )
    monkeypatch.setattr(
        tp.TpapEncryptionSession,
        "_suite_parameters",
        staticmethod(lambda suite_type: (m_comp, n_comp, fake_nist, crypto_curve)),
    )
    transport = _make_tpap_transport()
    session = transport._encryption_session
    session._user_random = base64.b64encode(b"\x01" * 16).decode()

    share_params = session._build_share_params_from_register(
        _register_result(), "secret"
    )

    assert share_params["user_confirm"]


# --------------------------
# Scheme and port rules
# --------------------------


@pytest.mark.asyncio
async def test_camera_is_always_https() -> None:
    """Like the app, a camera's TPAP endpoint is https whatever tls says."""
    transport = _make_https_camera_tpap_transport()
    session = transport._encryption_session
    session._tpap_tls = 0
    session._tpap_port = 443

    session._update_transport_url()

    assert transport._app_url.scheme == "https"
    assert transport._app_url.port == 443
    await transport.close()


@pytest.mark.parametrize(
    ("tls", "port", "expected_scheme", "expected_port"),
    [
        pytest.param(0, 80, "http", 80, id="kl420l5"),
        pytest.param(0, None, "http", 80, id="http-default-80"),
        pytest.param(1, None, "https", 80, id="tls1-default-80"),
        pytest.param(2, 4433, "https", 4433, id="tls2-port"),
        pytest.param(3, None, "https", 80, id="any-tls-but-0-is-https"),
        pytest.param(None, None, "http", 80, id="no-tls"),
    ],
)
async def test_kasa_iot_url(
    tls: int | None, port: int | None, expected_scheme: str, expected_port: int
) -> None:
    """Kasa IOT devices follow the app's Kasa client, not its IoT client."""
    transport = _make_tpap_transport(family=DeviceFamily.IotSmartBulb)
    transport._config.connection_type.http_port = 9999
    session = transport._encryption_session
    session._tpap_tls = tls
    session._tpap_port = port

    session._update_transport_url()

    assert transport._app_url.scheme == expected_scheme
    assert transport._app_url.port == expected_port
    await transport.close()


async def test_kasa_iot_url_keeps_port_override() -> None:
    """A port forward set by the user still applies when tpap has no port."""
    transport = _make_tpap_transport(family=DeviceFamily.IotSmartPlugSwitch)
    transport._config.port_override = 8080
    session = transport._encryption_session
    session._tpap_tls = 1
    session._tpap_port = None

    session._update_transport_url()

    assert transport._app_url.scheme == "https"
    assert transport._app_url.port == 8080
    await transport.close()


async def test_kasa_iot_handshake_from_in_band_discover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-band discover drives the Kasa IOT URL and passcode."""
    transport = _make_tpap_transport(
        family=DeviceFamily.IotSmartBulb, credentials=Credentials("user", "pass")
    )
    session = transport._encryption_session
    captured_register: dict[str, Any] = {}
    transport._http_client.post = _make_discover_post(  # type: ignore[assignment]
        _discover_response(tls=1, port=0, pake=[0, 2], dac=True)
    )
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert transport._app_url.scheme == "https"
    assert transport._app_url.port == 80
    assert captured_register["passcode_type"] == "userpw"
    assert captured_register["username"] == tp.TpapEncryptionSession._md5_hex("admin")
    # What the in-band discover said, as discover config prints it
    assert transport.tpap_parameters == TpapParameters(
        tls=1, port=0, pake=[0, 2], dac=True, mac="AA:BB:CC:DD:EE:FF"
    )
    await transport.close()


def _make_https_camera_tpap_transport(host: str = "cam-host") -> tp.TpapTransport:
    config = DeviceConfig(
        host,
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.SmartIpCamera,
            encryption_type=DeviceEncryptionType.Tpap,
            https=True,
        ),
        credentials=Credentials("user", "pass"),
    )
    return tp.TpapTransport(config=config)


def _make_error_post(response: dict[str, Any]) -> Any:
    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, dict[str, Any]]:
        del url, json, data, headers, ssl
        return 200, response

    return post


@pytest.mark.asyncio
async def test_camera_handshake_skips_in_band_discover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cameras refuse the in-band discover, so it is not sent; defaults apply."""
    transport = _make_https_camera_tpap_transport()
    session = transport._encryption_session
    posts: list[Any] = []

    async def post(*args: Any, **kwargs: Any) -> Any:
        posts.append(kwargs.get("json"))
        raise AssertionError("no request expected besides the login")

    transport._http_client.post = post  # type: ignore[assignment]
    captured_register: dict[str, Any] = {}
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert posts == []
    assert transport._port == 443
    assert session._tpap_pake == [2]
    assert session._tpap_tls == 1
    assert session._tpap_port == 443
    assert session._tpap_dac is False
    assert transport._app_url.scheme == "https"
    assert transport._app_url.port == 443
    assert captured_register["passcode_type"] == "userpw"
    assert captured_register["username"] == tp.TpapEncryptionSession._md5_hex("admin")
    assert transport.tpap_parameters == TpapParameters(tls=1, port=443, pake=[2])
    await transport.close()


@pytest.mark.parametrize(
    ("family", "user_hash_type", "expected"),
    [
        pytest.param(
            DeviceFamily.SmartIpCamera,
            1,
            tp.TpapEncryptionSession._sha256_hex_upper("admin"),
            id="camera-sha256",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            0,
            tp.TpapEncryptionSession._md5_hex("admin"),
            id="camera-md5",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            1,
            tp.TpapEncryptionSession._md5_hex("admin"),
            id="iot-ignores-user-hash-type",
        ),
    ],
)
async def test_register_username_follows_user_hash_type_on_cameras(
    family: DeviceFamily, user_hash_type: int, expected: str
) -> None:
    transport = _make_tpap_transport(family=family)
    session = transport._encryption_session
    session._tpap_user_hash_type = user_hash_type

    assert session._get_register_username() == expected
    await transport.close()


@pytest.mark.asyncio
async def test_non_camera_discover_still_raises_on_refusal() -> None:
    transport = _make_tpap_transport(credentials=Credentials("user", "pass"))
    session = transport._encryption_session
    transport._http_client.post = _make_error_post(  # type: ignore[assignment]
        {"error_code": SmartErrorCode.INVALID_ARGUMENTS.value}
    )

    with pytest.raises(DeviceError):
        await session._discover()


@pytest.mark.asyncio
async def test_default_port_uses_443_for_https_cameras() -> None:
    assert _make_https_camera_tpap_transport()._port == 443
    generic_https = tp.TpapTransport(
        config=DeviceConfig(
            "plug-host",
            connection_type=DeviceConnectionParameters(
                device_family=DeviceFamily.SmartTapoPlug,
                encryption_type=DeviceEncryptionType.Tpap,
                https=True,
            ),
        )
    )
    assert generic_https._port == tp.TpapTransport.DEFAULT_HTTPS_PORT


@pytest.mark.parametrize(
    ("step", "response"),
    [
        pytest.param(
            "pake_share",
            {"error_code": SmartErrorCode.SESSION_EXPIRED.value},
            id="share-session-expired",
        ),
        pytest.param(
            "pake_share",
            {"error_code": SmartErrorCode.STAT_ACCESS_ERROR.value},
            id="share-credentials-illegal",
        ),
        pytest.param(
            "discover",
            {
                "error_code": SmartErrorCode.ACCOUNT_ERROR.value,
                "error_info": {"lockedMinute": 30, "remainAttempts": 0},
            },
            id="discover-locked",
        ),
    ],
)
async def test_login_refused_after_device_rejection(
    step: str, response: dict[str, Any]
) -> None:
    """Any rejected pake_share, or a lockout, marks the login as refused."""
    transport = _make_tpap_transport(credentials=Credentials("user", "pass"))
    session = transport._encryption_session

    assert transport.login_refused is False
    with pytest.raises(KasaException):
        session._handle_login_error_code(response, step)
    assert transport.login_refused is True
    await transport.close()


async def test_login_not_refused_by_local_or_early_errors() -> None:
    """Errors before pake_share, and refusing locally, send no counted login."""
    transport = _make_tpap_transport(credentials=Credentials("user", ""))
    session = transport._encryption_session
    session._tpap_pake = [2]

    with pytest.raises(DeviceError):
        session._handle_login_error_code(
            {"error_code": SmartErrorCode.INVALID_ARGUMENTS.value}, "pake_register"
        )
    with pytest.raises(AuthenticationError, match="no credential candidates"):
        await session._perform_auth_handshake()
    assert transport.login_refused is False
    await transport.close()


# --------------------------
# TPAP parameters from discovery
# --------------------------


def _make_discovered_transport(
    tpap: TpapParameters,
    *,
    family: DeviceFamily = DeviceFamily.SmartTapoPlug,
    https: bool = False,
    http_port: int | None = None,
) -> tp.TpapTransport:
    config = DeviceConfig(
        "disc-host",
        credentials=Credentials("user", "pass"),
        connection_type=DeviceConnectionParameters(
            device_family=family,
            encryption_type=DeviceEncryptionType.Tpap,
            login_version=2,
            https=https,
            http_port=http_port,
            tpap=tpap,
        ),
    )
    return tp.TpapTransport(config=config)


async def _no_post(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("the in-band discover must not be sent")


@pytest.mark.parametrize(
    ("family", "https", "http_port", "tpap", "expected"),
    [
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            False,
            80,
            TpapParameters(tls=0, pake=[2], port=80),
            ("http", 80, 0),
            id="p115-plug",
        ),
        pytest.param(
            DeviceFamily.SmartTapoPlug,
            False,
            80,
            TpapParameters(tls=1, pake=[2]),
            ("https", 4433, 1),
            id="plug-tls-without-port",
        ),
        pytest.param(
            DeviceFamily.SmartTapoRobovac,
            True,
            4433,
            TpapParameters(tls=2, pake=[2], port=4433),
            ("https", 4433, 2),
            id="rv50-robovac",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            True,
            None,
            TpapParameters(tls=1, pake=[2], port=443),
            ("https", 443, 1),
            id="c510w-camera",
        ),
        pytest.param(
            DeviceFamily.SmartIpCamera,
            True,
            None,
            TpapParameters(tls=1, pake=[2]),
            ("https", 443, 1),
            id="camera-without-port",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            False,
            80,
            TpapParameters(tls=0, dac=True, pake=[2], port=80),
            ("http", 80, 0),
            id="kl420l5-kasa-iot",
        ),
        pytest.param(
            DeviceFamily.IotSmartBulb,
            False,
            9999,
            TpapParameters(tls=1, pake=[2]),
            ("https", 80, 1),
            id="kasa-iot-tls-without-port",
        ),
    ],
)
async def test_discovered_parameters_skip_in_band_discover(
    monkeypatch: pytest.MonkeyPatch,
    family: DeviceFamily,
    https: bool,
    http_port: int | None,
    tpap: TpapParameters,
    expected: tuple[str, int, int],
) -> None:
    """With the discovery tpap object the transport logs in straight away."""
    transport = _make_discovered_transport(
        tpap, family=family, https=https, http_port=http_port
    )
    session = transport._encryption_session
    transport._http_client.post = _no_post  # type: ignore[assignment]
    captured_register: dict[str, Any] = {}
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    url = transport._app_url
    assert (url.scheme, url.port, session.tls_mode) == expected
    assert captured_register["passcode_type"] == "userpw"
    # A dropped session logs in again without the in-band discover either
    session._invalidate_session()
    await session.perform_handshake()
    url = transport._app_url
    assert (url.scheme, url.port, session.tls_mode) == expected
    await transport.close()


async def test_discovered_dac_sends_dac_nonce(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dac from discovery asks the device for its attestation, as on KP125M."""
    transport = _make_discovered_transport(
        TpapParameters(tls=0, dac=True, pake=[2], port=80),
        family=DeviceFamily.SmartKasaPlug,
    )
    session = transport._encryption_session
    transport._http_client.post = _no_post  # type: ignore[assignment]
    shares: list[dict[str, Any]] = []

    async def fake_login(params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        if step_name == "pake_register":
            return _register_result()
        shares.append(params)
        raise AuthenticationError("stop after the share request")

    monkeypatch.setattr(session, "_login", fake_login, raising=True)

    with pytest.raises(AuthenticationError):
        await session.perform_handshake()
    assert "dac_nonce" in shares[0]
    await transport.close()


async def test_discovered_user_hash_type_on_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A camera announcing user_hash_type 1 registers with SHA-256 of admin."""
    transport = _make_discovered_transport(
        TpapParameters(tls=1, pake=[2], port=443, user_hash_type=1),
        family=DeviceFamily.SmartIpCamera,
        https=True,
    )
    session = transport._encryption_session
    transport._http_client.post = _no_post  # type: ignore[assignment]
    captured_register: dict[str, Any] = {}
    monkeypatch.setattr(
        session,
        "_login",
        _make_handshake_login(session, capture_register=captured_register),
        raising=True,
    )

    await session.perform_handshake()

    assert captured_register["username"] == (
        tp.TpapEncryptionSession._sha256_hex_upper("admin")
    )
    await transport.close()


async def test_discovered_mac_gives_default_passcode() -> None:
    """The MAC from discovery derives the default passcode without discover."""
    transport = _make_discovered_transport(
        TpapParameters(tls=0, pake=[0], port=80, mac="AA-BB-CC-DD-EE-FF")
    )
    session = transport._encryption_session

    assert session._get_passcode_type() == "default_userpw"
    assert session._get_candidate_secrets() == [
        tp.TpapEncryptionSession._mac_pass_from_device_mac("AA:BB:CC:DD:EE:FF")
    ]
    await transport.close()


async def test_stored_config_keeps_discovered_parameters() -> None:
    """A config stored after discovery reconnects without the in-band discover."""
    tpap = TpapParameters(
        tls=1, port=443, pake=[2], user_hash_type=1, mac="AA-BB-CC-DD-EE-FF"
    )
    transport = _make_discovered_transport(
        tpap, family=DeviceFamily.SmartIpCamera, https=True
    )
    restored = tp.TpapTransport(
        config=DeviceConfig.from_dict(transport._config.to_dict())
    )

    assert restored._has_discovery_tpap is True
    assert restored._config.connection_type.tpap == tpap
    await transport.close()
    await restored.close()


async def test_connection_logs_each_step(caplog: pytest.LogCaptureFixture) -> None:
    """Like KLAP, the debug log shows every step of a connection, no secrets."""
    transport = _make_tpap_transport(
        family=DeviceFamily.SmartTapoPlug,
        credentials=Credentials("user", "secret-pass"),
    )
    session = transport._encryption_session

    async def post(
        url: URL,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool | None = None,
    ) -> tuple[int, Any]:
        if json is None:
            return 200, data  # the /ds request, echoed
        sub_method = json["params"]["sub_method"]
        if sub_method == "discover":
            return 200, _discover_response(tls=0, port=80, pake=[2])
        if sub_method == "pake_register":
            result = _register_result(
                extra_crypt={"type": "password_shadow", "params": {"passwd_id": 2}},
                cipher_suites=1,
            )
            return 200, {"error_code": 0, "result": result}
        return 200, {"error_code": 0, "result": _share_result(session)}

    transport._http_client.post = post  # type: ignore[assignment]

    with caplog.at_level(logging.DEBUG, logger="kasa.transports.tpaptransport"):
        await transport.send('{"result": {"ok": true}}')

    messages = [record.getMessage() for record in caplog.records]
    expected = [
        "Starting handshake with tpap-host",
        "Discover posted at",
        "Using the TPAP login from the in-band discover for tpap-host: tls 0, "
        "port 80, pake [2], dac False",
        "pake_register posted at",
        "pake_register success at",
        "credential encoding is password_shadow passwd_id 2",
        "pake_share posted at",
        "pake_share confirmation matches the expected credentials (candidate 1/1)",
        "Handshake with tpap-host complete",
        "Device tpap-host query posted Host is tpap-host, Sequence is",
        "Device tpap-host query response received",
    ]
    for text in expected:
        assert any(text in message for message in messages), text
    assert "Response status is 200" in caplog.text
    # No credentials and no SPAKE2+ values
    assert "secret-pass" not in caplog.text
    assert session._user_random
    assert session._user_random not in caplog.text
    assert "AA:BB:CC:DD:EE:FF" not in caplog.text
    assert not any(m.startswith("TPAP: ") for m in messages)
    await transport.close()


@pytest.mark.parametrize(
    ("register_result", "expected"),
    [
        pytest.param({}, "none", id="missing"),
        pytest.param({"extra_crypt": {}}, "none", id="empty"),
        pytest.param(
            {"extra_crypt": {"type": "password_authkey", "params": {}}},
            "password_authkey",
            id="type-only",
        ),
        pytest.param(
            {"extra_crypt": {"type": "password_shadow", "params": {"passwd_id": 5}}},
            "password_shadow passwd_id 5",
            id="password-shadow",
        ),
    ],
)
def test_describe_extra_crypt(register_result: dict[str, Any], expected: str) -> None:
    assert tp.TpapEncryptionSession._describe_extra_crypt(register_result) == expected


async def test_no_pake_refuses_before_logging_in() -> None:
    """A discover reply without pake sends no login, as in the Tapo app."""
    transport = _make_tpap_transport(
        family=DeviceFamily.SmartTapoPlug, credentials=Credentials("user", "pass")
    )
    response = _discover_response(tls=0, port=80)
    del response["result"]["tpap"]["pake"]
    counts = _fake_login_device(transport, discover=response)

    with pytest.raises(AuthenticationError, match="no supported passcode type"):
        await transport._encryption_session.perform_handshake()
    assert counts == {"discover": 1, "pake_register": 0, "pake_share": 0}
    await transport.close()
