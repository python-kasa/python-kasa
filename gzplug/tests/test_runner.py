"""RunEngine: plan validation, fail-fast vs continue-on-error, restore."""

from __future__ import annotations

import asyncio

import pytest

from gzplug.core.events import EventKind
from gzplug.core.registry import DeviceRegistry, RegistryError
from gzplug.core.runner import RunEngine, RunFailed, RunPlan, RunState
from gzplug.core.session import PlugSession, RetryPolicy
from kasa import DeviceConfig

from .conftest import FakeDevice


def make_registry(bus, devices: dict[str, FakeDevice], *, retry=None) -> DeviceRegistry:
    registry = DeviceRegistry()
    for profile_id in devices:
        registry.add(
            PlugSession(
                profile_id,
                profile_id.title(),
                DeviceConfig(host="127.0.0.1"),
                bus,
                retry=retry or RetryPolicy(),
            )
        )
    return registry


@pytest.fixture
def instant_plan():
    """Build a plan with no dwell time, so tests do not sleep."""

    def build(devices, **kwargs):
        params = {
            "devices": tuple(devices),
            "cycles": 2,
            "on_time_s": 0.0,
            "off_time_s": 0.0,
        }
        params.update(kwargs)
        return RunPlan(**params)

    return build


# -- plan validation ---------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"devices": ()}, "at least one device"),
        ({"devices": ("a", "a")}, "more than once"),
        ({"cycles": 0}, "at least one cycle"),
        ({"on_time_s": -1}, "cannot be negative"),
    ],
)
def test_invalid_plans_are_rejected(kwargs, message):
    params = {"devices": ("a",), "cycles": 1, "on_time_s": 0.0, "off_time_s": 0.0}
    params.update(kwargs)
    with pytest.raises(ValueError, match=message):
        RunPlan(**params)


def test_registry_caps_concurrent_plugs(bus):
    registry = DeviceRegistry(max_devices=2)
    for name in ("a", "b"):
        registry.add(PlugSession(name, name, DeviceConfig(host="127.0.0.1"), bus))
    with pytest.raises(RegistryError, match="at most 2"):
        registry.add(PlugSession("c", "c", DeviceConfig(host="127.0.0.1"), bus))


# -- execution ---------------------------------------------------------


async def test_run_cycles_the_plug_and_restores_it(bus, patch_connect, instant_plan):
    device = FakeDevice(is_on=True)
    patch_connect(device)
    registry = make_registry(bus, {"bench-a": device})
    await registry.connect_all()

    engine = RunEngine(registry, bus)
    await engine.execute(instant_plan(["bench-a"], cycles=3))

    assert engine.status.state is RunState.COMPLETED
    assert engine.status.cycle == 3
    # 3 on + 3 off + 1 restore
    assert device.commands == 7
    assert device.is_on is True, "the plug should be left as it was found"


async def test_no_restore_leaves_the_plug_where_the_run_left_it(
    bus, patch_connect, instant_plan
):
    device = FakeDevice(is_on=True)
    patch_connect(device)
    registry = make_registry(bus, {"bench-a": device})
    await registry.connect_all()

    await RunEngine(registry, bus).execute(
        instant_plan(["bench-a"], cycles=1, restore_state=False)
    )

    assert device.is_on is False


async def test_fail_fast_stops_the_run(bus, patch_connect, instant_plan):
    """The default: an anomaly ends the run rather than being papered over."""
    device = FakeDevice(fail_commands=99)
    patch_connect(device)
    registry = make_registry(bus, {"bench-a": device})
    await registry.connect_all()
    engine = RunEngine(registry, bus)

    with pytest.raises(RunFailed):
        await engine.execute(instant_plan(["bench-a"], cycles=5))

    assert engine.status.state is RunState.FAILED
    assert engine.status.cycle == 1, "it should not have reached cycle 2"


async def test_continue_on_error_presses_on_and_counts_faults(
    bus, patch_connect, instant_plan
):
    device = FakeDevice(fail_commands=2)
    patch_connect(device)
    registry = make_registry(
        bus,
        {"bench-a": device},
        retry=RetryPolicy(enabled=True, max_attempts=1, initial_backoff_s=0),
    )
    await registry.connect_all()
    engine = RunEngine(registry, bus)

    await engine.execute(instant_plan(["bench-a"], cycles=3, continue_on_error=True))

    assert engine.status.state is RunState.COMPLETED
    assert engine.status.cycle == 3
    assert engine.status.faults["bench-a"] == 2


async def test_multiple_plugs_switch_together(bus, patch_connect, instant_plan):
    """Each plug in the plan is driven, and each is restored."""
    a = FakeDevice(is_on=False)
    b = FakeDevice(is_on=True)
    patch_connect({"192.168.0.1": a, "192.168.0.2": b})

    registry = DeviceRegistry()
    for profile_id, host in (("bench-a", "192.168.0.1"), ("bench-b", "192.168.0.2")):
        registry.add(
            PlugSession(profile_id, profile_id.title(), DeviceConfig(host=host), bus)
        )
    await registry.connect_all()

    await RunEngine(registry, bus).execute(
        instant_plan(["bench-a", "bench-b"], cycles=2)
    )

    # 2 on + 2 off + 1 restore, per plug.
    assert a.commands == 5
    assert b.commands == 5
    assert a.is_on is False, "plug A was found off and should be left off"
    assert b.is_on is True, "plug B was found on and should be left on"


async def test_stop_aborts_and_still_restores(bus, patch_connect):
    device = FakeDevice(is_on=True)
    patch_connect(device)
    registry = make_registry(bus, {"bench-a": device})
    await registry.connect_all()
    engine = RunEngine(registry, bus)

    # Long dwell so the run is definitely mid-cycle when stopped.
    engine.start(
        RunPlan(devices=("bench-a",), cycles=100, on_time_s=30.0, off_time_s=30.0)
    )
    await asyncio.sleep(0)
    while engine.status.cycle < 1:
        await asyncio.sleep(0)
    await engine.stop()

    assert engine.status.state is RunState.ABORTED
    assert device.is_on is True, "an aborted run must still put the plug back"


async def test_run_publishes_start_and_finish(bus, patch_connect, instant_plan):
    patch_connect(FakeDevice())
    registry = make_registry(bus, {"bench-a": FakeDevice()})
    await registry.connect_all()

    with bus.subscribe(maxsize=0) as queue:
        await RunEngine(registry, bus).execute(instant_plan(["bench-a"], cycles=1))
        kinds = [queue.get_nowait().kind for _ in range(queue.qsize())]

    assert kinds[0] is EventKind.RUN_STARTED
    assert kinds[-1] is EventKind.RUN_FINISHED
    assert EventKind.CYCLE_STARTED in kinds
