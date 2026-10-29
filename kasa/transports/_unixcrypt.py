"""MD5-crypt and SHA-256-crypt password hashes, as made by glibc's crypt().

TPAP devices can ask for the password as one of these hashes
(``password_shadow`` with ``passwd_id`` 1 or 5).

MD5-crypt is Poul-Henning Kamp's ``$1$`` scheme. SHA-256-crypt follows
Ulrich Drepper's specification, https://www.akkadia.org/drepper/SHA-crypt.txt:
without a round count it uses 5000 rounds and leaves them out of the result,
and a given round count is clamped to 1000-999999999 and kept in the result.
"""

from __future__ import annotations

import hashlib

_ITOA64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

_SHA256_DEFAULT_ROUNDS = 5000
_SHA256_MIN_ROUNDS = 1000
_SHA256_MAX_ROUNDS = 999_999_999

# Byte order of the final digest in the encoded hash, three bytes per group
_MD5_ORDER = ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5))
_SHA256_ORDER = (
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


def _b64_from_24bit(byte2: int, byte1: int, byte0: int, chars: int) -> str:
    value = (byte2 << 16) | (byte1 << 8) | byte0
    out = []
    for _ in range(chars):
        out.append(_ITOA64[value & 0x3F])
        value >>= 6
    return "".join(out)


def _repeat_to(digest: bytes, length: int) -> bytes:
    return (digest * (length // len(digest) + 1))[:length]


def md5_crypt(password: bytes, salt: bytes) -> str:
    """Return the ``$1$`` hash of the password with up to 8 bytes of salt."""
    salt = salt[:8]
    alternate = hashlib.md5(password + salt + password).digest()  # noqa: S324
    context = password + b"$1$" + salt + _repeat_to(alternate, len(password))
    length = len(password)
    while length:
        context += b"\x00" if length & 1 else password[:1]
        length >>= 1
    final = hashlib.md5(context).digest()  # noqa: S324

    for round_ in range(1000):
        context = password if round_ & 1 else final
        if round_ % 3:
            context += salt
        if round_ % 7:
            context += password
        context += final if round_ & 1 else password
        final = hashlib.md5(context).digest()  # noqa: S324

    encoded = "".join(
        _b64_from_24bit(final[a], final[b], final[c], 4) for a, b, c in _MD5_ORDER
    ) + _b64_from_24bit(0, 0, final[11], 2)
    return f"$1${salt.decode('latin-1')}${encoded}"


def sha256_crypt(password: bytes, salt: bytes, rounds: int | None = None) -> str:
    """Return the ``$5$`` hash of the password with up to 16 bytes of salt."""
    salt = salt[:16]
    if rounds is None:
        rounds_prefix = ""
        rounds = _SHA256_DEFAULT_ROUNDS
    else:
        rounds = max(_SHA256_MIN_ROUNDS, min(_SHA256_MAX_ROUNDS, rounds))
        rounds_prefix = f"rounds={rounds}$"

    alternate = hashlib.sha256(password + salt + password).digest()
    context = hashlib.sha256(password + salt + _repeat_to(alternate, len(password)))
    length = len(password)
    while length:
        context.update(alternate if length & 1 else password)
        length >>= 1
    digest_a = context.digest()

    p_bytes = _repeat_to(
        hashlib.sha256(password * len(password)).digest(), len(password)
    )
    s_bytes = _repeat_to(hashlib.sha256(salt * (16 + digest_a[0])).digest(), len(salt))

    final = digest_a
    for round_ in range(rounds):
        data = p_bytes if round_ & 1 else final
        if round_ % 3:
            data += s_bytes
        if round_ % 7:
            data += p_bytes
        data += final if round_ & 1 else p_bytes
        final = hashlib.sha256(data).digest()

    encoded = "".join(
        _b64_from_24bit(final[a], final[b], final[c], 4) for a, b, c in _SHA256_ORDER
    ) + _b64_from_24bit(0, final[31], final[30], 3)
    return f"$5${rounds_prefix}{salt.decode('latin-1')}${encoded}"
