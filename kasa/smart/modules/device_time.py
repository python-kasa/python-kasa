from datetime import datetime, timedelta, timezone
from typing import cast

from ..smartmodule import SmartModule


class DeviceTime(SmartModule):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "device_local_time"
    QUERY_GETTER_NAME = "get_device_time"

    @property
    def time(self):
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

    def __cli_output__(self):
        return f"Time: {self.time}"
