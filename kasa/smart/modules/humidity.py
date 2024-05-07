"""Implementation of humidity module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class HumiditySensor(SmartModule):
    """Implementation of humidity module."""

    REQUIRED_COMPONENT = "humidity"
    QUERY_GETTER_NAME = "get_comfort_humidity_config"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="humidity",
                name="Humidity",
                container=self,
                attribute_getter="humidity",
                icon="mdi:water-percent",
                unit="%",
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="humidity_warning",
                name="Humidity warning",
                container=self,
                attribute_getter="humidity_warning",
                type=Feature.Type.BinarySensor,
                icon="mdi:alert",
                category=Feature.Category.Debug,
            )
        )

    @property
    def humidity(self):
        """Return current humidity in percentage."""
        return self._device.sys_info["current_humidity"]

    @property
    def humidity_warning(self) -> bool:
        """Return true if humidity is outside of the wanted range."""
        return self._device.sys_info["current_humidity_exception"] != 0
