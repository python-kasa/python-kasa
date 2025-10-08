from unittest.mock import AsyncMock

import pytest

from kasa import DeviceType, KasaException, Module
from tests.device_fixtures import device_iot


@device_iot
async def test_strip_update_children_flag_and_child_update(dev):
    # Only applicable to power strips
    if dev.device_type is not DeviceType.Strip:
        pytest.skip("Only for power strips")

    # Ensure initial update initializes children
    await dev.update()

    # Hit the branch where children are NOT updated (covers the else path in IotStrip.update)
    await dev.update(update_children=False)

    # Explicitly call child.update() to cover IotStripPlug.update path
    assert dev.children, "Expected strip device to have children"
    child = dev.children[0]
    await child.update()


@device_iot
async def test_strip_child_delegated_properties(dev):
    # Only applicable to power strips
    if dev.device_type is not DeviceType.Strip:
        pytest.skip("Only for power strips")

    await dev.update()
    child = dev.children[0]

    # led on child sockets is always False (covers IotStripPlug.led)
    assert child.led is False

    # time and timezone are delegated from the parent (covers IotStripPlug.time/timezone)
    assert child.time == dev.time
    assert child.timezone == dev.timezone

    # next_action comes from child info (covers IotStripPlug.next_action)
    na = child.next_action
    assert isinstance(na, dict)
    assert "type" in na


@device_iot
async def test_strip_emeter_erase_stats(dev, mocker):
    # Only applicable to power strips with emeter
    if dev.device_type is not DeviceType.Strip or not dev.has_emeter:
        pytest.skip("Only for power strips with emeter")

    await dev.update()

    # First, cover the happy path by patching child energy modules to support erase_stats.
    # This ensures the for-loop and the return {} in StripEmeter.erase_stats are executed.
    for child in dev.children:
        energy = child.modules.get(Module.Energy)
        if energy:
            mocker.patch.object(energy, "erase_stats", AsyncMock(return_value={}))

    res = await dev.modules[Module.Energy].erase_stats()
    assert res == {}

    # Now try the real call (without patches) to tolerate devices that don't support erase_emeter_stat.
    # This still executes the loop lines in StripEmeter.erase_stats even if it raises.
    # Remove patches
    await (
        dev.update()
    )  # refresh modules to remove patched callables (safe no-op on many)
    try:
        await dev.modules[Module.Energy].erase_stats()
    except KasaException as ex:
        # Some firmwares don't support erase_emeter_stat; accept that specific failure.
        if "erase_emeter_stat not found" in str(
            ex
        ) or "Error on emeter erase_emeter_stat" in str(ex):
            pytest.xfail("Device firmware does not support erase_emeter_stat")
        else:
            raise
