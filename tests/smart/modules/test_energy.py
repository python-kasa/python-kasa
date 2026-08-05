import calendar
import copy
import logging
from contextlib import nullcontext as does_not_raise
from datetime import date
from unittest.mock import patch

import pytest

from kasa import DeviceError, KasaException, Module
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
p110_v1_smart = parametrize(
    "p110 v1 smart",
    model_filter={"P110(EU)_1.0_1.0.7"},
    protocol_filter={"SMART"},
)
kp125m_smart = parametrize(
    "kp125m smart",
    model_filter={"KP125M(US)_1.0_1.2.3"},
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


def _copy_last_update(dev: SmartDevice, *remove_keys: str) -> dict[str, object]:
    """Copy the cached update response, removing keys from the cache if needed."""
    response = copy.deepcopy(dev._last_update)
    for key in remove_keys:
        response.pop(key, None)
        dev._last_update.pop(key, None)

    return response


def _device_error(method: str, error_code: SmartErrorCode) -> DeviceError:
    return DeviceError(method, error_code=error_code)


def _mock_query(responses: dict[str, object], calls: list[str]):
    async def query(request: dict[str, dict | None]) -> dict[str, object]:
        method = next(iter(request))
        calls.append(method)

        if method not in responses:
            raise AssertionError(f"Unexpected request: {request}")

        response = responses[method]
        if isinstance(response, DeviceError):
            raise response

        return {method: response}

    return query


@has_emeter_smart
async def test_supported(dev: SmartDevice) -> None:
    energy_module = _get_energy_module(dev)
    assert energy_module.supports(Energy.ModuleFeature.CONSUMPTION_TOTAL) is False
    if energy_module.supported_version < 2:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is False
        assert energy_module.supports(Energy.ModuleFeature.PERIODIC_STATS) is False
    else:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is True
        # v2 devices expose historical stats via get_energy_data.
        assert energy_module.supports(Energy.ModuleFeature.PERIODIC_STATS) is True


@has_emeter_smart
async def test_get_energy_usage_error(
    dev: SmartDevice, caplog: pytest.LogCaptureFixture
) -> None:
    """Test errors on get_energy_usage."""
    caplog.set_level(logging.DEBUG)

    energy_module = _get_energy_module(dev)
    version = energy_module.supported_version

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

    resp = _copy_last_update(dev)

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
@pytest.mark.parametrize(
    ("remove_keys", "response_updates", "expected_power"),
    [
        pytest.param(
            (),
            {
                "get_emeter_data": {"power_mw": 3003},
                "get_energy_usage": _energy_usage(current_power=2002),
                "get_current_power": {"current_power": 1.001},
            },
            3.003,
            id="prefers_get_emeter_data",
        ),
        pytest.param(
            ("get_emeter_data",),
            {
                "get_energy_usage": _energy_usage(current_power=2002),
                "get_current_power": {"current_power": 1.001},
            },
            2.002,
            id="falls_back_to_get_energy_usage",
        ),
    ],
)
async def test_v2_current_power_source_precedence(
    dev: SmartDevice,
    remove_keys: tuple[str, ...],
    response_updates: dict[str, object],
    expected_power: float,
) -> None:
    """Prefer higher precision current power sources for v2 devices."""
    energy_module = _get_v2_energy_module(dev)
    resp = _copy_last_update(dev, *remove_keys)
    resp.update(response_updates)

    with patch.object(dev.protocol, "query", return_value=resp):
        await dev.update()

    assert energy_module.current_consumption == expected_power
    assert energy_module.status.power == expected_power


@has_emeter_smart
@pytest.mark.parametrize(
    ("response_updates", "expected_power", "expect_energy_usage_removed"),
    [
        pytest.param(
            {
                "get_current_power": {"current_power": 2.002},
                "get_energy_usage": SmartErrorCode.JSON_DECODE_FAIL_ERROR,
            },
            2.002,
            True,
            id="falls_back_to_get_current_power",
        ),
        pytest.param(
            {
                "get_energy_usage": _energy_usage(),
                "get_current_power": SmartErrorCode.PARAMS_ERROR,
            },
            None,
            False,
            id="returns_none_without_current_power",
        ),
    ],
)
async def test_v2_current_power_fallbacks(
    dev: SmartDevice,
    response_updates: dict[str, object],
    expected_power: float | None,
    expect_energy_usage_removed: bool,
) -> None:
    """Test fallback behavior when higher precision power sources are unavailable."""
    energy_module = _get_v2_energy_module(dev)
    resp = _copy_last_update(dev, "get_emeter_data")
    resp.update(response_updates)

    with patch.object(dev.protocol, "query", return_value=resp):
        await dev.update()

    if expect_energy_usage_removed:
        assert "get_energy_usage" not in energy_module.data

    assert energy_module.current_consumption == expected_power
    assert energy_module.status.power == expected_power


@has_emeter_smart
@pytest.mark.parametrize(
    ("responses", "expected_calls", "expected_power"),
    [
        pytest.param(
            {
                "get_emeter_data": {
                    "current_ma": 25,
                    "energy_wh": 321,
                    "power_mw": 3003,
                    "voltage_mv": 120456,
                }
            },
            ["get_emeter_data"],
            3.003,
            id="prefers_get_emeter_data",
        ),
        pytest.param(
            {
                "get_emeter_data": _device_error(
                    "get_emeter_data", SmartErrorCode.PARAMS_ERROR
                ),
                "get_energy_usage": _energy_usage(current_power=2002),
            },
            ["get_emeter_data", "get_energy_usage"],
            2.002,
            id="falls_back_to_get_energy_usage",
        ),
        pytest.param(
            {
                "get_emeter_data": _device_error(
                    "get_emeter_data", SmartErrorCode.UNKNOWN_METHOD_ERROR
                ),
                "get_energy_usage": _energy_usage(current_power=2002),
            },
            ["get_emeter_data", "get_energy_usage"],
            2.002,
            id="falls_back_after_unknown_method",
        ),
        pytest.param(
            {
                "get_emeter_data": _device_error(
                    "get_emeter_data", SmartErrorCode.PARAMS_ERROR
                ),
                "get_energy_usage": _energy_usage(),
                "get_current_power": {"current_power": 2.002},
            },
            ["get_emeter_data", "get_energy_usage", "get_current_power"],
            2.002,
            id="falls_back_to_get_current_power",
        ),
        pytest.param(
            {
                "get_emeter_data": _device_error(
                    "get_emeter_data", SmartErrorCode.PARAMS_ERROR
                ),
                "get_energy_usage": _device_error(
                    "get_energy_usage", SmartErrorCode.JSON_DECODE_FAIL_ERROR
                ),
                "get_current_power": {"current_power": 2.002},
            },
            ["get_emeter_data", "get_energy_usage", "get_current_power"],
            2.002,
            id="continues_after_get_energy_usage_error",
        ),
        pytest.param(
            {
                "get_emeter_data": _device_error(
                    "get_emeter_data", SmartErrorCode.PARAMS_ERROR
                ),
                "get_energy_usage": _energy_usage(),
                "get_current_power": _device_error(
                    "get_current_power", SmartErrorCode.PARAMS_ERROR
                ),
            },
            ["get_emeter_data", "get_energy_usage", "get_current_power"],
            None,
            id="returns_none_when_all_sources_fail",
        ),
    ],
)
async def test_v2_get_status_current_power_sources(
    dev: SmartDevice,
    responses: dict[str, object],
    expected_calls: list[str],
    expected_power: float | None,
) -> None:
    """get_status should use the same source precedence as cached status."""
    energy_module = _get_v2_energy_module(dev)
    calls: list[str] = []

    with patch.object(dev.protocol, "query", side_effect=_mock_query(responses, calls)):
        status = await energy_module.get_status()

    assert calls == expected_calls
    assert status.power == expected_power


@has_emeter_smart
@pytest.mark.parametrize(
    ("responses", "expected_calls", "expected_match"),
    [
        pytest.param(
            {
                "get_emeter_data": _device_error(
                    "get_emeter_data", SmartErrorCode.JSON_DECODE_FAIL_ERROR
                ),
            },
            ["get_emeter_data"],
            "get_emeter_data",
            id="get_emeter_data",
        ),
        pytest.param(
            {
                "get_emeter_data": _device_error(
                    "get_emeter_data", SmartErrorCode.PARAMS_ERROR
                ),
                "get_energy_usage": _energy_usage(),
                "get_current_power": _device_error(
                    "get_current_power", SmartErrorCode.JSON_DECODE_FAIL_ERROR
                ),
            },
            ["get_emeter_data", "get_energy_usage", "get_current_power"],
            "get_current_power",
            id="get_current_power",
        ),
    ],
)
async def test_v2_get_status_raises_unexpected_optional_method_errors(
    dev: SmartDevice,
    responses: dict[str, object],
    expected_calls: list[str],
    expected_match: str,
) -> None:
    """Only unsupported optional method errors should fall back silently."""
    energy_module = _get_v2_energy_module(dev)
    calls: list[str] = []

    with (
        patch.object(dev.protocol, "query", side_effect=_mock_query(responses, calls)),
        pytest.raises(DeviceError, match=expected_match),
    ):
        await energy_module.get_status()

    assert calls == expected_calls


@p110_v1_smart
async def test_v1_get_status_uses_energy_usage_only(dev: SmartDevice) -> None:
    """V1 devices should return energy usage data without querying current power."""
    energy_module = _get_energy_module(dev)
    calls: list[str] = []

    with patch.object(
        dev.protocol,
        "query",
        side_effect=_mock_query({"get_energy_usage": _energy_usage()}, calls),
    ):
        status = await energy_module.get_status()

    assert calls == ["get_energy_usage"]
    assert status.power is None


@p110_v1_smart
async def test_v1_get_status_raises_on_get_energy_usage_error(
    dev: SmartDevice,
) -> None:
    """V1 devices should still raise when get_energy_usage fails."""
    energy_module = _get_energy_module(dev)

    async def query(request: dict[str, dict | None]) -> dict[str, dict]:
        method = next(iter(request))
        raise DeviceError(method, error_code=SmartErrorCode.JSON_DECODE_FAIL_ERROR)

    with (
        patch.object(dev.protocol, "query", side_effect=query),
        pytest.raises(DeviceError, match="get_energy_usage"),
    ):
        await energy_module.get_status()


@s515d_smart
async def test_s515d_missing_get_current_power_is_optional(dev: SmartDevice) -> None:
    """S515D exposes current power without a working get_current_power query."""
    energy_module = _get_v2_energy_module(dev)

    assert energy_module.disabled is False
    assert energy_module._last_update_error is None
    assert "get_current_power" not in energy_module.data
    assert energy_module.current_consumption == 0.0
    assert energy_module.status.power == 0.0


@kp125m_smart
async def test_get_monthly_stats(dev: SmartDevice) -> None:
    """Monthly stats map the 12 get_energy_data buckets to {month: energy}."""
    energy_module = _get_v2_energy_module(dev)
    assert energy_module.supports(Energy.ModuleFeature.PERIODIC_STATS)

    # Fake transport returns month*1000 Wh per bucket.
    stats = await energy_module.get_monthly_stats(year=2024)
    assert stats == {month: float(month) for month in range(1, 13)}

    stats_wh = await energy_module.get_monthly_stats(year=2024, kwh=False)
    assert stats_wh == {month: month * 1000 for month in range(1, 13)}


@kp125m_smart
async def test_get_daily_stats(dev: SmartDevice) -> None:
    """Daily stats return the requested month's days keyed by day-of-month."""
    energy_module = _get_v2_energy_module(dev)

    year, month = 2024, 2  # leap February -> 29 days
    days_in_month = calendar.monthrange(year, month)[1]

    stats = await energy_module.get_daily_stats(year=year, month=month)
    assert set(stats) == set(range(1, days_in_month + 1))

    # Fake transport returns day_of_year*10 Wh per bucket; 1 Feb 2024 is doy 32.
    expected_first = date(year, month, 1).timetuple().tm_yday * 10 / 1000
    assert stats[1] == expected_first
    expected_last = date(year, month, days_in_month).timetuple().tm_yday * 10 / 1000
    assert stats[days_in_month] == expected_last


@kp125m_smart
async def test_energy_data_follows_continuation_cursor(dev: SmartDevice) -> None:
    """A response ending before the requested window is re-queried and merged."""
    energy_module = _get_v2_energy_module(dev)

    pages = [
        {"get_energy_data": {"end_timestamp": 150, "data": [10, 20]}},
        {"get_energy_data": {"end_timestamp": 300, "data": [30]}},
    ]
    starts: list[int] = []

    async def fake_call(method: str, params: dict | None = None) -> dict:
        assert method == "get_energy_data"
        assert params is not None
        starts.append(params["start_timestamp"])
        return pages[len(starts) - 1]

    with patch.object(energy_module, "call", side_effect=fake_call):
        data = await energy_module._query_energy_data(0, 300, 1440)

    assert data == [10, 20, 30]
    # Second request continues from the first response's end_timestamp.
    assert starts == [0, 150]


@kp125m_smart
async def test_get_monthly_stats_defaults_to_current_year(dev: SmartDevice) -> None:
    """With no year, the current year's full 12 months are returned."""
    energy_module = _get_v2_energy_module(dev)
    # get_monthly_stats always spans Jan 1 -> Jan 1, so the mapping is
    # independent of the current date.
    stats = await energy_module.get_monthly_stats()
    assert stats == {month: float(month) for month in range(1, 13)}


@kp125m_smart
async def test_get_daily_stats_defaults_to_current_month(dev: SmartDevice) -> None:
    """With no year/month, the current month's days are returned."""
    energy_module = _get_v2_energy_module(dev)
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    stats = await energy_module.get_daily_stats()
    assert set(stats) == set(range(1, days_in_month + 1))


@kp125m_smart
async def test_get_daily_stats_fourth_quarter(dev: SmartDevice) -> None:
    """A Q4 month uses next-year Jan 1 as the quarter end."""
    energy_module = _get_v2_energy_module(dev)

    year, month = 2024, 11
    days_in_month = calendar.monthrange(year, month)[1]

    stats = await energy_module.get_daily_stats(year=year, month=month, kwh=False)
    assert set(stats) == set(range(1, days_in_month + 1))
    # kwh=False returns raw Wh (day_of_year * 10 from the fake transport).
    assert stats[1] == date(year, month, 1).timetuple().tm_yday * 10


@kp125m_smart
async def test_query_energy_data_edge_cases(dev: SmartDevice) -> None:
    """A zero-width window makes no calls; a stalled cursor stops the loop."""
    energy_module = _get_v2_energy_module(dev)

    # start == end -> no request, empty result.
    assert await energy_module._query_energy_data(300, 300, 1440) == []

    async def stalled_call(method: str, params: dict | None = None) -> dict:
        # Always report the same end_timestamp, i.e. no forward progress.
        assert params is not None
        return {
            "get_energy_data": {
                "end_timestamp": params["start_timestamp"],
                "data": [7],
            }
        }

    with patch.object(energy_module, "call", side_effect=stalled_call):
        data = await energy_module._query_energy_data(0, 300, 1440)
    assert data == [7]  # single page, no infinite loop


@kp125m_smart
async def test_erase_stats_not_supported(dev: SmartDevice) -> None:
    """erase_stats is not implemented for SMART devices."""
    energy_module = _get_v2_energy_module(dev)
    with pytest.raises(KasaException, match="does not support erasing"):
        await energy_module.erase_stats()
