"""Implementation of energy monitoring module."""

from __future__ import annotations

from ...emeterstatus import EmeterStatus
from ...exceptions import KasaException
from ...interfaces.energy import Energy as EnergyInterface
from ..smartmodule import SmartModule, raise_if_update_error


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
    @raise_if_update_error
    def current_consumption(self) -> float | None:
        """Current power in watts."""
        if (power := self.energy.get("current_power")) is not None:
            return power / 1_000
        # Fallback if get_energy_usage does not provide current_power,
        # which can happen on some newer devices (e.g. P304M).
        elif (
            power := self.data.get("get_current_power").get("current_power")
        ) is not None:
            return power
        return None

    @property
    @raise_if_update_error
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
    @raise_if_update_error
    def status(self):
        """Get the emeter status."""
        return self._get_status_from_energy(self.energy)

    async def get_status(self):
        """Return real-time statistics."""
        res = await self.call("get_energy_usage")
        return self._get_status_from_energy(res["get_energy_usage"])

    @property
    @raise_if_update_error
    def consumption_this_month(self) -> float | None:
        """Get the emeter value for this month in kWh."""
        return self.energy.get("month_energy") / 1_000

    @property
    @raise_if_update_error
    def consumption_today(self) -> float | None:
        """Get the emeter value for today in kWh."""
        return self.energy.get("today_energy") / 1_000

    @property
    @raise_if_update_error
    def consumption_total(self) -> float | None:
        """Return total consumption since last reboot in kWh."""
        return None

    @property
    @raise_if_update_error
    def current(self) -> float | None:
        """Return the current in A."""
        return None

    @property
    @raise_if_update_error
    def voltage(self) -> float | None:
        """Get the current voltage in V."""
        return None

    async def _deprecated_get_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        return self.status

    async def erase_stats(self):
        """Erase all stats."""
        raise KasaException("Device does not support periodic statistics")

    async def get_daily_stats(self, *, year=None, month=None, kwh=True) -> dict:
        """Return daily stats for the given year & month.

        The return value is a dictionary of {day: energy, ...}.
        """
        raise KasaException("Device does not support periodic statistics")

    async def get_monthly_stats(self, *, year=None, kwh=True) -> dict:
        """Return monthly stats for the given year."""
        raise KasaException("Device does not support periodic statistics")

    async def _check_supported(self):
        """Additional check to see if the module is supported by the device."""
        # Energy module is not supported on P304M parent device
        return "device_on" in self._device.sys_info
