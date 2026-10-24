from unittest.mock import PropertyMock, patch

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.exceptions import TimeoutError
from kasa.iot import IotDevice
from kasa.iot.modules.homekit import HomeKit

from ...conftest import get_device_for_fixture_protocol
from ...device_fixtures import device_iot

HOMEKIT = "smartlife.iot.homekit"


async def _homekit_module(dev: IotDevice) -> HomeKit:
    """Create the module with the data from the device, skip if not supported."""
    if not await dev.supports_module(Module.IotHomeKit):
        pytest.skip("HomeKit module not present on this device")
    homekit = HomeKit(dev, HOMEKIT)
    dev._last_update.update(await dev.protocol.query(homekit.query()))
    homekit._initialize_features()
    return homekit


@device_iot
async def test_homekit_getters(dev: IotDevice) -> None:
    # HomeKit can be present on any IOT device
    homekit = await _homekit_module(dev)
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
async def test_homekit_feature(dev: IotDevice) -> None:
    homekit = await _homekit_module(dev)
    if not homekit.info:
        pytest.skip("No HomeKit data present for this device")
    feature = homekit._all_features.get("homekit_setup_code")
    assert feature is not None
    assert isinstance(feature.attribute_getter, str)
    value = getattr(homekit, feature.attribute_getter)
    assert value == homekit.setup_code


@device_iot
def test_initialize_features_skips_when_no_data(dev: IotDevice) -> None:
    homekit = HomeKit(dev, HOMEKIT)
    if "homekit_setup_code" in homekit._all_features:
        pytest.skip("HomeKit feature already present on this device")
    # Patch .data so it looks like no homekit data is present
    with patch.object(HomeKit, "data", new_callable=PropertyMock) as mock_data:
        mock_data.return_value = {}
        homekit._initialize_features()
    # Since there was no data, no features should be added
    assert "homekit_setup_code" not in homekit._all_features


@pytest.mark.requires_dummy
@device_iot
async def test_update_does_not_query_homekit(dev, mocker: MockerFixture) -> None:
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    assert not [call for call in spy.call_args_list if HOMEKIT in call.args[0]]


@pytest.mark.requires_dummy
@pytest.mark.parametrize(
    ("fixture", "supported"),
    [("EP25(US)_1.0_1.0.14.json", True), ("HS100(US)_2.0_1.5.6.json", False)],
)
async def test_supports_module(
    mocker: MockerFixture, fixture: str, supported: bool
) -> None:
    dev = await get_device_for_fixture_protocol(fixture, "IOT")
    spy = mocker.spy(dev.protocol, "query")

    assert await dev.supports_module(Module.IotHomeKit) is supported
    assert await dev.supports_module(Module.IotHomeKit) is supported
    assert spy.call_count == 1


@pytest.mark.requires_dummy
async def test_timeout_is_not_supported_and_not_remembered(
    mocker: MockerFixture,
) -> None:
    dev = await get_device_for_fixture_protocol("EP25(US)_1.0_1.0.14.json", "IOT")
    query = dev.protocol.query

    mocker.patch.object(dev.protocol, "query", side_effect=TimeoutError("timeout"))
    assert await dev.supports_module(Module.IotHomeKit) is False

    mocker.patch.object(dev.protocol, "query", side_effect=query)
    assert await dev.supports_module(Module.IotHomeKit) is True
