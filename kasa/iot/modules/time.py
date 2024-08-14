"""Provides the current time and timezone information."""

from datetime import datetime

from ...exceptions import KasaException
from ..iotmodule import IotModule, _merge_dict


class Time(IotModule):
    """Implements the timezone settings."""

    def query(self):
        """Request time and timezone."""
        q = self.query_for_command("get_time")
        return _merge_dict(q, self.query_for_command("get_timezone"))

    @property
    def time(self) -> datetime:
        """Return current device time."""
        res = self.data["get_time"]
        return datetime(
            res["year"],
            res["month"],
            res["mday"],
            res["hour"],
            res["min"],
            res["sec"],
        )

    @property
    def timezone(self):
        """Return current timezone."""
        res = self.data["get_timezone"]
        return res

    async def get_time(self):
        """Return current device time."""
        try:
            res = await self.call("get_time")
            return datetime(
                res["year"],
                res["month"],
                res["mday"],
                res["hour"],
                res["min"],
                res["sec"],
            )
        except KasaException:
            return None

    async def get_timezone(self):
        """Request timezone information from the device."""
        return await self.call("get_timezone")
