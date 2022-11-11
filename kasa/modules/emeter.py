"""Implementation of the emeter module."""
from datetime import datetime
from typing import Dict, Optional

from ..daymonthstat import EmeterStat
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
        data = self._convert_stat_data(raw_data)

        return data.get(today)

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Return this month's energy consumption in kWh."""
        raw_data = self.monthly_data
        current_month = datetime.now().month
        data = self._convert_stat_data(raw_data)

        return data.get(current_month)

    async def erase_stats(self):
        """Erase all stats.

        Uses different query than usage meter.
        """
        return await self.call("erase_emeter_stat")

    async def get_realtime(self):
        """Return real-time statistics."""
        return await self.call("get_realtime")

    async def get_daystat(self, *, year=None, month=None, kwh=True) -> Dict:
        """Return daily stats for the given year & month as a dictionary of {day: energy, ...}."""
        data = await self.get_raw_daystat(year=year, month=month)
        data = self._convert_stat_data(data["day_list"], kwh=kwh)
        return data

    async def get_monthstat(self, *, year=None, kwh=True) -> Dict:
        """Return monthly stats for the given year as a dictionary of {month: energy, ...}."""
        data = await self.get_raw_monthstat(year=year)
        data = self._convert_stat_data(data["month_list"], kwh=kwh)
        return data

    def _convert_stat_data(self, data, kwh=True) -> Dict:
        """Return emeter energy information keyed with the day/month."""
        return dict(EmeterStat(**entry).datekv(kwh=kwh) for entry in data)
