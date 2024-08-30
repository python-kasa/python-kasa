import pytest

from kasa import Module, SmartDevice
from kasa.tests.device_fixtures import parametrize

motion = parametrize(
    "is motion sensor", model_filter="T100", protocol_filter={"SMART.CHILD"}
)


@motion
@pytest.mark.parametrize(
    ("feature", "type"),
    [
        ("motion_detected", bool),
    ],
)
async def test_motion_features(dev: SmartDevice, feature, type):
    """Test that features are registered and work as expected."""
    motion = dev.modules.get(Module.MotionSensor)
    assert motion is not None

    prop = getattr(motion, feature)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)
