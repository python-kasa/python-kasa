"""Client for the local media protocol of Tapo cameras.

Cameras expose a second HTTP server, separate from the management API, that
carries audio and video as multipart streams of MPEG-TS packets. Only the
speaker (talkback) direction is implemented: already encoded G.711 A-law
(PCMA) 8 kHz mono audio is sent to the camera in real time.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import time
from asyncio import timeout as asyncio_timeout
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
)
from contextlib import contextmanager
from typing import Any

from ..exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
)
from ..exceptions import TimeoutError as KasaTimeoutError
from ..json import loads as json_loads
from ._mpegts import _PcmaTsMuxer

_LOGGER = logging.getLogger(__name__)

MEDIA_PORT = 8800

_USERNAME = "admin"
_URI = "/stream"
_CLIENT_BOUNDARY = b"--client-stream-boundary--"
_DEVICE_BOUNDARY = b"--device-stream-boundary--"
_TALK_REQUEST = (
    b'{"params":{"talk":{"mode":"aec"},"method":"get"},"seq":3,"type":"request"}'
)

#: Encoded bytes per second of G.711 A-law 8 kHz mono audio
_BYTES_PER_SECOND = 8000
#: Audio sent per multipart part, 20 ms
_FRAME_SIZE = 160
#: Lateness after which the schedule restarts instead of catching up
_MAX_LATENESS = 0.1

_CHALLENGE_PARAM = re.compile(r'(\w+)=(?:"([^"]*)"|([^\s,]*))')


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()  # noqa: S324


def _parse_challenge(header: str) -> dict[str, str]:
    """Parse a Digest WWW-Authenticate header supported by the camera."""
    scheme, _, params = header.partition(" ")
    challenge = {
        key.lower(): quoted or token
        for key, quoted, token in _CHALLENGE_PARAM.findall(params)
    }
    qop = {option.strip() for option in challenge.get("qop", "").split(",")}
    if (
        scheme.lower() != "digest"
        or not challenge.get("realm")
        or not challenge.get("nonce")
        or "auth" not in qop
        or challenge.get("algorithm", "MD5").upper() != "MD5"
    ):
        raise KasaException("Unsupported media authentication challenge")
    return challenge


def _digest_password(cloud_password: str, encrypt_type: str | None) -> str:
    """Return the camera media password derived from the cloud password."""
    hash_func = hashlib.sha256 if encrypt_type == "3" else hashlib.md5
    return hash_func(cloud_password.encode()).hexdigest().upper()


def _authorization(challenge: dict[str, str], password: str, cnonce: str) -> str:
    """Return the Digest Authorization header value for the stream request."""
    realm, nonce, nc = challenge["realm"], challenge["nonce"], "00000001"
    ha1 = _md5_hex(f"{_USERNAME}:{realm}:{password}")
    ha2 = _md5_hex(f"POST:{_URI}")
    response = _md5_hex(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}")
    header = (
        f'Digest username="{_USERNAME}", realm="{realm}", nonce="{nonce}", '
        f'uri="{_URI}", qop=auth, nc={nc}, cnonce="{cnonce}", '
        f'response="{response}"'
    )
    if opaque := challenge.get("opaque"):
        header += f', opaque="{opaque}"'
    return header


def _parse_headers(lines: Iterable[str]) -> dict[str, str]:
    headers = {}
    for line in lines:
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    return headers


async def _frames(audio: AsyncIterable[bytes]) -> AsyncIterator[bytes]:
    """Regroup chunks of any size into frames of _FRAME_SIZE bytes."""
    buffer = bytearray()
    async for chunk in audio:
        buffer += chunk
        while len(buffer) >= _FRAME_SIZE:
            yield bytes(buffer[:_FRAME_SIZE])
            del buffer[:_FRAME_SIZE]
    if buffer:
        yield bytes(buffer)


def _part(headers: dict[str, str], body: bytes) -> bytes:
    lines = [b"--" + _CLIENT_BOUNDARY]
    lines += [f"{key}: {value}".encode() for key, value in headers.items()]
    lines += [f"Content-Length: {len(body)}".encode(), b""]
    return b"\r\n".join(lines) + b"\r\n" + body


class _TalkSession:
    """Speaker session on the camera media port, opened as a context manager."""

    def __init__(
        self,
        host: str,
        cloud_password: str,
        *,
        timeout: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self._host = host
        self._cloud_password = cloud_password
        self._timeout = timeout
        self._clock = clock
        self._sleep = sleep
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._session_id: str | None = None
        self._finished = False

    @property
    def session_id(self) -> str | None:
        """Return the talk session id assigned by the camera."""
        return self._session_id

    async def __aenter__(self) -> _TalkSession:
        try:
            await self.open()
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    @contextmanager
    def _media_errors(self, action: str) -> Iterator[None]:
        try:
            yield
        except TimeoutError as ex:
            raise KasaTimeoutError(
                f"Timeout {action} talk session with {self._host}:{MEDIA_PORT}"
            ) from ex
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as ex:
            raise KasaException(
                f"Error {action} talk session with {self._host}:{MEDIA_PORT}: {ex!r}"
            ) from ex

    async def open(self) -> None:
        """Connect, authenticate and start a talk session."""
        _LOGGER.debug("Opening talk session with %s:%s", self._host, MEDIA_PORT)
        with self._media_errors("opening"):
            async with asyncio_timeout(self._timeout):
                self._reader, self._writer = await asyncio.open_connection(
                    self._host, MEDIA_PORT
                )
                await self._authenticate()
                self._session_id = await self._start_talk()
        _LOGGER.debug("Talk session %s started on %s", self._session_id, self._host)

    async def _authenticate(self) -> None:
        assert self._writer  # noqa: S101
        request = (
            f"POST {_URI} HTTP/1.1\r\n"
            f"Host: {self._host}:{MEDIA_PORT}\r\n"
            f"Content-Type: multipart/mixed; boundary={_CLIENT_BOUNDARY.decode()}\r\n"
            "Content-Length: 0\r\n"
        )
        self._writer.write(f"{request}\r\n".encode())
        status, headers = await self._read_response()
        if status != 401 or "www-authenticate" not in headers:
            raise KasaException(
                f"Unexpected media response from {self._host}: HTTP {status}"
            )
        challenge = _parse_challenge(headers["www-authenticate"])
        password = _digest_password(self._cloud_password, challenge.get("encrypt_type"))
        authorization = _authorization(challenge, password, secrets.token_hex(16))
        self._writer.write(f"{request}Authorization: {authorization}\r\n\r\n".encode())
        status, _ = await self._read_response()
        if status == 401:
            raise AuthenticationError(
                f"Media authentication failed for {self._host}, check credentials"
            )
        if status != 200:
            raise KasaException(
                f"Unexpected media response from {self._host}: HTTP {status}"
            )

    async def _read_response(self) -> tuple[int, dict[str, str]]:
        assert self._reader  # noqa: S101
        head = await self._reader.readuntil(b"\r\n\r\n")
        status_line, *header_lines = head.decode("latin-1").split("\r\n")
        version, _, rest = status_line.partition(" ")
        status = rest.partition(" ")[0]
        headers = _parse_headers(header_lines)
        length = headers.get("content-length", "0")
        if not (version.startswith("HTTP/") and status.isdigit() and length.isdigit()):
            raise KasaException(f"Invalid media response from {self._host}")
        await self._reader.readexactly(int(length))
        return int(status), headers

    async def _start_talk(self) -> str:
        assert self._reader  # noqa: S101
        assert self._writer  # noqa: S101
        self._writer.write(
            _part({"Content-Type": "application/json"}, _TALK_REQUEST) + b"\r\n"
        )
        await self._writer.drain()

        invalid = KasaException(f"Invalid talk session response from {self._host}")
        boundary = b"--" + _DEVICE_BOUNDARY
        while (line := (await self._reader.readline()).rstrip(b"\r\n")) != boundary:
            if line or self._reader.at_eof():
                raise invalid
        lines = []
        while line := (await self._reader.readline()).rstrip(b"\r\n"):
            lines.append(line.decode("latin-1"))
        headers = _parse_headers(lines)
        if not (length := headers.get("content-length", "")).isdigit():
            raise invalid
        try:
            response = json_loads(await self._reader.readexactly(int(length)))
        except ValueError as ex:
            raise invalid from ex
        params = response.get("params") if isinstance(response, dict) else None
        if not isinstance(params, dict):
            raise invalid
        if code := params.get("error_code"):
            try:
                error_code: SmartErrorCode | None = SmartErrorCode.from_int(code)
            except ValueError:
                error_code = None
            raise DeviceError(
                f"Camera {self._host} rejected the talk session: {code}",
                error_code=error_code,
            )
        if not (session_id := params.get("session_id")):
            raise invalid
        return str(session_id)

    async def stream(self, audio: AsyncIterable[bytes]) -> None:
        """Send the audio to the speaker in real time until the input ends.

        Returns once the last sent audio is expected to have been played.
        """
        muxer = _PcmaTsMuxer()
        await self._send(muxer.header())

        due: float | None = None
        async for frame in _frames(audio):
            now = self._clock()
            if due is None or now - due > _MAX_LATENESS:
                # First audio or the producer stalled: restart the schedule
                # rather than bursting the backlog, which the camera drops.
                due = now
            await self._wait_until(due)
            await self._send(muxer.audio(frame))
            due += len(frame) / _BYTES_PER_SECOND
        if due is not None:
            await self._wait_until(due)
        self._finished = True

    async def _wait_until(self, deadline: float) -> None:
        if (delay := deadline - self._clock()) > 0:
            await self._sleep(delay)

    async def _send(self, body: bytes) -> None:
        assert self._writer  # noqa: S101
        part = _part(
            {
                "Content-Type": "audio/mp2t",
                "X-If-Encrypt": "0",
                "X-Session-Id": str(self._session_id),
            },
            body,
        )
        with self._media_errors("writing to"):
            async with asyncio_timeout(self._timeout):
                self._writer.write(part)
                await self._writer.drain()

    async def close(self) -> None:
        """Close the session, dropping unsent audio unless playback completed."""
        writer, self._reader, self._writer = self._writer, None, None
        if writer is None:
            return
        if not self._finished:
            writer.transport.abort()
        writer.close()
        try:
            async with asyncio_timeout(self._timeout):
                await writer.wait_closed()
        except Exception:
            writer.transport.abort()
