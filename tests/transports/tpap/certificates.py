"""Certificates for the TPAP tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID


def build_certificate(
    private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    subject_common_name: str,
    issuer_common_name: str,
    issuer_private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    *,
    is_ca: bool = False,
    subject_alt_names: list[x509.GeneralName] | None = None,
) -> x509.Certificate:
    """Return a certificate for the key, signed by the issuer key."""
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


def mac_name(text: bytes, oid: str = "1.0.15961.13.375") -> x509.GeneralName:
    """Return the SubjectAltName otherName a TLS mode 2 certificate names the MAC in."""
    # The otherName value is an OCTET STRING holding the text
    length = len(text)
    header = bytes([0x04, length]) if length < 0x80 else bytes([0x04, 0x81, length])
    return x509.OtherName(x509.ObjectIdentifier(oid), header + text)
