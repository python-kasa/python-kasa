"""Module for base alarm module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated

from ..module import FeatureAttribute, Module


class Alarm(Module, ABC):
    """Base interface to represent an alarm module."""

    @property
    @abstractmethod
    def alarm_sound(self) -> Annotated[str, FeatureAttribute()]:
        """Return current alarm sound."""

    @abstractmethod
    async def set_alarm_sound(self, sound: str) -> Annotated[dict, FeatureAttribute()]:
        """Set alarm sound.

        See *alarm_sounds* for list of available sounds.
        """

    @property
    @abstractmethod
    def alarm_sounds(self) -> list[str]:
        """Return list of available alarm sounds."""

    @property
    @abstractmethod
    def alarm_volume(self) -> Annotated[int, FeatureAttribute()]:
        """Return alarm volume."""

    @abstractmethod
    async def set_alarm_volume(
        self, volume: int
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set alarm volume."""

    @property
    @abstractmethod
    def alarm_duration(self) -> Annotated[int, FeatureAttribute()]:
        """Return alarm duration."""

    @abstractmethod
    async def set_alarm_duration(
        self, duration: int
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set alarm duration."""

    @property
    @abstractmethod
    def active(self) -> bool:
        """Return true if alarm is active."""

    @abstractmethod
    async def play(
        self,
        *,
        duration: int | None = None,
        volume: int | None = None,
        sound: str | None = None,
    ) -> dict:
        """Play alarm.

        The optional *duration*, *volume*, and *sound* to override the device settings.
        *duration* is in seconds.
        See *alarm_sounds* for the list of sounds available for the device.
        """

    @abstractmethod
    async def stop(self) -> dict:
        """Stop alarm."""
