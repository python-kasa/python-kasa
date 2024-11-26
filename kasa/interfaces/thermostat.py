"""Interact with a TPLink Thermostat."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Annotated, Literal

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
