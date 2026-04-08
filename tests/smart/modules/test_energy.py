import copy
import logging
from contextlib import nullcontext as does_not_raise
from unittest.mock import patch

import pytest

from kasa import DeviceError, Module
from kasa.exceptions import SmartErrorCode
from kasa.interfaces.energy import Energy
from kasa.smart import SmartDevice
from kasa.smart.modules import Energy as SmartEnergyModule

from ...device_fixtures import has_emeter_smart, parametrize

s515d_smart = parametrize(
    "s515d smart",
    model_filter={"S515D(US)_1.6_1.0.4"},
    protocol_filter={"SMART"},
)


def _get_energy_module(dev: SmartDevice) -> SmartEnergyModule:
    energy_module = dev.modules.get(Module.Energy)
    if not energy_module:
        pytest.skip(f"Energy module not supported for {dev}.")

    assert isinstance(energy_module, SmartEnergyModule)
    return energy_module


def _get_v2_energy_module(dev: SmartDevice) -> SmartEnergyModule:
    energy_module = _get_energy_module(dev)
    if energy_module.supported_version <= 1:
        pytest.skip("Only applicable for energy v2+ fixtures.")

    return energy_module


def _energy_usage(current_power: int | None = None) -> dict[str, int]:
    energy_usage = {
        "month_energy": 0,
        "today_energy": 0,
    }
    if current_power is not None:
        energy_usage["current_power"] = current_power

    return energy_usage


@has_emeter_smart
async def test_supported(dev: SmartDevice) -> None:
    energy_module = _get_energy_module(dev)
    assert energy_module.supports(Energy.ModuleFeature.CONSUMPTION_TOTAL) is False
    assert energy_module.supports(Energy.ModuleFeature.PERIODIC_STATS) is False
    if energy_module.supported_version < 2:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is False
    else:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is True


@has_emeter_smart
async def test_get_energy_usage_error(
    dev: SmartDevice, caplog: pytest.LogCaptureFixture
) -> None:
    """Test errors on get_energy_usage."""
    caplog.set_level(logging.DEBUG)

    energy_module = _get_energy_module(dev)
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

    last_update = copy.deepcopy(dev._last_update)
    resp = copy.deepcopy(last_update)

    if version > 1:
        resp["get_emeter_data"] = {"power_mw": 2002}
    resp["get_energy_usage"] = SmartErrorCode.JSON_DECODE_FAIL_ERROR

    # version 1 only has get_energy_usage so module should raise an error if
    # version 1 and get_energy_usage is in error
    with patch.object(dev.protocol, "query", return_value=resp):
        await dev.update()

    with expected_raise:
        assert "get_energy_usage" not in energy_module.data

    assert energy_module.current_consumption == expected_current_consumption
    assert energy_module.consumption_today is None
    assert energy_module.consumption_this_month is None

    msg = (
        f"Removed key get_energy_usage from response for device {dev.host}"
        " as it returned error: JSON_DECODE_FAIL_ERROR"
    )
    if version > 1:
        assert msg in caplog.text


@has_emeter_smart
async def test_v2_current_power_source_precedence(dev: SmartDevice) -> None:
    """Prefer higher precision current power sources for v2 devices."""
    energy_module = _get_v2_energy_module(dev)
    last_update = copy.deepcopy(dev._last_update)

    resp = copy.deepcopy(last_update)
    resp["get_emeter_data"] = {"power_mw": 3003}
    resp["get_energy_usage"] = _energy_usage(current_power=2002)
    resp["get_current_power"] = {"current_power": 1.001}

    with patch.object(dev.protocol, "query", return_value=resp):
        await dev.update()

    assert energy_module.current_consumption == 3.003
    assert energy_module.status.power == 3.003

    resp = copy.deepcopy(last_update)
    resp.pop("get_emeter_data", None)
    dev._last_update.pop("get_emeter_data", None)
    resp["get_energy_usage"] = _energy_usage(current_power=2002)
    resp["get_current_power"] = {"current_power": 1.001}

    with patch.object(dev.protocol, "query", return_value=resp):
        await dev.update()

    assert energy_module.current_consumption == 2.002
    assert energy_module.status.power == 2.002


@has_emeter_smart
async def test_get_energy_usage_error_falls_back_to_get_current_power(
    dev: SmartDevice,
) -> None:
    """Use get_current_power when it is the only remaining power source."""
    energy_module = _get_v2_energy_module(dev)

    resp = copy.deepcopy(dev._last_update)
    resp.pop("get_emeter_data", None)
    dev._last_update.pop("get_emeter_data", None)
    resp["get_current_power"] = {"current_power": 2.002}
    resp["get_energy_usage"] = SmartErrorCode.JSON_DECODE_FAIL_ERROR

    with patch.object(dev.protocol, "query", return_value=resp):
        await dev.update()

    assert "get_energy_usage" not in energy_module.data
    assert energy_module.current_consumption == 2.002
    assert energy_module.status.power == 2.002


@has_emeter_smart
async def test_v2_get_status_falls_back_to_get_current_power(dev: SmartDevice) -> None:
    """get_status should use the same fallback sources as the cached status."""
    energy_module = _get_v2_energy_module(dev)

    async def query(request: dict[str, dict | None]) -> dict[str, dict]:
        method = next(iter(request))
        if method == "get_emeter_data":
            raise DeviceError(method, error_code=SmartErrorCode.PARAMS_ERROR)
        if method == "get_energy_usage":
            return {"get_energy_usage": _energy_usage()}
        if method == "get_current_power":
            return {"get_current_power": {"current_power": 2.002}}
        raise AssertionError(f"Unexpected request: {request}")

    with patch.object(dev.protocol, "query", side_effect=query):
        status = await energy_module.get_status()

    assert status.power == 2.002


@s515d_smart
async def test_s515d_missing_get_current_power_is_optional(dev: SmartDevice) -> None:
    """S515D exposes current power without a working get_current_power query."""
    energy_module = _get_v2_energy_module(dev)

    assert energy_module.disabled is False
    assert energy_module._last_update_error is None
    assert "get_current_power" not in energy_module.data
    assert energy_module.current_consumption == 0.0
    assert energy_module.status.power == 0.0
