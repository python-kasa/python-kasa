"""Provides the current time and timezone information."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo

from ...exceptions import KasaException
from ...interfaces import Time as TimeInterface
from ..iotmodule import IotModule, merge
from ..iottimezone import get_timezone, get_timezone_index


class Time(IotModule, TimeInterface):
    """Implements the timezone settings."""

    _timezone: tzinfo = UTC

    def query(self) -> dict:
        """Request time and timezone."""
        q = self.query_for_command("get_time")

        merge(q, self.query_for_command("get_timezone"))
        return q

    async def _post_update_hook(self) -> None:
        """Perform actions after a device update."""
        if res := self.data.get("get_timezone"):
            self._timezone = await get_timezone(res.get("index"))

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
            tzinfo=self.timezone,
        )
        return time

    @property
    def timezone(self) -> tzinfo:
        """Return current timezone."""
        return self._timezone

    async def get_time(self) -> datetime | None:
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
                tzinfo=self.timezone,
            )
        except KasaException:
            return None

    async def set_time(self, dt: datetime) -> dict:
        """Set the device time."""
        params = {
            "year": dt.year,
            "month": dt.month,
            "mday": dt.day,
            "hour": dt.hour,
            "min": dt.minute,
            "sec": dt.second,
        }
        if dt.tzinfo:
            index = await get_timezone_index(dt.tzinfo)
            current_index = self.data.get("get_timezone", {}).get("index", -1)
            if current_index != -1 and current_index != index:
                params["index"] = index
                method = "set_timezone"
            else:
                method = "set_time"
        else:
            method = "set_time"
        try:
            return await self.call(method, params)
        except Exception as ex:
            raise KasaException(ex) from ex

    async def get_timezone(self) -> dict:
        """Request timezone information from the device."""
        return await self.call("get_timezone")
