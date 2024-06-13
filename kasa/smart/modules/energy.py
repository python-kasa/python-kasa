"""Implementation of energy monitoring module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...emeterstatus import EmeterStatus
from ...exceptions import KasaException
from ...interfaces.energy import Energy as EnergyInterface
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    pass


class Energy(SmartModule, EnergyInterface):
    """Implementation of energy monitoring module."""

    REQUIRED_COMPONENT = "energy_monitoring"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        req = {
            "get_energy_usage": None,
        }
        if self.supported_version > 1:
            req["get_current_power"] = None
        return req

    @property
    def current_consumption(self) -> float | None:
        """Current power in watts."""
        if power := self.energy.get("current_power"):
            return power / 1_000
        return None

    @property
    def energy(self):
        """Return get_energy_usage results."""
        if en := self.data.get("get_energy_usage"):
            return en
        return self.data

    def _get_status_from_energy(self, energy) -> EmeterStatus:
        return EmeterStatus(
            {
                "power_mw": energy.get("current_power"),
                "total": energy.get("today_energy") / 1_000,
            }
        )

    @property
    def status(self):
        """Get the emeter status."""
        return self._get_status_from_energy(self.energy)

    async def get_status(self):
        """Return real-time statistics."""
        res = await self.call("get_energy_usage")
        return self._get_status_from_energy(res["get_energy_usage"])

    @property
    def consumption_this_month(self) -> float | None:
        """Get the emeter value for this month."""
        return self.energy.get("month_energy")

    @property
    def consumption_today(self) -> float | None:
        """Get the emeter value for today."""
        return self.energy.get("today_energy")

    @property
    def consumption_total(self) -> float | None:
        """Return total consumption since last reboot in kWh."""
        return None

    @property
    def current(self) -> float | None:
        """Return the current in A."""
        return None

    @property
    def voltage(self) -> float | None:
        """Get the current voltage in V."""
        return None

    @property
    def has_voltage_current(self) -> bool:
        """Return True if the device reports current and voltage."""
        return False

    @property
    def has_total_consumption(self) -> bool:
        """Return True if device reports total energy consumption since last reboot."""
        return False

    async def _deprecated_get_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        return self.status

    @property
    def has_periodic_stats(self) -> bool:
        """Return True if device can report statistics for different time periods."""
        return False

    async def erase_stats(self):
        """Erase all stats."""
        raise KasaException("Device does not support periodic statistics")

    async def get_daystat(self, *, year=None, month=None, kwh=True) -> dict:
        """Return daily stats for the given year & month.

        The return value is a dictionary of {day: energy, ...}.
        """
        raise KasaException("Device does not support periodic statistics")

    async def get_monthstat(self, *, year=None, kwh=True) -> dict:
        """Return monthly stats for the given year."""
        raise KasaException("Device does not support periodic statistics")
