"""Implementation of the temperature correction module."""

from __future__ import annotations

from ...feature import Feature
from ...module import Module
from ..smartmodule import SmartModule


class TemperatureCorrection(SmartModule):
    """Implementation of the temperature correction module.

    Thermostats can use the temperature from another sensor paired to the
    same hub (e.g. a T310) instead of their own built-in sensor.
    """

    REQUIRED_COMPONENT = "temperature_correction"
    QUERY_GETTER_NAME = "get_temperature_correction"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="external_temperature_sensor",
                name="External temperature sensor",
                container=self,
                attribute_getter="external_sensor_id",
                type=Feature.Type.Sensor,
                category=Feature.Category.Info,
            )
        )

    @property
    def offset(self) -> int:
        """Return the temperature offset applied to the reading."""
        return self.data["offset"]

    @property
    def external_sensor_id(self) -> str | None:
        """Return the device id of the external sensor in use, if any."""
        if not self.data.get("use_other_temp_sensor"):
            return None
        return self.data.get("temp_sensor_device_id")

    @property
    def using_external_sensor(self) -> bool:
        """Return True if the device reports it is reading the external sensor."""
        return bool(self.data.get("using_other_temp_sensor"))

    async def set_external_sensor(self, device_id: str | None) -> dict:
        """Use the temperature from another sensor on the hub.

        Pass None to go back to the thermostat's built-in sensor.
        """
        if device_id is not None:
            self._check_sensor(device_id)
        use_other = device_id is not None
        res = await self.call(
            "set_temperature_correction",
            {
                "use_other_temp_sensor": use_other,
                "offset": self.offset,
                "temp_sensor_device_id": device_id or self._device.device_id,
                "using_other_temp_sensor": use_other,
            },
        )
        self._last_update_time = None  # Re-read on the next update
        return res

    def _check_sensor(self, device_id: str) -> None:
        """Check the sensor is a temperature sensor on the same hub, if known."""
        if device_id == self._device.device_id:
            raise ValueError("Use None to select the built-in sensor")
        if (parent := self._device.parent) is None:
            return
        sensor = next((c for c in parent.children if c.device_id == device_id), None)
        if sensor is None:
            raise ValueError(f"No device {device_id} on the same hub")
        if Module.TemperatureSensor not in sensor.modules:
            raise ValueError(f"{sensor.alias} has no temperature sensor")
