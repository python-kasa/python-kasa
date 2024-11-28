"""Tests for smart camera devices."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory

from kasa import Credentials, Device, DeviceType, Module, StreamResolution

from ..conftest import camera_smartcam, device_smartcam, hub_smartcam


@device_smartcam
async def test_state(dev: Device):
    if dev.device_type is DeviceType.Hub:
        pytest.skip("Hubs cannot be switched on and off")

    state = dev.is_on
    await dev.set_state(not state)
    await dev.update()
    assert dev.is_on is not state


@camera_smartcam
async def test_stream_rtsp_url(dev: Device):
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


@device_smartcam
async def test_alias(dev):
    test_alias = "TEST1234"
    original = dev.alias

    assert isinstance(original, str)
    await dev.set_alias(test_alias)
    await dev.update()
    assert dev.alias == test_alias

    await dev.set_alias(original)
    await dev.update()
    assert dev.alias == original


@hub_smartcam
async def test_hub(dev):
    assert dev.children
    for child in dev.children:
        assert "Cloud" in child.modules
        assert child.modules["Cloud"].data
        assert child.alias
        await child.update()
        assert "Time" not in child.modules
        assert child.time


@device_smartcam
async def test_device_time(dev: Device, freezer: FrozenDateTimeFactory):
    """Test a child device gets the time from it's parent module."""
    fallback_time = datetime.now(UTC).astimezone().replace(microsecond=0)
    assert dev.time != fallback_time
    module = dev.modules[Module.Time]
    await module.set_time(fallback_time)
    await dev.update()
    assert dev.time == fallback_time
