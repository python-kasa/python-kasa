"""Implementation of the temperature and humidity records module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo

from ...exceptions import KasaException
from ..smartmodule import SmartModule
from .temperaturerecords import NO_READING


@dataclass
class TemperatureHumidityRecord:
    """A single reading from the history, None where there is no reading."""

    timestamp: datetime
    temperature: float | None
    humidity: int | None
    #: Non-zero when the temperature was outside the comfort range.
    temperature_exception: int = 0
    #: Non-zero when the humidity was outside the comfort range.
    humidity_exception: int = 0


class TemperatureHumidityRecords(SmartModule):
    """Implementation of the temperature and humidity history of a sensor.

    The device keeps a reading for every 15 minutes of the last 24 hours.
    """

    REQUIRED_COMPONENT = "temp_humidity_record"
    QUERY_GETTER_NAME = "get_temp_humidity_records"
    INTERVAL = timedelta(minutes=15)
    MINIMUM_UPDATE_INTERVAL_SECS = 15 * 60
    MINIMUM_HUB_CHILD_UPDATE_INTERVAL_SECS = 15 * 60

    @property
    def last_record_time(self) -> datetime:
        """Return the time of the most recent reading."""
        try:
            tz: tzinfo = self._device.timezone
        except KasaException:
            tz = UTC  # The timestamp is absolute; only the display zone differs.
        return datetime.fromtimestamp(self.data["local_time"], tz=tz)

    @property
    def records(self) -> list[TemperatureHumidityRecord]:
        """Return the readings, oldest first."""
        data = self.data
        temps = data.get("past24h_temp", [])
        humidities = data.get("past24h_humidity", [])
        temp_exc = data.get("past24h_temp_exception", [0] * len(temps))
        hum_exc = data.get("past24h_humidity_exception", [0] * len(humidities))
        count = min(len(temps), len(humidities))
        last = self.last_record_time
        return [
            TemperatureHumidityRecord(
                timestamp=last - self.INTERVAL * (count - 1 - i),
                temperature=None if temps[i] == NO_READING else temps[i] / 10,
                humidity=None if humidities[i] == NO_READING else humidities[i],
                temperature_exception=temp_exc[i],
                humidity_exception=hum_exc[i],
            )
            for i in range(count)
        ]
