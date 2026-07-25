"""Tests for the Lock module (SMART.TAPOLOCK / DL100).

Mirrors the structure of tests/smart/modules/test_childlock.py (setter + boolean
state) and test_contact.py (simple sysinfo-key sensor).

Polarity is intentionally counterintuitive and must NOT be inverted:
    lock_status == 0  -> bolt extended  -> LOCKED   (is_locked is True)
    lock_status == 1  -> bolt retracted -> UNLOCKED (is_locked is False)
"""

from __future__ import annotations

from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize
from ...fakeprotocol_smart import FakeSmartTransport

# The DL100 has no dedicated component for the lock; the module loads off the
# `lock_status` sysinfo key (SYSINFO_LOOKUP_KEYS=["lock_status"]), so we select
# the fixture by model rather than component_filter.
lock_iter = parametrize(
    "has lock",
    model_filter={"DL100"},
    protocol_filter={"SMART"},
)

# Module.Lock is now a typed ModuleName[Lock], so use it instead of the bare
# string key. This gives static checkers the concrete Lock type back from
# dev.modules.get()/[] instead of the base SmartModule.
LOCK_MODULE = Module.Lock


def _set_lock_status(dev: SmartDevice, value: int) -> None:
    """Flip the device's reported lock_status in the fake transport fixture.

    Updates lock_status in every device-info key present in the transport's
    info dict (get_device_info and, if present, getDeviceInfo) so that
    is_locked reflects the change after the next update() call.
    """
    transport = dev.protocol._transport
    assert isinstance(transport, FakeSmartTransport)
    info = transport.info
    for key in ("get_device_info", "getDeviceInfo"):
        if key in info:
            info[key]["lock_status"] = value


@lock_iter
async def test_lock_module_loaded(dev: SmartDevice):
    """Lock module loads whenever lock_status is present in sysinfo."""
    lock = dev.modules.get(LOCK_MODULE)
    assert lock is not None
    assert "lock_status" in dev.sys_info


@lock_iter
async def test_is_locked_polarity(dev: SmartDevice):
    """lock_status 0 -> True (LOCKED), 1 -> False (UNLOCKED). Do not invert.

    Drives real data through the fake transport + update() rather than patching
    module internals, so it stays correct no matter where is_locked reads from.
    """
    lock = dev.modules.get(LOCK_MODULE)
    assert lock is not None

    # Fixture ships lock_status=0 (bolt extended = LOCKED).
    _set_lock_status(dev, 0)
    await dev.update()
    assert lock.is_locked is True

    # Retract the bolt -> UNLOCKED.
    _set_lock_status(dev, 1)
    await dev.update()
    assert lock.is_locked is False


@lock_iter
async def test_lock_sends_setlockstatus(dev: SmartDevice, mocker: MockerFixture):
    """lock()/unlock() send setLockStatus with the correct owner params."""
    lock = dev.modules.get(LOCK_MODULE)
    assert lock is not None
    call = mocker.patch.object(lock, "call", new_callable=mocker.AsyncMock)

    await lock.lock()
    call.assert_called_with(
        "setLockStatus", {"lock_status": 0, "sa_user_id": "local_1"}
    )

    await lock.unlock()
    call.assert_called_with(
        "setLockStatus", {"lock_status": 1, "sa_user_id": "local_1"}
    )


@lock_iter
async def test_lock_command_omits_owner_forbidden_fields(
    dev: SmartDevice, mocker: MockerFixture
):
    """Owner path must NOT include shared-user fields."""
    lock = dev.modules.get(LOCK_MODULE)
    assert lock is not None
    call = mocker.patch.object(lock, "call", new_callable=mocker.AsyncMock)

    await lock.lock()
    _method, params = call.call_args.args
    for forbidden in ("tplink_account", "access_info", "lock_type", "unlock_type"):
        assert forbidden not in params


@lock_iter
async def test_battery(dev: SmartDevice):
    """Battery / battery_low read from sysinfo (DL100 lacks battery_detect)."""
    lock = dev.modules.get(LOCK_MODULE)
    assert lock is not None
    assert lock.battery == 81
    assert lock.battery_low is False


@lock_iter
async def test_battery_features_present(dev: SmartDevice):
    """battery_level and battery_low features are exposed by the Lock module."""
    lock = dev.modules.get(LOCK_MODULE)
    assert lock is not None
    assert "battery_level" in dev.features
    assert "battery_low" in dev.features
