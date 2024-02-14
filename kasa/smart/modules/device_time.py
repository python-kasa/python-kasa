"""Implementation of device time module."""
from datetime import datetime, timedelta, timezone
from time import mktime
from typing import TYPE_CHECKING, cast

from ..smartmodule import SmartModule

if TYPE_CHECKING:
    pass


class DeviceTime(SmartModule):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "device_local_time"
    QUERY_GETTER_NAME = "get_device_time"

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
        return await self.call(
            "set_device_time",
            {"timestamp": unixtime, "time_diff": dt.utcoffset(), "region": dt.tzname()},
        )

    def __cli_output__(self):
        return f"Time: {self.time}"
