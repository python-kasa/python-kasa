"""Implementation of the usage interface."""
from datetime import datetime
from typing import Dict

from ..daymonthstat import UsageStat
from .module import Module, merge


class Usage(Module):
    """Baseclass for emeter/usage interfaces."""

    def query(self):
        """Return the base query."""
        year = datetime.now().year
        month = datetime.now().month

        req = self.query_for_command("get_realtime")
        req = merge(
            req, self.query_for_command("get_daystat", {"year": year, "month": month})
        )
        req = merge(req, self.query_for_command("get_monthstat", {"year": year}))

        return req

    @property
    def daily_data(self):
        """Return statistics on daily basis."""
        return self.data["get_daystat"]["day_list"]

    @property
    def monthly_data(self):
        """Return statistics on monthly basis."""
        return self.data["get_monthstat"]["month_list"]

    @property
    def usage_today(self):
        """Return today's usage in minutes."""
        today = datetime.now().day
        converted = [x["time"] for x in self.daily_data if x["day"] == today]
        if not converted:
            return None

        return converted.pop()

    @property
    def usage_this_month(self):
        """Return usage in this month in minutes."""
        this_month = datetime.now().month
        converted = [x["time"] for x in self.monthly_data if x["month"] == this_month]
        if not converted:
            return None

        return converted.pop()

    async def get_raw_daystat(self, *, year=None, month=None) -> Dict:
        """Return raw daily stats for the given year & month."""
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        return await self.call("get_daystat", {"year": year, "month": month})

    async def get_raw_monthstat(self, *, year=None) -> Dict:
        """Return raw monthly stats for the given year."""
        if year is None:
            year = datetime.now().year

        return await self.call("get_monthstat", {"year": year})

    async def get_daystat(self, *, year=None, month=None) -> Dict:
        """Return daily stats for the given year & month as a dictionary of {day: time, ...}."""
        data = await self.get_raw_daystat(year=year, month=month)
        data = self._convert_stat_data(data)
        return data

    async def get_monthstat(self, *, year=None) -> Dict:
        """Return monthly stats for the given year as a dictionary of {month: time, ...}."""
        data = await self.get_raw_monthstat(year=year)
        data = self._convert_stat_data(data)
        return data

    def _convert_stat_data(self, data) -> Dict:
        """Return usage information keyed with the day/month."""
        return dict(UsageStat(**entry).datekv() for entry in data)

    async def erase_stats(self):
        """Erase all stats."""
        return await self.call("erase_runtime_stat")
