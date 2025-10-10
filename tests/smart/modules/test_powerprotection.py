import pytest
from pytest_mock import MockerFixture

from kasa import Device, Module

from ...device_fixtures import get_parent_and_child_modules, parametrize

powerprotection = parametrize(
    "has powerprotection",
    component_filter="power_protection",
    protocol_filter={"SMART"},
)


@powerprotection
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("overloaded", "overloaded", bool),
        ("power_protection_threshold", "protection_threshold", int),
    ],
)
async def test_features(dev, feature, prop_name, type):
    """Test that features are registered and work as expected."""
    powerprot = next(get_parent_and_child_modules(dev, Module.PowerProtection))
    assert powerprot
    device = powerprot._device

    prop = getattr(powerprot, prop_name)
    assert isinstance(prop, type)

    feat = device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@powerprotection
async def test_set_enable(dev: Device, mocker: MockerFixture):
    """Test enable."""
    powerprot = next(get_parent_and_child_modules(dev, Module.PowerProtection))
    assert powerprot
    device = powerprot._device

    original_enabled = powerprot.enabled
    original_threshold = powerprot.protection_threshold

    try:
        # Simple enable with an existing threshold
        call_spy = mocker.spy(powerprot, "call")
        await powerprot.set_enabled(True)

        args, kwargs = call_spy.call_args
        method, params = args
        assert method == "set_protection_power"

        enabled_key = next(
            k for k in powerprot.data["get_protection_power"] if "enabled" in k
        )
        assert params[enabled_key] is True
        assert params["protection_power"] is not None

        # Enable with no threshold param when 0
        call_spy.reset_mock()
        await powerprot.set_protection_threshold(0)
        await device.update()
        await powerprot.set_enabled(True)

        args, kwargs = call_spy.call_args
        method, params = args
        assert method == "set_protection_power"
        assert "enabled" in params or "protection_enabled" in params
        assert params["protection_power"] == int(powerprot._max_power / 2)

        # Enable false should not update the threshold
        call_spy.reset_mock()
        await powerprot.set_protection_threshold(0)
        await device.update()
        await powerprot.set_enabled(False)

        args, kwargs = call_spy.call_args
        method, params = args
        assert method == "set_protection_power"
        assert "enabled" in params or "protection_enabled" in params
        assert params["protection_power"] == 0

    finally:
        await powerprot.set_enabled(original_enabled, threshold=original_threshold)


@powerprotection
async def test_set_threshold(dev: Device, mocker: MockerFixture):
    """Test enable."""
    powerprot = next(get_parent_and_child_modules(dev, Module.PowerProtection))
    assert powerprot

    call_spy = mocker.spy(powerprot, "call")
    await powerprot.set_protection_threshold(123)

    args, kwargs = call_spy.call_args
    method, params = args
    assert method == "set_protection_power"
    assert "enabled" in params or "protection_enabled" in params
    assert params["protection_power"] == 123

    with pytest.raises(ValueError, match="Threshold out of range"):
        await powerprot.set_protection_threshold(-10)
