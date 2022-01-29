"""Implementation of the emeter module."""
from datetime import datetime
from typing import Dict, Optional

from ..emeterstatus import EmeterStatus
from .usage import Usage


class Emeter(Usage):
    """Emeter module."""

    @property  # type: ignore
    def realtime(self) -> EmeterStatus:
        """Return current energy readings."""
        return EmeterStatus(self.data["get_realtime"])

    @property
    def emeter_today(self) -> Optional[float]:
        """Return today's energy consumption in kWh."""
        raw_data = self.daily_data
        today = datetime.now().day
        data = self._emeter_convert_emeter_data(raw_data)

        return data.get(today)

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Return this month's energy consumption in kWh."""
        raw_data = self.monthly_data
        current_month = datetime.now().month
        data = self._emeter_convert_emeter_data(raw_data)

        return data.get(current_month)

    async def erase_stats(self):
        """Erase all stats.

        Uses different query than usage meter.
        """
        return await self.call("erase_emeter_stat")

    async def get_realtime(self):
        """Return real-time statistics."""
        return await self.call("get_realtime")

    async def get_daystat(self, *, year, month, kwh=True):
        """Return daily stats for the given year & month."""
        raw_data = await super().get_daystat(year=year, month=month)
        return self._emeter_convert_emeter_data(raw_data["day_list"], kwh)

    async def get_monthstat(self, *, year, kwh=True):
        """Return monthly stats for the given year."""
        raw_data = await super().get_monthstat(year=year)
        return self._emeter_convert_emeter_data(raw_data["month_list"], kwh)

    def _emeter_convert_emeter_data(self, data, kwh=True) -> Dict:
        """Return emeter information keyed with the day/month.."""
        response = [EmeterStatus(**x) for x in data]

        if not response:
            return {}

        energy_key = "energy_wh"
        if kwh:
            energy_key = "energy"

        entry_key = "month"
        if "day" in response[0]:
            entry_key = "day"

        data = {entry[entry_key]: entry[energy_key] for entry in response}

        return data
