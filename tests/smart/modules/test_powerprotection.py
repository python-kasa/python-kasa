import pytest
from pytest_mock import MockerFixture

from kasa import Module, SmartDevice
from kasa.smart.modules import PowerProtection

from ...device_fixtures import parametrize

powerprotection = parametrize(
    "has powerprotection",
    component_filter="power_protection",
    protocol_filter={"SMART"},
)


def _skip_on_unavailable(dev: SmartDevice):
    if Module.PowerProtection not in dev.modules:
        pytest.skip(f"No powerprotection module on {dev}, maybe a strip parent?")


@powerprotection
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("overloaded", "overloaded", bool | None),
        ("power_protection_enabled", "enabled", bool),
        ("power_protection_threshold", "protection_threshold", int),
    ],
)
async def test_features(dev, feature, prop_name, type):
    """Test that features are registered and work as expected."""
    _skip_on_unavailable(dev)

    powerprot: PowerProtection = dev.modules[Module.PowerProtection]

    prop = getattr(powerprot, prop_name)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@powerprotection
async def test_set_enable(dev: SmartDevice, mocker: MockerFixture):
    """Test enable."""
    _skip_on_unavailable(dev)

    powerprot: PowerProtection = dev.modules[Module.PowerProtection]

    call_spy = mocker.spy(powerprot, "call")
    await powerprot.set_enabled(True)
    params = {
        "enabled": mocker.ANY,
        "protection_power": mocker.ANY,
    }
    call_spy.assert_called_with("set_protection_power", params)


@powerprotection
async def test_set_threshold(dev: SmartDevice, mocker: MockerFixture):
    """Test enable."""
    _skip_on_unavailable(dev)

    powerprot: PowerProtection = dev.modules[Module.PowerProtection]

    call_spy = mocker.spy(powerprot, "call")
    await powerprot.set_protection_threshold(123)
    params = {
        "enabled": mocker.ANY,
        "protection_power": 123,
    }
    call_spy.assert_called_with("set_protection_power", params)

    with pytest.raises(ValueError, match="Threshold out of range"):
        await powerprot.set_protection_threshold(-10)
