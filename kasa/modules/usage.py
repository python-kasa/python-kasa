"""Implementation of the usage interface."""
from datetime import datetime

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
        req = merge(req, self.query_for_command("get_next_action"))

        return req

    async def get_daystat(self, year, month):
        """Return stats for the current day."""
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month
        return await self.call("get_daystat", {"year": year, "month": month})

    async def get_monthstat(self, year):
        """Return stats for the current month."""
        if year is None:
            year = datetime.now().year
        return await self.call("get_monthstat", {"year": year})

    async def erase_stats(self):
        """Erase all stats."""
        return await self.call("erase_runtime_stat")
