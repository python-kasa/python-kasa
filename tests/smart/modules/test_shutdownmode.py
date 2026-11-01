import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.exceptions import DeviceError
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

shutdownmode = parametrize(
    "has shutdown mode",
    component_filter="shutdown_mode",
    protocol_filter={"SMART.CHILD"},
)

hubs_with_children = parametrize(
    "smart hubs", model_filter={"KH100"}, protocol_filter={"SMART"}
)


@shutdownmode
async def test_enabled_and_position(dev: SmartDevice) -> None:
    """Enable and position are independently settable."""
    mod = dev.modules[Module.ShutdownMode]

    await mod.set_enabled(True)
    await mod.set_valve_position("full_open")
    await dev.update()
    assert mod.enabled is True
    assert mod.valve_position == "full_open"
    assert dev.features["summer_mode"].value is True
    assert dev.features["summer_mode_valve_position"].value == "full_open"

    await dev.features["summer_mode_valve_position"].set_value("full_closed")
    await dev.features["summer_mode"].set_value(False)
    await dev.update()
    assert mod.enabled is False
    assert mod.valve_position == "full_closed"


@shutdownmode
async def test_writes_use_fresh_values(dev: SmartDevice, mocker: MockerFixture) -> None:
    """A second write before the next update must not undo the first."""
    mod = dev.modules[Module.ShutdownMode]
    call = mocker.spy(mod, "call")

    await mod.set_enabled(True)
    await mod.set_valve_position("full_open")
    call.assert_called_with("set_shutdown_info", {"enable": True, "mode": "full_open"})


@shutdownmode
async def test_enabled_follows_device_info(dev: SmartDevice) -> None:
    """The state is live even when the module query is not due."""
    mod = dev.modules[Module.ShutdownMode]
    dev._info["trv_states"] = ["shutdown"]
    assert mod.enabled is True
    dev._info["trv_states"] = []
    assert mod.enabled is False


@shutdownmode
async def test_invalid_position(dev: SmartDevice) -> None:
    mod = dev.modules[Module.ShutdownMode]
    with pytest.raises(ValueError, match="Invalid position"):
        await mod.set_valve_position("half_open")


@shutdownmode
async def test_anti_blocking(dev: SmartDevice) -> None:
    """Anti-blocking is only exposed from version 2 of the component."""
    mod = dev.modules[Module.ShutdownMode]
    if mod.supported_version < 2:
        assert "anti_blocking" not in dev.features
        return

    await dev.features["anti_blocking"].set_value(True)
    await dev.features["anti_blocking_day"].set_value("Saturday")
    await dev.features["anti_blocking_minute"].set_value(1439)
    await dev.update()
    assert mod.anti_blocking_enabled is True
    assert mod.anti_blocking_day == "Saturday"
    assert mod.anti_blocking_minute == 1439


@shutdownmode
@pytest.mark.parametrize(
    ("setter", "value", "match"),
    [
        ("set_anti_blocking_day", "Someday", "Invalid day"),
        ("set_anti_blocking_minute", 1440, "Invalid minute"),
        ("set_anti_blocking_minute", 600.5, "Invalid minute"),
    ],
)
async def test_anti_blocking_invalid_values(
    dev: SmartDevice, setter: str, value: float | str, match: str
) -> None:
    mod = dev.modules[Module.ShutdownMode]
    with pytest.raises(ValueError, match=match):
        await getattr(mod, setter)(value)


@shutdownmode
async def test_whole_number_floats_are_sent_as_integers(
    dev: SmartDevice, mocker: MockerFixture
) -> None:
    mod = dev.modules[Module.ShutdownMode]
    call = mocker.spy(mod, "call")

    await mod.set_anti_blocking_minute(600.0)
    params = call.call_args.args[1]
    assert params["anti_clogging_min"] == 600
    assert isinstance(params["anti_clogging_min"], int)


@shutdownmode
@pytest.mark.parametrize(
    ("name", "firmware_value"), [("Sunday", 0), ("Monday", 1), ("Saturday", 6)]
)
async def test_anti_blocking_day_names_map_to_firmware_values(
    dev: SmartDevice, mocker: MockerFixture, name: str, firmware_value: int
) -> None:
    mod = dev.modules[Module.ShutdownMode]
    call = mocker.spy(mod, "call")

    await mod.set_anti_blocking_day(name)
    assert call.call_args.args[1]["anti_clogging_day"] == firmware_value


@shutdownmode
async def test_shutdown_replaces_heating_and_survives_setpoint_writes(
    dev: SmartDevice,
) -> None:
    """Match the states reported by a KE100 on firmware 2.15.0."""
    mod = dev.modules[Module.ShutdownMode]
    temp = dev.modules[Module.TemperatureControl]
    high = temp.maximum_target_temperature

    await temp.set_target_temperature(high)
    await dev.update()
    assert "heating" in temp.states

    await mod.set_enabled(True)
    await dev.update()
    assert "heating" not in temp.states

    await temp.set_target_temperature(high - 1)
    await dev.update()
    assert mod.enabled is True
    assert "heating" not in temp.states

    await mod.set_enabled(False)
    await dev.update()
    assert "shutdown" not in temp.states
    assert "heating" in temp.states


@shutdownmode
@pytest.mark.parametrize(
    "params",
    [
        {"enable": True},
        {"mode": "full_closed"},
        {"anti_clogging_min": 600},
        {"enable": True, "mode": "bogus"},
        {"enable": True, "mode": "full_closed", "anti_clogging_day": 7},
        {"enable": True, "mode": "full_closed", "anti_clogging_min": 1440},
    ],
)
async def test_firmware_rejects_invalid_writes(dev: SmartDevice, params: dict) -> None:
    with pytest.raises(DeviceError):
        await dev.modules[Module.ShutdownMode].call("set_shutdown_info", params)


@hubs_with_children
async def test_data_survives_update_of_other_modules(
    dev: SmartDevice, mocker: MockerFixture
) -> None:
    """Hub child modules update on their own schedule, and must keep each other's data."""
    children = [
        child
        for child in dev.children
        if Module.ShutdownMode in child.modules
        and Module.TemperatureRecords in child.modules
    ]
    if not children:
        pytest.skip("Needs a child with shutdown mode and temperature records")

    for child in children:
        mod = child.modules[Module.ShutdownMode]
        position = mod.valve_position
        mocker.patch.object(mod, "_should_update", return_value=False)
        mocker.patch.object(
            child.modules[Module.TemperatureRecords],
            "_should_update",
            return_value=True,
        )
        await child.update()
        assert mod.valve_position == position
