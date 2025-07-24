import pytest
from pytest_mock import MockerFixture

from kasa import Module, SmartDevice

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
async def test_set_enable(dev: SmartDevice, mocker: MockerFixture):
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

        # Check which key is used by this device
        protection_data = powerprot.data["get_protection_power"]
        if "protection_enabled" in protection_data:
            params = {
                "protection_enabled": True,
                "protection_power": mocker.ANY,
            }
        else:
            params = {
                "enabled": True,
                "protection_power": mocker.ANY,
            }
        call_spy.assert_called_with("set_protection_power", params)

        # Enable with no threshold param when 0
        call_spy.reset_mock()
        await powerprot.set_protection_threshold(0)
        await device.update()
        await powerprot.set_enabled(True)

        # Check which key is used by this device
        protection_data = powerprot.data["get_protection_power"]
        if "protection_enabled" in protection_data:
            params = {
                "protection_enabled": True,
                "protection_power": int(powerprot._max_power / 2),
            }
        else:
            params = {
                "enabled": True,
                "protection_power": int(powerprot._max_power / 2),
            }
        call_spy.assert_called_with("set_protection_power", params)

        # Enable false should not update the threshold
        call_spy.reset_mock()
        await powerprot.set_protection_threshold(0)
        await device.update()
        await powerprot.set_enabled(False)

        # Check which key is used by this device
        protection_data = powerprot.data["get_protection_power"]
        if "protection_enabled" in protection_data:
            params = {
                "protection_enabled": False,
                "protection_power": 0,
            }
        else:
            params = {
                "enabled": False,
                "protection_power": 0,
            }
        call_spy.assert_called_with("set_protection_power", params)

    finally:
        await powerprot.set_enabled(original_enabled, threshold=original_threshold)


@powerprotection
async def test_set_threshold(dev: SmartDevice, mocker: MockerFixture):
    """Test enable."""
    powerprot = next(get_parent_and_child_modules(dev, Module.PowerProtection))
    assert powerprot

    call_spy = mocker.spy(powerprot, "call")
    await powerprot.set_protection_threshold(123)

    # Check which key is used by this device
    protection_data = powerprot.data["get_protection_power"]
    if "protection_enabled" in protection_data:
        params = {
            "protection_enabled": mocker.ANY,
            "protection_power": 123,
        }
    else:
        params = {
            "enabled": mocker.ANY,
            "protection_power": 123,
        }
    call_spy.assert_called_with("set_protection_power", params)

    with pytest.raises(ValueError, match="Threshold out of range"):
        await powerprot.set_protection_threshold(-10)
