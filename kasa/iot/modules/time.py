"""Provides the current time and timezone information."""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo

from ...exceptions import KasaException
from ..iotmodule import IotModule, merge
from ..iottimezone import get_timezone


class Time(IotModule):
    """Implements the timezone settings."""

    def query(self):
        """Request time and timezone."""
        q = self.query_for_command("get_time")

        merge(q, self.query_for_command("get_timezone"))
        return q

    @property
    def time(self) -> datetime:
        """Return current device time."""
        res = self.data["get_time"]
        time = datetime(
            res["year"],
            res["month"],
            res["mday"],
            res["hour"],
            res["min"],
            res["sec"],
        )
        return time.astimezone(self.timezone)

    @property
    def timezone(self) -> tzinfo:
        """Return current timezone."""
        if res := self.data.get("get_timezone"):
            return get_timezone(res.get("index"))
        return timezone.utc

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
