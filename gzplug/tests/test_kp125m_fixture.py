"""Energy mapping checked against the real KP125M fixture.

This is the one test coupled to upstream's fixture machinery, and it is
deliberately isolated in its own file: if an upstream merge changes those
helpers, exactly one clearly-labelled test breaks.

What it guards is the mapping that is most likely to be silently wrong --
which library property feeds which CSV column, and in which units. The device
reports milliwatts and milliamps on the wire; the library normalises to watts,
amps and kWh; the CSV must record the normalised values.
"""

from __future__ import annotations

import pytest

from gzplug.core.events import EventBus
from gzplug.core.session import PlugSession
from kasa import DeviceConfig, Module

pytest.importorskip("tests.device_fixtures", reason="upstream test helpers")

from tests.device_fixtures import get_device_for_fixture_protocol  # noqa: E402

FIXTURE = "KP125M(US)_1.0_1.2.3.json"


@pytest.fixture
async def kp125m():
    """Return a KP125M backed by the fake protocol -- no sockets, no hardware."""
    device = await get_device_for_fixture_protocol(FIXTURE, "SMART")
    assert device is not None, f"fixture {FIXTURE} not found"
    return device


async def test_fixture_exposes_energy_monitoring(kp125m):
    assert kp125m.modules.get(Module.Energy) is not None


async def test_session_maps_energy_into_a_sample(kp125m, monkeypatch):
    """The plug's metering should arrive in the units the CSV documents."""
    monkeypatch.setattr(
        "gzplug.core.session.Device.connect",
        staticmethod(lambda *, config: _ready(kp125m)),
    )
    session = PlugSession(
        "kp125m", "KP125M", DeviceConfig(host="127.0.0.123"), EventBus()
    )

    sample = await session.connect()

    energy = kp125m.modules[Module.Energy]
    assert sample.is_on is kp125m.is_on
    assert sample.power_w == energy.current_consumption
    assert sample.voltage_v == energy.voltage
    assert sample.current_a == energy.current
    assert sample.energy_today_kwh == energy.consumption_today

    # The fixture reports 1003 mW / 121215 mV; anything near those raw numbers
    # in the watt/volt columns would mean the units were not normalised.
    assert sample.power_w is not None
    assert sample.power_w < 100
    assert sample.voltage_v is not None
    assert 100 < sample.voltage_v < 140


async def _ready(device):
    """Coroutine adapter so the patched connect can return an existing device."""
    return device


async def test_profile_from_a_discovered_device_round_trips(kp125m):
    """A saved profile must rebuild the exact connection the plug needs.

    This is what lets normal startup skip discovery, so getting the
    connection parameters wrong here would only show up on a bench.
    """
    from gzplug.config import AppConfig, BenchProfile

    profile = BenchProfile.from_device(kp125m, "Bench 2 - plug A")
    assert profile.id == "bench-2-plug-a"
    assert "credentials" not in profile.config

    config = AppConfig(username="lab@example.com", password="pw")
    rebuilt = profile.device_config(config.credentials)

    assert rebuilt.host == kp125m.config.host
    assert rebuilt.connection_type == kp125m.config.connection_type
    assert rebuilt.credentials is not None
    assert rebuilt.credentials.username == "lab@example.com"
