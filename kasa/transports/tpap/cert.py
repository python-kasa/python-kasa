"""Certificate checks of the TPAP login.

The device attestation (DAC) chain and proof, and with TLS mode 2 the
device's TLS certificate, which has to name the device MAC.
"""

from __future__ import annotations

import base64
import ssl
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from kasa.exceptions import KasaException

# With TLS mode 2 the device certificate names the device MAC in a
# SubjectAltName otherName with this OID (the Tapo app's
# TpapCertificateTrustManager).
_TLS2_MAC_OID = x509.ObjectIdentifier("1.0.15961.13.375")


TLS2_CIPHERS = ":".join(
    [
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-AES256-SHA384",
        "ECDHE-ECDSA-AES256-SHA",
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES128-SHA256",
        "ECDHE-ECDSA-AES128-SHA",
    ]
)


TPAP_ROOT_CA_PEM = """
-----BEGIN CERTIFICATE-----
MIICNzCCAdygAwIBAgIUNLD7w5j5WU/efCe8bqkfGSRGgLYwCgYIKoZIzj0EAwIw
ezEnMCUGA1UEAwweVFAtTElOSyBTWVNURU1TIERFVklDRSBST09UIENBMR0wGwYD
VQQKDBRUUC1MSU5LIFNZU1RFTVMgSU5DLjEPMA0GA1UEBwwGSXJ2aW5lMRMwEQYD
VQQIDApDYWxpZm9ybmlhMQswCQYDVQQGEwJVUzAgFw0yNDExMjIwMjU3NDhaGA8y
MDU0MTExNTAyNTc0OFowezEnMCUGA1UEAwweVFAtTElOSyBTWVNURU1TIERFVklD
RSBST09UIENBMR0wGwYDVQQKDBRUUC1MSU5LIFNZU1RFTVMgSU5DLjEPMA0GA1UE
BwwGSXJ2aW5lMRMwEQYDVQQIDApDYWxpZm9ybmlhMQswCQYDVQQGEwJVUzBZMBMG
ByqGSM49AgEGCCqGSM49AwEHA0IABLwo8H9H6BoJDvcoewi4wPrPryVXir4z4yXV
n29R5XCAcFfKk06pYPupG6pjaKOLKWXnaOdPZThDFxwGLo3urV2jPDA6MAsGA1Ud
DwQEAwIBhjAMBgNVHRMEBTADAQH/MB0GA1UdDgQWBBRivfUtiHYsZBOKo80uZEwk
XhBkdDAKBggqhkjOPQQDAgNJADBGAiEA+7j5jemtXcGYN0unH+9rjVhVAL7WrsOi
5rbc0IIvD6MCIQCZuGGssu4Ygt2V8Vr0QF2fO9wxfNB3aRRMYQ+6lMrLGA==
-----END CERTIFICATE-----
""".strip()


def _der_string(value: bytes) -> str:
    """Return the text of a DER-encoded string value, such as an OCTET STRING."""
    if len(value) < 2:
        return ""
    length, offset = value[1], 2
    if length & 0x80:
        count = length & 0x7F
        length, offset = int.from_bytes(value[2 : 2 + count], "big"), 2 + count
    return value[offset : offset + length].decode("utf-8", "replace")


def _certificate_names_mac(der: bytes | None, mac: str) -> bool:
    """Return True if the certificate's SubjectAltName names the device MAC."""
    if not der:
        return False
    try:
        cert = x509.load_der_x509_certificate(der)
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except (ValueError, x509.ExtensionNotFound):
        return False
    wanted = mac.replace(":", "").replace("-", "").upper()
    return any(
        wanted in _der_string(name.value).replace(":", "").replace("-", "").upper()
        for name in names.value.get_values_for_type(x509.OtherName)
        if name.type_id == _TLS2_MAC_OID
    )


def mac_checking_sslobject(mac: str) -> type[ssl.SSLObject]:
    """Return an SSLObject class that checks the certificate names the MAC.

    The check runs at the end of every TLS handshake, so it applies to the
    connection the requests then use.
    """

    class _MacCheckingSSLObject(ssl.SSLObject):
        def do_handshake(self) -> None:
            super().do_handshake()
            if not _certificate_names_mac(self.getpeercert(binary_form=True), mac):
                raise ssl.SSLCertVerificationError(
                    "TPAP TLS certificate does not name the device MAC"
                )

    return _MacCheckingSSLObject


def _load_root_ca_certificate() -> x509.Certificate:
    return x509.load_pem_x509_certificate(TPAP_ROOT_CA_PEM.encode())


def load_certificate_value(certificate_value: str) -> x509.Certificate:
    """Load a certificate the device sent, as PEM or DER, base64 or not."""
    raw_value = certificate_value.strip()
    if not raw_value:
        raise KasaException("Empty certificate value")

    candidates: list[bytes] = [raw_value.encode()]
    decoded_candidate: bytes | None = None
    try:
        decoded_candidate = base64.b64decode(raw_value, validate=True)
    except Exception:
        decoded_candidate = None
    if decoded_candidate is not None:
        candidates.insert(0, decoded_candidate)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            if b"-----BEGIN CERTIFICATE-----" in candidate:
                return x509.load_pem_x509_certificate(candidate)
            return x509.load_der_x509_certificate(candidate)
        except Exception as exc:
            last_error = exc

    raise KasaException("Invalid certificate value") from last_error


def _verify_certificate_validity(certificate: x509.Certificate) -> None:
    now = datetime.now(UTC)
    if hasattr(certificate, "not_valid_before_utc"):
        not_before = certificate.not_valid_before_utc
        not_after = certificate.not_valid_after_utc
    else:
        not_before = certificate.not_valid_before.replace(tzinfo=UTC)
        not_after = certificate.not_valid_after.replace(tzinfo=UTC)
    if now < not_before or now > not_after:
        raise KasaException("Certificate is outside its validity period")


def _verify_certificate_signature(
    certificate: x509.Certificate, issuer: x509.Certificate
) -> None:
    public_key = issuer.public_key()
    signature_hash = certificate.signature_hash_algorithm
    if signature_hash is None:
        raise KasaException("Certificate signature hash algorithm is unavailable")
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            ec.ECDSA(signature_hash),
        )
        return
    if isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            padding.PKCS1v15(),
            signature_hash,
        )
        return
    raise KasaException(
        f"Unsupported DAC issuer public key type: {type(public_key).__name__}"
    )


def verify_dac_certificate_chain(
    dac_ca_certificate: x509.Certificate,
    dac_ica_certificate: x509.Certificate | None,
) -> None:
    """Check the DAC chain up to TP-Link's device root CA."""
    try:
        root_certificate = _load_root_ca_certificate()
        _verify_certificate_validity(dac_ca_certificate)
        if dac_ica_certificate is not None:
            _verify_certificate_validity(dac_ica_certificate)
            _verify_certificate_signature(dac_ca_certificate, dac_ica_certificate)
            _verify_certificate_signature(dac_ica_certificate, root_certificate)
        else:
            _verify_certificate_signature(dac_ca_certificate, root_certificate)
    except Exception as exc:
        raise KasaException(
            f"DAC certificate chain verification failed: {exc}"
        ) from exc
