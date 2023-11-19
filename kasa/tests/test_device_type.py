import inspect
from datetime import datetime
from unittest.mock import patch

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

import kasa
from kasa import Credentials, SmartDevice, SmartDeviceException
from kasa.smartdevice import DeviceType
from kasa.smartstrip import SmartStripPlug

from .conftest import handle_turn_on, has_emeter, no_emeter, turn_on
from .newfakes import PLUG_SCHEMA, TZ_SCHEMA, FakeTransportProtocol


async def test_device_type_from_value():
    """Make sure that every device type can be created from its value."""
    for name in DeviceType:
        assert DeviceType.from_value(name.value) is not None

    assert DeviceType.from_value("nonexistent") is DeviceType.Unknown
    assert DeviceType.from_value("plug") is DeviceType.Plug
    assert DeviceType.Plug.value == "plug"

    assert DeviceType.from_value("bulb") is DeviceType.Bulb
    assert DeviceType.Bulb.value == "bulb"

    assert DeviceType.from_value("dimmer") is DeviceType.Dimmer
    assert DeviceType.Dimmer.value == "dimmer"

    assert DeviceType.from_value("strip") is DeviceType.Strip
    assert DeviceType.Strip.value == "strip"

    assert DeviceType.from_value("lightstrip") is DeviceType.LightStrip
    assert DeviceType.LightStrip.value == "lightstrip"
