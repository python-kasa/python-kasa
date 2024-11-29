import copy
from contextlib import nullcontext as does_not_raise
from unittest.mock import patch

import pytest

from kasa import DeviceError, Module
from kasa.exceptions import SmartErrorCode
from kasa.interfaces.energy import Energy
from kasa.smart import SmartDevice
from kasa.smart.modules import Energy as SmartEnergyModule
from tests.conftest import has_emeter_smart


@has_emeter_smart
async def test_supported(dev: SmartDevice):
    energy_module = dev.modules.get(Module.Energy)
    if not energy_module:
        pytest.skip(f"Energy module not supported for {dev}.")

    assert isinstance(energy_module, SmartEnergyModule)
    assert energy_module.supports(Energy.ModuleFeature.CONSUMPTION_TOTAL) is False
    assert energy_module.supports(Energy.ModuleFeature.PERIODIC_STATS) is False
    if energy_module.supported_version < 2:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is False
    else:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is True


@has_emeter_smart
async def test_get_energy_usage_error(dev: SmartDevice):
    energy_module = dev.modules.get(Module.Energy)
    if not energy_module:
        pytest.skip(f"Energy module not supported for {dev}.")

    version = dev._components["energy_monitoring"]

    expected_raise = does_not_raise() if version > 1 else pytest.raises(DeviceError)
    if version > 1:
        expected = "get_energy_usage"
        expected_current_consumption = 2.002
    else:
        expected = "current_power"
        expected_current_consumption = None

    assert expected in energy_module.data
    assert energy_module.current_consumption is not None
    assert energy_module.consumption_today is not None
    assert energy_module.consumption_this_month is not None

    resp = copy.deepcopy(dev._last_update)

    if ed := resp.get("get_emeter_data"):
        ed["power_mw"] = 2002
    if cp := resp.get("get_current_power"):
        cp["current_power"] = 2.002
    resp["get_energy_usage"] = SmartErrorCode.JSON_DECODE_FAIL_ERROR

    with patch.object(dev.protocol, "query", return_value=resp):
        await dev.update()

    with expected_raise:
        assert "get_energy_usage" not in energy_module.data

    assert energy_module.current_consumption == expected_current_consumption
    assert energy_module.consumption_today is None
    assert energy_module.consumption_this_month is None
