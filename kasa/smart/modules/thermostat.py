"""Module for a Thermostat."""

from __future__ import annotations

from typing import Annotated, Literal

from ...interfaces.thermostat import Thermostat as ThermostatInterface
from ...interfaces.thermostat import ThermostatState
from ...module import FeatureAttribute, Module
from ..smartmodule import SmartModule


class Thermostat(SmartModule, ThermostatInterface):
    """Implementation of a Thermostat."""

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def state(self) -> bool:
        """Return thermostat state."""
        return self._device.modules[Module.TemperatureControl].state

    async def set_state(self, enabled: bool) -> dict:
        """Set thermostat state."""
        return await self._device.modules[Module.TemperatureControl].set_state(enabled)

    @property
    def mode(self) -> ThermostatState:
        """Return thermostat state."""
        return self._device.modules[Module.TemperatureControl].mode

    @property
    def target_temperature(self) -> Annotated[float, FeatureAttribute()]:
        """Return target temperature."""
        return self._device.modules[Module.TemperatureControl].target_temperature

    async def set_target_temperature(
        self, target: float
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set target temperature."""
        return await self._device.modules[
            Module.TemperatureControl
        ].set_target_temperature(target)

    @property
    def _target_temperature_range(self) -> tuple[int, int]:
        """Return allowed temperature range."""
        return self._device.modules[Module.TemperatureControl].allowed_temperature_range

    @property
    def temperature(self) -> Annotated[float, FeatureAttribute()]:
        """Return current humidity in percentage."""
        return self._device.modules[Module.TemperatureSensor].temperature

    @property
    def temperature_unit(self) -> Literal["celsius", "fahrenheit"]:
        """Return current temperature unit."""
        return self._device.modules[Module.TemperatureSensor].temperature_unit

    async def set_temperature_unit(
        self, unit: Literal["celsius", "fahrenheit"]
    ) -> dict:
        """Set the device temperature unit."""
        return await self._device.modules[
            Module.TemperatureSensor
        ].set_temperature_unit(unit)
