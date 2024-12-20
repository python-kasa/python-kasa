"""Implementation of time module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...cachedzoneinfo import CachedZoneInfo
from ...feature import Feature
from ...interfaces import Time as TimeInterface
from ..smartmodule import SmartModule


class Time(SmartModule, TimeInterface):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "time"
    QUERY_GETTER_NAME = "get_device_time"

    _timezone: tzinfo = UTC

    def _initialize_features(self) -> None:
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

    async def _post_update_hook(self) -> None:
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

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device.

        Hub attached sensors report the time module but do return device time.
        """
        if self._device._is_hub_child:
            return False
        return await super()._check_supported()
