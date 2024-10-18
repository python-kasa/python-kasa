"""Implementation of humidity module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class HumiditySensor(SmartModule):
    """Implementation of humidity module."""

    REQUIRED_COMPONENT = "humidity"
    QUERY_GETTER_NAME = "get_comfort_humidity_config"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="humidity",
                name="Humidity",
                container=self,
                attribute_getter="humidity",
                icon="mdi:water-percent",
                unit_getter=lambda: "%",
                category=Feature.Category.Primary,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="humidity_warning",
                name="Humidity warning",
                container=self,
                attribute_getter="humidity_warning",
                type=Feature.Type.BinarySensor,
                icon="mdi:alert",
                category=Feature.Category.Debug,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def humidity(self) -> int:
        """Return current humidity in percentage."""
        return self._device.sys_info["current_humidity"]

    @property
    def humidity_warning(self) -> bool:
        """Return true if humidity is outside of the wanted range."""
        return self._device.sys_info["current_humidity_exception"] != 0
