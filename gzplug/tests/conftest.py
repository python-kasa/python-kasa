"""Fakes for exercising the run engine without hardware or sockets."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from gzplug.core.events import EventBus
from kasa import KasaException, Module


class FakeEnergy:
    """Just enough of the Energy interface for PlugSession to read."""

    def __init__(
        self,
        current_consumption: float | None = 12.5,
        voltage: float | None = 121.2,
        current: float | None = 0.103,
        consumption_today: float | None = 0.02,
        consumption_this_month: float | None = 0.971,
    ) -> None:
        self.current_consumption = current_consumption
        self.voltage = voltage
        self.current = current
        self.consumption_today = consumption_today
        self.consumption_this_month = consumption_this_month


class FakeFeature:
    """One entry of the device's feature map."""

    def __init__(self, value: Any) -> None:
        self.value = value


#: Mirrors what the KP125M fixture actually exposes, so the fakes cannot
#: drift into offering fields a real plug does not have.
DEFAULT_FEATURES: dict[str, Any] = {
    "overheated": False,
    "overloaded": False,
    "rssi": -50,
    "signal_level": 2,
    "ssid": "bench-wifi",
    "auto_off_enabled": False,
    "auto_off_minutes": 120,
    "auto_update_enabled": True,
    "update_available": None,
    "power_protection_threshold": 0,
    "led": True,
}


class FakeDevice:
    """A plug that can be told to misbehave in specific, bench-realistic ways.

    Two failure modes matter here and both have bitten the scratch scripts'
    successors elsewhere: a device that refuses the connection, and a device
    that *accepts* a command and then does not perform it.
    """

    def __init__(
        self,
        *,
        is_on: bool = False,
        alias: str = "Fake Plug",
        model: str = "KP125M",
        energy: FakeEnergy | None = None,
        fail_updates: int = 0,
        fail_commands: int = 0,
        lying: bool = False,
        device_id: str = "FAKE0000000000000000000000000001",
        features: dict[str, Any] | None = None,
    ) -> None:
        self._is_on = is_on
        self.alias = alias
        self.model = model
        self.host = "127.0.0.1"
        self.device_id = device_id
        self.mac = "78:8C:B5:00:00:01"
        self.on_since = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
        self.hw_info = {"sw_ver": "1.2.3 Build 240624", "hw_ver": "1.0"}
        self.features = {
            name: FakeFeature(value)
            for name, value in {**DEFAULT_FEATURES, **(features or {})}.items()
        }
        self.modules: dict[Any, Any] = {}
        if energy is not None:
            self.modules[Module.Energy] = energy
        #: Remaining failures to inject before behaving.
        self.fail_updates = fail_updates
        self.fail_commands = fail_commands
        #: Accept commands but never actually switch.
        self.lying = lying
        self.updates = 0
        self.commands = 0
        self.disconnects = 0

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def update(self, update_children: bool = True) -> None:
        self.updates += 1
        if self.fail_updates > 0:
            self.fail_updates -= 1
            raise KasaException("injected update failure")

    async def turn_on(self, **kwargs: Any) -> dict:
        return self._switch(True)

    async def turn_off(self, **kwargs: Any) -> dict:
        return self._switch(False)

    def _switch(self, on: bool) -> dict:
        self.commands += 1
        if self.fail_commands > 0:
            self.fail_commands -= 1
            raise KasaException("injected command failure")
        if not self.lying:
            self._is_on = on
        return {}

    async def disconnect(self) -> None:
        self.disconnects += 1


@pytest.fixture
def bus() -> EventBus:
    """Return a fresh event bus."""
    return EventBus()


@pytest.fixture
def fake_device() -> FakeDevice:
    """Return a well-behaved plug that starts switched off."""
    return FakeDevice(energy=FakeEnergy())


@pytest.fixture
def patch_connect(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Make PlugSession dial a fake instead of the network.

    Accepts one device, or a mapping of host to device when a test needs each
    session to drive its own plug. Returns the call counter so a test can
    assert how many times a redial happened.
    """

    def install(device: FakeDevice | dict[str, FakeDevice]) -> dict[str, int]:
        calls = {"connect": 0}
        by_host = device if isinstance(device, dict) else None

        async def fake_connect(*, config: Any) -> FakeDevice:
            calls["connect"] += 1
            if by_host is None:
                return device  # type: ignore[return-value]
            return by_host[config.host]

        monkeypatch.setattr(
            "gzplug.core.session.Device.connect", staticmethod(fake_connect)
        )
        return calls

    return install
