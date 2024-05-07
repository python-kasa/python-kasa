"""Implementation of the emeter module."""

from __future__ import annotations

from datetime import datetime

from ... import Device
from ...emeterstatus import EmeterStatus
from ...feature import Feature
from .usage import Usage


class Emeter(Usage):
    """Emeter module."""

    def __init__(self, device: Device, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                name="Current consumption",
                attribute_getter="current_consumption",
                container=self,
                unit="W",
                id="current_power_w",  # for homeassistant backwards compat
                precision_hint=1,
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                device,
                name="Today's consumption",
                attribute_getter="emeter_today",
                container=self,
                unit="kWh",
                id="today_energy_kwh",  # for homeassistant backwards compat
                precision_hint=3,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="consumption_this_month",
                name="This month's consumption",
                attribute_getter="emeter_this_month",
                container=self,
                unit="kWh",
                precision_hint=3,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                name="Total consumption since reboot",
                attribute_getter="emeter_total",
                container=self,
                unit="kWh",
                id="total_energy_kwh",  # for homeassistant backwards compat
                precision_hint=3,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                name="Voltage",
                attribute_getter="voltage",
                container=self,
                unit="V",
                id="voltage",  # for homeassistant backwards compat
                precision_hint=1,
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                device,
                name="Current",
                attribute_getter="current",
                container=self,
                unit="A",
                id="current_a",  # for homeassistant backwards compat
                precision_hint=2,
                category=Feature.Category.Primary,
            )
        )

    @property  # type: ignore
    def realtime(self) -> EmeterStatus:
        """Return current energy readings."""
        return EmeterStatus(self.data["get_realtime"])

    @property
    def emeter_today(self) -> float | None:
        """Return today's energy consumption in kWh."""
        raw_data = self.daily_data
        today = datetime.now().day
        data = self._convert_stat_data(raw_data, entry_key="day", key=today)
        return data.get(today)

    @property
    def emeter_this_month(self) -> float | None:
        """Return this month's energy consumption in kWh."""
        raw_data = self.monthly_data
        current_month = datetime.now().month
        data = self._convert_stat_data(raw_data, entry_key="month", key=current_month)
        return data.get(current_month)

    @property
    def current_consumption(self) -> float | None:
        """Get the current power consumption in Watt."""
        return self.realtime.power

    @property
    def emeter_total(self) -> float | None:
        """Return total consumption since last reboot in kWh."""
        return self.realtime.total

    @property
    def current(self) -> float | None:
        """Return the current in A."""
        return self.realtime.current

    @property
    def voltage(self) -> float | None:
        """Get the current voltage in V."""
        return self.realtime.voltage

    async def erase_stats(self):
        """Erase all stats.

        Uses different query than usage meter.
        """
        return await self.call("erase_emeter_stat")

    async def get_realtime(self):
        """Return real-time statistics."""
        return await self.call("get_realtime")

    async def get_daystat(self, *, year=None, month=None, kwh=True) -> dict:
        """Return daily stats for the given year & month.

        The return value is a dictionary of {day: energy, ...}.
        """
        data = await self.get_raw_daystat(year=year, month=month)
        data = self._convert_stat_data(data["day_list"], entry_key="day", kwh=kwh)
        return data

    async def get_monthstat(self, *, year=None, kwh=True) -> dict:
        """Return monthly stats for the given year.

        The return value is a dictionary of {month: energy, ...}.
        """
        data = await self.get_raw_monthstat(year=year)
        data = self._convert_stat_data(data["month_list"], entry_key="month", kwh=kwh)
        return data

    def _convert_stat_data(
        self,
        data: list[dict[str, int | float]],
        entry_key: str,
        kwh: bool = True,
        key: int | None = None,
    ) -> dict[int | float, int | float]:
        """Return emeter information keyed with the day/month.

        The incoming data is a list of dictionaries::

            [{'year':      int,
              'month':     int,
              'day':       int,     <-- for get_daystat not get_monthstat
              'energy_wh': int,     <-- for emeter in some versions (wh)
              'energy':    float    <-- for emeter in other versions (kwh)
            }, ...]

        :return: a dictionary keyed by day or month with energy as the value.
        """
        if not data:
            return {}

        scale: float = 1

        if "energy_wh" in data[0]:
            value_key = "energy_wh"
            if kwh:
                scale = 1 / 1000
        else:
            value_key = "energy"
            if not kwh:
                scale = 1000

        if key is None:
            # Return all the data
            return {entry[entry_key]: entry[value_key] * scale for entry in data}

        # In this case we want a specific key in the data
        # i.e. the current day or month.
        #
        # Since we usually want the data at the end of the list so we can
        # optimize the search by starting at the end and avoid scaling
        # the data we don't need.
        #
        for entry in reversed(data):
            if entry[entry_key] == key:
                return {entry[entry_key]: entry[value_key] * scale}

        return {}
