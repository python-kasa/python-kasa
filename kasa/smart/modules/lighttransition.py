"""Module for smooth light transitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from ...exceptions import KasaException
from ...feature import Feature
from ..smartmodule import SmartModule, allow_update_after

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class _State(TypedDict):
    duration: int
    enable: bool
    max_duration: int


class LightTransition(SmartModule):
    """Implementation of gradual on/off."""

    REQUIRED_COMPONENT = "on_off_gradually"
    QUERY_GETTER_NAME = "get_on_off_gradually_info"
    MINIMUM_UPDATE_INTERVAL_SECS = 60
    # v3 added max_duration, we default to 60 when it's not available
    MAXIMUM_DURATION = 60

    # Key in sysinfo that indicates state can be retrieved from there.
    # Usually only for child lights, i.e, ks240.
    SYS_INFO_STATE_KEYS = (
        "gradually_on_mode",
        "gradually_off_mode",
        "fade_on_time",
        "fade_off_time",
    )

    _on_state: _State
    _off_state: _State
    _enabled: bool

    def __init__(self, device: SmartDevice, module: str) -> None:
        super().__init__(device, module)
        self._state_in_sysinfo = all(
            key in device.sys_info for key in self.SYS_INFO_STATE_KEYS
        )
        self._supports_on_and_off: bool = self.supported_version > 1

    def _initialize_features(self) -> None:
        """Initialize features."""
        icon = "mdi:transition"
        if not self._supports_on_and_off:
            self._add_feature(
                Feature(
                    device=self._device,
                    container=self,
                    id="smooth_transitions",
                    name="Smooth transitions",
                    icon=icon,
                    attribute_getter="enabled",
                    attribute_setter="set_enabled",
                    type=Feature.Type.Switch,
                )
            )
        else:
            self._add_feature(
                Feature(
                    self._device,
                    id="smooth_transition_on",
                    name="Smooth transition on",
                    container=self,
                    attribute_getter="turn_on_transition",
                    attribute_setter="set_turn_on_transition",
                    icon=icon,
                    type=Feature.Type.Number,
                    range_getter=lambda: (0, self._turn_on_transition_max),
                )
            )
            self._add_feature(
                Feature(
                    self._device,
                    id="smooth_transition_off",
                    name="Smooth transition off",
                    container=self,
                    attribute_getter="turn_off_transition",
                    attribute_setter="set_turn_off_transition",
                    icon=icon,
                    type=Feature.Type.Number,
                    range_getter=lambda: (0, self._turn_off_transition_max),
                )
            )

    async def _post_update_hook(self) -> None:
        """Update the states."""
        # Assumes any device with state in sysinfo supports on and off and
        # has maximum values for both.
        # v2 adds separate on & off states
        # v3 adds max_duration except for ks240 which is v2 but supports it
        if not self._supports_on_and_off:
            self._enabled = self.data["enable"]
            return

        if self._state_in_sysinfo:
            on_max = self._device.sys_info.get(
                "max_fade_on_time", self.MAXIMUM_DURATION
            )
            off_max = self._device.sys_info.get(
                "max_fade_off_time", self.MAXIMUM_DURATION
            )
            on_enabled = bool(self._device.sys_info["gradually_on_mode"])
            off_enabled = bool(self._device.sys_info["gradually_off_mode"])
            on_duration = self._device.sys_info["fade_on_time"]
            off_duration = self._device.sys_info["fade_off_time"]
        elif (on_state := self.data.get("on_state")) and (
            off_state := self.data.get("off_state")
        ):
            on_max = on_state.get("max_duration", self.MAXIMUM_DURATION)
            off_max = off_state.get("max_duration", self.MAXIMUM_DURATION)
            on_enabled = on_state["enable"]
            off_enabled = off_state["enable"]
            on_duration = on_state["duration"]
            off_duration = off_state["duration"]
        else:
            raise KasaException(
                f"Unsupported for {self.REQUIRED_COMPONENT} v{self.supported_version}"
            )

        self._enabled = on_enabled or off_enabled
        self._on_state = {
            "duration": on_duration,
            "enable": on_enabled,
            "max_duration": on_max,
        }
        self._off_state = {
            "duration": off_duration,
            "enable": off_enabled,
            "max_duration": off_max,
        }

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Enable gradual on/off."""
        if not self._supports_on_and_off:
            return await self.call("set_on_off_gradually_info", {"enable": enable})
        else:
            on = await self.call(
                "set_on_off_gradually_info",
                {
                    "on_state": {
                        "enable": enable,
                        "duration": self._on_state["duration"],
                    }
                },
            )
            off = await self.call(
                "set_on_off_gradually_info",
                {
                    "off_state": {
                        "enable": enable,
                        "duration": self._off_state["duration"],
                    }
                },
            )
            return {**on, **off}

    @property
    def enabled(self) -> bool:
        """Return True if gradual on/off is enabled."""
        return self._enabled

    @property
    def turn_on_transition(self) -> int:
        """Return transition time for turning the light on.

        Available only from v2.
        """
        return self._on_state["duration"] if self._on_state["enable"] else 0

    @property
    def _turn_on_transition_max(self) -> int:
        """Maximum turn on duration."""
        return self._on_state["max_duration"]

    @allow_update_after
    async def set_turn_on_transition(self, seconds: int) -> dict:
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
                {"on_state": {"enable": False, "duration": self._on_state["duration"]}},
            )

        return await self.call(
            "set_on_off_gradually_info",
            {"on_state": {"enable": True, "duration": seconds}},
        )

    @property
    def turn_off_transition(self) -> int:
        """Return transition time for turning the light off.

        Available only from v2.
        """
        return self._off_state["duration"] if self._off_state["enable"] else 0

    @property
    def _turn_off_transition_max(self) -> int:
        """Maximum turn on duration."""
        # v3 added max_duration, we default to 60 when it's not available
        return self._off_state["max_duration"]

    @allow_update_after
    async def set_turn_off_transition(self, seconds: int) -> dict:
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
                {
                    "off_state": {
                        "enable": False,
                        "duration": self._off_state["duration"],
                    }
                },
            )

        return await self.call(
            "set_on_off_gradually_info",
            {"off_state": {"enable": True, "duration": seconds}},
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Some devices have the required info in the device info.
        if self._state_in_sysinfo:
            return {}
        else:
            return {self.QUERY_GETTER_NAME: None}

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        # For devices that report child components on the parent that are not
        # actually supported by the parent.
        return "brightness" in self._device.sys_info
