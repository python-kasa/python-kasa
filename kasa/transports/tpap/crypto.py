"""SPAKE2+ and the password encodings of the TPAP login."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from ecdsa import NIST256p, NIST384p, NIST521p, ellipticcurve
from ecdsa.curves import Curve
from ecdsa.ellipticcurve import CurveFp, PointJacobi

from kasa.exceptions import KasaException

_LOGGER = logging.getLogger(__name__)

PAKE_CONTEXT_TAG = b"PAKE V1"
# The rounds in passwd_prefix come from the unauthenticated pake_register
# reply and are hashed on the event loop; crypt() itself allows up to
# 999,999,999.
MAX_PASSWD_ROUNDS = 100_000


def _md5(data: bytes) -> bytes:
    return hashlib.md5(data).digest()  # noqa: S324


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def md5_hex(value: str) -> str:
    """Return the MD5 of the text as lowercase hex."""
    return _md5(value.encode()).hex()


def sha256_hex_upper(value: str) -> str:
    """Return the SHA-256 of the text as uppercase hex."""
    return _sha256(value.encode()).hex().upper()


def _sha1_hex(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()  # noqa: S324


def _authkey_mask(passcode: str, tmpkey: str, dictionary: str) -> str:
    masked = []
    max_length = max(len(tmpkey), len(passcode))
    for index in range(max_length):
        lhs = ord(passcode[index]) if index < len(passcode) else 0xBB
        rhs = ord(tmpkey[index]) if index < len(tmpkey) else 0xBB
        masked.append(dictionary[(lhs ^ rhs) % len(dictionary)])
    return "".join(masked)


def _sha1_username_mac_shadow(username: str, mac12hex: str, password: str) -> str:
    if (
        not username
        or len(mac12hex) != 12
        or not all(char in "0123456789abcdefABCDEF" for char in mac12hex)
    ):
        return password

    mac = ":".join(mac12hex[index : index + 2] for index in range(0, 12, 2)).upper()
    return _sha1_hex(md5_hex(username) + "_" + mac)


def _crypt_repeat(data: bytes, length: int) -> bytes:
    return (data * (length // len(data) + 1))[:length]


def _crypt_b64(value: int, length: int) -> str:
    alphabet = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(alphabet[(value >> 6 * index) & 0x3F] for index in range(length))


def _md5_crypt(password: str, prefix: str) -> str | None:
    """Return glibc's crypt() of the password for a ``$1$`` (MD5) prefix."""
    if not prefix or not prefix.startswith("$1$") or len(password) > 30000:
        return None

    salt = prefix[3:].split("$", 1)[0][:8]
    secret, salt_bytes = password.encode(), salt.encode()
    alternate = _md5(secret + salt_bytes + secret)
    data = secret + b"$1$" + salt_bytes + _crypt_repeat(alternate, len(secret))
    length = len(secret)
    while length:
        data += b"\x00" if length & 1 else secret[:1]
        length >>= 1
    final = _md5(data)

    for round_ in range(1000):
        data = secret if round_ & 1 else final
        if round_ % 3:
            data += salt_bytes
        if round_ % 7:
            data += secret
        data += final if round_ & 1 else secret
        final = _md5(data)

    order = ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5))
    encoded = "".join(
        _crypt_b64(final[a] << 16 | final[b] << 8 | final[c], 4) for a, b, c in order
    )
    return f"$1${salt}${encoded}{_crypt_b64(final[11], 2)}"


def _sha256_crypt(password: str, prefix: str) -> str | None:
    """Return glibc's crypt() of the password for a ``$5$`` (SHA-256) prefix.

    Without a round count it uses 5000 rounds and leaves them out of the
    result, see https://www.akkadia.org/drepper/SHA-crypt.txt. Like the app,
    only the prefix sets the rounds; ``passwd_rounds`` is not used.
    """
    if not prefix:
        return None

    default_rounds = 5000
    spec = prefix[3:] if prefix.startswith("$5$") else prefix
    rounds: int | None = None

    if spec.startswith("rounds="):
        rounds_part, _, spec = spec.partition("$")
        try:
            rounds = int(rounds_part.split("=", 1)[1])
        except ValueError:
            rounds = default_rounds
    salt = spec.split("$", 1)[0][:16]

    if rounds is not None and rounds > MAX_PASSWD_ROUNDS:
        raise KasaException(
            f"TPAP register response has too many passwd_prefix rounds: {rounds}"
        )
    rounds_spec = ""
    if rounds is not None:
        rounds = max(1000, rounds)
        rounds_spec = f"rounds={rounds}$"

    secret, salt_bytes = password.encode(), salt.encode()
    alternate = _sha256(secret + salt_bytes + secret)
    data = secret + salt_bytes + _crypt_repeat(alternate, len(secret))
    length = len(secret)
    while length:
        data += alternate if length & 1 else secret
        length >>= 1
    final = _sha256(data)
    p_bytes = _crypt_repeat(_sha256(secret * len(secret)), len(secret))
    s_bytes = _crypt_repeat(_sha256(salt_bytes * (16 + final[0])), len(salt_bytes))

    for round_ in range(rounds or default_rounds):
        data = p_bytes if round_ & 1 else final
        if round_ % 3:
            data += s_bytes
        if round_ % 7:
            data += p_bytes
        data += final if round_ & 1 else p_bytes
        final = _sha256(data)

    order = (
        (0, 10, 20),
        (21, 1, 11),
        (12, 22, 2),
        (3, 13, 23),
        (24, 4, 14),
        (15, 25, 5),
        (6, 16, 26),
        (27, 7, 17),
        (18, 28, 8),
        (9, 19, 29),
    )
    encoded = "".join(
        _crypt_b64(final[a] << 16 | final[b] << 8 | final[c], 4) for a, b, c in order
    )
    tail = _crypt_b64(final[31] << 8 | final[30], 3)
    return f"$5${rounds_spec}{salt}${encoded}{tail}"


def build_credentials(
    extra_crypt: dict | None, username: str, passcode: str, mac_no_colon: str
) -> str:
    """Return the passcode encoded as the device's ``extra_crypt`` asks."""
    if not extra_crypt:
        return f"{username}/{passcode}" if username else passcode

    crypt_type = (extra_crypt.get("type") or "").lower()
    params = extra_crypt.get("params")
    if not isinstance(params, dict):
        # Like the app, a type without params falls back to user/password.
        return f"{username}/{passcode}" if username else passcode

    if crypt_type == "password_shadow":
        try:
            passwd_id = int(params.get("passwd_id", 0))
        except (TypeError, ValueError):
            _LOGGER.debug("invalid passwd_id, using passcode")
            return passcode
        prefix = str(params.get("passwd_prefix", "") or "")
        if passwd_id == 1:
            return _md5_crypt(passcode, prefix) or passcode
        if passwd_id == 2:
            return _sha1_hex(passcode)
        if passwd_id == 3:
            return _sha1_username_mac_shadow(username, mac_no_colon, passcode)
        if passwd_id == 5:
            return _sha256_crypt(passcode, prefix) or passcode
        return passcode

    if crypt_type == "password_authkey":
        tmpkey = str(params.get("authkey_tmpkey", "") or "")
        dictionary = str(params.get("authkey_dictionary", "") or "")
        if tmpkey and dictionary:
            return _authkey_mask(passcode, tmpkey, dictionary)
        return passcode

    if crypt_type == "password_sha_with_salt":
        try:
            sha_name = int(params.get("sha_name", -1))
        except (TypeError, ValueError):
            _LOGGER.debug("invalid sha_name, using passcode")
            return passcode
        sha_salt_b64 = str(params.get("sha_salt", "") or "")
        username_hint = "admin" if sha_name == 0 else "user"
        try:
            decoded_salt = base64.b64decode(sha_salt_b64).decode()
        except Exception:
            _LOGGER.debug("invalid base64 salt, using passcode")
            return passcode
        return _sha256((username_hint + decoded_salt + passcode).encode()).hex()

    return f"{username}/{passcode}" if username else passcode


def mac_pass_from_device_mac(mac_colon: str) -> str:
    """Return the default passcode, derived from the device MAC."""
    mac_hex = mac_colon.replace(":", "").replace("-", "")
    try:
        mac_bytes = bytes.fromhex(mac_hex)
    except ValueError as exc:
        raise KasaException(
            "Invalid device MAC for TPAP default passcode derivation"
        ) from exc
    if len(mac_bytes) < 6:
        raise KasaException(
            "Device MAC is too short for TPAP default passcode derivation"
        )
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


def _suite_hash_name(suite_type: int) -> str:
    return "SHA512" if suite_type in (2, 4, 5, 7, 9) else "SHA256"


def _suite_mac_is_cmac(suite_type: int) -> bool:
    return suite_type in (8, 9)


def _suite_parameters(
    suite_type: int,
) -> tuple[bytes, bytes, Curve, ec.EllipticCurve]:
    if suite_type in (1, 2, 8, 9):
        return (
            bytes.fromhex(
                "02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f"
            ),
            bytes.fromhex(
                "03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49"
            ),
            NIST256p,
            ec.SECP256R1(),
        )
    if suite_type in (3, 4):
        return (
            bytes.fromhex(
                "030ff0895ae5ebf6187080a82d82b42e2765e3b2f8749c7e05eba366434b363d3dc36f15314739074d2eb8613fceec2853"
            ),
            bytes.fromhex(
                "02c72cf2e390853a1c1c4ad816a62fd15824f56078918f43f922ca21518f9c543bb252c5490214cf9aa3f0baab4b665c10"
            ),
            NIST384p,
            ec.SECP384R1(),
        )
    if suite_type == 5:
        return (
            bytes.fromhex(
                "02003f06f38131b2ba2600791e82488e8d20ab889af753a41806c5db18d37d85608cfae06b82e4a72cd744c719193562a653ea1f119eef9356907edc9b56979962d7aa"
            ),
            bytes.fromhex(
                "0200c7924b9ec017f3094562894336a53c50167ba8c5963876880542bc669e494b2532d76c5b53dfb349fdf69154b9e0048c58a42e8ed04cef052a3bc349d95575cd25"
            ),
            NIST521p,
            ec.SECP521R1(),
        )
    raise KasaException(f"Unsupported TPAP suite type: {suite_type}")


def _sec1_to_xy(sec1: bytes, curve: ec.EllipticCurve) -> tuple[int, int]:
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(curve, sec1)
    numbers = public_key.public_numbers()
    return numbers.x, numbers.y


def _xy_to_uncompressed(x: int, y: int, curve: ec.EllipticCurve) -> bytes:
    # ecdsa returns gmpy2.mpz coordinates when gmpy2 is installed, and
    # cryptography accepts only int
    numbers = ec.EllipticCurvePublicNumbers(int(x), int(y), curve)
    public_key = numbers.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )


def _len8le(value: bytes) -> bytes:
    return len(value).to_bytes(8, "little") + value


def _encode_w(value: int, length: int) -> bytes:
    # The app writes w0 at the byte length of the curve order, so a value
    # with leading zero bytes must keep them (BigIntegers.asUnsignedByteArray).
    return value.to_bytes(length, "big")


def _hash(algorithm: str, data: bytes) -> bytes:
    if algorithm.upper() == "SHA512":
        return hashlib.sha512(data).digest()
    return hashlib.sha256(data).digest()


def _hkdf_expand(label: str, prk: bytes, digest_len: int, algorithm: str) -> bytes:
    hkdf_algorithm = (
        hashes.SHA512() if algorithm.upper() == "SHA512" else hashes.SHA256()
    )
    zero_salt = b"\x00" * digest_len
    return HKDF(
        algorithm=hkdf_algorithm,
        length=digest_len,
        salt=zero_salt,
        info=label.encode(),
    ).derive(prk)


def _hmac(algorithm: str, key: bytes, data: bytes) -> bytes:
    digest = hashlib.sha512 if algorithm.upper() == "SHA512" else hashlib.sha256
    return hmac.new(key, data, digest).digest()


def _cmac_aes(key: bytes, data: bytes) -> bytes:
    cmac = CMAC(algorithms.AES(key))
    cmac.update(data)
    return cmac.finalize()


def _pbkdf2_sha256(password: bytes, salt: bytes, iterations: int, length: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, length)


def _derive_ab(
    credentials: bytes, salt: bytes, iterations: int, hash_len: int = 32
) -> tuple[int, int]:
    i_d = hash_len + 8
    derived = _pbkdf2_sha256(credentials, salt, iterations, 2 * i_d)
    return (
        int.from_bytes(derived[:i_d], "big"),
        int.from_bytes(derived[i_d:], "big"),
    )


def spake2p_share(
    credentials: bytes,
    *,
    suite_type: int,
    salt: bytes,
    iterations: int,
    user_random: bytes,
    dev_random: bytes,
    dev_share: bytes,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Return the SPAKE2+ values of the pake_share step.

    That is ``(user_share, user_confirm, dev_confirm, shared_key)``, where
    ``dev_confirm`` is the confirmation the device has to answer with.
    """
    hash_name = _suite_hash_name(suite_type)
    m_comp, n_comp, nist, crypto_curve = _suite_parameters(suite_type)
    curve: CurveFp = nist.curve
    generator: PointJacobi = nist.generator
    # an mpz when gmpy2 is installed; keep the protocol integers plain int
    order = int(generator.order())
    g_point = generator

    m_x, m_y = _sec1_to_xy(m_comp, crypto_curve)
    n_x, n_y = _sec1_to_xy(n_comp, crypto_curve)
    m_point = ellipticcurve.Point(curve, m_x, m_y, order)
    n_point = ellipticcurve.Point(curve, n_x, n_y, order)

    a_value, b_value = _derive_ab(credentials, salt, iterations, 32)
    w_value = a_value % order
    h_value = b_value % order
    x_value = secrets.randbelow(order - 1) + 1

    l_point = x_value * g_point + w_value * m_point
    l_encoded = _xy_to_uncompressed(l_point.x(), l_point.y(), crypto_curve)

    r_x, r_y = _sec1_to_xy(dev_share, crypto_curve)
    r_point = ellipticcurve.Point(curve, r_x, r_y, order)
    r_encoded = _xy_to_uncompressed(r_point.x(), r_point.y(), crypto_curve)

    r_prime = r_point + (-(w_value * n_point))
    z_point = x_value * r_prime
    v_point = (h_value % order) * r_prime

    z_encoded = _xy_to_uncompressed(z_point.x(), z_point.y(), crypto_curve)
    v_encoded = _xy_to_uncompressed(v_point.x(), v_point.y(), crypto_curve)
    m_encoded = _xy_to_uncompressed(m_point.x(), m_point.y(), crypto_curve)
    n_encoded = _xy_to_uncompressed(n_point.x(), n_point.y(), crypto_curve)

    context_hash = _hash(hash_name, PAKE_CONTEXT_TAG + user_random + dev_random)
    w_encoded = _encode_w(w_value, (order.bit_length() + 7) // 8)

    transcript = (
        _len8le(context_hash)
        + _len8le(b"")
        + _len8le(b"")
        + _len8le(m_encoded)
        + _len8le(n_encoded)
        + _len8le(l_encoded)
        + _len8le(r_encoded)
        + _len8le(z_encoded)
        + _len8le(v_encoded)
        + _len8le(w_encoded)
    )

    transcript_hash = _hash(hash_name, transcript)
    digest_len = 64 if hash_name.upper() == "SHA512" else 32
    mac_len = 16 if _suite_mac_is_cmac(suite_type) else 32
    confirmation_keys = _hkdf_expand(
        "ConfirmationKeys", transcript_hash, mac_len * 2, hash_name
    )
    key_confirm_a = confirmation_keys[:mac_len]
    key_confirm_b = confirmation_keys[mac_len : mac_len * 2]
    shared_key = _hkdf_expand("SharedKey", transcript_hash, digest_len, hash_name)

    if _suite_mac_is_cmac(suite_type):
        user_confirm = _cmac_aes(key_confirm_a, r_encoded)
        dev_confirm = _cmac_aes(key_confirm_b, l_encoded)
    else:
        user_confirm = _hmac(hash_name, key_confirm_a, r_encoded)
        dev_confirm = _hmac(hash_name, key_confirm_b, l_encoded)
    return l_encoded, user_confirm, dev_confirm, shared_key
