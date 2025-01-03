"""Tests for smart camera devices."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import pytest

from kasa import Credentials, Device, DeviceType, Module, StreamResolution

from ...conftest import device_smartcam, parametrize

not_child_camera_smartcam = parametrize(
    "not child camera smartcam",
    device_type_filter=[DeviceType.Camera],
    protocol_filter={"SMARTCAM"},
)


@device_smartcam
async def test_state(dev: Device):
    if dev.device_type is DeviceType.Hub:
        pytest.skip("Hubs cannot be switched on and off")

    state = dev.is_on
    await dev.set_state(not state)
    await dev.update()
    assert dev.is_on is not state


@not_child_camera_smartcam
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


@not_child_camera_smartcam
async def test_onvif_url(dev: Device):
    """Test the onvif url."""
    camera_module = dev.modules.get(Module.Camera)
    assert camera_module

    url = camera_module.onvif_url()
    assert url == "http://127.0.0.123:2020/onvif/device_service"
