"""Implementation of time module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from time import mktime
from typing import TYPE_CHECKING, cast

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class Time(SmartModule):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "time"
    QUERY_GETTER_NAME = "get_device_time"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)

        self._add_feature(
            Feature(
                device=device,
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
