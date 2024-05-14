import logging

import pytest

from kasa.smart.modules import TemperatureControl
from kasa.smart.modules.temperaturecontrol import ThermostatState
from kasa.tests.device_fixtures import parametrize, thermostats_smart

temperature = parametrize(
    "has temperature control",
    component_filter="temperature_control",
    protocol_filter={"SMART.CHILD"},
)


@thermostats_smart
@pytest.mark.parametrize(
    "feature, type",
    [
        ("target_temperature", float),
        ("temperature_offset", int),
    ],
)
async def test_temperature_control_features(dev, feature, type):
    """Test that features are registered and work as expected."""
    temp_module: TemperatureControl = dev.modules["TemperatureControl"]

    prop = getattr(temp_module, feature)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)

    await feat.set_value(10)
    await dev.update()
    assert feat.value == 10


@thermostats_smart
async def test_set_temperature_turns_heating_on(dev):
    """Test that set_temperature turns heating on."""
    temp_module: TemperatureControl = dev.modules["TemperatureControl"]

    await temp_module.set_state(False)
    await dev.update()
    assert temp_module.state is False
    assert temp_module.mode is ThermostatState.Off

    await temp_module.set_target_temperature(10)
    await dev.update()
    assert temp_module.state is True
    assert temp_module.mode is ThermostatState.Heating
    assert temp_module.target_temperature == 10


@thermostats_smart
async def test_set_temperature_invalid_values(dev):
    """Test that out-of-bounds temperature values raise errors."""
    temp_module: TemperatureControl = dev.modules["TemperatureControl"]

    with pytest.raises(ValueError):
        await temp_module.set_target_temperature(-1)

    with pytest.raises(ValueError):
        await temp_module.set_target_temperature(100)


@thermostats_smart
async def test_temperature_offset(dev):
    """Test the temperature offset API."""
    temp_module: TemperatureControl = dev.modules["TemperatureControl"]
    with pytest.raises(ValueError):
        await temp_module.set_temperature_offset(100)

    with pytest.raises(ValueError):
        await temp_module.set_temperature_offset(-100)

    await temp_module.set_temperature_offset(5)
    await dev.update()
    assert temp_module.temperature_offset == 5


@thermostats_smart
@pytest.mark.parametrize(
    "mode, states, frost_protection",
    [
        pytest.param(ThermostatState.Idle, [], False, id="idle has empty"),
        pytest.param(
            ThermostatState.Off,
            ["anything"],
            True,
            id="any state with frost_protection on means off",
        ),
        pytest.param(
            ThermostatState.Heating,
            [ThermostatState.Heating],
            False,
            id="heating is heating",
        ),
        pytest.param(ThermostatState.Unknown, ["invalid"], False, id="unknown state"),
    ],
)
async def test_thermostat_mode(dev, mode, states, frost_protection):
    """Test different thermostat modes."""
    temp_module: TemperatureControl = dev.modules["TemperatureControl"]

    temp_module.data["frost_protection_on"] = frost_protection
    temp_module.data["trv_states"] = states

    assert temp_module.state is not frost_protection
    assert temp_module.mode is mode


@thermostats_smart
@pytest.mark.parametrize(
    "mode, states, msg",
    [
        pytest.param(
            ThermostatState.Heating,
            ["heating", "something else"],
            "Got multiple states",
            id="multiple states",
        ),
        pytest.param(
            ThermostatState.Unknown, ["foobar"], "Got unknown state", id="unknown state"
        ),
    ],
)
async def test_thermostat_mode_warnings(dev, mode, states, msg, caplog):
    """Test thermostat modes that should log a warning."""
    temp_module: TemperatureControl = dev.modules["TemperatureControl"]
    caplog.set_level(logging.WARNING)

    temp_module.data["trv_states"] = states
    assert temp_module.mode is mode
    assert msg in caplog.text
