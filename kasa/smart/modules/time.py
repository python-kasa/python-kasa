"""Implementation of time module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from time import mktime
from typing import cast

from ...feature import Feature
from ..smartmodule import SmartModule


class Time(SmartModule):
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
    def time(self) -> datetime:
        """Return device's current datetime."""
        td = timedelta(minutes=cast(float, self.data.get("time_diff")))
        if self.data.get("region"):
            tz = timezone(td, str(self.data.get("region")))
        else:
            # in case the device returns a blank region this will result in the
            # tzname being a UTC offset
            tz = timezone(td)
        return datetime.fromtimestamp(
            cast(float, self.data.get("timestamp")),
            tz=tz,
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
