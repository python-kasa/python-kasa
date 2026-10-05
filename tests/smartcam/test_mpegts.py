from __future__ import annotations

import pytest

from kasa.smartcam._mpegts import AUDIO_PID, PACKET_SIZE, _crc32_mpeg2, _PcmaTsMuxer


def _packets(data: bytes) -> list[bytes]:
    assert len(data) % PACKET_SIZE == 0
    return [data[i : i + PACKET_SIZE] for i in range(0, len(data), PACKET_SIZE)]


def _pid(packet: bytes) -> int:
    return ((packet[1] & 0x1F) << 8) | packet[2]


def _payload(packet: bytes) -> bytes:
    if packet[3] & 0x20:
        return packet[5 + packet[4] :]
    return packet[4:]


def _section(packet: bytes) -> bytes:
    payload = _payload(packet)
    start = 1 + payload[0]
    length = ((payload[start + 1] & 0x0F) << 8) | payload[start + 2]
    return payload[start : start + 3 + length]


def _pts(header: bytes) -> int:
    return (
        ((header[0] >> 1) & 0x07) << 30
        | header[1] << 22
        | (header[2] >> 1) << 15
        | header[3] << 7
        | header[4] >> 1
    )


def test_crc32_mpeg2():
    assert _crc32_mpeg2(b"123456789") == 0x0376E6E7


def test_header():
    pat, pmt = _packets(_PcmaTsMuxer().header())

    assert pat[:4] == bytes([0x47, 0x40, 0x00, 0x10])
    section = _section(pat)
    assert section[:-4] == bytes.fromhex("00b00d0001c100000001f000")
    assert _crc32_mpeg2(section) == 0
    assert set(pat[4 + 1 + len(section) :]) == {0xFF}

    assert pmt[:4] == bytes([0x47, 0x50, 0x00, 0x10])
    section = _section(pmt)
    assert section[:-4] == bytes.fromhex("02b0120001c10000fffff00090e100f000")
    assert _crc32_mpeg2(section) == 0


@pytest.mark.parametrize("size", [1, 160, 170, 171, 176, 184, 1000, 8000])
def test_audio_roundtrip(size: int):
    payload = bytes(i % 251 for i in range(size))
    packets = _packets(_PcmaTsMuxer().audio(payload))

    assert all(p[0] == 0x47 and _pid(p) == AUDIO_PID for p in packets)
    assert [bool(p[1] & 0x40) for p in packets] == [True] + [False] * (len(packets) - 1)
    assert [p[3] & 0x0F for p in packets] == [i % 16 for i in range(len(packets))]

    pes = b"".join(_payload(p) for p in packets)
    assert pes[:4] == bytes([0x00, 0x00, 0x01, 0xC0])
    assert int.from_bytes(pes[4:6]) == 8 + size
    assert pes[6:9] == bytes([0x80, 0x80, 0x05])
    assert pes[9] & 0xF1 == 0x21
    assert pes[14:] == payload


@pytest.mark.parametrize(
    ("size", "adaptation"),
    [
        pytest.param(160, bytes([9, 0x00]) + b"\xff" * 8, id="stuffed"),
        pytest.param(169, bytes([0]), id="length-only"),
        pytest.param(170, b"", id="none"),
    ],
)
def test_audio_adaptation_field(size: int, adaptation: bytes):
    data = _PcmaTsMuxer().audio(b"\xd5" * size)
    assert len(data) == PACKET_SIZE
    assert data[3] == (0x30 if adaptation else 0x10)
    assert data[4 : 4 + len(adaptation)] == adaptation
    assert data[4 + len(adaptation) : 4 + len(adaptation) + 4] == b"\x00\x00\x01\xc0"


def test_audio_pts_and_continuity():
    muxer = _PcmaTsMuxer()
    frames = [_packets(muxer.audio(b"\xd5" * 160)) for _ in range(20)]

    assert [f[0][3] & 0x0F for f in frames] == [i % 16 for i in range(20)]
    pts = [_pts(_payload(f[0])[9:14]) for f in frames]
    assert pts == [i * 1800 for i in range(20)]


def test_audio_continuity_independent_from_header():
    muxer = _PcmaTsMuxer()
    muxer.header()
    assert muxer.audio(b"\xd5")[3] & 0x0F == 0
    assert _packets(muxer.header())[0][3] & 0x0F == 1


def test_audio_too_large():
    with pytest.raises(ValueError, match="too large"):
        _PcmaTsMuxer().audio(bytes(0xFFFF))
