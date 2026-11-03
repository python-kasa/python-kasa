from __future__ import annotations

import base64
import hashlib
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from kasa.exceptions import KasaException
from kasa.transports.tpap import crypto


def test_encode_w_and_hash_helpers_cover_edge_cases() -> None:
    assert crypto._encode_w(0, 32) == bytes(32)
    assert crypto._encode_w(0x80, 32) == bytes(31) + b"\x80"
    # 31 significant bytes with the top bit clear: the old minimal encoding
    # dropped the leading zero byte here.
    assert crypto._encode_w(1 << 240, 32) == (1 << 240).to_bytes(32, "big")
    assert crypto._hash("SHA512", b"data") == hashlib.sha512(b"data").digest()
    assert len(crypto._cmac_aes(b"\x00" * 16, b"data")) == 16


def test_authkey_shadow_and_crypt_helpers() -> None:
    masked = crypto._authkey_mask("abc", "xy", "0123456789")
    assert len(masked) == 3
    assert crypto._sha1_username_mac_shadow("", "AABBCCDDEEFF", "p") == "p"
    assert crypto._sha1_username_mac_shadow(
        "user", "AABBCCDDEEFF", "p"
    ) == crypto._sha1_hex(crypto.md5_hex("user") + "_AA:BB:CC:DD:EE:FF")
    assert crypto._md5_crypt("pass", "") is None
    assert crypto._md5_crypt("pass", "$1$salt$") is not None
    assert crypto._md5_crypt("pass", "$1$salt") is not None
    assert crypto._sha256_crypt("pass", "") is None
    assert crypto._sha256_crypt("pass", "$5$rounds=oops$salt") is not None


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
    assert crypto._sha256_crypt(password, prefix) == expected


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
        crypto.build_credentials(extra_crypt, "", "Hello world!", "AABBCCDDEEFF")
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
    assert crypto._md5_crypt(password, prefix) == expected


def test_sha256_crypt_rejects_too_many_rounds() -> None:
    """The prefix rounds come from an unauthenticated reply and are hashed on the loop."""
    with pytest.raises(KasaException, match="too many passwd_prefix rounds"):
        crypto._sha256_crypt("pass", "$5$rounds=100001$salt$")


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
            crypto._sha1_hex("pass"),
        ),
        (
            {
                "type": "password_shadow",
                "params": {"passwd_id": 3},
            },
            "user",
            "pass",
            "AABBCCDDEEFF",
            crypto._sha1_username_mac_shadow("user", "AABBCCDDEEFF", "pass"),
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
            crypto._authkey_mask("pass", "xy", "0123456789"),
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
        crypto.build_credentials(extra_crypt, username, passcode, mac_no_colon)
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
    result = crypto.build_credentials(
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
        crypto.build_credentials(
            {"type": "password_shadow"}, "", "pass", "AABBCCDDEEFF"
        )
        == "pass"
    )


def test_mac_pass_from_device_mac_validates_input() -> None:
    with pytest.raises(KasaException, match="Invalid device MAC"):
        crypto.mac_pass_from_device_mac("not-a-mac")

    with pytest.raises(KasaException, match="too short"):
        crypto.mac_pass_from_device_mac("AA:BB:CC:DD:EE")


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
    _, _, curve, _ = crypto._suite_parameters(suite_type)
    assert curve.name == curve_name


def test_suite_parameters_reject_unsupported_suite() -> None:
    with pytest.raises(KasaException, match="Unsupported TPAP suite type"):
        crypto._suite_parameters(999)


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
    encoded = crypto._xy_to_uncompressed(
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


def _p256_point() -> bytes:
    """Return a fixed P-256 point, standing in for the device share."""
    private_key = ec.derive_private_key(
        int.from_bytes(b"\x01" * 32, "big"),
        ec.SECP256R1(),
    )
    return private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )


def _share(**overrides: Any) -> tuple[bytes, bytes, bytes, bytes]:
    values: dict[str, Any] = {
        "suite_type": 2,
        "salt": b"\x11" * 16,
        "iterations": 100,
        "user_random": b"\x01" * 16,
        "dev_random": b"\x00" * 16,
        "dev_share": _p256_point(),
    }
    values.update(overrides)
    return crypto.spake2p_share(b"secret", **values)


def test_spake2p_share_accepts_non_int_curve_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m_comp, n_comp, nist, crypto_curve = crypto._suite_parameters(2)
    fake_nist = SimpleNamespace(
        curve=nist.curve, generator=_GeneratorWithNonIntOrder(nist.generator)
    )
    monkeypatch.setattr(
        crypto,
        "_suite_parameters",
        lambda suite_type: (m_comp, n_comp, fake_nist, crypto_curve),
    )

    _, user_confirm, _, _ = _share(suite_type=2)

    assert user_confirm


def test_spake2p_share_encodes_w0_at_curve_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """w0 keeps its leading zero bytes in the transcript, as the app writes it."""
    small_w0 = 0x1234
    monkeypatch.setattr(crypto, "_derive_ab", lambda *args, **kwargs: (small_w0, 7))
    hashed: list[bytes] = []
    real_hash = crypto._hash

    def capture(algorithm: str, data: bytes) -> bytes:
        hashed.append(data)
        return real_hash(algorithm, data)

    monkeypatch.setattr(crypto, "_hash", capture)

    _share(suite_type=1, user_random=b"\x01" * 32)

    w0_element = (32).to_bytes(8, "little") + small_w0.to_bytes(32, "big")
    assert any(data.endswith(w0_element) for data in hashed)


def test_spake2p_share_with_cmac_suite() -> None:
    user_share, user_confirm, dev_confirm, shared_key = _share(suite_type=8)

    assert len(user_confirm) == len(dev_confirm) == 16
    assert user_share
    assert shared_key
