"""Tests for smart camera devices."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture

from kasa import (
    AuthenticationError,
    Credentials,
    Device,
    DeviceType,
    KasaException,
    Module,
    StreamResolution,
)
from kasa.smartcam._mpegts import _PcmaTsMuxer
from kasa.smartcam.media import _TalkSession

from ...conftest import device_smartcam, parametrize
from ..test_media import FakeWriter, _audio_part, _camera

not_child_camera_smartcam = parametrize(
    "not child camera smartcam",
    device_type_filter=[DeviceType.Camera],
    protocol_filter={"SMARTCAM"},
)
audio_camera_smartcam = parametrize(
    "camera with audio",
    component_filter="audio",
    device_type_filter=[DeviceType.Camera, DeviceType.Doorbell],
    protocol_filter={"SMARTCAM"},
)
audio_hub_child = parametrize(
    "hub child with audio",
    component_filter="audio",
    protocol_filter={"SMARTCAM.CHILD"},
)


@device_smartcam
async def test_state(dev: Device) -> None:
    if dev.device_type is DeviceType.Hub:
        pytest.skip("Hubs cannot be switched on and off")

    state = dev.is_on
    await dev.set_state(not state)
    await dev.update()
    assert dev.is_on is not state


@not_child_camera_smartcam
async def test_stream_rtsp_url(dev: Device) -> None:
    camera_module = dev.modules.get(Module.Camera)
    assert camera_module

    await camera_module.set_state(True)
    await dev.update()
    assert camera_module.is_on
    url = camera_module.stream_rtsp_url(Credentials("foo", "bar"))
    assert url == "rtsp://foo:bar@127.0.0.123:554/stream1"

    url = camera_module.stream_rtsp_url(
        Credentials("foo", "bar"), stream_resolution=StreamResolution.HD
    )
    assert url == "rtsp://foo:bar@127.0.0.123:554/stream1"

    url = camera_module.stream_rtsp_url(
        Credentials("foo", "bar"), stream_resolution=StreamResolution.SD
    )
    assert url == "rtsp://foo:bar@127.0.0.123:554/stream2"

    with patch.object(dev.config, "credentials", Credentials("bar", "foo")):
        url = camera_module.stream_rtsp_url()
    assert url == "rtsp://bar:foo@127.0.0.123:554/stream1"

    with patch.object(dev.config, "credentials", Credentials("bar", "")):
        url = camera_module.stream_rtsp_url()
    assert url is None

    with patch.object(dev.config, "credentials", Credentials("", "Foo")):
        url = camera_module.stream_rtsp_url()
    assert url is None

    # Test with credentials_hash
    cred = json.dumps({"un": "bar", "pwd": "foobar"})
    cred_hash = base64.b64encode(cred.encode()).decode()
    with (
        patch.object(dev.config, "credentials", None),
        patch.object(dev.config, "credentials_hash", cred_hash),
    ):
        url = camera_module.stream_rtsp_url()
    assert url == "rtsp://bar:foobar@127.0.0.123:554/stream1"

    # Test with invalid credentials_hash
    with (
        patch.object(dev.config, "credentials", None),
        patch.object(dev.config, "credentials_hash", b"238472871"),
    ):
        url = camera_module.stream_rtsp_url()
    assert url is None

    # Test with no credentials
    with (
        patch.object(dev.config, "credentials", None),
        patch.object(dev.config, "credentials_hash", None),
    ):
        url = camera_module.stream_rtsp_url()
    assert url is None


@not_child_camera_smartcam
async def test_onvif_url(dev: Device) -> None:
    """Test the onvif url."""
    camera_module = dev.modules.get(Module.Camera)
    assert camera_module

    url = camera_module.onvif_url()
    assert url == "http://127.0.0.123:2020/onvif/device_service"


async def _audio(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def _patch_session(mocker: MockerFixture):
    session = mocker.AsyncMock(spec=_TalkSession)
    factory = mocker.patch(
        "kasa.smartcam.modules.camera._TalkSession", return_value=session
    )
    return factory, session


@audio_camera_smartcam
async def test_play_audio(dev: Device, mocker: MockerFixture) -> None:
    camera_module = dev.modules[Module.Camera]
    writer = FakeWriter()
    reader = asyncio.StreamReader()
    reader.feed_data(_camera())
    connect = mocker.patch(
        "asyncio.open_connection", mocker.AsyncMock(return_value=(reader, writer))
    )

    with patch.object(dev.config, "credentials", Credentials("user", "cloud-password")):
        await camera_module.play_audio(_audio())

    connect.assert_awaited_once_with("127.0.0.123", 8800)
    assert writer.data.endswith(_audio_part(_PcmaTsMuxer().header()))
    assert writer.closed
    assert not writer.aborted


@audio_camera_smartcam
async def test_play_audio_session_lifecycle(dev: Device, mocker: MockerFixture) -> None:
    camera_module = dev.modules[Module.Camera]
    factory, session = _patch_session(mocker)
    audio = _audio(b"\xd5")

    with patch.object(dev.config, "credentials", Credentials("user", "secret")):
        await camera_module.play_audio(audio)

    factory.assert_called_once_with("127.0.0.123", "secret", timeout=5)
    session.open.assert_awaited_once()
    session.stream.assert_awaited_once_with(audio)
    session.close.assert_awaited_once()


@audio_camera_smartcam
async def test_play_audio_credentials_hash(dev: Device, mocker: MockerFixture) -> None:
    camera_module = dev.modules[Module.Camera]
    factory, _ = _patch_session(mocker)
    cred_hash = base64.b64encode(json.dumps({"un": "u", "pwd": "hashed"}).encode())

    with (
        patch.object(dev.config, "credentials", None),
        patch.object(dev.config, "credentials_hash", cred_hash.decode()),
        patch.object(dev.config, "timeout", None),
    ):
        await camera_module.play_audio(_audio())

    factory.assert_called_once_with("127.0.0.123", "hashed", timeout=5)


@pytest.mark.parametrize(
    "credentials",
    [pytest.param(None, id="none"), pytest.param(Credentials("user", ""), id="empty")],
)
@audio_camera_smartcam
async def test_play_audio_no_credentials(
    dev: Device, mocker: MockerFixture, credentials: Credentials | None
) -> None:
    camera_module = dev.modules[Module.Camera]
    factory, _ = _patch_session(mocker)

    with (
        patch.object(dev.config, "credentials", credentials),
        patch.object(dev.config, "credentials_hash", None),
        pytest.raises(AuthenticationError),
    ):
        await camera_module.play_audio(_audio())
    factory.assert_not_called()


@audio_camera_smartcam
async def test_play_audio_without_audio_component(
    dev: Device, mocker: MockerFixture
) -> None:
    camera_module = dev.modules[Module.Camera]
    factory, _ = _patch_session(mocker)
    components = {k: v for k, v in dev._components.items() if k != "audio"}  # type: ignore[attr-defined]
    mocker.patch.object(dev, "_components", components)

    with pytest.raises(KasaException, match="does not support audio"):
        await camera_module.play_audio(_audio())
    factory.assert_not_called()


@audio_hub_child
async def test_play_audio_hub_child(dev: Device, mocker: MockerFixture) -> None:
    camera_module = dev.modules.get(Module.Camera)
    if not camera_module:
        pytest.skip("Hub child has no camera module")
    factory, _ = _patch_session(mocker)

    with pytest.raises(KasaException, match="hub child"):
        await camera_module.play_audio(_audio())
    factory.assert_not_called()


@audio_camera_smartcam
async def test_play_audio_concurrent(dev: Device, mocker: MockerFixture) -> None:
    camera_module = dev.modules[Module.Camera]
    _, session = _patch_session(mocker)
    streaming = asyncio.Event()

    async def stream(audio: AsyncIterator[bytes]) -> None:
        streaming.set()
        await asyncio.Event().wait()

    session.stream.side_effect = stream

    with patch.object(dev.config, "credentials", Credentials("user", "secret")):
        first = asyncio.create_task(camera_module.play_audio(_audio()))
        await streaming.wait()
        with pytest.raises(KasaException, match="already active"):
            await camera_module.play_audio(_audio())

        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        session.close.assert_awaited_once()

        session.stream.side_effect = None
        await camera_module.play_audio(_audio())
    assert session.close.await_count == 2


@pytest.mark.parametrize(
    "failing",
    [pytest.param("open", id="open"), pytest.param("stream", id="stream")],
)
@audio_camera_smartcam
async def test_play_audio_failure_cleans_up(
    dev: Device, mocker: MockerFixture, failing: str
) -> None:
    camera_module = dev.modules[Module.Camera]
    _, session = _patch_session(mocker)
    getattr(session, failing).side_effect = KasaException("boom")

    with patch.object(dev.config, "credentials", Credentials("user", "secret")):
        with pytest.raises(KasaException, match="boom"):
            await camera_module.play_audio(_audio())
        session.close.assert_awaited_once()

        getattr(session, failing).side_effect = None
        await camera_module.play_audio(_audio())
    assert session.close.await_count == 2
