"""Implementation of the thermostat temperature records module."""

from __future__ import annotations

from datetime import timedelta

from ..smartmodule import SmartModule

#: Value the device uses for slots without a reading.
NO_READING = -1000


class TemperatureRecords(SmartModule):
    """Implementation of the temperature history of a thermostat.

    The device keeps a reading for every 15 minutes of the last 24 hours,
    ordered oldest first, with the most recent reading last.
    """

    REQUIRED_COMPONENT = "temp_record"
    QUERY_GETTER_NAME = "get_temperature_records"
    INTERVAL = timedelta(minutes=15)
    MINIMUM_UPDATE_INTERVAL_SECS = 15 * 60
    MINIMUM_HUB_CHILD_UPDATE_INTERVAL_SECS = 15 * 60

    @property
    def temperatures(self) -> list[float | None]:
        """Return the readings oldest first, None where there is no reading."""
        return [
            None if value == NO_READING else value / 10
            for value in self.data.get("temp_data", [])
        ]
