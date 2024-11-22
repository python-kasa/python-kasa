"""Interact with a TPLink Thermostat."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Annotated, Literal

from ..feature import Feature
from ..module import FeatureAttribute, Module


class ThermostatState(Enum):
    """Thermostat state."""

    Heating = "heating"
    Calibrating = "progress_calibration"
    Idle = "idle"
    Off = "off"
    Unknown = "unknown"


class Thermostat(Module, ABC):
    """Base class for TP-Link Thermostat."""

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="state",
                name="State",
                container=self,
                attribute_getter="state",
                attribute_setter="set_state",
                category=Feature.Category.Primary,
                type=Feature.Type.Switch,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="target_temperature",
                name="Target temperature",
                container=self,
                attribute_getter="target_temperature",
                attribute_setter="set_target_temperature",
                range_getter="_target_temperature_range",
                icon="mdi:thermometer",
                type=Feature.Type.Number,
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="thermostat_mode",
                name="Thermostat mode",
                container=self,
                attribute_getter="mode",
                category=Feature.Category.Primary,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="temperature",
                name="Temperature",
                container=self,
                attribute_getter="temperature",
                icon="mdi:thermometer",
                category=Feature.Category.Primary,
                unit_getter="temperature_unit",
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="temperature_unit",
                name="Temperature unit",
                container=self,
                attribute_getter="temperature_unit",
                attribute_setter="set_temperature_unit",
                type=Feature.Type.Choice,
                choices_getter=lambda: ["celsius", "fahrenheit"],
            )
        )

    @property
    @abstractmethod
    def state(self) -> bool:
        """Return thermostat state."""

    @abstractmethod
    async def set_state(self, enabled: bool) -> dict:
        """Set thermostat state."""

    @property
    @abstractmethod
    def mode(self) -> ThermostatState:
        """Return thermostat state."""

    @property
    @abstractmethod
    def target_temperature(self) -> Annotated[float, FeatureAttribute()]:
        """Return target temperature."""

    @abstractmethod
    async def set_target_temperature(
        self, target: float
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set target temperature."""

    @property
    @abstractmethod
    def _target_temperature_range(self) -> tuple[int, int]:
        """Return target temperature range.

        Private method. Consumers of the api should use:
        get_feature(self.set_target_temperature).minimum_value
        get_feature(self.set_target_temperature).maximum_value
        """

    @property
    @abstractmethod
    def temperature(self) -> Annotated[float, FeatureAttribute()]:
        """Return current humidity in percentage."""
        return self._device.sys_info["current_temp"]

    @property
    @abstractmethod
    def temperature_unit(self) -> Literal["celsius", "fahrenheit"]:
        """Return current temperature unit."""

    @abstractmethod
    async def set_temperature_unit(
        self, unit: Literal["celsius", "fahrenheit"]
    ) -> dict:
        """Set the device temperature unit."""
