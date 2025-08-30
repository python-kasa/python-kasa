import pytest

from kasa import Module
from kasa.iot.modules.homekit import HomeKit

from ...device_fixtures import device_iot


@device_iot
def test_homekit_getters(dev):
    # HomeKit can be present on any IOT device
    if Module.IotHomeKit not in dev.modules:
        pytest.skip("HomeKit module not present on this device")
    homekit: HomeKit = dev.modules[Module.IotHomeKit]
    info = homekit.info
    assert "setup_code" in info
    assert "setup_payload" in info
    assert "err_code" in info
    # Check that the setup_code and setup_payload are strings
    assert isinstance(info["setup_code"], str)
    assert isinstance(info["setup_payload"], str)
    assert isinstance(info["err_code"], int)
    # Check that the HomeKit module properties match
    assert info["setup_code"] == homekit.setup_code
    assert info["setup_payload"] == homekit.setup_payload


@device_iot
def test_homekit_feature(dev):
    if Module.IotHomeKit not in dev.modules:
        pytest.skip("HomeKit module not present on this device")
    homekit: HomeKit = dev.modules[Module.IotHomeKit]
    homekit._initialize_features()
    feature = homekit._all_features.get("homekit_setup_code")
    assert feature is not None
    value = getattr(homekit, feature.attribute_getter)
    assert value == homekit.setup_code
