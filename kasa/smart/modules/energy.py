"""Implementation of energy monitoring module."""

from __future__ import annotations

from typing import NoReturn

from ...emeterstatus import EmeterStatus
from ...exceptions import KasaException
from ...interfaces.energy import Energy as EnergyInterface
from ..smartmodule import SmartModule, raise_if_update_error


class Energy(SmartModule, EnergyInterface):
    """Implementation of energy monitoring module."""

    REQUIRED_COMPONENT = "energy_monitoring"

    async def _post_update_hook(self) -> None:
        if "voltage_mv" in self.data.get("get_emeter_data", {}):
            self._supported = (
                self._supported | EnergyInterface.ModuleFeature.VOLTAGE_CURRENT
            )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        req = {
            "get_energy_usage": None,
        }
        if self.supported_version > 1:
            req["get_current_power"] = None
            req["get_emeter_data"] = None
            req["get_emeter_vgain_igain"] = None
        return req

    @property
    @raise_if_update_error
    def current_consumption(self) -> float | None:
        """Current power in watts."""
        if (power := self.energy.get("current_power")) is not None or (
            power := self.data.get("get_emeter_data", {}).get("power_mw")
        ) is not None:
            return power / 1_000
        # Fallback if get_energy_usage does not provide current_power,
        # which can happen on some newer devices (e.g. P304M).
        elif (
            power := self.data.get("get_current_power", {}).get("current_power")
        ) is not None:
            return power
        return None

    @property
    @raise_if_update_error
    def energy(self) -> dict:
        """Return get_energy_usage results."""
        if en := self.data.get("get_energy_usage"):
            return en
        return self.data

    def _get_status_from_energy(self, energy: dict) -> EmeterStatus:
        return EmeterStatus(
            {
                "power_mw": energy.get("current_power", 0),
                "total": energy.get("today_energy", 0) / 1_000,
            }
        )

    @property
    @raise_if_update_error
    def status(self) -> EmeterStatus:
        """Get the emeter status."""
        if "get_emeter_data" in self.data:
            return EmeterStatus(self.data["get_emeter_data"])
        else:
            return self._get_status_from_energy(self.energy)

    async def get_status(self) -> EmeterStatus:
        """Return real-time statistics."""
        if "get_emeter_data" in self.data:
            res = await self.call("get_emeter_data")
            return EmeterStatus(res["get_emeter_data"])
        else:
            res = await self.call("get_energy_usage")
            return self._get_status_from_energy(res["get_energy_usage"])

    @property
    @raise_if_update_error
    def consumption_this_month(self) -> float | None:
        """Get the emeter value for this month in kWh."""
        return self.energy.get("month_energy", 0) / 1_000

    @property
    @raise_if_update_error
    def consumption_today(self) -> float | None:
        """Get the emeter value for today in kWh."""
        return self.energy.get("today_energy", 0) / 1_000

    @property
    @raise_if_update_error
    def consumption_total(self) -> float | None:
        """Return total consumption since last reboot in kWh."""
        return None

    @property
    @raise_if_update_error
    def current(self) -> float | None:
        """Return the current in A."""
        ma = self.data.get("get_emeter_data", {}).get("current_ma")
        return ma / 1000 if ma else None

    @property
    @raise_if_update_error
    def voltage(self) -> float | None:
        """Get the current voltage in V."""
        mv = self.data.get("get_emeter_data", {}).get("voltage_mv")
        return mv / 1000 if mv else None

    async def _deprecated_get_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        return self.status

    async def erase_stats(self) -> NoReturn:
        """Erase all stats."""
        raise KasaException("Device does not support periodic statistics")

    async def get_daily_stats(
        self, *, year: int | None = None, month: int | None = None, kwh: bool = True
    ) -> dict:
        """Return daily stats for the given year & month.

        The return value is a dictionary of {day: energy, ...}.
        """
        raise KasaException("Device does not support periodic statistics")

    async def get_monthly_stats(
        self, *, year: int | None = None, kwh: bool = True
    ) -> dict:
        """Return monthly stats for the given year."""
        raise KasaException("Device does not support periodic statistics")

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        # Energy module is not supported on P304M parent device
        return "device_on" in self._device.sys_info
