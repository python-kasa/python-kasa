import asyncio
from unittest.mock import PropertyMock, patch

import pytest

from kasa import Module
from kasa.exceptions import TimeoutError
from kasa.iot import IotDevice
from kasa.iot.modules.homekit import HomeKit

from ...device_fixtures import device_iot, get_device_for_fixture, get_fixture_info

HOMEKIT = "smartlife.iot.homekit"


@device_iot
def test_homekit_getters(dev: IotDevice) -> None:
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
def test_homekit_feature(dev: IotDevice) -> None:
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
def test_initialize_features_skips_when_no_data(dev: IotDevice) -> None:
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


@pytest.mark.requires_dummy
@pytest.mark.parametrize("discovered", [True, False])
@pytest.mark.parametrize(
    "fixture",
    [
        "EP10(US)_1.0_1.0.2.json",
        "HS103(US)_2.1_1.1.4.json",
        "KP115(US)_1.0_1.0.17.json",
        "HS300(US)_1.0_1.0.21.json",
        "EP25(US)_1.0_1.0.14.json",
    ],
)
async def test_homekit_update_with_order_sensitive_firmware(
    mocker, fixture, discovered
):
    """Unsupported HomeKit following another module must not block updates."""
    info = get_fixture_info(fixture, "IOT")
    dev = await get_device_for_fixture(info, update_after_init=False)
    if not discovered:
        dev._last_update = {}
    supported = HOMEKIT in info.data
    query = dev.protocol.query

    async def query_with_homekit(request):
        if HOMEKIT in request and not supported:
            if next(iter(request)) != HOMEKIT:
                raise TimeoutError("HomeKit following another module times out")
            return {HOMEKIT: {"err_code": -1, "err_msg": "module not support"}}
        return await query(request)

    query_mock = mocker.patch.object(
        dev.protocol, "query", side_effect=query_with_homekit
    )
    for update in range(3):
        query_mock.reset_mock()
        await dev.update()
        requests = [call.args[0] for call in query_mock.call_args_list]
        homekit_requests = [request for request in requests if HOMEKIT in request]
        assert len(homekit_requests) == (1 if supported or update == 0 else 0)
        if homekit_requests:
            assert homekit_requests == [{HOMEKIT: {"setup_info_get": {}}}]
        assert any("system" in request for request in requests)
        assert (Module.IotHomeKit in dev.modules) == supported
        assert ("homekit_setup_code" in dev.features) == supported
        if supported:
            assert (
                dev.features["homekit_setup_code"].value
                == info.data[HOMEKIT]["setup_info_get"]["setup_code"]
            )
        if dev.has_emeter:
            assert dev.modules[Module.Energy].current_consumption is not None


@pytest.mark.requires_dummy
@pytest.mark.parametrize("failure_module", [HOMEKIT, "schedule"])
@pytest.mark.parametrize("exception", [TimeoutError, asyncio.CancelledError])
async def test_homekit_update_propagates_errors(mocker, failure_module, exception):
    """Communication failures must propagate without disabling HomeKit."""
    info = get_fixture_info("EP25(US)_1.0_1.0.14.json", "IOT")
    dev = await get_device_for_fixture(info, update_after_init=False)
    query = dev.protocol.query

    async def failing_query(request):
        if failure_module in request:
            raise exception("Device unavailable")
        return await query(request)

    query_mock = mocker.patch.object(dev.protocol, "query", side_effect=failing_query)
    with pytest.raises(exception, match="Device unavailable"):
        await dev.update()
    assert not dev.features

    query_mock.side_effect = query
    await dev.update()
    assert Module.IotHomeKit in dev.modules
    assert "homekit_setup_code" in dev.features
