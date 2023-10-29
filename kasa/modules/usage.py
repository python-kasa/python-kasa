"""Implementation of the usage interface."""
from datetime import datetime
from typing import Dict

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
    def estimated_query_response_size(self):
        """Estimated maximum query response size."""
        return 2048

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
        """Return daily stats for the given year & month.

        The return value is a dictionary of {day: time, ...}.
        """
        data = await self.get_raw_daystat(year=year, month=month)
        data = self._convert_stat_data(data["day_list"], entry_key="day")
        return data

    async def get_monthstat(self, *, year=None) -> Dict:
        """Return monthly stats for the given year.

        The return value is a dictionary of {month: time, ...}.
        """
        data = await self.get_raw_monthstat(year=year)
        data = self._convert_stat_data(data["month_list"], entry_key="month")
        return data

    async def erase_stats(self):
        """Erase all stats."""
        return await self.call("erase_runtime_stat")

    def _convert_stat_data(self, data, entry_key) -> Dict:
        """Return usage information keyed with the day/month.

        The incoming data is a list of dictionaries::

               [{'year':      int,
                 'month':     int,
                 'day':       int,     <-- for get_daystat not get_monthstat
                 'time':      int,     <-- for usage (mins)
               }, ...]

        :return: return a dictionary keyed by day or month with time as the value.
        """
        if not data:
            return {}

        data = {entry[entry_key]: entry["time"] for entry in data}

        return data
