"""Interact with a TPLink Thermostat."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal

from ..module import Module


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
    async def set_state(self, enabled: bool):
        """Set thermostat state."""

    @property
    @abstractmethod
    def mode(self) -> ThermostatState:
        """Return thermostat state."""

    @property
    @abstractmethod
    def allowed_temperature_range(self) -> tuple[int, int]:
        """Return allowed temperature range."""

    @property
    @abstractmethod
    def minimum_target_temperature(self) -> int:
        """Minimum available target temperature."""

    @property
    @abstractmethod
    def maximum_target_temperature(self) -> int:
        """Minimum available target temperature."""

    @property
    @abstractmethod
    def target_temperature(self) -> float:
        """Return target temperature."""

    @abstractmethod
    async def set_target_temperature(self, target: float):
        """Set target temperature."""

    @property
    @abstractmethod
    def temperature_offset(self) -> int:
        """Return temperature offset."""

    @abstractmethod
    async def set_temperature_offset(self, offset: int):
        """Set temperature offset."""

    @property
    @abstractmethod
    def temperature(self):
        """Return current humidity in percentage."""
        return self._device.sys_info["current_temp"]

    @property
    @abstractmethod
    def temperature_warning(self) -> bool:
        """Return True if temperature is outside of the wanted range."""

    @property
    @abstractmethod
    def temperature_unit(self):
        """Return current temperature unit."""
        return self._device.sys_info["temp_unit"]

    @abstractmethod
    async def set_temperature_unit(self, unit: Literal["celsius", "fahrenheit"]):
        """Set the device temperature unit."""

    @property
    @abstractmethod
    def frost_control_temperature(self) -> int:
        """Return frost protection minimum temperature."""
