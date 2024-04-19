"""Module for smooth light transitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...exceptions import KasaException
from ...feature import Feature, FeatureType
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class LightTransitionModule(SmartModule):
    """Implementation of gradual on/off."""

    REQUIRED_COMPONENT = "on_off_gradually"
    QUERY_GETTER_NAME = "get_on_off_gradually_info"
    MAXIMUM_DURATION = 60

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._create_features()

    def _create_features(self):
        """Create features based on the available version."""
        icon = "mdi:transition"
        if self.supported_version == 1:
            self._add_feature(
                Feature(
                    device=self._device,
                    container=self,
                    name="Smooth transitions",
                    icon=icon,
                    attribute_getter="enabled_v1",
                    attribute_setter="set_enabled_v1",
                    type=FeatureType.Switch,
                )
            )
        elif self.supported_version >= 2:
            # v2 adds separate on & off states
            # v3 adds max_duration
            # TODO: note, hardcoding the maximums for now as the features get
            #  initialized before the first update.
            self._add_feature(
                Feature(
                    self._device,
                    "Smooth transition on",
                    container=self,
                    attribute_getter="turn_on_transition",
                    attribute_setter="set_turn_on_transition",
                    icon=icon,
                    type=FeatureType.Number,
                    maximum_value=self.MAXIMUM_DURATION,
                )
            )  # self._turn_on_transition_max
            self._add_feature(
                Feature(
                    self._device,
                    "Smooth transition off",
                    container=self,
                    attribute_getter="turn_off_transition",
                    attribute_setter="set_turn_off_transition",
                    icon=icon,
                    type=FeatureType.Number,
                    maximum_value=self.MAXIMUM_DURATION,
                )
            )  # self._turn_off_transition_max

    @property
    def _turn_on(self):
        """Internal getter for turn on settings."""
        if "on_state" not in self.data:
            raise KasaException(
                f"Unsupported for {self.REQUIRED_COMPONENT} v{self.supported_version}"
            )

        return self.data["on_state"]

    @property
    def _turn_off(self):
        """Internal getter for turn off settings."""
        if "off_state" not in self.data:
            raise KasaException(
                f"Unsupported for {self.REQUIRED_COMPONENT} v{self.supported_version}"
            )

        return self.data["off_state"]

    def set_enabled_v1(self, enable: bool):
        """Enable gradual on/off."""
        return self.call("set_on_off_gradually_info", {"enable": enable})

    @property
    def enabled_v1(self) -> bool:
        """Return True if gradual on/off is enabled."""
        return bool(self.data["enable"])

    @property
    def turn_on_transition(self) -> int:
        """Return transition time for turning the light on.

        Available only from v2.
        """
        return self._turn_on["duration"]

    @property
    def _turn_on_transition_max(self) -> int:
        """Maximum turn on duration."""
        # v3 added max_duration, we default to 60 when it's not available
        return self._turn_on.get("max_duration", 60)

    async def set_turn_on_transition(self, seconds: int):
        """Set turn on transition in seconds.

        Setting to 0 turns the feature off.
        """
        if seconds > self._turn_on_transition_max:
            raise ValueError(
                f"Value {seconds} out of range, max {self._turn_on_transition_max}"
            )

        if seconds <= 0:
            return await self.call(
                "set_on_off_gradually_info",
                {"on_state": {**self._turn_on, "enable": False}},
            )

        return await self.call(
            "set_on_off_gradually_info",
            {"on_state": {**self._turn_on, "duration": seconds}},
        )

    @property
    def turn_off_transition(self) -> int:
        """Return transition time for turning the light off.

        Available only from v2.
        """
        return self._turn_off["duration"]

    @property
    def _turn_off_transition_max(self) -> int:
        """Maximum turn on duration."""
        # v3 added max_duration, we default to 60 when it's not available
        return self._turn_off.get("max_duration", 60)

    async def set_turn_off_transition(self, seconds: int):
        """Set turn on transition in seconds.

        Setting to 0 turns the feature off.
        """
        if seconds > self._turn_off_transition_max:
            raise ValueError(
                f"Value {seconds} out of range, max {self._turn_off_transition_max}"
            )

        if seconds <= 0:
            return await self.call(
                "set_on_off_gradually_info",
                {"off_state": {**self._turn_off, "enable": False}},
            )

        return await self.call(
            "set_on_off_gradually_info",
            {"off_state": {**self._turn_on, "duration": seconds}},
        )

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        return True
