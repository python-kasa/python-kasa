"""PlugSession: read-back verification, retry policy, teardown."""

from __future__ import annotations

import pytest

from gzplug.core.events import EventBus, EventKind, Result
from gzplug.core.session import PlugSession, RetryPolicy, SessionFault
from kasa import DeviceConfig

from .conftest import FakeDevice, FakeEnergy


def make_session(bus: EventBus, **kwargs) -> PlugSession:
    return PlugSession(
        "bench-a", "Bench A", DeviceConfig(host="127.0.0.1"), bus, **kwargs
    )


async def test_connect_captures_original_state(bus, patch_connect):
    device = FakeDevice(is_on=True, energy=FakeEnergy())
    patch_connect(device)
    session = make_session(bus)

    sample = await session.connect()

    assert session.connected
    assert session.original_state is True
    assert sample.is_on is True
    assert sample.power_w == 12.5
    assert sample.energy_today_kwh == 0.02


async def test_read_without_energy_module_still_reports_state(bus, patch_connect):
    patch_connect(FakeDevice(is_on=False, energy=None))
    session = make_session(bus)
    await session.connect()

    sample = await session.read()

    assert sample.is_on is False
    assert sample.power_w is None


async def test_set_state_verifies_the_device_actually_switched(bus, patch_connect):
    """A command that is accepted but not performed must not count as success."""
    patch_connect(FakeDevice(lying=True))
    session = make_session(bus)
    await session.connect()

    with pytest.raises(SessionFault, match="reports off"):
        await session.set_state(True)


async def test_fail_fast_does_not_retry(bus, patch_connect):
    device = FakeDevice(fail_commands=99)
    patch_connect(device)
    session = make_session(bus)
    await session.connect()

    with pytest.raises(SessionFault):
        await session.set_state(True)

    assert device.commands == 1, "fail-fast must make exactly one attempt"
    assert session.fault_count == 1


async def test_retry_recovers_from_a_transient_fault(bus, patch_connect):
    device = FakeDevice(fail_commands=2)
    calls = patch_connect(device)
    session = make_session(
        bus,
        retry=RetryPolicy(enabled=True, max_attempts=3, initial_backoff_s=0),
    )
    await session.connect()

    sample = await session.set_state(True)

    assert sample.is_on is True
    assert session.fault_count == 2, "both transient failures should be recorded"
    assert calls["connect"] == 3, "each retry should redial"


async def test_retry_gives_up_and_reports(bus, patch_connect):
    patch_connect(FakeDevice(fail_commands=99))
    session = make_session(
        bus, retry=RetryPolicy(enabled=True, max_attempts=2, initial_backoff_s=0)
    )
    await session.connect()

    with pytest.raises(SessionFault):
        await session.set_state(True)
    assert session.fault_count == 2


async def test_restore_returns_the_plug_to_its_starting_state(bus, patch_connect):
    device = FakeDevice(is_on=True)
    patch_connect(device)
    session = make_session(bus)
    await session.connect()

    await session.set_state(False)
    assert device.is_on is False

    await session.restore()
    assert device.is_on is True


async def test_disconnect_is_idempotent_and_always_reaches_the_device(
    bus, patch_connect
):
    """Device has no async context manager, so this must never be skipped."""
    device = FakeDevice()
    patch_connect(device)
    session = make_session(bus)
    await session.connect()

    await session.disconnect()
    await session.disconnect()

    assert device.disconnects == 1
    assert not session.connected


async def test_faults_are_published_with_attempt_detail(bus, patch_connect):
    patch_connect(FakeDevice(fail_commands=99))
    session = make_session(bus)
    await session.connect()

    with bus.subscribe() as queue:
        with pytest.raises(SessionFault):
            await session.set_state(True)
        events = [queue.get_nowait() for _ in range(queue.qsize())]

    faults = [e for e in events if e.kind is EventKind.FAULT]
    assert len(faults) == 1
    assert faults[0].result is Result.ERROR
    assert "attempt 1/1" in (faults[0].detail or "")
