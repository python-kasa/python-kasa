"""Minimal MPEG-TS writer for the Tapo talkback audio stream.

Only the subset needed to carry G.711 A-law (PCMA) 8 kHz mono audio to a
camera speaker is implemented: one program with one audio stream, PAT and PMT
tables, and PES packets carrying a presentation timestamp.
"""

from __future__ import annotations

PACKET_SIZE = 188
SYNC_BYTE = 0x47

PAT_PID = 0x0000
PMT_PID = 0x1000
AUDIO_PID = 0x0100
NO_PCR_PID = 0x1FFF

#: Stream type Tapo cameras use for PCMA audio
STREAM_TYPE_PCMA_TAPO = 0x90
#: PES stream id of the first MPEG audio stream
AUDIO_STREAM_ID = 0xC0

_SAMPLE_RATE = 8000
_PTS_CLOCK = 90000
_PES_HEADER_SIZE = 14
_MAX_PES_PAYLOAD = 0xFFFF - (_PES_HEADER_SIZE - 6)


def _make_crc_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i << 24
        for _ in range(8):
            crc = (crc << 1) ^ 0x04C11DB7 if crc & 0x80000000 else crc << 1
        table.append(crc & 0xFFFFFFFF)
    return table


_CRC_TABLE = _make_crc_table()


def _crc32_mpeg2(data: bytes) -> int:
    """Return the CRC-32/MPEG-2 checksum used by PSI sections."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC_TABLE[(crc >> 24) ^ byte]
    return crc


class _PcmaTsMuxer:
    """Mux PCMA 8 kHz mono audio frames into MPEG-TS packets."""

    def __init__(self) -> None:
        self._counters: dict[int, int] = {}
        self._samples = 0

    def header(self) -> bytes:
        """Return the PAT and PMT packets announcing the audio stream."""
        pat = (
            (1).to_bytes(2)  # program number
            + (0xE000 | PMT_PID).to_bytes(2)
        )
        pmt = (
            (0xE000 | NO_PCR_PID).to_bytes(2)
            + (0xF000).to_bytes(2)  # no program info
            + bytes([STREAM_TYPE_PCMA_TAPO])
            + (0xE000 | AUDIO_PID).to_bytes(2)
            + (0xF000).to_bytes(2)  # no ES info
        )
        return self._psi_packet(PAT_PID, 0x00, pat) + self._psi_packet(
            PMT_PID, 0x02, pmt
        )

    def audio(self, payload: bytes) -> bytes:
        """Return the TS packets carrying one PES packet of PCMA audio."""
        if len(payload) > _MAX_PES_PAYLOAD:
            raise ValueError(f"Audio payload too large: {len(payload)} bytes")

        pts = (self._samples * _PTS_CLOCK // _SAMPLE_RATE) & (2**33 - 1)
        self._samples += len(payload)

        pes = (
            b"\x00\x00\x01"
            + bytes([AUDIO_STREAM_ID])
            + (len(payload) + _PES_HEADER_SIZE - 6).to_bytes(2)
            + b"\x80\x80\x05"  # PTS only
            + bytes(
                [
                    0x21 | ((pts >> 29) & 0x0E),
                    (pts >> 22) & 0xFF,
                    ((pts >> 14) & 0xFE) | 0x01,
                    (pts >> 7) & 0xFF,
                    ((pts << 1) & 0xFE) | 0x01,
                ]
            )
            + payload
        )

        packets = bytearray()
        unit_start = True
        while pes:
            chunk, pes = pes[: PACKET_SIZE - 4], pes[PACKET_SIZE - 4 :]
            packets += self._packet(AUDIO_PID, chunk, unit_start=unit_start)
            unit_start = False
        return bytes(packets)

    def _psi_packet(self, pid: int, table_id: int, data: bytes) -> bytes:
        section_length = 5 + len(data) + 4
        section = (
            bytes([table_id])
            + (0xB000 | section_length).to_bytes(2)
            + (1).to_bytes(2)  # transport stream id / program number
            + b"\xc1"  # version 0, current
            + b"\x00\x00"  # section number, last section number
            + data
        )
        section += _crc32_mpeg2(section).to_bytes(4)
        payload = b"\x00" + section  # pointer field
        return self._packet(pid, payload, unit_start=True, psi=True)

    def _packet(
        self,
        pid: int,
        payload: bytes,
        *,
        unit_start: bool,
        psi: bool = False,
    ) -> bytes:
        counter = self._counters.get(pid, 0)
        self._counters[pid] = (counter + 1) & 0x0F
        header = bytes(
            [
                SYNC_BYTE,
                (0x40 if unit_start else 0x00) | (pid >> 8),
                pid & 0xFF,
            ]
        )
        free = PACKET_SIZE - 4 - len(payload)
        if psi or free == 0:
            # PSI tables are padded after the section with 0xFF bytes.
            return header + bytes([0x10 | counter]) + payload + b"\xff" * free

        # PES packets are padded with an adaptation field before the payload.
        adaptation_length = free - 1
        adaptation = bytes([adaptation_length])
        if adaptation_length:
            adaptation += b"\x00" + b"\xff" * (adaptation_length - 1)
        return header + bytes([0x30 | counter]) + adaptation + payload
