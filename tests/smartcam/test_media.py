from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from pytest_mock import MockerFixture

from kasa.exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
)
from kasa.exceptions import TimeoutError as KasaTimeoutError
from kasa.smartcam._mpegts import _PcmaTsMuxer
from kasa.smartcam.media import _TalkSession

HOST = "127.0.0.1"
PASSWORD = "cloud-password"  # noqa: S105
CNONCE = "c0ffee"
SESSION_ID = "11"
CHALLENGE = (
    'Digest realm="TP-Link IP-Camera", nonce="abc123", qop="auth", encrypt_type="3"'
)

FIRST_REQUEST = (
    b"POST /stream HTTP/1.1\r\n"
    b"Host: 127.0.0.1:8800\r\n"
    b"Content-Type: multipart/mixed; boundary=--client-stream-boundary--\r\n"
    b"Content-Length: 0\r\n"
    b"\r\n"
)
TALK_REQUEST = (
    b'{"params":{"talk":{"mode":"aec"},"method":"get"},"seq":3,"type":"request"}'
)


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()  # noqa: S324


def _http(
    status: str, headers: dict[str, str] | None = None, body: bytes = b""
) -> bytes:
    lines = [f"HTTP/1.1 {status}"] + [f"{k}: {v}" for k, v in (headers or {}).items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def _device_part(body: bytes, *, length: bool = True) -> bytes:
    headers = b"----device-stream-boundary--\r\nContent-Type: application/json\r\n"
    if length:
        headers += f"Content-Length: {len(body)}\r\n".encode()
    return headers + b"\r\n" + body + b"\r\n"


def _talk_response(params: object) -> bytes:
    return _device_part(
        json.dumps({"type": "response", "seq": 3, "params": params}).encode()
    )


def _camera(
    challenge: str = CHALLENGE,
    *,
    second: bytes | None = None,
    talk: bytes | None = None,
) -> bytes:
    return (
        _http(
            "401 Unauthorized",
            {"WWW-Authenticate": challenge, "Content-Length": "4"},
            b"oops",
        )
        + (second if second is not None else _http("200 OK"))
        + (
            talk
            if talk is not None
            else _talk_response({"error_code": 0, "session_id": SESSION_ID})
        )
    )


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []
        self.blocker: asyncio.Event | None = None

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        if self.blocker:
            await self.blocker.wait()
        self.now += delay
        await asyncio.sleep(0)


class FakeWriter:
    def __init__(self, clock: FakeClock | None = None) -> None:
        self.data = bytearray()
        self.writes: list[tuple[float, bytes]] = []
        self.clock = clock
        self.drain_hook: Callable[[], Awaitable[None]] | None = None
        self.closed = False
        self.aborted = False
        self.wait_closed_error: Exception | None = None
        self.transport = self

    def write(self, data: bytes) -> None:
        self.data += data
        self.writes.append((self.clock.now if self.clock else 0.0, bytes(data)))

    async def drain(self) -> None:
        if self.drain_hook:
            await self.drain_hook()

    def close(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.aborted = True

    async def wait_closed(self) -> None:
        if self.wait_closed_error:
            raise self.wait_closed_error


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def writer(clock: FakeClock) -> FakeWriter:
    return FakeWriter(clock)


def _connect(
    mocker: MockerFixture, writer: FakeWriter, data: bytes, *, eof: bool = True
):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    if eof:
        reader.feed_eof()
    return mocker.patch(
        "asyncio.open_connection", mocker.AsyncMock(return_value=(reader, writer))
    )


def _session(clock: FakeClock, **kwargs) -> _TalkSession:
    return _TalkSession(
        HOST,
        PASSWORD,
        clock=clock.monotonic,
        sleep=clock.sleep,
        cnonce=lambda: CNONCE,
        **kwargs,
    )


def _audio_part(body: bytes) -> bytes:
    return (
        b"----client-stream-boundary--\r\n"
        b"Content-Type: audio/mp2t\r\n"
        b"X-If-Encrypt: 0\r\n"
        b"X-Session-Id: " + SESSION_ID.encode() + b"\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    )


def _audio_writes(writer: FakeWriter) -> list[tuple[float, bytes]]:
    return [(t, d) for t, d in writer.writes if b"audio/mp2t" in d]


async def _chunks(data: bytes, size: int) -> AsyncIterator[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


async def _open(
    mocker: MockerFixture, clock: FakeClock, writer: FakeWriter
) -> _TalkSession:
    _connect(mocker, writer, _camera())
    session = _session(clock)
    await session.open()
    writer.data.clear()
    writer.writes.clear()
    return session


@pytest.mark.parametrize(
    ("encrypt_type", "password_hash"),
    [
        pytest.param(
            ', encrypt_type="3"',
            hashlib.sha256(PASSWORD.encode()).hexdigest().upper(),
            id="sha256",
        ),
        pytest.param(
            "",
            hashlib.md5(PASSWORD.encode()).hexdigest().upper(),  # noqa: S324
            id="md5",
        ),
        pytest.param(
            ', encrypt_type="2"',
            hashlib.md5(PASSWORD.encode()).hexdigest().upper(),  # noqa: S324
            id="md5-explicit",
        ),
    ],
)
async def test_open_digest(mocker, clock, writer, encrypt_type, password_hash):
    challenge = (
        f'Digest realm="TP-Link IP-Camera", nonce="abc123", qop="auth"{encrypt_type}'
    )
    connect = _connect(mocker, writer, _camera(challenge))

    session = _session(clock)
    await session.open()

    connect.assert_awaited_once_with(HOST, 8800)
    ha1 = _md5(f"admin:TP-Link IP-Camera:{password_hash}")
    ha2 = _md5("POST:/stream")
    response = _md5(f"{ha1}:abc123:00000001:{CNONCE}:auth:{ha2}")
    authorization = (
        'Authorization: Digest username="admin", realm="TP-Link IP-Camera", '
        f'nonce="abc123", uri="/stream", qop=auth, nc=00000001, cnonce="{CNONCE}", '
        f'response="{response}"\r\n'
    ).encode()
    second_request = FIRST_REQUEST[:-2] + authorization + b"\r\n"
    talk_part = (
        b"----client-stream-boundary--\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: "
        + str(len(TALK_REQUEST)).encode()
        + b"\r\n\r\n"
        + TALK_REQUEST
        + b"\r\n"
    )
    assert bytes(writer.data) == FIRST_REQUEST + second_request + talk_part
    assert PASSWORD.encode() not in writer.data
    assert password_hash.encode() not in writer.data
    assert session.session_id == SESSION_ID


async def test_open_digest_opaque(mocker, clock, writer):
    _connect(mocker, writer, _camera(CHALLENGE + ', opaque="xyz", algorithm=MD5'))
    await _session(clock).open()
    assert b'response="' in writer.data
    assert b'opaque="xyz"\r\n' in writer.data


async def test_open_digest_without_qop(mocker, clock, writer):
    _connect(mocker, writer, _camera('Digest realm="r", nonce="n"'))
    await _session(clock).open()
    password_hash = hashlib.md5(PASSWORD.encode()).hexdigest().upper()  # noqa: S324
    response = _md5(f"{_md5(f'admin:r:{password_hash}')}:n:{_md5('POST:/stream')}")
    assert f'uri="/stream", response="{response}"\r\n'.encode() in writer.data
    assert b"qop" not in writer.data


@pytest.mark.parametrize(
    "challenge",
    [
        pytest.param('Basic realm="TP-Link IP-Camera"', id="basic"),
        pytest.param('Digest realm="TP-Link IP-Camera"', id="no-nonce"),
        pytest.param('Digest nonce="n"', id="no-realm"),
        pytest.param('Digest realm="r", nonce="n", qop="auth-int"', id="qop"),
        pytest.param('Digest realm="r", nonce="n", algorithm=SHA-256', id="algorithm"),
    ],
)
async def test_open_unsupported_challenge(mocker, clock, writer, challenge):
    _connect(mocker, writer, _camera(challenge))
    session = _session(clock)
    with pytest.raises(KasaException, match="authentication challenge"):
        await session.open()
    assert writer.data == FIRST_REQUEST


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(_http("200 OK"), id="no-auth"),
        pytest.param(_http("401 Unauthorized"), id="no-challenge"),
        pytest.param(b"garbage\r\n\r\n", id="garbage"),
        pytest.param(b"HTTP/1.1 abc\r\n\r\n", id="bad-status"),
        pytest.param(b"HTTP/1.1 401", id="truncated"),
    ],
)
async def test_open_unexpected_first_response(mocker, clock, writer, response):
    _connect(mocker, writer, response)
    with pytest.raises(KasaException):
        await _session(clock).open()


async def test_open_authentication_failure(mocker, clock, writer):
    _connect(
        mocker,
        writer,
        _camera(second=_http("401 Unauthorized", {"WWW-Authenticate": CHALLENGE})),
    )
    with pytest.raises(AuthenticationError):
        await _session(clock).open()


async def test_open_rejected_stream(mocker, clock, writer):
    _connect(mocker, writer, _camera(second=_http("503 Service Unavailable")))
    with pytest.raises(KasaException, match="503") as exc_info:
        await _session(clock).open()
    assert not isinstance(exc_info.value, AuthenticationError)


async def test_open_session_id_int(mocker, clock, writer):
    _connect(
        mocker, writer, _camera(talk=_talk_response({"error_code": 0, "session_id": 7}))
    )
    session = _session(clock)
    await session.open()
    assert session.session_id == "7"


async def test_open_skips_blank_lines(mocker, clock, writer):
    _connect(
        mocker, writer, _camera(talk=b"\r\n" + _talk_response({"session_id": "5"}))
    )
    session = _session(clock)
    await session.open()
    assert session.session_id == "5"


@pytest.mark.parametrize(
    "talk",
    [
        pytest.param(_device_part(b"{not json"), id="malformed"),
        pytest.param(_device_part(b"[]"), id="not-object"),
        pytest.param(_talk_response({"error_code": 0}), id="missing-session-id"),
        pytest.param(_talk_response({"session_id": ""}), id="empty-session-id"),
        pytest.param(_talk_response("oops"), id="params-not-object"),
        pytest.param(_device_part(b"{}", length=False), id="no-content-length"),
        pytest.param(b"unexpected\r\n", id="no-boundary"),
        pytest.param(b"", id="eof"),
    ],
)
async def test_open_malformed_talk_response(mocker, clock, writer, talk):
    _connect(mocker, writer, _camera(talk=talk))
    with pytest.raises(KasaException, match="talk session") as exc_info:
        await _session(clock).open()
    assert not isinstance(exc_info.value, DeviceError)


@pytest.mark.parametrize(
    ("code", "error_code"),
    [
        pytest.param(-40401, SmartErrorCode.SESSION_EXPIRED, id="known"),
        pytest.param(-52405, None, id="unknown"),
    ],
)
async def test_open_rejected_talk_session(mocker, clock, writer, code, error_code):
    _connect(mocker, writer, _camera(talk=_talk_response({"error_code": code})))
    with pytest.raises(DeviceError, match=str(code)) as exc_info:
        await _session(clock).open()
    assert exc_info.value.error_code == error_code


async def test_open_connection_refused(mocker, clock):
    mocker.patch("asyncio.open_connection", side_effect=ConnectionRefusedError)
    with pytest.raises(KasaException, match="talk session"):
        await _session(clock).open()


async def test_open_connect_timeout(mocker, clock):
    mocker.patch("asyncio.open_connection", side_effect=TimeoutError)
    with pytest.raises(KasaTimeoutError):
        await _session(clock).open()


async def test_open_read_timeout(mocker, clock, writer):
    _connect(mocker, writer, b"", eof=False)
    with pytest.raises(KasaTimeoutError):
        await _session(clock, timeout=0.01).open()


async def test_stream_wire_format(mocker, clock, writer):
    session = await _open(mocker, clock, writer)
    await session.stream(_chunks(b"\xd5" * 200, 200))

    muxer = _PcmaTsMuxer()
    assert bytes(writer.data) == (
        _audio_part(muxer.header())
        + _audio_part(muxer.audio(b"\xd5" * 160))
        + _audio_part(muxer.audio(b"\xd5" * 40))
    )


@pytest.mark.parametrize("chunk_size", [1, 159, 160, 161, 1024, 4096, 16384])
async def test_stream_chunk_sizes(mocker, clock, writer, chunk_size):
    audio = bytes(i % 256 for i in range(8000 + 80))
    session = await _open(mocker, clock, writer)
    start = clock.now
    await session.stream(_chunks(audio, chunk_size))

    muxer = _PcmaTsMuxer()
    frames = [audio[i : i + 160] for i in range(0, len(audio), 160)]
    assert bytes(writer.data) == _audio_part(muxer.header()) + b"".join(
        _audio_part(muxer.audio(frame)) for frame in frames
    )
    times = [t - start for t, _ in _audio_writes(writer)]
    assert times == pytest.approx([0.0] + [i * 0.02 for i in range(len(frames))])
    assert clock.now - start == pytest.approx(len(audio) / 8000)


async def test_stream_empty(mocker, clock, writer):
    session = await _open(mocker, clock, writer)
    await session.stream(_chunks(b"", 160))
    assert bytes(writer.data) == _audio_part(_PcmaTsMuxer().header())
    assert clock.sleeps == []


async def test_stream_starts_schedule_on_first_audio(mocker, clock, writer):
    async def delayed() -> AsyncIterator[bytes]:
        clock.now += 3
        yield b"\xd5" * 320

    session = await _open(mocker, clock, writer)
    await session.stream(delayed())
    assert clock.sleeps == pytest.approx([0.02, 0.02])


async def test_stream_reanchors_after_producer_stall(mocker, clock, writer):
    async def stalling() -> AsyncIterator[bytes]:
        yield b"\xd5" * 320
        clock.now += 1
        yield b"\xd5" * 320

    session = await _open(mocker, clock, writer)
    start = clock.now
    await session.stream(stalling())
    times = [t - start for t, _ in _audio_writes(writer)[1:]]
    assert times == pytest.approx([0.0, 0.02, 1.02, 1.04])


async def test_stream_catches_up_small_lateness(mocker, clock, writer):
    async def jittery() -> AsyncIterator[bytes]:
        yield b"\xd5" * 160
        clock.now += 0.05
        yield b"\xd5" * 480

    session = await _open(mocker, clock, writer)
    start = clock.now
    await session.stream(jittery())
    times = [t - start for t, _ in _audio_writes(writer)[1:]]
    assert times == pytest.approx([0.0, 0.05, 0.05, 0.06])


@pytest.mark.parametrize("chunk_size", [160, 1024, 16384])
async def test_stream_backpressure(mocker, clock, writer, chunk_size):
    consumed = 0
    ahead: list[int] = []

    async def producer() -> AsyncIterator[bytes]:
        nonlocal consumed
        for _ in range(4):
            consumed += chunk_size
            yield b"\xd5" * chunk_size

    async def drain() -> None:
        sent = (len(_audio_writes(writer)) - 1) * 160
        ahead.append(consumed - sent)

    session = await _open(mocker, clock, writer)
    writer.drain_hook = drain
    await session.stream(producer())
    assert len(ahead) == 1 + -(-4 * chunk_size // 160)
    assert max(ahead) < chunk_size + 160


async def test_stream_blocked_drain_stops_producer(mocker, clock, writer):
    consumed = 0
    release = asyncio.Event()

    async def producer() -> AsyncIterator[bytes]:
        nonlocal consumed
        for _ in range(100):
            consumed += 1
            yield b"\xd5" * 160

    async def drain() -> None:
        if len(_audio_writes(writer)) >= 3:
            await release.wait()

    session = await _open(mocker, clock, writer)
    writer.drain_hook = drain
    task = asyncio.create_task(session.stream(producer()))
    for _ in range(20):
        await asyncio.sleep(0)
    assert consumed == 2
    release.set()
    await task
    assert consumed == 100


async def test_stream_cancel_during_pacing(mocker, clock, writer):
    session = await _open(mocker, clock, writer)
    clock.blocker = asyncio.Event()
    task = asyncio.create_task(session.stream(_chunks(b"\xd5" * 800, 800)))
    while not clock.sleeps:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await session.close()
    assert writer.aborted
    assert writer.closed


async def test_stream_cancel_during_drain(mocker, clock, writer):
    blocked = asyncio.Event()

    async def drain() -> None:
        blocked.set()
        await asyncio.Event().wait()

    session = await _open(mocker, clock, writer)
    writer.drain_hook = drain
    task = asyncio.create_task(session.stream(_chunks(b"\xd5" * 800, 800)))
    await blocked.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await session.close()
    assert writer.aborted


async def test_stream_producer_error(mocker, clock, writer):
    async def failing() -> AsyncIterator[bytes]:
        yield b"\xd5" * 160
        raise OSError("producer failed")

    session = await _open(mocker, clock, writer)
    with pytest.raises(OSError, match="producer failed") as exc_info:
        await session.stream(failing())
    assert not isinstance(exc_info.value, KasaException)
    await session.close()
    assert writer.aborted


async def test_stream_connection_reset(mocker, clock, writer):
    async def drain() -> None:
        raise ConnectionResetError

    session = await _open(mocker, clock, writer)
    writer.drain_hook = drain
    with pytest.raises(KasaException, match="talk session"):
        await session.stream(_chunks(b"\xd5" * 160, 160))


async def test_stream_write_timeout(mocker, clock, writer):
    async def drain() -> None:
        await asyncio.Event().wait()

    _connect(mocker, writer, _camera())
    session = _session(clock, timeout=0.01)
    await session.open()
    writer.drain_hook = drain
    with pytest.raises(KasaTimeoutError):
        await session.stream(_chunks(b"\xd5" * 160, 160))


async def test_stream_requires_open(clock):
    with pytest.raises(KasaException, match="not open"):
        await _session(clock).stream(_chunks(b"\xd5", 1))


async def test_close_after_completion_is_graceful(mocker, clock, writer):
    session = await _open(mocker, clock, writer)
    await session.stream(_chunks(b"\xd5" * 160, 160))
    await session.close()
    assert writer.closed
    assert not writer.aborted


async def test_close_aborts_when_wait_closed_fails(mocker, clock, writer):
    session = await _open(mocker, clock, writer)
    await session.stream(_chunks(b"\xd5" * 160, 160))
    writer.wait_closed_error = ConnectionResetError()
    await session.close()
    assert writer.aborted


async def test_close_is_idempotent(mocker, clock, writer):
    await _session(clock).close()
    session = await _open(mocker, clock, writer)
    await session.close()
    writer.closed = False
    await session.close()
    assert not writer.closed
