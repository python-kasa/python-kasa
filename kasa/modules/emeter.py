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
        data = self._convert_stat_data(raw_data, entry_key="day")

        return data.get(today)

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Return this month's energy consumption in kWh."""
        raw_data = self.monthly_data
        current_month = datetime.now().month
        data = self._convert_stat_data(raw_data, entry_key="month")

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
        """Return daily stats for the given year & month.

        The return value is a dictionary of {day: energy, ...}.
        """
        data = await self.get_raw_daystat(year=year, month=month)
        data = self._convert_stat_data(data["day_list"], entry_key="day", kwh=kwh)
        return data

    async def get_monthstat(self, *, year=None, kwh=True) -> Dict:
        """Return monthly stats for the given year.

        The return value is a dictionary of {month: energy, ...}.
        """
        data = await self.get_raw_monthstat(year=year)
        data = self._convert_stat_data(data["month_list"], entry_key="month", kwh=kwh)
        return data

    def _convert_stat_data(self, data, entry_key, kwh=True) -> Dict:
        """Return emeter information keyed with the day/month.

        The incoming data is a list of dictionaries::

            [{'year':      int,
              'month':     int,
              'day':       int,     <-- for get_daystat not get_monthstat
              'energy_wh': int,     <-- for emeter in some versions (wh)
              'energy':    float    <-- for emeter in other versions (kwh)
            }, ...]

        :return: a dictionary keyed by day or month with energy as the value.
        """
        if not data:
            return {}

        scale: float = 1

        if "energy_wh" in data[0]:
            value_key = "energy_wh"
            if kwh:
                scale = 1 / 1000
        else:
            value_key = "energy"
            if not kwh:
                scale = 1000

        data = {entry[entry_key]: entry[value_key] * scale for entry in data}

        return data
