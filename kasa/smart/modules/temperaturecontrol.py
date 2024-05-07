"""Implementation of temperature control module."""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


_LOGGER = logging.getLogger(__name__)


class ThermostatState(Enum):
    """Thermostat state."""

    Heating = "heating"
    Calibrating = "progress_calibration"
    Idle = "idle"
    Off = "off"
    Unknown = "unknown"


class TemperatureControl(SmartModule):
    """Implementation of temperature module."""

    REQUIRED_COMPONENT = "temp_control"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="target_temperature",
                name="Target temperature",
                container=self,
                attribute_getter="target_temperature",
                attribute_setter="set_target_temperature",
                range_getter="allowed_temperature_range",
                icon="mdi:thermometer",
                type=Feature.Type.Number,
                category=Feature.Category.Primary,
            )
        )
        # TODO: this might belong into its own module, temperature_correction?
        self._add_feature(
            Feature(
                device,
                id="temperature_offset",
                name="Temperature offset",
                container=self,
                attribute_getter="temperature_offset",
                attribute_setter="set_temperature_offset",
                minimum_value=-10,
                maximum_value=10,
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device,
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
                device,
                id="mode",
                name="Mode",
                container=self,
                attribute_getter="mode",
                category=Feature.Category.Primary,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Target temperature is contained in the main device info response.
        return {}

    @property
    def state(self) -> bool:
        """Return thermostat state."""
        return self._device.sys_info["frost_protection_on"] is False

    async def set_state(self, enabled: bool):
        """Set thermostat state."""
        return await self.call("set_device_info", {"frost_protection_on": not enabled})

    @property
    def mode(self) -> ThermostatState:
        """Return thermostat state."""
        # If frost protection is enabled, the thermostat is off.
        if self._device.sys_info.get("frost_protection_on", False):
            return ThermostatState.Off

        states = self._device.sys_info["trv_states"]

        # If the states is empty, the device is idling
        if not states:
            return ThermostatState.Idle

        if len(states) > 1:
            _LOGGER.warning(
                "Got multiple states (%s), using the first one: %s", states, states[0]
            )

        state = states[0]
        try:
            return ThermostatState(state)
        except:  # noqa: E722
            _LOGGER.warning("Got unknown state: %s", state)
            return ThermostatState.Unknown

    @property
    def allowed_temperature_range(self) -> tuple[int, int]:
        """Return allowed temperature range."""
        return self.minimum_target_temperature, self.maximum_target_temperature

    @property
    def minimum_target_temperature(self) -> int:
        """Minimum available target temperature."""
        return self._device.sys_info["min_control_temp"]

    @property
    def maximum_target_temperature(self) -> int:
        """Minimum available target temperature."""
        return self._device.sys_info["max_control_temp"]

    @property
    def target_temperature(self) -> float:
        """Return target temperature."""
        return self._device.sys_info["target_temp"]

    async def set_target_temperature(self, target: float):
        """Set target temperature."""
        if (
            target < self.minimum_target_temperature
            or target > self.maximum_target_temperature
        ):
            raise ValueError(
                f"Invalid target temperature {target}, must be in range "
                f"[{self.minimum_target_temperature},{self.maximum_target_temperature}]"
            )

        payload = {"target_temp": target}
        # If the device has frost protection, we set it off to enable heating
        if "frost_protection_on" in self._device.sys_info:
            payload["frost_protection_on"] = False

        return await self.call("set_device_info", payload)

    @property
    def temperature_offset(self) -> int:
        """Return temperature offset."""
        return self._device.sys_info["temp_offset"]

    async def set_temperature_offset(self, offset: int):
        """Set temperature offset."""
        if offset < -10 or offset > 10:
            raise ValueError("Temperature offset must be [-10, 10]")

        return await self.call("set_device_info", {"temp_offset": offset})
