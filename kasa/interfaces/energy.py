"""Module for base energy module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import IntFlag, auto
from warnings import warn

from ..emeterstatus import EmeterStatus
from ..feature import Feature
from ..module import Module


class Energy(Module, ABC):
    """Base interface to represent an Energy module."""

    class ModuleFeature(IntFlag):
        """Features supported by the device."""

        #: Device reports :attr:`voltage` and :attr:`current`
        VOLTAGE_CURRENT = auto()
        #: Device reports :attr:`consumption_total`
        CONSUMPTION_TOTAL = auto()
        #: Device reports periodic stats via :meth:`get_daily_stats`
        #: and :meth:`get_monthly_stats`
        PERIODIC_STATS = auto()

    _supported: ModuleFeature = ModuleFeature(0)

    def supports(self, module_feature: ModuleFeature) -> bool:
        """Return True if module supports the feature."""
        return module_feature in self._supported

    def _initialize_features(self):
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device,
                name="Current consumption",
                attribute_getter="current_consumption",
                container=self,
                unit="W",
                id="current_consumption",
                precision_hint=1,
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                device,
                name="Today's consumption",
                attribute_getter="consumption_today",
                container=self,
                unit="kWh",
                id="consumption_today",
                precision_hint=3,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="consumption_this_month",
                name="This month's consumption",
                attribute_getter="consumption_this_month",
                container=self,
                unit="kWh",
                precision_hint=3,
                category=Feature.Category.Info,
            )
        )
        if self.supports(self.ModuleFeature.CONSUMPTION_TOTAL):
            self._add_feature(
                Feature(
                    device,
                    name="Total consumption since reboot",
                    attribute_getter="consumption_total",
                    container=self,
                    unit="kWh",
                    id="consumption_total",
                    precision_hint=3,
                    category=Feature.Category.Info,
                )
            )
        if self.supports(self.ModuleFeature.VOLTAGE_CURRENT):
            self._add_feature(
                Feature(
                    device,
                    name="Voltage",
                    attribute_getter="voltage",
                    container=self,
                    unit="V",
                    id="voltage",
                    precision_hint=1,
                    category=Feature.Category.Primary,
                )
            )
            self._add_feature(
                Feature(
                    device,
                    name="Current",
                    attribute_getter="current",
                    container=self,
                    unit="A",
                    id="current",
                    precision_hint=2,
                    category=Feature.Category.Primary,
                )
            )

    @property
    @abstractmethod
    def status(self) -> EmeterStatus:
        """Return current energy readings."""

    @property
    @abstractmethod
    def current_consumption(self) -> float | None:
        """Get the current power consumption in Watt."""

    @property
    @abstractmethod
    def consumption_today(self) -> float | None:
        """Return today's energy consumption in kWh."""

    @property
    @abstractmethod
    def consumption_this_month(self) -> float | None:
        """Return this month's energy consumption in kWh."""

    @property
    @abstractmethod
    def consumption_total(self) -> float | None:
        """Return total consumption since last reboot in kWh."""

    @property
    @abstractmethod
    def current(self) -> float | None:
        """Return the current in A."""

    @property
    @abstractmethod
    def voltage(self) -> float | None:
        """Get the current voltage in V."""

    @abstractmethod
    async def get_status(self):
        """Return real-time statistics."""

    @abstractmethod
    async def erase_stats(self):
        """Erase all stats."""

    @abstractmethod
    async def get_daily_stats(self, *, year=None, month=None, kwh=True) -> dict:
        """Return daily stats for the given year & month.

        The return value is a dictionary of {day: energy, ...}.
        """

    @abstractmethod
    async def get_monthly_stats(self, *, year=None, kwh=True) -> dict:
        """Return monthly stats for the given year."""

    _deprecated_attributes = {
        "emeter_today": "consumption_today",
        "emeter_this_month": "consumption_this_month",
        "realtime": "status",
        "get_realtime": "get_status",
        "erase_emeter_stats": "erase_stats",
        "get_daystat": "get_daily_stats",
        "get_monthstat": "get_monthly_stats",
    }

    def __getattr__(self, name):
        if attr := self._deprecated_attributes.get(name):
            msg = f"{name} is deprecated, use {attr} instead"
            warn(msg, DeprecationWarning, stacklevel=1)
            return getattr(self, attr)
        raise AttributeError(f"Energy module has no attribute {name!r}")
