"""Implementation of time module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import cast

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...feature import Feature
from ...interfaces import Time as TimeInterface
from ..smartmodule import SmartModule


class Time(SmartModule, TimeInterface):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "time"
    QUERY_GETTER_NAME = "get_device_time"

    def _initialize_features(self):
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                id="device_time",
                name="Device time",
                attribute_getter="time",
                container=self,
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )

    @property
    def timezone(self) -> tzinfo:
        """Return current timezone."""
        td = timedelta(minutes=cast(float, self.data.get("time_diff")))
        if region := self.data.get("region"):
            try:
                # Zoneinfo will return a DST aware object
                tz: tzinfo = ZoneInfo(region)
            except ZoneInfoNotFoundError:
                tz = timezone(td, region)
        else:
            # in case the device returns a blank region this will result in the
            # tzname being a UTC offset
            tz = timezone(td)
        return tz

    @property
    def time(self) -> datetime:
        """Return device's current datetime."""
        return datetime.fromtimestamp(
            cast(float, self.data.get("timestamp")),
            tz=self.timezone,
        )

    async def set_time(self, dt: datetime) -> dict:
        """Set device time."""
        if not dt.tzinfo:
            timestamp = dt.replace(tzinfo=self.timezone).timestamp()
            utc_offset = cast(timedelta, self.timezone.utcoffset(dt))
        else:
            timestamp = dt.timestamp()
            utc_offset = cast(timedelta, dt.utcoffset())
        time_diff = utc_offset / timedelta(minutes=1)

        params: dict[str, int | str] = {
            "timestamp": int(timestamp),
            "time_diff": int(time_diff),
        }
        if tz := dt.tzinfo:
            region = tz.key if isinstance(tz, ZoneInfo) else dt.tzname()
            # tzname can return null if a simple timezone object is provided.
            if region:
                params["region"] = region
        return await self.call("set_device_time", params)
