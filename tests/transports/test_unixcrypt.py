"""Tests for the glibc-compatible crypt() hashes used by TPAP."""

from __future__ import annotations

import pytest

from kasa.transports._unixcrypt import md5_crypt, sha256_crypt


# The test vectors of https://www.akkadia.org/drepper/SHA-crypt.txt,
# also produced by `openssl passwd -5`.
@pytest.mark.parametrize(
    ("password", "salt", "rounds", "expected"),
    [
        pytest.param(
            "Hello world!",
            "saltstring",
            None,
            "$5$saltstring$5B8vYYiY.CVt1RlTTf8KbXBH3hsxY/GNooZaBBGWEc5",
            id="default-rounds",
        ),
        pytest.param(
            "Hello world!",
            "saltstringsaltstring",
            10000,
            "$5$rounds=10000$saltstringsaltst$3xv.VbSHBb41AL9AvLeujZkZRBAwqFMz2.opqey6IcA",
            id="rounds-10000",
        ),
        pytest.param(
            "This is just a test",
            "toolongsaltstring",
            5000,
            "$5$rounds=5000$toolongsaltstrin$Un/5jzAHMgOGZ5.mWJpuVolil07guHPvOW8mGRcvxa5",
            id="explicit-default-rounds-kept",
        ),
        pytest.param(
            "a very much longer text to encrypt.  "
            "This one even stretches over morethan one line.",
            "anotherlongsaltstring",
            1400,
            "$5$rounds=1400$anotherlongsalts$Rx.j8H.h8HjEDGomFU8bDkXm3XIUnzyxf12oP84Bnq1",
            id="long-password",
        ),
        pytest.param(
            "we have a short salt string but not a short password",
            "short",
            77777,
            "$5$rounds=77777$short$JiO1O3ZpDAxGJeaDIuqCoEFysAe1mZNJRs3pw0KQRd/",
            id="short-salt",
        ),
        pytest.param(
            "a short string",
            "asaltof16chars..",
            123456,
            "$5$rounds=123456$asaltof16chars..$gP3VQ/6X7UUEW3HkBn2w1/Ptq2jxPyzV/cZKmF/wJvD",
            id="16-char-salt",
        ),
        pytest.param(
            "the minimum number is still observed",
            "roundstoolow",
            10,
            "$5$rounds=1000$roundstoolow$yfvwcWrQ8l/K0DAWyuPMDNHpIVlTQebY9l/gL972bIC",
            id="rounds-below-minimum",
        ),
    ],
)
def test_sha256_crypt(
    password: str, salt: str, rounds: int | None, expected: str
) -> None:
    assert sha256_crypt(password.encode(), salt.encode(), rounds) == expected


# Produced by `openssl passwd -1`.
@pytest.mark.parametrize(
    ("password", "salt", "expected"),
    [
        pytest.param("pass", "saltsalt", "$1$saltsalt$hZR.9zfJXcVTsa9iTxnQR1", id="8"),
        pytest.param("pass", "salt", "$1$salt$M6xQvx9eSlM4zTu69di5B/", id="short"),
        pytest.param(
            "correct horse battery staple",
            "longersaltstring",
            "$1$longersa$COeekwSWUn4OO9X02U7s21",
            id="salt-truncated",
        ),
        pytest.param("", "TFsy6I", "$1$TFsy6I$uDeFAJQ.oIhIuUsAK14Zf1", id="empty"),
    ],
)
def test_md5_crypt(password: str, salt: str, expected: str) -> None:
    assert md5_crypt(password.encode(), salt.encode()) == expected
