"""Implementation of the TP-Link TPAP Protocol."""

from __future__ import annotations

import asyncio
import base64
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
from ecdsa import NIST256p, NIST384p, NIST521p, ellipticcurve
from ecdsa.ellipticcurve import PointJacobi
from passlib.hash import md5_crypt, sha256_crypt
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


# codeql[py/weak-sensitive-data-hashing]: disable
def _tp_link_protocol_md5_digest(data: bytes) -> bytes:
    return hashlib.md5(data).digest()  # noqa: S324


def _tp_link_protocol_md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()  # noqa: S324


def _tp_link_protocol_sha1_digest(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()  # noqa: S324


def _tp_link_protocol_sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()  # noqa: S324


# codeql[py/weak-sensitive-data-hashing]: enable


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
        algorithm = hashes.SHA256() if algo.upper() == "SHA256" else hashes.SHA512()
        return HKDF(algorithm=algorithm, length=length, salt=salt, info=info).derive(
            master
        )

    @staticmethod
    def _nonce_from_base(base: bytes, seq: int) -> bytes:
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
    sessionType: str
    sessionCipher: _SessionCipher
    startSequence: int


@dataclass
class TpapNOCData:
    """NOC materials for NOC authentication and TLS client auth."""

    nocPrivateKey: str
    nocCertificate: str
    nocIntermediateCertificate: str
    nocRootCertificate: str


class NOCClient:
    """Client to fetch App NOC materials from TP-Link Cloud."""

    ACCESS_KEY = "4d11b6b9d5ea4d19a829adbb9714b057"  # noqa: S105
    SECRET_KEY = "6ed7d97f3e73467f8a5bab90b577ba4c"  # noqa: S105

    def __init__(self) -> None:
        self._key_pem: str | None = None
        self._cert_pem: str | None = None
        self._inter_pem: str | None = None
        self._root_pem: str | None = None

    def _get(self) -> TpapNOCData:
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
        md5_bytes = _tp_link_protocol_md5_digest(body_bytes)
        content_md5 = base64.b64encode(md5_bytes).decode()
        timestamp = str(int(datetime.now(UTC).timestamp()))
        nonce = str(uuid.uuid4())
        message = (content_md5 + "\n" + timestamp + "\n" + nonce + "\n" + path).encode()
        # codeql[py/weak-sensitive-data-hashing]: disable-next-line
        signature = hmac.new(
            self.SECRET_KEY.encode(),
            message,
            hashlib.sha1,  # noqa: S324
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
        inter_pem, root_pem = chain_pem.split("-----END CERTIFICATE-----", 1)
        inter_pem += "-----END CERTIFICATE-----"
        return inter_pem, root_pem

    def apply(self, username: str, password: str) -> TpapNOCData:
        """Apply for a new NOC and cache materials."""
        if self._key_pem and self._cert_pem and self._inter_pem and self._root_pem:
            return self._get()
        try:
            token, account_id = self._login(username, password)
            url = self._get_url(account_id, token, username)
            priv = ec.generate_private_key(ec.SECP256R1())
            pub_der = priv.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
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
                                            _tp_link_protocol_sha1_digest(pub_der)
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
            endpoint = url.rstrip("/") + "/v1/certificate/noc/app/apply"
            body = {"userToken": token, "csr": csr_pem}
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
            self._cert_pem = cert_pem
            self._key_pem = key_pem
            self._inter_pem = inter_pem
            self._root_pem = root_pem
            return self._get()
        except Exception as exc:
            raise KasaException(f"TPLink Cloud NOC apply failed: {exc}") from exc


class BaseAuthContext:
    """Shared helpers for TPAP authentication contexts."""

    def __init__(self, authenticator: Authenticator) -> None:
        """Bind to transport and authenticator."""
        self._authenticator = authenticator
        self._transport = authenticator._transport

    @staticmethod
    def _md5_hex(s: str) -> str:
        return _tp_link_protocol_md5_hex(s.encode())

    @staticmethod
    def _base64(b: bytes) -> str:
        return base64.b64encode(b).decode()

    @staticmethod
    def _unbase64(s: str) -> bytes:
        return base64.b64decode(s)

    async def _login(self, params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        body = {"method": "login", "params": params}
        status, data = await self._transport._http_client.post(
            self._transport._app_url.with_path("/"),
            json=body,
            headers=self._transport.COMMON_HEADERS,
            ssl=await self._transport.get_ssl_context(),
        )
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"{self._transport._host} {step_name} bad status/body: "
                f"{status} {type(data)}"
            )
        resp = cast(dict[str, Any], data)
        self._authenticator.handle_response_error_code(resp, f"TPAP {step_name} failed")
        return cast(dict, resp.get("result") or {})


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
        self.user_icac_pem = noc.nocIntermediateCertificate
        self.device_root_pem = noc.nocRootCertificate
        self._ephemeral_priv: ec.EllipticCurvePrivateKey | None = None
        self._ephemeral_pub_bytes: bytes | None = None
        self._dev_pub_bytes: bytes | None = None
        self._shared_secret: bytes | None = None
        self._chosen_cipher: _CipherId = "aes_128_ccm"
        self._hkdf_hash = "SHA256"

    def _gen_ephemeral(self) -> bytes:
        if self._ephemeral_pub_bytes is None:
            self._ephemeral_priv = ec.generate_private_key(ec.SECP256R1())
            self._ephemeral_pub_bytes = self._ephemeral_priv.public_key().public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
        return self._ephemeral_pub_bytes

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
        try:
            dev_noc_pem = dev_proof_obj.get("dev_noc") or dev_proof_obj.get(
                "devNocCertificate"
            )
            dev_ica_pem = dev_proof_obj.get("dev_icac") or dev_proof_obj.get(
                "devIcacCertificate"
            )
            proof_base64 = dev_proof_obj.get("proof")
            if not dev_noc_pem or not proof_base64:
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
            signature = self._unbase64(proof_base64)
            dev_pub = cast(ec.EllipticCurvePublicKey, dev_cert.public_key())
            dev_pub.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise KasaException("Invalid NOC device proof signature") from exc
        except Exception as exc:
            raise KasaException(f"NOC device proof verification failed: {exc}") from exc

    async def start(self) -> TlaSession | None:
        """Run NOC KEX + proof exchange and return session."""
        user_pk_base64 = self._base64(self._gen_ephemeral())
        admin_md5 = self._md5_hex("admin")
        params = {
            "sub_method": "noc_kex",
            "username": admin_md5,
            "encryption": ["aes_128_ccm", "chacha20_poly1305", "aes_256_ccm"],
            "user_pk": user_pk_base64,
            "stok": None,
        }
        resp = await self._login(params, step_name="noc_kex")
        dev_pk_base64 = resp.get("dev_pk")
        if not dev_pk_base64:
            raise KasaException(f"NOC KEX response missing dev_pk, got {resp!r}")
        self._dev_pub_bytes = self._unbase64(dev_pk_base64)
        chosen = (resp.get("encryption") or "aes_128_ccm").lower().replace("-", "_")
        self._chosen_cipher = (
            cast(_CipherId, chosen)
            if chosen in ("aes_128_ccm", "aes_256_ccm", "chacha20_poly1305")
            else "aes_128_ccm"
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
                "proof": self._base64(signature),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        ct_body, tag = _SessionCipher.sec_encrypt(
            self._chosen_cipher, key, base_nonce, proof_json, seq=1
        )
        proof_params = {
            "sub_method": "noc_proof",
            "user_proof_encrypt": self._base64(ct_body),
            "tag": self._base64(tag),
        }
        proof_res = await self._login(proof_params, step_name="noc_proof")
        dev_proof_base64 = proof_res.get("dev_proof_encrypt")
        tag_base64 = proof_res.get("tag")
        if not dev_proof_base64:
            raise KasaException("NOC proof response missing device proof")
        dev_ct = self._unbase64(dev_proof_base64)
        dev_tag = self._unbase64(tag_base64) if tag_base64 else b""
        dev_plain = _SessionCipher.sec_decrypt(
            self._chosen_cipher, key, base_nonce, dev_ct, dev_tag, seq=1
        )
        dev_obj = json.loads(dev_plain.decode("utf-8"))
        self._verify_device_proof(dev_obj)
        session_id = proof_res.get("stok") or ""
        start_seq = int(proof_res.get("start_seq") or 1)
        session_cipher = _SessionCipher.from_shared_key(
            self._chosen_cipher, self._shared_secret, hkdf_hash=self._hkdf_hash
        )
        return TlaSession(
            sessionId=session_id,
            sessionType="NOC",
            sessionCipher=session_cipher,
            startSequence=start_seq,
        )


class Spake2pAuthContext(BaseAuthContext):
    """SPAKE2+ authentication and session key schedule."""

    PAKE_CONTEXT_TAG = b"PAKE V1"

    def __init__(self, authenticator: Authenticator) -> None:
        """Init SPAKE2+ context with config and discovery info."""
        super().__init__(authenticator)
        creds = getattr(self._transport._config, "credentials", None)
        self.username: str = (creds.username if creds else "") or ""
        self.passcode: str = (creds.password if creds else "") or ""
        self.discover_mac = self._authenticator._device_mac or ""
        self.discover_pake = self._authenticator._tpap_pake or []
        self._expected_dev_confirm: str | None = None
        self._shared_key: bytes | None = None
        self._chosen_cipher: _CipherId = "aes_128_ccm"
        self._hkdf_hash: str = "SHA256"
        self._dac_nonce_base64: str | None = None
        self.user_random = self._base64(os.urandom(32))

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
        minimal_len = 1 if w == 0 else (w.bit_length() + 7) // 8
        unsigned = w.to_bytes(minimal_len, "big", signed=False)
        if minimal_len % 2 == 0:
            return unsigned
        if unsigned[0] & 0x80:
            return b"\x00" + unsigned
        return unsigned

    @staticmethod
    def _hash(alg: str, data: bytes) -> bytes:
        return (
            hashlib.sha512(data).digest()
            if alg.upper() == "SHA512"
            else hashlib.sha256(data).digest()
        )

    @staticmethod
    def _hkdf_expand(label: str, prk: bytes, digest_len: int, alg: str) -> bytes:
        algorithm = hashes.SHA512() if alg.upper() == "SHA512" else hashes.SHA256()
        zero_salt = b"\x00" * digest_len
        hkdf = HKDF(
            algorithm=algorithm, length=digest_len, salt=zero_salt, info=label.encode()
        )
        return hkdf.derive(prk)

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
        a = int.from_bytes(out[:iD], "big")
        b = int.from_bytes(out[iD:], "big")
        return a, b

    @staticmethod
    def _sha1_hex(s: str) -> str:
        return _tp_link_protocol_sha1_hex(s.encode())

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
    def _md5_crypt(cls, password: str, prefix: str) -> str | None:
        if not prefix or not prefix.startswith("$1$"):
            return None
        if len(password) > 30000:
            return None
        spec = prefix[3:]
        if "$" in spec:
            spec = spec.split("$", 1)[0]
        salt = spec[:8]
        return md5_crypt.using(salt=salt).hash(password)

    @classmethod
    def _sha256_crypt(
        cls, password: str, prefix: str, rounds_from_params: int | None = None
    ) -> str | None:
        if not prefix:
            return None
        DEFAULT_ROUNDS = 5000
        MIN_ROUNDS = 1000
        MAX_ROUNDS = 999_999_999
        spec = prefix
        rounds: int | None = None
        salt = ""
        if spec.startswith("$5$"):
            spec = spec[3:]
        if spec.startswith("rounds="):
            parts = spec.split("$", 1)
            try:
                rounds_val = int(parts[0].split("=", 1)[1])
            except Exception:
                rounds_val = DEFAULT_ROUNDS
            rounds_val = max(MIN_ROUNDS, min(MAX_ROUNDS, rounds_val))
            rounds = rounds_val
            salt = parts[1] if len(parts) > 1 else ""
        else:
            salt = spec.split("$", 1)[0] if "$" in spec else spec
        if rounds_from_params is not None:
            r = int(rounds_from_params)
            r = max(MIN_ROUNDS, min(MAX_ROUNDS, r))
            rounds = r
        salt = (salt or "")[:16]
        if rounds is not None:
            return sha256_crypt.using(rounds=rounds, salt=salt).hash(password)
        return sha256_crypt.using(salt=salt).hash(password)

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
                md = cls._md5_crypt(passcode, prefix)
                return md if md is not None else passcode
            if pid == 2:
                val = cls._sha1_hex(passcode)
                return val
            if pid == 3:
                val = cls._sha1_username_mac_shadow(username, mac_no_colon, passcode)
                return val
            if pid == 5:
                rounds = p.get("passwd_rounds")
                s5 = cls._sha256_crypt(passcode, prefix, rounds_from_params=rounds)
                return s5 if s5 is not None else passcode
            return passcode
        if t == "password_authkey":
            tmp = p.get("authkey_tmpkey", "") or ""
            dic = p.get("authkey_dictionary", "") or ""
            res = cls._authkey_mask(passcode, tmp, dic) if tmp and dic else passcode
            return res
        if t == "password_sha_with_salt":
            sha_name = int(p.get("sha_name", -1))
            sha_salt_b64 = p.get("sha_salt", "") or ""
            name = "admin" if sha_name == 0 else "user"
            try:
                salt_dec = base64.b64decode(sha_salt_b64).decode()
                # codeql[py/weak-sensitive-data-hashing]: disable-next-line
                return hashlib.sha256((name + salt_dec + passcode).encode()).hexdigest()  # noqa: S324
            except Exception:
                _LOGGER.debug(
                    "SPAKE2+: Invalid base64 salt provided, falling back to passcode"
                )
                return passcode
        return (username + "/" + passcode) if username else passcode

    def _suite_hash_name(self, suite_type: int) -> str:
        hash_name = "SHA512" if suite_type in (2, 4, 5, 7, 9) else "SHA256"
        return hash_name

    def _suite_mac_is_cmac(self, suite_type: int) -> bool:
        is_cmac = suite_type in (8, 9)
        return is_cmac

    def _use_dac_certification(self) -> bool:
        use_dac = (self._authenticator._tpap_tls == 0) and bool(
            self._authenticator._tpap_dac
        )
        return use_dac

    @staticmethod
    def _mac_pass_from_device_mac(mac_colon: str) -> str:
        mac_hex = mac_colon.replace(":", "").replace("-", "")
        mac_bytes = bytes.fromhex(mac_hex)
        seed = b"GqY5o136oa4i6VprTlMW2DpVXxmfW8"
        ikm = seed + mac_bytes[3:6] + mac_bytes[0:3]
        derived = (
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
        return derived

    def _get_passcode_type(self) -> str:
        if self.discover_pake and 0 in self.discover_pake:
            passcode_type = "default_userpw"
        elif self.discover_pake and 2 in self.discover_pake:
            passcode_type = "userpw"
        elif self.discover_pake and 3 in self.discover_pake:
            passcode_type = "shared_token"
        else:
            passcode_type = "userpw"
        return passcode_type

    async def start(self) -> TlaSession | None:
        """Run SPAKE2+ register/share and return session."""
        admin_md5 = self._md5_hex("admin")
        passcode_type = self._get_passcode_type()
        params = {
            "sub_method": "pake_register",
            "username": admin_md5,
            "user_random": self.user_random,
            "cipher_suites": [1],
            "encryption": ["aes_128_ccm", "chacha20_poly1305", "aes_256_ccm"],
            "passcode_type": passcode_type,
            "stok": None,
        }
        resp = await self._login(params, step_name="pake_register")
        share_params = self._process_register_result(resp)
        if self._use_dac_certification():
            self._dac_nonce_base64 = self._base64(os.urandom(16))
            share_params["dac_nonce"] = self._dac_nonce_base64
        share_res = await self._login(share_params, step_name="pake_share")
        return self._process_share_result(share_res)

    def _process_register_result(self, reg: dict[str, Any]) -> dict[str, Any]:
        dev_random = reg.get("dev_random") or ""
        dev_salt = reg.get("dev_salt") or ""
        dev_share = reg.get("dev_share") or ""
        suite_type = int(reg.get("cipher_suites") or 2)
        iterations = int(reg.get("iterations") or 10000)
        chosen_cipher = cast(_CipherId, reg.get("encryption") or "aes_128_ccm")
        extra_crypt = reg.get("extra_crypt") or {}
        self._chosen_cipher = chosen_cipher
        self._hkdf_hash = self._suite_hash_name(suite_type)
        if (self.discover_pake and 0 in self.discover_pake) and self.discover_mac:
            cred_str = self._mac_pass_from_device_mac(self.discover_mac)
        else:
            cred_str = self._build_credentials(
                extra_crypt,
                self.username,
                self.passcode,
                self.discover_mac.replace(":", "").replace("-", ""),
            )
        # Select curve and hardcoded M/N points based on suite_type
        if suite_type in (1, 2, 8, 9):
            # P-256
            M_comp = bytes.fromhex(
                "02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f"
            )
            N_comp = bytes.fromhex(
                "03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49"
            )
            nist = NIST256p
        elif suite_type in (3, 4):
            # P-384
            M_comp = bytes.fromhex(
                "030ff0895ae5ebf6187080a82d82b42e2765e3b2f8749c7e05eba366434b363d3dc36f15314739074d2eb8613fceec2853"
            )
            N_comp = bytes.fromhex(
                "02c72cf2e390853a1c1c4ad816a62fd15824f56078918f43f922ca21518f9c543bb252c5490214cf9aa3f0baab4b665c10"
            )
            nist = NIST384p
        elif suite_type == 5:
            # P-521
            M_comp = bytes.fromhex(
                "02003f06f38131b2ba2600791e82488e8d20ab889af753a41806c5db18d37d85608cfae06b82e4a72cd744c719193562a653ea1f119eef9356907edc9b56979962d7aa"
            )
            N_comp = bytes.fromhex(
                "0200c7924b9ec017f3094562894336a53c50167ba8c5963876880542bc669e494b2532d76c5b53dfb349fdf69154b9e0048c58a42e8ed04cef052a3bc349d95575cd25"
            )
            nist = NIST521p
        else:
            # Unsupported/untreated groups (e.g., curve25519/curve448)
            raise KasaException(f"Unsupported SPAKE2+ suite type: {suite_type}")

        curve = nist.curve
        generator: PointJacobi = nist.generator
        G = generator
        order: int = generator.order()
        Mx, My = self._sec1_to_xy(M_comp)
        Nx, Ny = self._sec1_to_xy(N_comp)
        M = ellipticcurve.Point(curve, Mx, My, order)
        N = ellipticcurve.Point(curve, Nx, Ny, order)
        cred = cred_str.encode()
        a, b = self._derive_ab(cred, self._unbase64(dev_salt), iterations, 32)
        w = a % order
        h = b % order
        x = secrets.randbelow(order - 1) + 1
        L: ellipticcurve.Point = x * G + w * M
        L_enc = self._xy_to_uncompressed(L.x(), L.y())
        dev_share_bytes = self._unbase64(dev_share) if dev_share else b""
        Rx, Ry = self._sec1_to_xy(dev_share_bytes)
        R = ellipticcurve.Point(curve, Rx, Ry, order)
        R_enc = self._xy_to_uncompressed(R.x(), R.y())
        Rprime = R + (-(w * N))
        Z: ellipticcurve.Point = x * Rprime
        V: ellipticcurve.Point = (h % order) * Rprime
        Z_enc = self._xy_to_uncompressed(Z.x(), Z.y())
        V_enc = self._xy_to_uncompressed(V.x(), V.y())
        M_enc = self._xy_to_uncompressed(M.x(), M.y())
        N_enc = self._xy_to_uncompressed(N.x(), N.y())
        context_hash = self._hash(
            self._hkdf_hash,
            self.PAKE_CONTEXT_TAG
            + self._unbase64(self.user_random)
            + self._unbase64(dev_random),
        )
        w_enc = self._encode_w(w)
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
            + self._len8le(w_enc)
        )
        T = self._hash(self._hkdf_hash, transcript)
        digest_len = 64 if self._hkdf_hash == "SHA512" else 32
        mac_len = 16 if self._suite_mac_is_cmac(suite_type) else 32
        conf = self._hkdf_expand("ConfirmationKeys", T, mac_len * 2, self._hkdf_hash)
        KcA, KcB = conf[:mac_len], conf[mac_len : mac_len * 2]
        self._shared_key = self._hkdf_expand(
            "SharedKey", T, digest_len, self._hkdf_hash
        )
        if self._suite_mac_is_cmac(suite_type):
            user_confirm = self._cmac_aes(KcA, R_enc)
            expected_dev_confirm = self._cmac_aes(KcB, L_enc)
        else:
            user_confirm = self._hmac(self._hkdf_hash, KcA, R_enc)
            expected_dev_confirm = self._hmac(self._hkdf_hash, KcB, L_enc)

        self._expected_dev_confirm = self._base64(expected_dev_confirm)
        return {
            "sub_method": "pake_share",
            "user_share": self._base64(L_enc),
            "user_confirm": self._base64(user_confirm),
        }

    def _verify_dac(self, share: dict[str, Any]) -> None:
        """Verify DAC proof: ECDSA-SHA256 over (sharedKey || nonce) with DAC CA."""
        try:
            dac_ca = str(share.get("dac_ca"))
            dac_proof = share.get("dac_proof")
            if not (
                dac_ca and dac_proof and self._shared_key and self._dac_nonce_base64
            ):
                return
            ca_cert = x509.load_pem_x509_certificate(dac_ca.encode())
            msg = self._shared_key + self._unbase64(self._dac_nonce_base64)
            sig = self._unbase64(dac_proof)
            ca_pub = cast(ec.EllipticCurvePublicKey, ca_cert.public_key())
            ca_pub.verify(sig, msg, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            _LOGGER.error("SPAKE2+: Invalid DAC proof signature")
            raise KasaException("Invalid DAC proof signature") from exc
        except Exception as exc:
            _LOGGER.error("SPAKE2+: DAC verification failed: %s", exc)
            raise KasaException(f"DAC verification failed: {exc}") from exc

    def _process_share_result(self, share: dict[str, Any]) -> TlaSession:
        dev_confirm_raw = (share.get("dev_confirm") or "") or ""
        dev_confirm = dev_confirm_raw.lower()
        if dev_confirm != (self._expected_dev_confirm or "").lower():
            raise KasaException("SPAKE2+ confirmation mismatch")
        if self._use_dac_certification():
            self._verify_dac(share)
        session_id = share.get("sessionId") or share.get("stok") or ""
        start_seq = int(share.get("start_seq") or 1)
        if not session_id:
            _LOGGER.error("SPAKE2+: Missing session ID from device")
            raise KasaException("Missing session fields from device")
        cipher = _SessionCipher.from_shared_key(
            self._chosen_cipher, self._shared_key or b"", hkdf_hash=self._hkdf_hash
        )
        return TlaSession(
            sessionId=session_id,
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
        if self._cached_session is not None:
            self._session_id = self._cached_session.sessionId
            self._seq = self._cached_session.startSequence
            self._cipher = self._cached_session.sessionCipher
            self._ds_url = URL(
                f"{str(self._transport._app_url)}/stok={self._session_id}/ds"
            )

    async def _discover(self) -> None:
        body = {"method": "login", "params": {"sub_method": "discover"}}
        status, data = await self._transport._http_client.post(
            self._transport._app_url.with_path("/"),
            json=body,
            headers=self._transport.COMMON_HEADERS,
            ssl=await self._transport.get_ssl_context(),
        )
        if status != 200:
            raise KasaException(
                f"{self._transport._host} _discover failed status: {status}"
            )
        response: dict[str, Any] = cast(dict, data)
        self.handle_response_error_code(response, "_discover failed")
        result = response["result"]
        self._device_mac = result.get("mac")
        tpap = result["tpap"]
        self._tpap_noc = bool(tpap.get("noc"))
        self._tpap_dac = bool(tpap.get("dac"))
        self._tpap_tls = tpap.get("tls")
        self._tpap_pake = tpap.get("pake") or []

    def handle_response_error_code(self, response: dict[str, Any], msg: str) -> None:
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
        context_classes: list[type[NocAuthContext | Spake2pAuthContext]] = []
        if self._tpap_noc:
            context_classes.append(NocAuthContext)
        context_classes.append(Spake2pAuthContext)
        last_exc: Exception | None = None
        for ctx_cls in context_classes:
            try:
                auth_ctx = ctx_cls(self)
                session = await auth_ctx.start()
                if isinstance(session, TlaSession):
                    self._cached_session = session
                    self._set_session_from_tla()
                    self._transport._state = TransportState.ESTABLISHED
                    _LOGGER.debug(
                        "Authenticator: established session via %s",
                        session.sessionType,
                    )
                    return
            except Exception as exc:
                last_exc = exc
                _LOGGER.debug(
                    "Authenticator: %s attempt failed",
                    ctx_cls.__name__,
                    exc_info=True,
                )
        if last_exc is not None:
            raise KasaException(
                "Authenticator: failed to establish session via NOC or SPAKE2+ with "
                f"{self._transport._host}"
            ) from last_exc


class TpapTransport(BaseTransport):
    """Transport implementing the TPAP encrypted DS channel."""

    DEFAULT_PORT: int = 80
    DEFAULT_HTTPS_PORT: int = 4433
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
        protocol = "https" if config.connection_type.https else "http"
        self._app_url = URL(f"{protocol}://{self._host}:{self._port}")
        self._authenticator = Authenticator(self)
        self._send_lock: asyncio.Lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        config = self._config
        if port := config.connection_type.http_port:
            return port
        if config.connection_type.https:
            return self.DEFAULT_HTTPS_PORT
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """Return a stable hash of credentials if available, else None."""
        return self._config.credentials_hash

    async def get_ssl_context(self) -> ssl.SSLContext | bool:
        """Get or create SSL context as configured by device (TLS mode)."""
        if not self._ssl_context:
            self._ssl_context = await self._loop.run_in_executor(
                None, self._create_ssl_context
            )
        return self._ssl_context

    def _create_ssl_context(self) -> ssl.SSLContext | bool:
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
                ds_url, data=payload, headers=headers, ssl=await self.get_ssl_context()
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
            self._authenticator.handle_response_error_code(
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
