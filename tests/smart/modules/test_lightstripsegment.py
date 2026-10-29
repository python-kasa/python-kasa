import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules.lightstripsegment import SEGMENTS_MAX, SEGMENTS_MIN

from ...device_fixtures import parametrize

segment = parametrize(
    "has segment", component_filter="segment", protocol_filter={"SMART"}
)


@segment
async def test_feature(dev: SmartDevice) -> None:
    """Test that the strip length feature is registered and reads the device value."""
    segment_module = dev.modules[Module.LightStripSegment]

    feat = dev.features["strip_segments"]
    assert feat.value == segment_module.segments
    assert isinstance(feat.value, int)
    assert (feat.minimum_value, feat.maximum_value) == (SEGMENTS_MIN, SEGMENTS_MAX)


@segment
async def test_set_segments(dev: SmartDevice, mocker: MockerFixture) -> None:
    """Test that setting the length calls the device with the right payload."""
    segment_module = dev.modules[Module.LightStripSegment]
    call_spy = mocker.spy(segment_module, "call")

    await segment_module.set_segments(47)

    call_spy.assert_called_once_with("set_device_segment", {"segment": 47})


@segment
@pytest.mark.parametrize("value", [SEGMENTS_MIN - 1, SEGMENTS_MAX + 1, 1.5, "47"])
async def test_set_segments_out_of_range(dev: SmartDevice, value: object) -> None:
    """Test that invalid lengths are rejected before reaching the device."""
    segment_module = dev.modules[Module.LightStripSegment]

    with pytest.raises(ValueError, match="Invalid segment count"):
        await segment_module.set_segments(value)  # type: ignore[arg-type]


@segment
async def test_set_segments_via_feature(
    dev: SmartDevice, mocker: MockerFixture
) -> None:
    """Test that the feature setter reaches the module."""
    segment_module = dev.modules[Module.LightStripSegment]
    call_spy = mocker.spy(segment_module, "call")

    await dev.features["strip_segments"].set_value(SEGMENTS_MAX)

    call_spy.assert_called_once_with("set_device_segment", {"segment": SEGMENTS_MAX})
