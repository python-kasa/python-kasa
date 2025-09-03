from unittest.mock import PropertyMock, patch

import pytest

from kasa import Module
from kasa.iot import IotDevice
from kasa.iot.modules.homekit import HomeKit

from ...device_fixtures import device_iot


@device_iot
def test_homekit_getters(dev: IotDevice):
    # HomeKit can be present on any IOT device
    if Module.IotHomeKit not in dev.modules:
        pytest.skip("HomeKit module not present on this device")
    homekit: HomeKit = dev.modules[Module.IotHomeKit]
    info = homekit.info
    if not info:
        pytest.skip("No HomeKit data present for this fixture")
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
def test_homekit_feature(dev: IotDevice):
    if Module.IotHomeKit not in dev.modules:
        pytest.skip("HomeKit module not present on this device")
    homekit: HomeKit = dev.modules[Module.IotHomeKit]
    if not homekit.info:
        pytest.skip("No HomeKit data present for this device")
    feature = homekit._all_features.get("homekit_setup_code")
    assert feature is not None
    assert isinstance(feature.attribute_getter, str)
    value = getattr(homekit, feature.attribute_getter)
    assert value == homekit.setup_code


@device_iot
def test_initialize_features_skips_when_no_data(dev: IotDevice):
    if Module.IotHomeKit not in dev.modules:
        pytest.skip("HomeKit module not present on this device")
    homekit: HomeKit = dev.modules[Module.IotHomeKit]
    if "homekit_setup_code" in homekit._all_features:
        pytest.skip("HomeKit feature already present on this device")
    # Patch .data so it looks like no homekit data is present
    with patch.object(HomeKit, "data", new_callable=PropertyMock) as mock_data:
        mock_data.return_value = {}
        homekit._initialize_features()
    # Since there was no data, no features should be added
    assert "homekit_setup_code" not in homekit._all_features
