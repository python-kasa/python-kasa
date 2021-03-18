import pytest

from kasa import SmartDeviceException

from .conftest import has_emeter, no_emeter, pytestmark
from .newfakes import CURRENT_CONSUMPTION_SCHEMA


@no_emeter
async def test_no_emeter(dev):
    assert not dev.has_emeter

    with pytest.raises(SmartDeviceException):
        await dev.get_emeter_realtime()
    with pytest.raises(SmartDeviceException):
        await dev.get_emeter_daily()
    with pytest.raises(SmartDeviceException):
        await dev.get_emeter_monthly()
    with pytest.raises(SmartDeviceException):
        await dev.erase_emeter_stats()


@has_emeter
async def test_get_emeter_realtime(dev):
    if dev.is_strip:
        pytest.skip("Disabled for strips temporarily")

    assert dev.has_emeter

    current_emeter = await dev.get_emeter_realtime()
    CURRENT_CONSUMPTION_SCHEMA(current_emeter)


@has_emeter
async def test_get_emeter_daily(dev):
    if dev.is_strip:
        pytest.skip("Disabled for strips temporarily")

    assert dev.has_emeter

    assert await dev.get_emeter_daily(year=1900, month=1) == {}

    d = await dev.get_emeter_daily()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = await dev.get_emeter_daily(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter
async def test_get_emeter_monthly(dev):
    if dev.is_strip:
        pytest.skip("Disabled for strips temporarily")

    assert dev.has_emeter

    assert await dev.get_emeter_monthly(year=1900) == {}

    d = await dev.get_emeter_monthly()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = await dev.get_emeter_monthly(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter
async def test_emeter_status(dev):
    if dev.is_strip:
        pytest.skip("Disabled for strips temporarily")

    assert dev.has_emeter

    d = await dev.get_emeter_realtime()

    with pytest.raises(KeyError):
        assert d["foo"]

    assert d["power_mw"] == d["power"] * 1000
    # bulbs have only power according to tplink simulator.
    if not dev.is_bulb:
        assert d["voltage_mv"] == d["voltage"] * 1000

        assert d["current_ma"] == d["current"] * 1000
        assert d["total_wh"] == d["total"] * 1000


@pytest.mark.skip("not clearing your stats..")
@has_emeter
async def test_erase_emeter_stats(dev):
    assert dev.has_emeter

    await dev.erase_emeter()


@has_emeter
async def test_current_consumption(dev):
    if dev.is_strip:
        pytest.skip("Disabled for strips temporarily")

    if dev.has_emeter:
        x = await dev.current_consumption()
        assert isinstance(x, float)
        assert x >= 0.0
    else:
        assert await dev.current_consumption() is None


async def test_emeterstatus_missing_current():
    """KL125 does not report 'current' for emeter."""
    from kasa import EmeterStatus

    regular = EmeterStatus(
        {"err_code": 0, "power_mw": 0, "total_wh": 13, "current_ma": 123}
    )
    assert regular["current"] == 0.123

    with pytest.raises(KeyError):
        regular["invalid_key"]

    missing_current = EmeterStatus({"err_code": 0, "power_mw": 0, "total_wh": 13})
    assert missing_current["current"] is None
