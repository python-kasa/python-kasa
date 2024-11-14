"""Implementation of the motion detection (PIR) module found in some dimmers."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Literal, overload

from ...exceptions import KasaException
from ...feature import Feature
from ..iotmodule import IotModule, merge

_LOGGER = logging.getLogger(__name__)


class Range(Enum):
    """Range for motion detection."""

    Far = 0
    Mid = 1
    Near = 2
    Custom = 3

    def __str__(self) -> str:
        return self.name


class Motion(IotModule):
    """Implements the motion detection (PIR) module."""

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        # Only add features if the device supports the module
        if "get_config" not in self.data:
            return

        # Require that ADC value is also present.
        if "get_adc_value" not in self.data:
            _LOGGER.warning("%r initialized, but no get_adc_value in response")
            return

        if "enable" not in self.config:
            _LOGGER.warning("%r initialized, but no enable in response")
            return

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_enabled",
                name="PIR enabled",
                icon="mdi:motion-sensor",
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_range",
                name="Motion Sensor Range",
                icon="mdi:motion-sensor",
                attribute_getter="range",
                attribute_setter="_set_range_cli",
                type=Feature.Type.Choice,
                choices_getter="ranges",
                value_parser="parse_range_value",
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_threshold",
                name="Motion Sensor Threshold",
                icon="mdi:motion-sensor",
                attribute_getter="threshold",
                attribute_setter="set_threshold",
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_adc_value",
                name="PIR ADC Value",
                icon="mdi:motion-sensor",
                attribute_getter="adc_value",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Primary,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="pir_triggered",
                name="PIR Triggered",
                icon="mdi:motion-sensor",
                attribute_getter="is_triggered",
                attribute_setter=None,
                type=Feature.Type.Sensor,
                category=Feature.Category.Primary,
            )
        )

    def query(self) -> dict:
        """Request PIR configuration."""
        req = merge(
            self.query_for_command("get_config"),
            self.query_for_command("get_adc_value"),
        )

        return req

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return self.data["get_config"]

    @property
    def enabled(self) -> bool:
        """Return True if module is enabled."""
        return bool(self.config["enable"])

    async def set_enabled(self, state: bool) -> dict:
        """Enable/disable PIR."""
        return await self.call("set_enable", {"enable": int(state)})

    def _parse_range_value(self, value: str) -> int | Range | None:
        """Attempt to parse a range value from the given string."""
        _LOGGER.debug("Parse Range Value: %s", value)
        parsed: int | Range | None = None
        try:
            parsed = int(value)
            _LOGGER.debug("Parse Range Value: %s is an integer.", value)
            return parsed
        except ValueError:
            _LOGGER.debug("Parse Range Value: %s is not an integer.", value)
        value = value.strip().upper()
        if value in Range._member_names_:
            _LOGGER.debug("Parse Range Value: %s is an enumeration.", value)
            parsed = Range[value]
            return parsed
        _LOGGER.debug("Parse Range Value: %s is not a Range Value.", value)
        return None

    @property
    def ranges(self) -> list[Range]:
        """Return set of supported range classes."""
        range_min = 0
        range_max = len(self.config["array"])
        valid_ranges = list()
        for r in Range:
            if (r.value >= range_min) and (r.value < range_max):
                valid_ranges.append(r)
        return valid_ranges

    @property
    def range(self) -> Range:
        """Return motion detection Range."""
        return Range(self.config["trigger_index"])

    @overload
    async def set_range(self, *, range: Range) -> dict: ...

    @overload
    async def set_range(self, *, range: Literal[Range.Custom], value: int) -> dict: ...

    @overload
    async def set_range(self, *, value: int) -> dict: ...

    async def set_range(
        self, *, range: Range | None = None, value: int | None = None
    ) -> dict:
        """Set the Range for the sensor.

        :param Range: for using standard Ranges
        :param custom_Range: Range in decimeters, overrides the Range parameter
        """
        if value is not None:
            if range is not None and range is not Range.Custom:
                raise KasaException(
                    "Refusing to set non-custom range %s to value %d." % (range, value)
                )
            elif value is None:
                raise KasaException("Custom range threshold may not be set to None.")
            payload = {"index": Range.Custom.value, "value": value}
        elif range is not None:
            payload = {"index": range.value}
        else:
            raise KasaException("Either range or value needs to be defined")

        return await self.call("set_trigger_sens", payload)

    async def _set_range_cli(self, input: Range | int) -> dict:
        if isinstance(input, Range):
            return await self.set_range(range=input)
        elif isinstance(input, int):
            return await self.set_range(value=input)
        else:
            raise KasaException(
                "Invalid type: %s given to cli motion set." % (type(input))
            )

    def get_range_threshold(self, range_type: Range) -> int:
        """Get the distance threshold at which the PIR sensor is will trigger."""
        if range_type.value < 0 or range_type.value >= len(self.config["array"]):
            raise KasaException(
                "Range type is outside the bounds of the configured device ranges."
            )
        return int(self.config["array"][range_type.value])

    @property
    def threshold(self) -> int:
        """Return motion detection Range."""
        return self.get_range_threshold(self.range)

    async def set_threshold(self, value: int) -> dict:
        """Set the distance threshold at which the PIR sensor is will trigger."""
        return await self.set_range(value=value)

    @property
    def inactivity_timeout(self) -> int:
        """Return inactivity timeout in milliseconds."""
        return self.config["cold_time"]

    async def set_inactivity_timeout(self, timeout: int) -> dict:
        """Set inactivity timeout in milliseconds.

        Note, that you need to delete the default "Smart Control" rule in the app
        to avoid reverting this back to 60 seconds after a period of time.
        """
        return await self.call("set_cold_time", {"cold_time": timeout})

    @property
    def adc_value(self) -> int:
        """Return motion adc value."""
        return int(self.data["get_adc_value"]["value"])

    @property
    def is_triggered(self) -> bool:
        """Return if the motion sensor has been triggered."""
        return (self.enabled) and (self.adc_value < self.threshold)
