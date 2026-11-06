from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from kasa.exceptions import KasaException
from kasa.transports.tpap import cert

from .certificates import build_certificate, mac_name


def test_load_certificate_value_variants() -> None:
    cert_key = ec.generate_private_key(ec.SECP256R1())
    leaf_cert = build_certificate(cert_key, "leaf", "leaf", cert_key)
    pem = leaf_cert.public_bytes(serialization.Encoding.PEM).decode()
    der_b64 = base64.b64encode(
        leaf_cert.public_bytes(serialization.Encoding.DER)
    ).decode()

    assert cert.load_certificate_value(pem).subject == leaf_cert.subject
    assert cert.load_certificate_value(der_b64).subject == leaf_cert.subject

    with pytest.raises(KasaException, match="Empty certificate value"):
        cert.load_certificate_value("   ")
    with pytest.raises(KasaException, match="Invalid certificate value"):
        cert.load_certificate_value("totally-invalid")


def test_verify_certificate_validity_handles_naive_datetimes() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    valid = SimpleNamespace(
        not_valid_before=now - timedelta(days=1),
        not_valid_after=now + timedelta(days=1),
    )
    cert._verify_certificate_validity(cast(Any, valid))

    expired = SimpleNamespace(
        not_valid_before=now - timedelta(days=3),
        not_valid_after=now - timedelta(days=2),
    )
    with pytest.raises(KasaException, match="outside its validity period"):
        cert._verify_certificate_validity(cast(Any, expired))


def test_verify_certificate_signature_variants() -> None:
    ec_root = ec.generate_private_key(ec.SECP256R1())
    ec_leaf = ec.generate_private_key(ec.SECP256R1())
    ec_cert = build_certificate(ec_leaf, "leaf", "root", ec_root)
    ec_issuer = build_certificate(ec_root, "root", "root", ec_root, is_ca=True)
    cert._verify_certificate_signature(ec_cert, ec_issuer)

    rsa_root = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_leaf = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_cert = build_certificate(rsa_leaf, "leaf", "root", rsa_root)
    rsa_issuer = build_certificate(rsa_root, "root", "root", rsa_root, is_ca=True)
    cert._verify_certificate_signature(rsa_cert, rsa_issuer)

    no_hash_cert = SimpleNamespace(signature_hash_algorithm=None)
    with pytest.raises(KasaException, match="hash algorithm is unavailable"):
        cert._verify_certificate_signature(
            cast(Any, no_hash_cert),
            cast(Any, SimpleNamespace(public_key=lambda: ec_root.public_key())),
        )

    bad_issuer = SimpleNamespace(public_key=lambda: object())
    with pytest.raises(KasaException, match="Unsupported DAC issuer public key type"):
        cert._verify_certificate_signature(ec_cert, cast(Any, bad_issuer))


def test_verify_dac_certificate_chain_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_cert = build_certificate(root_key, "root", "root", root_key, is_ca=True)
    dac_key = ec.generate_private_key(ec.SECP256R1())
    dac_cert = build_certificate(dac_key, "dac", "root", root_key)

    monkeypatch.setattr(
        cert,
        "_load_root_ca_certificate",
        lambda: root_cert,
        raising=True,
    )
    cert.verify_dac_certificate_chain(dac_cert, None)

    monkeypatch.setattr(
        cert,
        "_load_root_ca_certificate",
        lambda: (_ for _ in ()).throw(ValueError("boom")),
        raising=True,
    )
    with pytest.raises(
        KasaException, match="DAC certificate chain verification failed"
    ):
        cert.verify_dac_certificate_chain(dac_cert, None)


def _usage(*, cert_sign: bool) -> x509.KeyUsage:
    return x509.KeyUsage(
        digital_signature=not cert_sign,
        content_commitment=False,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=cert_sign,
        crl_sign=cert_sign,
        encipher_only=False,
        decipher_only=False,
    )


UNKNOWN_EXTENSION = x509.UnrecognizedExtension(
    x509.ObjectIdentifier("1.3.6.1.4.1.55555.1"), b"\x05\x00"
)


@pytest.mark.parametrize(
    ("ica_kwargs", "dac_kwargs", "dac_issuer", "match"),
    [
        pytest.param({}, {}, "ica", None, id="valid"),
        pytest.param(
            {"extensions": [(_usage(cert_sign=True), True)]},
            {},
            "ica",
            None,
            id="valid-with-key-usage",
        ),
        pytest.param(
            {},
            {"extensions": [(UNKNOWN_EXTENSION, False)]},
            "ica",
            None,
            id="unknown-not-critical",
        ),
        pytest.param({"is_ca": False}, {}, "ica", "not a CA", id="ica-not-a-ca"),
        pytest.param(
            {"basic_constraints": False},
            {},
            "ica",
            "not a CA",
            id="ica-without-basic-constraints",
        ),
        pytest.param(
            {"extensions": [(_usage(cert_sign=False), True)]},
            {},
            "ica",
            "may not sign",
            id="ica-may-not-sign",
        ),
        pytest.param({}, {}, "someone else", "issuer does not match", id="issuer-name"),
        pytest.param(
            {"extensions": [(UNKNOWN_EXTENSION, True)]},
            {},
            "ica",
            "unknown critical extension",
            id="ica-unknown-critical",
        ),
        pytest.param(
            {},
            {"extensions": [(UNKNOWN_EXTENSION, True)]},
            "ica",
            "unknown critical extension",
            id="dac-unknown-critical",
        ),
    ],
)
def test_verify_dac_certificate_chain_checks_the_path(
    monkeypatch: pytest.MonkeyPatch,
    ica_kwargs: dict[str, Any],
    dac_kwargs: dict[str, Any],
    dac_issuer: str,
    match: str | None,
) -> None:
    """The chain is checked as path validation does, not only its signatures."""
    root_key, ica_key, dac_key = (
        ec.generate_private_key(ec.SECP256R1()) for _ in "123"
    )
    root = build_certificate(root_key, "root", "root", root_key, is_ca=True)
    ica = build_certificate(
        ica_key, "ica", "root", root_key, **{"is_ca": True, **ica_kwargs}
    )
    dac = build_certificate(dac_key, "dac", dac_issuer, ica_key, **dac_kwargs)
    monkeypatch.setattr(cert, "_load_root_ca_certificate", lambda: root)

    if match is None:
        cert.verify_dac_certificate_chain(dac, ica)
        return
    with pytest.raises(KasaException, match=match):
        cert.verify_dac_certificate_chain(dac, ica)


def _device_cert_der(names: list[x509.GeneralName] | None) -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    device_cert = build_certificate(
        key, "device", "device", key, subject_alt_names=names
    )
    return device_cert.public_bytes(serialization.Encoding.DER)


@pytest.mark.parametrize(
    ("names", "mac", "expected"),
    [
        pytest.param([mac_name(b"AABBCCDDEEFF")], "AA-BB-CC-DD-EE-FF", True, id="udp"),
        pytest.param([mac_name(b"AABBCCDDEEFF")], "aa:bb:cc:dd:ee:ff", True, id="lc"),
        pytest.param(
            [mac_name(b"mac=AA:BB:CC:DD:EE:FF")], "AABBCCDDEEFF", True, id="in-text"
        ),
        pytest.param(
            [mac_name(b"x" * 200 + b"AABBCCDDEEFF")],
            "AABBCCDDEEFF",
            True,
            id="long-form-length",
        ),
        pytest.param([mac_name(b"112233445566")], "AABBCCDDEEFF", False, id="other"),
        pytest.param(
            [mac_name(b"AABBCCDDEEFF", oid="1.2.3.4")],
            "AABBCCDDEEFF",
            False,
            id="other-oid",
        ),
        pytest.param(
            [x509.DNSName("AABBCCDDEEFF")], "AABBCCDDEEFF", False, id="dns-name"
        ),
        pytest.param(None, "AABBCCDDEEFF", False, id="no-san"),
    ],
)
def test_certificate_names_mac(
    names: list[x509.GeneralName] | None, mac: str, expected: bool
) -> None:
    assert cert._certificate_names_mac(_device_cert_der(names), mac) is expected


def test_certificate_names_mac_without_certificate() -> None:
    assert cert._certificate_names_mac(None, "AABBCCDDEEFF") is False
    assert cert._certificate_names_mac(b"not a certificate", "AABBCCDDEEFF") is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(b"", "", id="empty"),
        pytest.param(b"\x04", "", id="no-length"),
        pytest.param(b"\x04\x03abc", "abc", id="short-form"),
        pytest.param(b"\x04\x81\x03abc", "abc", id="long-form"),
    ],
)
def test_der_string(value: bytes, expected: str) -> None:
    assert cert._der_string(value) == expected


def test_verify_dac_proof_needs_an_ec_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The proof is an ECDSA signature, so a DAC with another key type fails."""
    root_key = ec.generate_private_key(ec.SECP256R1())
    root = build_certificate(root_key, "root", "root", root_key, is_ca=True)
    dac_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    dac = build_certificate(dac_key, "dac", "root", root_key)
    monkeypatch.setattr(
        cert, "TPAP_ROOT_CA_PEM", root.public_bytes(serialization.Encoding.PEM).decode()
    )
    dac_der = base64.b64encode(dac.public_bytes(serialization.Encoding.DER)).decode()

    with pytest.raises(KasaException, match="Unsupported DAC proof public key type"):
        cert.verify_dac_proof(dac_der, "", base64.b64encode(b"proof").decode(), b"m")
