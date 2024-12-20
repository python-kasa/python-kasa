from kasa.device_type import DeviceType


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
