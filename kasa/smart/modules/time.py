"""Implementation of time module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from time import mktime
from typing import cast

from zoneinfo import ZoneInfoNotFoundError

from ...cachedzoneinfo import CachedZoneInfo
from ...feature import Feature
from ..smartmodule import SmartModule


class Time(SmartModule):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "time"
    QUERY_GETTER_NAME = "get_device_time"

    _timezone: tzinfo = timezone.utc

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

    async def _post_update_hook(self):
        """Perform actions after a device update."""
        td = timedelta(minutes=cast(float, self.data.get("time_diff")))
        if region := self.data.get("region"):
            try:
                # Zoneinfo will return a DST aware object
                tz: tzinfo = await CachedZoneInfo.get_cached_zone_info(region)
            except ZoneInfoNotFoundError:
                tz = timezone(td, region)
        else:
            # in case the device returns a blank region this will result in the
            # tzname being a UTC offset
            tz = timezone(td)
        self._timezone = tz

    @property
    def timezone(self) -> tzinfo:
        """Return current timezone."""
        return self._timezone

    @property
    def time(self) -> datetime:
        """Return device's current datetime."""
        return datetime.fromtimestamp(
            cast(float, self.data.get("timestamp")),
            tz=self.timezone,
        )

    async def set_time(self, dt: datetime):
        """Set device time."""
        unixtime = mktime(dt.timetuple())
        offset = cast(timedelta, dt.utcoffset())
        diff = offset / timedelta(minutes=1)
        return await self.call(
            "set_device_time",
            {
                "timestamp": int(unixtime),
                "time_diff": int(diff),
                "region": dt.tzname(),
            },
        )
