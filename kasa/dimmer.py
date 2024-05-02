"""Module for bulb and light base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from pydantic.v1 import BaseModel, Field, root_validator

from .device import Device


class BehaviorMode(str, Enum):
    """Enum to present type of turn on behavior."""

    #: Return to the last state known state.
    Last = "last_status"
    #: Use chosen preset.
    Preset = "customize_preset"


class TurnOnBehavior(BaseModel):
    """Model to present a single turn on behavior.

    :param int preset: the index number of wanted preset.
    :param BehaviorMode mode: last status or preset mode.
     If you are changing existing settings, you should not set this manually.

    To change the behavior, it is only necessary to change the :attr:`preset` field
    to contain either the preset index, or ``None`` for the last known state.
    """

    #: Index of preset to use, or ``None`` for the last known state.
    preset: Optional[int] = Field(alias="index", default=None)  # noqa: UP007
    #: Wanted behavior
    mode: BehaviorMode

    @root_validator
    def _mode_based_on_preset(cls, values):
        """Set the mode based on the preset value."""
        if values["preset"] is not None:
            values["mode"] = BehaviorMode.Preset
        else:
            values["mode"] = BehaviorMode.Last

        return values

    class Config:
        """Configuration to make the validator run when changing the values."""

        validate_assignment = True


class TurnOnBehaviors(BaseModel):
    """Model to contain turn on behaviors."""

    #: The behavior when the bulb is turned on programmatically.
    soft: TurnOnBehavior = Field(alias="soft_on")
    #: The behavior when the bulb has been off from mains power.
    hard: TurnOnBehavior = Field(alias="hard_on")


class FadeType(Enum):
    """Fade on/off setting."""

    FadeOn = "fade_on"
    FadeOff = "fade_off"


class ButtonAction(Enum):
    """Button action."""

    NoAction = "none"
    Instant = "instant_on_off"
    Gentle = "gentle_on_off"
    Preset = "customize_preset"


class ActionType(Enum):
    """Button action."""

    DoubleClick = "double_click_action"
    LongPress = "long_press_action"


class Dimmer(Device, ABC):
    """Base class for devices that are dimmers."""

    @property
    @abstractmethod
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""

    @property
    @abstractmethod
    def brightness(self) -> int:
        """Return the current brightness in percentage."""

    @abstractmethod
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """

    @abstractmethod
    async def set_dimmer_transition(self, brightness: int, transition: int):
        """Turn the bulb on to brightness percentage over transition milliseconds.

        A brightness value of 0 will turn off the dimmer.
        """

    @property
    @abstractmethod
    def is_transitions(self):
        """Return True if the dimmer has transition settings."""

    @abstractmethod
    async def set_fade_time(self, fade_type: FadeType, time: int):
        """Set time for fade in / fade out."""

    @property
    def is_on_behaviours(self):
        """Return True if the device has turn on behaviour settings."""

    @abstractmethod
    async def get_behaviors(self):
        """Return button behavior settings."""

    @abstractmethod
    async def get_turn_on_behavior(self) -> TurnOnBehaviors:
        """Return the behavior for turning the bulb on."""

    @abstractmethod
    async def set_turn_on_behavior(self, behavior: TurnOnBehaviors):
        """Set the behavior for turning the bulb on.

        If you do not want to manually construct the behavior object,
        you should use :func:`get_turn_on_behavior` to get the current settings.
        """
