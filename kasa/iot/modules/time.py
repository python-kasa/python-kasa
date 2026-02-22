"""Provides the current time and timezone information."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfoNotFoundError

from ...exceptions import KasaException
from ...interfaces import Time as TimeInterface
from ..iotmodule import IotModule, merge
from ..iottimezone import (
    _expected_dst_behavior_for_index,
    _guess_timezone_by_offset,
    get_timezone,
    get_timezone_index,
)


class Time(IotModule, TimeInterface):
    """Implements the timezone settings."""

    _timezone: tzinfo = UTC

    def query(self) -> dict:
        """Request time and timezone."""
        q = self.query_for_command("get_time")

        merge(q, self.query_for_command("get_timezone"))
        return q

    async def _post_update_hook(self) -> None:
        """Perform actions after a device update.

        If the configured zone is not available on this host, compute the device's
        current UTC offset and choose a best-match available zone, preferring DST-
        observing candidates when the original index implies DST. As a last resort,
        use a fixed-offset timezone.
        """
        if res := self.data.get("get_timezone"):
            idx = res.get("index")
            try:
                self._timezone = await get_timezone(idx)
                return
            except ZoneInfoNotFoundError:
                pass  # fall through to offset-based match

        gt = self.data.get("get_time")
        if gt:
            device_local = datetime(
                gt["year"],
                gt["month"],
                gt["mday"],
                gt["hour"],
                gt["min"],
                gt["sec"],
            )
            now_utc = datetime.now(UTC)
            delta = device_local - now_utc.replace(tzinfo=None)
            rounded = timedelta(seconds=60 * round(delta.total_seconds() / 60))

            dst_expected = None
            if res := self.data.get("get_timezone"):
                idx = res.get("index")
                with contextlib.suppress(KeyError):
                    dst_expected = _expected_dst_behavior_for_index(idx)

            self._timezone = await _guess_timezone_by_offset(
                rounded, when_utc=now_utc, dst_expected=dst_expected
            )
        else:
            self._timezone = UTC

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
