import pytest
from pytest_mock import MockerFixture

from kasa import DeviceType, Module
from kasa.cli.hub import hub

from ..device_fixtures import HUBS_SMART, hubs_smart, parametrize, plug_iot


@hubs_smart
async def test_hub_pair(dev, mocker: MockerFixture, runner, caplog):
    """Test that pair calls the expected methods."""
    cs = dev.modules.get(Module.ChildSetup)
    # Patch if the device supports the module
    if cs is not None:
        mock_pair = mocker.patch.object(cs, "pair")

    res = await runner.invoke(hub, ["pair"], obj=dev, catch_exceptions=False)
    if cs is None:
        assert "is not a hub" in res.output
        return

    mock_pair.assert_awaited()
    assert "Finding new devices for 10 seconds" in res.output
    assert res.exit_code == 0


@parametrize("hubs smart", model_filter=HUBS_SMART, protocol_filter={"SMART"})
async def test_hub_unpair(dev, mocker: MockerFixture, runner):
    """Test that unpair calls the expected method."""
    if not dev.children:
        pytest.skip("Cannot test without child devices")

    id_ = next(iter(dev.children)).device_id

    cs = dev.modules.get(Module.ChildSetup)
    mock_unpair = mocker.spy(cs, "unpair")

    res = await runner.invoke(hub, ["unpair", id_], obj=dev, catch_exceptions=False)

    mock_unpair.assert_awaited()
    assert f"Unpaired {id_}" in res.output
    assert res.exit_code == 0


@plug_iot
async def test_non_hub(dev, mocker: MockerFixture, runner):
    """Test that hub commands return an error if executed on a non-hub."""
    assert dev.device_type is not DeviceType.Hub
    res = await runner.invoke(
        hub, ["unpair", "dummy_id"], obj=dev, catch_exceptions=False
    )
    assert "is not a hub" in res.output
