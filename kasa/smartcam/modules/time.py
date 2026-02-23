"""Implementation of time module."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...cachedzoneinfo import CachedZoneInfo
from ...feature import Feature
from ...interfaces import Time as TimeInterface
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule


class Time(SmartCamModule, TimeInterface):
    """Implementation of device_local_time."""

    QUERY_GETTER_NAME = "getTimezone"
    QUERY_MODULE_NAME = "system"
    QUERY_SECTION_NAMES = "basic"

    _timezone: tzinfo = UTC
    _time: datetime

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

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        q = super().query()
        q["getClockStatus"] = {self.QUERY_MODULE_NAME: {"name": "clock_status"}}

        return q

    async def _post_update_hook(self) -> None:
        """Perform actions after a device update."""
        time_data = self.data["getClockStatus"]["system"]["clock_status"]
        timezone_data = self.data["getTimezone"]["system"]["basic"]
        zone_id = timezone_data["zone_id"]
        timestamp = time_data["seconds_from_1970"]
        try:
            # Zoneinfo will return a DST aware object
            tz: tzinfo = await CachedZoneInfo.get_cached_zone_info(zone_id)
        except ZoneInfoNotFoundError:
            # timezone string like: UTC+10:00
            timezone_str = timezone_data["timezone"]
            tz = cast(tzinfo, datetime.strptime(timezone_str[-6:], "%z").tzinfo)

        self._timezone = tz
        self._time = datetime.fromtimestamp(
            cast(float, timestamp),
            tz=tz,
        )

    @property
    def timezone(self) -> tzinfo:
        """Return current timezone."""
        return self._timezone

    @property
    def time(self) -> datetime:
        """Return device's current datetime."""
        return self._time

    @allow_update_after
    async def set_time(self, dt: datetime) -> dict:
        """Set device time."""
        if not dt.tzinfo:
            timestamp = dt.replace(tzinfo=self.timezone).timestamp()
        else:
            timestamp = dt.timestamp()

        timestamp_int = int(timestamp)
        # The device reports local_time in UTC regardless of the configured
        # zone_id (confirmed by cross-referencing seconds_from_1970 with
        # local_time in captured traffic).  Use strftime to avoid the
        # sub-second precision that isoformat() would include.
        lt = datetime.fromtimestamp(timestamp_int, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")

        # Devices that report timing_mode "ntp" appear to ignore clock_status
        # updates.  Switching to "manual" first is the working hypothesis;
        # timing_mode is a field the device itself exposes via getTimezone.
        # Devices that have no timing_mode (e.g. H200 hub) are left alone.
        # Combine zone_id here too if a ZoneInfo was supplied, so both
        # changes land in a single request.
        tz_basic = self.data.get("getTimezone", {}).get("system", {}).get("basic", {})
        basic_params: dict[str, str] = {}
        if "timing_mode" in tz_basic:
            basic_params["timing_mode"] = "manual"
        if (zinfo := dt.tzinfo) and isinstance(zinfo, ZoneInfo):
            basic_params["zone_id"] = zinfo.key
        if basic_params:
            await self.call("setTimezone", {"system": {"basic": basic_params}})

        params = {"seconds_from_1970": timestamp_int, "local_time": lt}
        return await self.call("setTimezone", {"system": {"clock_status": params}})
