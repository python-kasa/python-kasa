import pytest
from asyncclick.testing import CliRunner
from pytest_mock import MockerFixture

from kasa import Device, DeviceType, Module
from kasa.cli.hub import hub

from ..device_fixtures import hubs, hubs_smart, plug_iot
from ..fakeprotocol_smart import FakeSmartTransport


@hubs
async def test_hub_pair(
    dev: Device,
    mocker: MockerFixture,
    runner: CliRunner,
    caplog: pytest.LogCaptureFixture,
) -> None:
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


@hubs
async def test_hub_unpair(
    dev: Device, mocker: MockerFixture, runner: CliRunner
) -> None:
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


@hubs_smart
@pytest.mark.requires_dummy
async def test_hub_list(dev: Device, runner: CliRunner) -> None:
    """Test that list shows each child with its index and availability."""
    if not dev.children:
        pytest.skip("Cannot test without child devices")

    assert isinstance(dev.protocol._transport, FakeSmartTransport)
    child_list = dev.protocol._transport.info["get_child_device_list"]
    child_list["child_device_list"][0]["status"] = "offline"
    await dev.update()

    res = await runner.invoke(hub, ["list"], obj=dev, catch_exceptions=False)

    rows = {line.split()[1]: line.split() for line in res.output.splitlines()[1:]}
    for index, child in enumerate(dev.children):
        row = rows[child.device_id]
        assert row[0] == str(index)
        assert row[3] == str(index != 0)
    assert res.exit_code == 0


@plug_iot
async def test_non_hub(dev: Device, mocker: MockerFixture, runner: CliRunner) -> None:
    """Test that hub commands return an error if executed on a non-hub."""
    assert dev.device_type is not DeviceType.Hub
    res = await runner.invoke(
        hub, ["unpair", "dummy_id"], obj=dev, catch_exceptions=False
    )
    assert "is not a hub" in res.output
