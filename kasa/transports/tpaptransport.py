"""Implementation of the TP-Link TPAP Protocol."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import logging
import os
import secrets
import ssl
import struct
import tempfile
import uuid
import warnings
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, ClassVar, Literal, TypedDict, cast

import requests
from asn1crypto import core as asn1_core
from asn1crypto import csr as asn1_csr
from asn1crypto import pem as asn1_pem
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESCCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from ecdsa import NIST256p, ellipticcurve
from ecdsa.ellipticcurve import PointJacobi
from urllib3.exceptions import InsecureRequestWarning
from yarl import URL

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
from kasa.httpclient import HttpClient
from kasa.json import loads as json_loads
from kasa.transports import BaseTransport

_LOGGER = logging.getLogger(__name__)

warnings.simplefilter("ignore", InsecureRequestWarning)


class TransportState(Enum):
    """State for TPAP transport handshake and session lifecycle."""

    ESTABLISHED = auto()
    NOT_ESTABLISHED = auto()


_CipherId = Literal["aes_128_ccm", "aes_256_ccm", "chacha20_poly1305"]


class _CipherLabels(TypedDict):
    """HKDF labels for session key and nonce derivation."""

    key_salt: bytes
    key_info: bytes
    nonce_salt: bytes
    nonce_info: bytes
    key_len: int


@dataclass
class _SessionCipher:
    """AEAD session cipher derived from the ECDH/SPAKE shared secret."""

    cipher_id: _CipherId
    key: bytes
    base_nonce: bytes

    TAG_LEN: ClassVar[int] = 16
    NONCE_LEN: ClassVar[int] = 12

    LABELS: ClassVar[dict[_CipherId, _CipherLabels]] = {
        "aes_128_ccm": {
            "key_salt": b"tp-kdf-salt-aes128-key",
            "key_info": b"tp-kdf-info-aes128-key",
            "nonce_salt": b"tp-kdf-salt-aes128-iv",
            "nonce_info": b"tp-kdf-info-aes128-iv",
            "key_len": 16,
        },
        "aes_256_ccm": {
            "key_salt": b"tp-kdf-salt-aes256-key",
            "key_info": b"tp-kdf-info-aes256-key",
            "nonce_salt": b"tp-kdf-salt-aes256-iv",
            "nonce_info": b"tp-kdf-info-aes256-iv",
            "key_len": 32,
        },
        "chacha20_poly1305": {
            "key_salt": b"tp-kdf-salt-chacha20-key",
            "key_info": b"tp-kdf-info-chacha20-key",
            "nonce_salt": b"tp-kdf-salt-chacha20-iv",
            "nonce_info": b"tp-kdf-info-chacha20-iv",
            "key_len": 32,
        },
    }

    @staticmethod
    def _hkdf(
        master: bytes, *, salt: bytes, info: bytes, length: int, algo: str = "SHA256"
    ) -> bytes:
        """Derive bytes from master via HKDF."""
        algorithm = hashes.SHA256() if algo.upper() == "SHA256" else hashes.SHA512()
        return HKDF(algorithm=algorithm, length=length, salt=salt, info=info).derive(
            master
        )

    @staticmethod
    def _nonce_from_base(base: bytes, seq: int) -> bytes:
        """Form per-message nonce from base-nonce + big-endian seq."""
        if len(base) < 4:
            raise ValueError("base nonce too short")
        return base[:-4] + struct.pack(">I", seq)

    @classmethod
    def from_shared_key(
        cls, cipher_id: _CipherId, shared_key: bytes, hkdf_hash: str = "SHA256"
    ) -> _SessionCipher:
        """Construct session cipher from a shared secret."""
        labels = cls.LABELS[cipher_id]
        return cls(
            cipher_id=cipher_id,
            key=cls._hkdf(
                shared_key,
                salt=labels["key_salt"],
                info=labels["key_info"],
                length=labels["key_len"],
                algo=hkdf_hash,
            ),
            base_nonce=cls._hkdf(
                shared_key,
                salt=labels["nonce_salt"],
                info=labels["nonce_info"],
                length=cls.NONCE_LEN,
                algo=hkdf_hash,
            ),
        )

    def encrypt(self, plaintext: bytes, seq: int) -> bytes:
        """Encrypt and append tag with the derived per-seq nonce."""
        n = self._nonce_from_base(self.base_nonce, seq)
        if self.cipher_id.startswith("aes_"):
            return AESCCM(self.key, tag_length=self.TAG_LEN).encrypt(n, plaintext, None)
        return ChaCha20Poly1305(self.key).encrypt(n, plaintext, None)

    def decrypt(self, ciphertext_and_tag: bytes, seq: int) -> bytes:
        """Decrypt and authenticate with the derived per-seq nonce."""
        n = self._nonce_from_base(self.base_nonce, seq)
        if self.cipher_id.startswith("aes_"):
            return AESCCM(self.key, tag_length=self.TAG_LEN).decrypt(
                n, ciphertext_and_tag, None
            )
        return ChaCha20Poly1305(self.key).decrypt(n, ciphertext_and_tag, None)

    @classmethod
    def key_nonce_from_shared(
        cls, shared: bytes, cipher_id: _CipherId, hkdf_hash: str = "SHA256"
    ) -> tuple[bytes, bytes]:
        """Derive raw key and base-nonce for a given cipher and HKDF hash."""
        labels = cls.LABELS[cipher_id]
        algo = hashes.SHA256() if hkdf_hash.upper() == "SHA256" else hashes.SHA512()
        key = HKDF(
            algorithm=algo,
            length=labels["key_len"],
            salt=labels["key_salt"],
            info=labels["key_info"],
        ).derive(shared)
        base_nonce = HKDF(
            algorithm=algo,
            length=cls.NONCE_LEN,
            salt=labels["nonce_salt"],
            info=labels["nonce_info"],
        ).derive(shared)
        return key, base_nonce

    @classmethod
    def sec_encrypt(
        cls,
        cipher_id: _CipherId,
        key: bytes,
        base_nonce: bytes,
        plaintext: bytes,
        seq: int = 1,
    ) -> tuple[bytes, bytes]:
        """Return (ciphertext, tag) for raw key/base-nonce input."""
        n = cls._nonce_from_base(base_nonce, seq)
        if cipher_id.startswith("aes_"):
            combined = AESCCM(key, tag_length=cls.TAG_LEN).encrypt(n, plaintext, None)
        else:
            combined = ChaCha20Poly1305(key).encrypt(n, plaintext, None)
        return combined[: -cls.TAG_LEN], combined[-cls.TAG_LEN :]

    @classmethod
    def sec_decrypt(
        cls,
        cipher_id: _CipherId,
        key: bytes,
        base_nonce: bytes,
        ct: bytes,
        tag: bytes,
        seq: int = 1,
    ) -> bytes:
        """Decrypt given raw key/base-nonce and (ciphertext, tag)."""
        n = cls._nonce_from_base(base_nonce, seq)
        combined = ct + tag
        if cipher_id.startswith("aes_"):
            return AESCCM(key, tag_length=cls.TAG_LEN).decrypt(n, combined, None)
        return ChaCha20Poly1305(key).decrypt(n, combined, None)


@dataclass
class TlaSession:
    """Established TPAP session details."""

    sessionId: str
    sessionExpired: int
    sessionType: str
    sessionCipher: _SessionCipher
    startSequence: int
    weakCipher: bool = False


@dataclass
class TpapNOCData:
    """NOC materials for NOC authentication and TLS client auth."""

    nocPrivateKey: str
    nocCertificate: str
    nocIntermediateCertificate: str
    nocRootCertificate: str


class NOCClient:
    """Client to fetch App NOC materials from TP-Link Cloud."""

    ACCESS_KEY = "4d11b6b9d5ea4d19a829adbb9714b057"
    SECRET_KEY = "6ed7d97f3e73467f8a5bab90b577ba4c"  # noqa: S105

    def __init__(self) -> None:
        self._key_pem: str | None = None
        self._cert_pem: str | None = None
        self._inter_pem: str | None = None
        self._root_pem: str | None = None

    def get(self) -> TpapNOCData:
        """Return cached NOC materials or raise if unavailable."""
        if not (
            self._key_pem and self._cert_pem and self._inter_pem and self._root_pem
        ):
            raise KasaException("No NOC materials available.")
        return TpapNOCData(
            nocPrivateKey=self._key_pem,
            nocCertificate=self._cert_pem,
            nocIntermediateCertificate=self._inter_pem,
            nocRootCertificate=self._root_pem,
        )

    def _login(self, username: str, password: str) -> tuple[str, str]:
        """Login to Cloud and return (token, account_id)."""
        payload = {
            "method": "login",
            "params": {
                "cloudUserName": username,
                "cloudPassword": password,
                "appType": "Tapo_Android",
                "terminalUUID": "UNOC",
            },
        }
        r = requests.post(
            "https://n-wap.i.tplinkcloud.com/",
            json=payload,
            verify=False,  # noqa: S501
            timeout=15.0,
        )
        r.raise_for_status()
        result = r.json()["result"]
        return result["token"], result["accountId"]

    def _get_url(self, account_id: str, token: str, username: str) -> str:
        """Resolve service URL for CVM server."""
        body_obj = {
            "serviceIds": ["nbu.cvm-server-v2"],
            "accountId": account_id,
            "cloudUserName": username,
        }
        body_bytes = json.dumps(body_obj, separators=(",", ":")).encode()
        endpoint = (
            "https://n-aps1-wap.i.tplinkcloud.com/api/v2/common/getAppServiceUrlById"
        )
        path = "/api/v2/common/getAppServiceUrlById"

        md5_bytes = hashlib.md5(body_bytes).digest()  # noqa: S324
        content_md5 = base64.b64encode(md5_bytes).decode()
        timestamp = str(int(datetime.now(UTC).timestamp()))
        nonce = str(uuid.uuid4())
        message = (content_md5 + "\n" + timestamp + "\n" + nonce + "\n" + path).encode()
        signature = hmac.new(  # noqa: S324
            self.SECRET_KEY.encode(), message, hashlib.sha1
        ).hexdigest()
        x_auth = (
            f"Timestamp={timestamp}, Nonce={nonce}, "
            f"AccessKey={self.ACCESS_KEY}, Signature={signature}"
        )
        headers = {
            "Content-Type": "application/json",
            "Content-MD5": content_md5,
            "X-Authorization": x_auth,
            "Authorization": token,
        }
        r = requests.post(
            endpoint,
            headers=headers,
            data=body_bytes,
            verify=False,  # noqa: S501
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()["result"]["serviceList"][0]["serviceUrl"]

    @staticmethod
    def _split_chain(chain_pem: str) -> tuple[str, str]:
        """Split intermediate and root certificates from a chain PEM."""
        inter_pem, root_pem = chain_pem.split("-----END CERTIFICATE-----", 1)
        inter_pem += "-----END CERTIFICATE-----"
        return inter_pem, root_pem

    def apply(self, username: str, password: str) -> TpapNOCData:
        """Apply for a new NOC and cache materials."""
        if self._key_pem and self._cert_pem and self._inter_pem and self._root_pem:
            return self.get()
        try:
            _LOGGER.debug("NOCClient: Starting NOC apply for user %r", username)
            token, account_id = self._login(username, password)
            _LOGGER.debug("NOCClient: Got token/account_id: %r/%r", token, account_id)
            url = self._get_url(account_id, token, username)
            _LOGGER.debug("NOCClient: Got service URL: %r", url)

            priv = ec.generate_private_key(ec.SECP256R1())
            pub_der = priv.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            _LOGGER.debug("NOCClient: Generated EC keypair for CSR")
            subject = asn1_x509.Name.build({"organizational_unit_name": "UNOC"})
            attributes = [
                {
                    "type": "1.2.840.113549.1.9.14",
                    "values": [
                        asn1_x509.Extensions(
                            [
                                asn1_x509.Extension(
                                    {
                                        "extn_id": "2.5.29.15",
                                        "critical": False,
                                        "extn_value": asn1_x509.KeyUsage(
                                            {"digital_signature"}
                                        ),
                                    }
                                ),
                                asn1_x509.Extension(
                                    {
                                        "extn_id": "2.5.29.19",
                                        "critical": False,
                                        "extn_value": asn1_x509.BasicConstraints(
                                            {"ca": False, "path_len_constraint": None}
                                        ),
                                    }
                                ),
                                asn1_x509.Extension(
                                    {
                                        "extn_id": "2.5.29.14",
                                        "critical": False,
                                        "extn_value": asn1_core.OctetString(
                                            hashlib.sha1(pub_der).digest()  # noqa: S324
                                        ),
                                    }
                                ),
                            ]
                        )
                    ],
                }
            ]
            cri = asn1_csr.CertificationRequestInfo(
                {
                    "version": 0,
                    "subject": subject,
                    "subject_pk_info": asn1_x509.PublicKeyInfo.load(pub_der),
                    "attributes": attributes,
                }
            )
            sig = priv.sign(cri.dump(), ec.ECDSA(hashes.SHA256()))
            csr = asn1_csr.CertificationRequest(
                {
                    "certification_request_info": cri,
                    "signature_algorithm": asn1_x509.SignedDigestAlgorithm(
                        {"algorithm": "sha256_ecdsa"}
                    ),
                    "signature": sig,
                }
            )
            csr_pem = asn1_pem.armor("CERTIFICATE REQUEST", csr.dump()).decode()
            key_pem = priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode()
            _LOGGER.debug(
                "NOCClient: Created CSR and private key (PEM length: %d)", len(key_pem)
            )

            endpoint = url.rstrip("/") + "/v1/certificate/noc/app/apply"
            body = {"userToken": token, "csr": csr_pem}
            _LOGGER.debug("NOCClient: Posting CSR to %r", endpoint)
            r = requests.post(
                endpoint,
                json=body,
                verify=False,  # noqa: S501
                timeout=15.0,
            )
            r.raise_for_status()
            res = r.json()["result"]
            cert_pem: str = res["certificate"]
            chain_pem: str = res["certificateChain"]
            inter_pem, root_pem = self._split_chain(chain_pem)
            _LOGGER.debug(
                "NOCClient: Received certificate and chain (cert PEM length: %d)",
                len(cert_pem),
            )

            self._cert_pem = cert_pem
            self._key_pem = key_pem
            self._inter_pem = inter_pem
            self._root_pem = root_pem
            _LOGGER.debug("NOCClient: NOC materials cached")
            return self.get()
        except Exception as exc:
            _LOGGER.exception("NOCClient: Error during NOC apply: %r", exc)
            raise KasaException(f"TPLink Cloud NOC apply failed: {exc}") from exc


class BaseAuthContext:
    """Shared helpers for TPAP authentication contexts."""

    def __init__(self, authenticator: Authenticator) -> None:
        """Bind to transport and authenticator."""
        self._authenticator = authenticator
        self._transport = authenticator._transport

    @staticmethod
    def _md5_hex(s: str) -> str:
        return hashlib.md5(s.encode()).hexdigest()  # noqa: S324

    async def _login(self, params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        """POST login step as JSON and return result payload."""
        body = {"method": "login", "params": params}
        status, data = await self._transport._http_client.post(
            self._transport._app_url.with_path("/"),
            json=body,
            headers=self._transport.COMMON_HEADERS,
            ssl=await self._transport._get_ssl_context(),
        )
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"{self._transport._host} {step_name} bad status/body: "
                f"{status} {type(data)}"
            )
        resp = cast(dict[str, Any], data)
        self._authenticator._handle_response_error_code(
            resp, f"TPAP {step_name} failed"
        )
        return cast(dict, resp.get("result") or {})

    async def _login_tslp(
        self, params: dict[str, Any], *, step_name: str
    ) -> dict[str, Any]:
        """POST login step as TSLP-octet wrapper and return result."""
        body = {"method": "login", "params": params}
        body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
        wrapped = self._wrap_tslp_packet(body_bytes)
        headers = {"Content-Type": "application/octet-stream"}
        status, data = await self._transport._http_client.post(
            self._transport._app_url.with_path("/"),
            data=wrapped,
            headers=headers,
            ssl=await self._transport._get_ssl_context(),
        )
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"{self._transport._host} TSLP {step_name} bad status/body: "
                f"{status} {type(data)}"
            )
        resp = cast(dict[str, Any], data)
        self._authenticator._handle_response_error_code(
            resp, f"TPAP {step_name} TSLP failed"
        )
        return cast(dict, resp.get("result") or {})

    @staticmethod
    def _wrap_tslp_packet(payload: bytes) -> bytes:
        """Wrap payload to TSLP."""
        b0 = (1).to_bytes(1, "big")
        b1 = (1).to_bytes(1, "big")
        b2 = (1).to_bytes(1, "big")
        b3 = (0).to_bytes(1, "big")
        length = len(payload).to_bytes(4, "big")
        name = b"".ljust(8, b"\x00")
        session_int = (0).to_bytes(4, "big")
        placeholder = (-1832963859 & 0xFFFFFFFF).to_bytes(4, "big")
        packet = b"".join(
            [b0, b1, b2, b3, length, name, session_int, placeholder, payload]
        )
        try:
            crc32 = zlib.crc32(packet) & 0xFFFFFFFF
        except Exception:
            crc32 = binascii.crc_hqx(packet, 0) & 0xFFFFFFFF
        crc_bytes = int(crc32).to_bytes(4, "big")
        packet = packet[:20] + crc_bytes + packet[24:]
        return packet


class NocAuthContext(BaseAuthContext):
    """NOC authentication: KEX -> proof encrypt -> dev proof verify."""

    def __init__(self, authenticator: Authenticator) -> None:
        """Init with NOC materials and ephemeral state."""
        super().__init__(authenticator)
        self._authenticator._ensure_noc()
        noc = self._authenticator._noc_data
        if noc is None:
            raise KasaException("NOC materials unavailable")
        self.noc_cert_pem = noc.nocCertificate
        self.noc_key_pem = noc.nocPrivateKey
        self.user_icac_pem = noc.nocIntermediateCertificate or ""
        self.device_root_pem = noc.nocRootCertificate

        self._ephemeral_priv: ec.EllipticCurvePrivateKey | None = None
        self._ephemeral_pub_bytes: bytes | None = None
        self._dev_pub_bytes: bytes | None = None
        self._shared_secret: bytes | None = None
        self._chosen_cipher: _CipherId = "aes_128_ccm"
        self._session_expired: int = 0
        self._hkdf_hash = "SHA256"

    @staticmethod
    def _hex(b: bytes) -> str:
        return binascii.hexlify(b).decode()

    @staticmethod
    def _unhex(s: str) -> bytes:
        return binascii.unhexlify(s.encode())

    def _gen_ephemeral(self) -> bytes:
        if self._ephemeral_priv is None:
            self._ephemeral_priv = ec.generate_private_key(ec.SECP256R1())
            self._ephemeral_pub_bytes = self._ephemeral_priv.public_key().public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
        return cast(bytes, self._ephemeral_pub_bytes)

    def _derive_shared_secret(self, dev_pub_uncompressed: bytes) -> bytes:
        if self._ephemeral_priv is None:
            raise KasaException("Ephemeral private key not generated")
        dev_pub = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), dev_pub_uncompressed
        )
        return self._ephemeral_priv.exchange(ec.ECDH(), dev_pub)

    def _sign_user_proof(
        self,
        user_cert_der: bytes,
        user_icac_der: bytes,
        dev_pub_bytes: bytes,
        user_pub_bytes: bytes,
    ) -> bytes:
        """Sign ECDSA-SHA256 over userCert || userIcac || userEphem || devPub."""
        try:
            private_key = serialization.load_pem_private_key(
                self.noc_key_pem.encode(), password=None
            )
            if not isinstance(private_key, ec.EllipticCurvePrivateKey):
                raise KasaException("NOC private key is not EC")
            message = user_cert_der + user_icac_der + user_pub_bytes + dev_pub_bytes
            return private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        except Exception as exc:
            raise KasaException(f"NOC user proof signing failed: {exc}") from exc

    def _verify_device_proof(self, dev_proof_obj: dict[str, Any]) -> None:
        """Verify dev proof signature over devCert || devIcac || devPub || userEphem."""
        try:
            dev_noc_pem = dev_proof_obj.get("dev_noc") or dev_proof_obj.get(
                "devNocCertificate"
            )
            dev_ica_pem = dev_proof_obj.get("dev_icac") or dev_proof_obj.get(
                "devIcacCertificate"
            )
            proof_hex = dev_proof_obj.get("proof")
            if not dev_noc_pem or not proof_hex:
                raise KasaException("Device proof missing fields")

            dev_cert = x509.load_pem_x509_certificate(dev_noc_pem.encode())
            dev_cert_der = dev_cert.public_bytes(serialization.Encoding.DER)
            dev_ica_der = b""
            if dev_ica_pem:
                ica_cert = x509.load_pem_x509_certificate(dev_ica_pem.encode())
                dev_ica_der = ica_cert.public_bytes(serialization.Encoding.DER)

            if self._dev_pub_bytes is None or self._ephemeral_pub_bytes is None:
                raise KasaException("Missing public keys for device proof verify")

            message = (
                dev_cert_der
                + dev_ica_der
                + self._dev_pub_bytes
                + self._ephemeral_pub_bytes
            )
            signature = binascii.unhexlify(proof_hex)
            dev_pub = cast(ec.EllipticCurvePublicKey, dev_cert.public_key())
            dev_pub.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise KasaException("Invalid NOC device proof signature") from exc
        except Exception as exc:
            raise KasaException(f"NOC device proof verification failed: {exc}") from exc

    async def start(self) -> TlaSession | None:
        """Run NOC KEX + proof exchange and return session."""
        user_pk_hex = self._hex(self._gen_ephemeral())
        admin_md5 = self._md5_hex("admin")
        _LOGGER.debug(
            "NocAuthContext: Generated ephemeral user_pk_hex: %r", user_pk_hex
        )
        params = {
            "sub_method": "noc_kex",
            "username": admin_md5,
            "user_pk": user_pk_hex,
            "sessionId": None,
        }
        _LOGGER.debug("NocAuthContext: Sending NOC KEX params: %r", params)
        resp = await self._login_tslp(params, step_name="noc_kex")

        _LOGGER.debug("NOC KEX response: %r", resp)
        dev_pk_hex = resp.get("dev_pk")
        if not dev_pk_hex:
            _LOGGER.error("NOC KEX response missing dev_pk, full response: %r", resp)
            raise KasaException(f"NOC KEX response missing dev_pk, got {resp!r}")
        self._dev_pub_bytes = self._unhex(dev_pk_hex)
        chosen = (resp.get("encryption") or "aes_128_ccm").lower().replace("-", "_")
        self._chosen_cipher = (
            cast(_CipherId, chosen)
            if chosen in ("aes_128_ccm", "aes_256_ccm", "chacha20_poly1305")
            else "aes_128_ccm"
        )
        self._session_expired = int(resp.get("expired") or 0)
        _LOGGER.debug(
            "NOC KEX: dev_pk_hex=%r, chosen_cipher=%r, session_expired=%r",
            dev_pk_hex,
            self._chosen_cipher,
            self._session_expired,
        )

        self._shared_secret = self._derive_shared_secret(self._dev_pub_bytes)
        key, base_nonce = _SessionCipher.key_nonce_from_shared(
            self._shared_secret, self._chosen_cipher, hkdf_hash=self._hkdf_hash
        )

        user_cert = x509.load_pem_x509_certificate(self.noc_cert_pem.encode())
        user_cert_der = user_cert.public_bytes(serialization.Encoding.DER)
        user_icac_der = (
            x509.load_pem_x509_certificate(self.user_icac_pem.encode()).public_bytes(
                serialization.Encoding.DER
            )
            if self.user_icac_pem
            else b""
        )
        signature = self._sign_user_proof(
            user_cert_der,
            user_icac_der,
            self._dev_pub_bytes,
            cast(bytes, self._ephemeral_pub_bytes),
        )
        proof_json = json.dumps(
            {
                "user_noc": self.noc_cert_pem,
                "user_icac": self.user_icac_pem,
                "proof": self._hex(signature),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        ct_body, tag = _SessionCipher.sec_encrypt(
            self._chosen_cipher, key, base_nonce, proof_json, seq=1
        )

        proof_params = {
            "sub_method": "noc_proof",
            "user_proof_encrypt": self._hex(ct_body),
            "tag": self._hex(tag),
        }
        proof_res = await self._login_tslp(proof_params, step_name="noc_proof")

        dev_proof_hex = proof_res.get("dev_proof_encrypt") or proof_res.get("dev_proof")
        tag_hex = proof_res.get("tag")
        if not dev_proof_hex:
            raise KasaException("NOC proof response missing device proof")
        dev_ct = self._unhex(dev_proof_hex)
        dev_tag = self._unhex(tag_hex) if tag_hex else b""
        dev_plain = _SessionCipher.sec_decrypt(
            self._chosen_cipher, key, base_nonce, dev_ct, dev_tag, seq=1
        )
        dev_obj = json.loads(dev_plain.decode("utf-8"))
        self._verify_device_proof(dev_obj)

        session_id = (
            proof_res.get("sessionId")
            or proof_res.get("stok")
            or proof_res.get("session_id")
            or ""
        )
        start_seq = int(proof_res.get("start_seq") or proof_res.get("startSeq") or 1)
        session_cipher = _SessionCipher.from_shared_key(
            self._chosen_cipher, self._shared_secret, hkdf_hash=self._hkdf_hash
        )
        return TlaSession(
            sessionId=session_id,
            sessionExpired=int(
                proof_res.get("expired")
                or proof_res.get("sessionExpired")
                or self._session_expired
                or 0
            ),
            sessionType="NOC",
            sessionCipher=session_cipher,
            startSequence=start_seq,
        )


class Spake2pAuthContext(BaseAuthContext):
    """SPAKE2+ authentication and session key schedule."""

    P256_M_COMP = bytes.fromhex(
        "02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f"
    )
    P256_N_COMP = bytes.fromhex(
        "03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49"
    )
    PAKE_CONTEXT_TAG = b"PAKE V1"

    def __init__(self, authenticator: Authenticator) -> None:
        """Init SPAKE2+ context with config and discovery info."""
        super().__init__(authenticator)
        creds = getattr(self._transport._config, "credentials", None)
        self.username: str = (creds.username if creds else "") or ""
        self.passcode: str = (creds.password if creds else "") or ""
        self.discover_mac = self._authenticator._device_mac or ""
        self.discover_suites = self._authenticator._tpap_pake or []

        self._curve = NIST256p
        self._generator: PointJacobi = self._curve.generator
        self._G = self._generator
        self._order = self._generator.order()
        Mx, My = self._sec1_to_xy(self.P256_M_COMP)
        Nx, Ny = self._sec1_to_xy(self.P256_N_COMP)
        self._M = ellipticcurve.Point(self._curve.curve, Mx, My, self._order)
        self._N = ellipticcurve.Point(self._curve.curve, Nx, Ny, self._order)

        self._w: int | None = None
        self._h_scalar: int | None = None
        self._L_enc: bytes | None = None
        self._R_enc: bytes | None = None
        self._expected_dev_confirm: str | None = None
        self._shared_key: bytes | None = None
        self._chosen_cipher: _CipherId = "aes_128_ccm"
        self._hkdf_hash: str = "SHA256"
        self._suite_type: int = 2
        self._dac_nonce_hex: str | None = None

        self.user_random = secrets.token_hex(16)
        self.extra_params: dict[str, Any] = {}

    @staticmethod
    def _sec1_to_xy(sec1: bytes) -> tuple[int, int]:
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sec1)
        nums = pub.public_numbers()
        return nums.x, nums.y

    @staticmethod
    def _xy_to_uncompressed(x: int, y: int) -> bytes:
        numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
        pub = numbers.public_key()
        return pub.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

    @staticmethod
    def _len8le(b: bytes) -> bytes:
        return len(b).to_bytes(8, "little") + b

    @staticmethod
    def _encode_w(w: int) -> bytes:
        wb = w.to_bytes((w.bit_length() + 7) // 8 or 1, "big", signed=False)
        if len(wb) > 1 and len(wb) % 2 == 0 and wb[0] == 0x00:
            wb = wb[1:]
        return wb

    @staticmethod
    def _hash(alg: str, data: bytes) -> bytes:
        return (
            hashlib.sha512(data).digest()
            if alg.upper() == "SHA512"
            else hashlib.sha256(data).digest()
        )

    @staticmethod
    def _hkdf_expand(label: str, ikm: bytes, out_len: int, alg: str) -> bytes:
        algorithm = hashes.SHA512() if alg.upper() == "SHA512" else hashes.SHA256()
        return HKDF(
            algorithm=algorithm, length=out_len, salt=None, info=label.encode()
        ).derive(ikm)

    @staticmethod
    def _hmac(alg: str, key: bytes, data: bytes) -> bytes:
        return hmac.new(
            key, data, hashlib.sha512 if alg.upper() == "SHA512" else hashlib.sha256
        ).digest()

    @staticmethod
    def _cmac_aes(key: bytes, data: bytes) -> bytes:
        c = CMAC(algorithms.AES(key))
        c.update(data)
        return c.finalize()

    @staticmethod
    def _pbkdf2_sha256(pw: bytes, salt: bytes, iterations: int, length: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", pw, salt, iterations, length)

    @classmethod
    def _derive_ab(
        cls, cred: bytes, salt: bytes, iterations: int, hash_len: int = 32
    ) -> tuple[int, int]:
        iD = hash_len + 8
        out = cls._pbkdf2_sha256(cred, salt, iterations, 2 * iD)
        return int.from_bytes(out[:iD], "big"), int.from_bytes(out[iD:], "big")

    @staticmethod
    def _sha1_hex(s: str) -> str:
        return hashlib.sha1(s.encode()).hexdigest()  # noqa: S324

    @staticmethod
    def _sha256crypt_simple(passcode: str, prefix: str) -> str:
        return prefix + "$" + hashlib.sha256(passcode.encode()).hexdigest()

    @classmethod
    def _authkey_mask(cls, passcode: str, tmpkey: str, dictionary: str) -> str:
        out = []
        L = max(len(tmpkey), len(passcode))
        for i in range(L):
            a = ord(passcode[i]) if i < len(passcode) else 0xBB
            b = ord(tmpkey[i]) if i < len(tmpkey) else 0xBB
            out.append(dictionary[(a ^ b) % len(dictionary)])
        return "".join(out)

    @classmethod
    def _sha1_username_mac_shadow(cls, username: str, mac12hex: str, pwd: str) -> str:
        if (
            (not username)
            or len(mac12hex) != 12
            or not all(c in "0123456789abcdefABCDEF" for c in mac12hex)
        ):
            return pwd
        mac = ":".join(mac12hex[i : i + 2] for i in range(0, 12, 2)).upper()
        return cls._sha1_hex(cls._md5_hex(username) + "_" + mac)

    @classmethod
    def _build_credentials(
        cls, extra_crypt: dict | None, username: str, passcode: str, mac_no_colon: str
    ) -> str:
        if not extra_crypt:
            return (username + "/" + passcode) if username else passcode
        t = (extra_crypt or {}).get("type", "").lower()
        p = (extra_crypt or {}).get("params", {}) or {}
        if t == "password_shadow":
            pid = int(p.get("passwd_id", 0))
            prefix = p.get("passwd_prefix", "") or ""
            if pid == 1:
                return cls._md5_hex(passcode)
            if pid == 2:
                return cls._sha1_hex(passcode)
            if pid == 3:
                return cls._sha1_username_mac_shadow(username, mac_no_colon, passcode)
            if pid == 5:
                return cls._sha256crypt_simple(passcode, prefix)
            return passcode
        if t == "password_authkey":
            tmp = p.get("authkey_tmpkey", "") or ""
            dic = p.get("authkey_dictionary", "") or ""
            return cls._authkey_mask(passcode, tmp, dic) if tmp and dic else passcode
        if t == "password_sha_with_salt":
            sha_name = int(p.get("sha_name", -1))
            sha_salt_b64 = p.get("sha_salt", "") or ""
            try:
                name = "admin" if sha_name == 0 else "user"
                salt_dec = base64.b64decode(sha_salt_b64).decode()
                return hashlib.sha256((name + salt_dec + passcode).encode()).hexdigest()
            except Exception:
                return passcode
        return (username + "/" + passcode) if username else passcode

    def _suite_hash_name(self, suite_type: int) -> str:
        return "SHA512" if suite_type in (2, 4, 5, 7, 9) else "SHA256"

    def _suite_mac_is_cmac(self, suite_type: int) -> bool:
        return suite_type in (8, 9)

    def _use_dac_certification(self) -> bool:
        return (self._authenticator._tpap_tls == 0) and bool(
            self._authenticator._tpap_dac
        )

    @staticmethod
    def _mac_pass_from_device_mac(mac_colon: str) -> str:
        mac_hex = mac_colon.replace(":", "").replace("-", "")
        mac_bytes = bytes.fromhex(mac_hex)
        seed = b"GqY5o136oa4i6VprTlMW2DpVXxmfW8"
        ikm = seed + mac_bytes[3:6] + mac_bytes[0:3]
        return (
            HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"tp-kdf-salt-default-passcode",
                info=b"tp-kdf-info-default-passcode",
            )
            .derive(ikm)
            .hex()
            .upper()
        )

    async def start(self) -> TlaSession | None:
        """Run SPAKE2+ register/share and return session."""
        reg_params = {
            "sub_method": "pake_register",
            "username": self.username,
            "user_random": self.user_random,
            "cipher_suites": self.discover_suites or [1, 2],
            "encryption": ["aes_128_ccm", "chacha20_poly1305", "aes_256_ccm"],
            "passcode_type": "password",
            "sessionId": None,
        }
        reg_params.update(self.extra_params)

        reg = await self._login(reg_params, step_name="pake_register")
        share_params = self.process_register_result(reg)

        if self._use_dac_certification():
            self._dac_nonce_hex = secrets.token_hex(32)
            share_params["dac_nonce"] = self._dac_nonce_hex

        share_res = await self._login(share_params, step_name="pake_share")
        return self.process_share_result(share_res)

    def process_register_result(self, reg: dict[str, Any]) -> dict[str, Any]:
        """Build PAKE share params; derive confirms and shared key."""
        dev_random = reg.get("dev_random") or ""
        dev_salt = reg.get("dev_salt") or ""
        dev_share = reg.get("dev_share") or ""
        suite_type = int(reg.get("cipher_suites") or 2)
        iterations = int(reg.get("iterations") or 10000)
        chosen_cipher = cast(_CipherId, reg.get("encryption") or "aes_128_ccm")
        extra_crypt = reg.get("extra_crypt") or {}

        self._suite_type = suite_type
        self._chosen_cipher = chosen_cipher
        self._hkdf_hash = self._suite_hash_name(suite_type)

        if (self.discover_suites and 0 in self.discover_suites) and self.discover_mac:
            cred_str = self._mac_pass_from_device_mac(self.discover_mac)
        else:
            cred_str = self._build_credentials(
                extra_crypt,
                self.username,
                self.passcode,
                self.discover_mac.replace(":", "").replace("-", ""),
            )

        cred = cred_str.encode()
        a, b = self._derive_ab(cred, bytes.fromhex(dev_salt), iterations, 32)
        order = self._order
        w = a % order
        h_scalar = b % order
        G, M, N = self._G, self._M, self._N
        x = secrets.randbelow(order - 1) + 1
        Lp = x * G + w * M

        Rx, Ry = self._sec1_to_xy(bytes.fromhex(dev_share))
        R = ellipticcurve.Point(self._curve.curve, Rx, Ry, order)
        Rprime = R + (-(w * N))
        Zp = x * Rprime
        Vp = (h_scalar % order) * Rprime

        L_enc = self._xy_to_uncompressed(Lp.x(), Lp.y())
        R_enc = self._xy_to_uncompressed(R.x(), R.y())
        Z_enc = self._xy_to_uncompressed(Zp.x(), Zp.y())
        V_enc = self._xy_to_uncompressed(Vp.x(), Vp.y())
        M_enc = self._xy_to_uncompressed(self._M.x(), self._M.y())
        N_enc = self._xy_to_uncompressed(self._N.x(), self._N.y())

        context_hash = self._hash(
            self._hkdf_hash,
            self.PAKE_CONTEXT_TAG
            + bytes.fromhex(self.user_random)
            + bytes.fromhex(dev_random),
        )
        transcript = (
            self._len8le(context_hash)
            + self._len8le(b"")
            + self._len8le(b"")
            + self._len8le(M_enc)
            + self._len8le(N_enc)
            + self._len8le(L_enc)
            + self._len8le(R_enc)
            + self._len8le(Z_enc)
            + self._len8le(V_enc)
            + self._len8le(self._encode_w(w))
        )
        T = self._hash(self._hkdf_hash, transcript)

        digest_len = 64 if self._hkdf_hash == "SHA512" else 32
        conf = self._hkdf_expand("ConfirmationKeys", T, digest_len, self._hkdf_hash)
        KcA, KcB = conf[: digest_len // 2], conf[digest_len // 2 :]
        self._shared_key = self._hkdf_expand(
            "SharedKey", T, digest_len, self._hkdf_hash
        )

        if self._suite_mac_is_cmac(self._suite_type):
            user_confirm = self._cmac_aes(KcA, R_enc).hex()
            expected_dev_confirm = self._cmac_aes(KcB, L_enc).hex()
        else:
            user_confirm = self._hmac(self._hkdf_hash, KcA, R_enc).hex()
            expected_dev_confirm = self._hmac(self._hkdf_hash, KcB, L_enc).hex()

        self._w = w
        self._h_scalar = h_scalar
        self._L_enc = L_enc
        self._R_enc = R_enc
        self._expected_dev_confirm = expected_dev_confirm

        return {
            "sub_method": "pake_share",
            "user_share": L_enc.hex(),
            "user_confirm": user_confirm,
        }

    def _verify_dac(self, share: dict[str, Any]) -> None:
        """Verify DAC proof: ECDSA-SHA256 over (sharedKey || nonce) with DAC CA."""
        try:
            dac_ca = share.get("dac_ca")
            dac_proof = share.get("dac_proof")
            if not (dac_ca and dac_proof and self._shared_key and self._dac_nonce_hex):
                return
            ca_pem = base64.b64decode(dac_ca).decode()
            ca_cert = x509.load_pem_x509_certificate(ca_pem.encode())
            msg = self._shared_key + bytes.fromhex(self._dac_nonce_hex)
            sig = bytes.fromhex(dac_proof)
            ca_pub = cast(ec.EllipticCurvePublicKey, ca_cert.public_key())
            ca_pub.verify(sig, msg, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise KasaException("Invalid DAC proof signature") from exc
        except Exception as exc:
            raise KasaException(f"DAC verification failed: {exc}") from exc

    def process_share_result(self, share: dict[str, Any]) -> TlaSession:
        """Validate dev confirm and construct the session."""
        dev_confirm = (share.get("dev_confirm") or "").lower()
        if dev_confirm != (self._expected_dev_confirm or "").lower():
            raise KasaException("SPAKE2+ confirmation mismatch")

        if self._use_dac_certification():
            self._verify_dac(share)

        session_id = share.get("sessionId") or share.get("stok") or ""
        start_seq = int(share.get("start_seq") or 1)
        if not session_id:
            raise KasaException("Missing session fields from device")
        cipher = _SessionCipher.from_shared_key(
            self._chosen_cipher, self._shared_key or b"", hkdf_hash=self._hkdf_hash
        )
        return TlaSession(
            sessionId=session_id,
            sessionExpired=int(
                share.get("sessionExpired") or share.get("expired") or 0
            ),
            sessionType="SPAKE2+",
            sessionCipher=cipher,
            startSequence=start_seq,
        )


class Authenticator:
    """Drive discovery and auth context to establish a TPAP session."""

    def __init__(self, transport: TpapTransport) -> None:
        """Initialize with transport; NOC materials are lazy-loaded."""
        self._transport: TpapTransport = transport
        self._noc_client: NOCClient = NOCClient()
        self._noc_data: TpapNOCData | None = None
        self._auth_lock: asyncio.Lock = asyncio.Lock()
        self._cached_session: TlaSession | None = None
        self._device_mac: str | None = None
        self._tpap_tls: int | None = None
        self._tpap_noc: bool = False
        self._tpap_dac: bool = False
        self._tpap_pake: list[int] | None = None
        self._session_id: str | None = None
        self._seq: int | None = None
        self._cipher: _SessionCipher | None = None
        self._ds_url: URL | None = None

    @property
    def seq(self) -> int | None:
        """Current message sequence number (DS)."""
        return self._seq

    @property
    def cipher(self) -> _SessionCipher | None:
        """Current session cipher (AEAD) if established."""
        return self._cipher

    @property
    def ds_url(self) -> URL | None:
        """DS endpoint URL for encrypted requests."""
        return self._ds_url

    def _ensure_noc(self) -> None:
        if self._noc_data is None:
            self._noc_data = self._noc_client.apply(
                self._transport._username, self._transport._password
            )

    async def ensure_authenticator(self) -> None:
        """Ensure discovery + session is established (idempotent)."""
        async with self._auth_lock:
            if self._cached_session is not None:
                self._set_session_from_tla()
                self._transport._state = TransportState.ESTABLISHED
                return
            await self._discover()
            await self._establish_session()

    def _set_session_from_tla(self) -> None:
        """Populate runtime session from the cached TLA session."""
        if self._cached_session is not None:
            self._session_id = self._cached_session.sessionId
            self._seq = self._cached_session.startSequence
            self._cipher = self._cached_session.sessionCipher
            self._ds_url = URL(
                f"{str(self._transport._app_url)}/stok={self._session_id}/ds"
            )

    async def _discover(self) -> None:
        """Query device for TPAP capabilities and MAC."""
        body = {"method": "login", "params": {"sub_method": "discover"}}
        status, data = await self._transport._http_client.post(
            self._transport._app_url.with_path("/"),
            json=body,
            headers=self._transport.COMMON_HEADERS,
            ssl=await self._transport._get_ssl_context(),
        )
        if status != 200:
            raise KasaException(
                f"{self._transport._host} _discover failed status: {status}"
            )
        response: dict[str, Any] = cast(dict, data)
        self._handle_response_error_code(response, "_discover failed")
        result = response["result"]
        self._device_mac = result.get("mac")
        tpap = result["tpap"]
        self._tpap_noc = bool(tpap.get("noc"))
        self._tpap_dac = bool(tpap.get("dac"))
        self._tpap_tls = tpap.get("tls")
        self._tpap_pake = tpap.get("pake") or []

    def _handle_response_error_code(self, response: dict[str, Any], msg: str) -> None:
        """Translate device error codes to proper exceptions."""
        error_code_raw = response.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except (ValueError, TypeError):
            error_code = SmartErrorCode.SUCCESS
        if error_code is SmartErrorCode.SUCCESS:
            return
        full = f"{msg}: {self._transport._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(full, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._transport._state = TransportState.NOT_ESTABLISHED
            raise AuthenticationError(full, error_code=error_code)
        raise DeviceError(full, error_code=error_code)

    async def _establish_session(self) -> None:
        """Try NOC first, fall back to SPAKE2+."""
        if self._tpap_noc:
            try:
                noc_ctx = NocAuthContext(self)
                session = await noc_ctx.start()
                if isinstance(session, TlaSession):
                    self._cached_session = session
                    self._set_session_from_tla()
                    self._transport._state = TransportState.ESTABLISHED
                    _LOGGER.debug("Authenticator: established session via NOC")
                    return
            except Exception:
                _LOGGER.debug("Authenticator: NOC attempt failed", exc_info=True)
        spake_ctx = Spake2pAuthContext(self)
        session = await spake_ctx.start()
        if isinstance(session, TlaSession):
            self._cached_session = session
            self._set_session_from_tla()
            self._transport._state = TransportState.ESTABLISHED
            _LOGGER.debug("Authenticator: established session via SPAKE2+")
            return
        raise KasaException(
            "Authenticator: failed to establish session via NOC or SPAKE2+ with "
            f"{self._transport._host}"
        )


class TpapTransport(BaseTransport):
    """Transport implementing the TPAP encrypted DS channel."""

    DEFAULT_PORT: int = 4433
    CIPHERS = ":".join(
        [
            "ECDHE-ECDSA-AES256-GCM-SHA384",
            "ECDHE-ECDSA-CHACHA20-POLY1305",
            "ECDHE-ECDSA-AES128-GCM-SHA256",
            "AES256-GCM-SHA384",
            "AES256-SHA256",
            "AES128-GCM-SHA256",
            "AES128-SHA256",
            "AES256-SHA",
        ]
    )
    COMMON_HEADERS = {"Content-Type": "application/json"}

    P256_M_COMP = Spake2pAuthContext.P256_M_COMP
    P256_N_COMP = Spake2pAuthContext.P256_N_COMP

    def __init__(self, *, config: DeviceConfig) -> None:
        """Initialize HTTP client and state."""
        super().__init__(config=config)
        self._http_client: HttpClient = HttpClient(self._config)
        self._username: str = (
            self._config.credentials.username if self._config.credentials else ""
        ) or ""
        self._password: str = (
            self._config.credentials.password if self._config.credentials else ""
        ) or ""
        self._ssl_context: ssl.SSLContext | bool = False
        self._state = TransportState.NOT_ESTABLISHED
        self._app_url = URL(f"https://{self._host}:{self._port}")
        self._authenticator = Authenticator(self)
        self._send_lock: asyncio.Lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()

    @property
    def default_port(self) -> int:
        """Return default HTTPS port for this transport."""
        if port := self._config.connection_type.http_port:
            return port
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """Return a stable hash of credentials if available, else None."""
        return self._config.credentials_hash

    async def _get_ssl_context(self) -> ssl.SSLContext | bool:
        """Get or create SSL context as configured by device (TLS mode)."""
        if not self._ssl_context:
            self._ssl_context = await self._loop.run_in_executor(
                None, self._create_ssl_context
            )
        return self._ssl_context

    def _create_ssl_context(self) -> ssl.SSLContext | bool:
        """Initialize SSL context for TLS mode: 0/1/2."""
        tls_mode = self._authenticator._tpap_tls
        if tls_mode == 0:
            return False

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers(self.CIPHERS)
        context.check_hostname = False

        if tls_mode in (None, 1):
            context.verify_mode = ssl.CERT_NONE
            return context

        if tls_mode == 2:
            context.verify_mode = ssl.CERT_REQUIRED
            try:
                self._authenticator._ensure_noc()
            except Exception as exc:
                _LOGGER.debug("Unable to load NOC materials: %s", exc)
            noc = self._authenticator._noc_data
            if noc:
                root_certificate = noc.nocRootCertificate
                noc_certificate = noc.nocCertificate
                noc_key = noc.nocPrivateKey
                certificate_path = ""
                key_path = ""
                try:
                    context.load_verify_locations(cadata=root_certificate)
                    with tempfile.NamedTemporaryFile(
                        "w+", delete=False
                    ) as certificate_file:
                        certificate_file.write(noc_certificate)
                        certificate_file.flush()
                        certificate_path = certificate_file.name
                    with tempfile.NamedTemporaryFile("w+", delete=False) as key_file:
                        key_file.write(noc_key)
                        key_file.flush()
                        key_path = key_file.name
                    context.load_cert_chain(certificate_path, key_path)
                except Exception as exc:
                    _LOGGER.debug(
                        "Failed to load NOC certificates into SSL context: %s", exc
                    )
                finally:
                    for path in (certificate_path, key_path):
                        if path:
                            with contextlib.suppress(Exception):
                                os.unlink(path)
        return context

    async def send(self, request: str) -> dict[str, Any]:
        """Send an encrypted DS request and return parsed JSON response."""
        if self._state is TransportState.NOT_ESTABLISHED:
            await self._authenticator.ensure_authenticator()
        seq = self._authenticator.seq
        ds_url = self._authenticator.ds_url
        cipher = self._authenticator.cipher
        if seq is None or ds_url is None:
            raise KasaException("TPAP transport is not established")
        if cipher is None:
            raise KasaException("TPAP transport AEAD cipher not initialized")

        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        async with self._send_lock:
            payload = struct.pack(">I", seq) + cipher.encrypt(request.encode(), seq)
            headers = {"Content-Type": "application/octet-stream"}
            status, data = await self._http_client.post(
                ds_url, data=payload, headers=headers, ssl=await self._get_ssl_context()
            )
            if status != 200:
                raise KasaException(
                    f"{self._host} responded with unexpected status {status} "
                    "on secure request"
                )
            if getattr(self._authenticator, "_seq", None) is not None:
                self._authenticator._seq = seq + 1

        if isinstance(data, (bytes | bytearray)):
            raw = bytes(data)
            if len(raw) < 4 + _SessionCipher.TAG_LEN:
                raise KasaException("TPAP response too short")
            rseq = struct.unpack(">I", raw[:4])[0]
            if rseq != seq:
                _LOGGER.debug(
                    "Device returned unexpected rseq %d (expected %d)", rseq, seq
                )
            plaintext = cipher.decrypt(raw[4:], rseq)
            return cast(dict, json_loads(plaintext.decode()))

        if isinstance(data, dict):
            self._authenticator._handle_response_error_code(
                data, "Error sending TPAP request"
            )
            return data

        raise KasaException("Unexpected response body type from device")

    async def close(self) -> None:
        """Close underlying HTTP client and clear state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset transport state; session will be re-established on demand."""
        self._state = TransportState.NOT_ESTABLISHED
