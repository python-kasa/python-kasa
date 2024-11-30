"""Implementation of vacuum consumables."""

from __future__ import annotations

import logging

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class VacuumConsumables(SmartModule):
    """Implementation of vacuum consumables."""

    REQUIRED_COMPONENT = "consumables"
    QUERY_GETTER_NAME = "getConsumablesInfo"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="consumable_charge_contact",
                name="Charge contact time",
                container=self,
                attribute_getter="charge_contact",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="consumable_main_brush_lid",
                name="Main brush lid time",
                container=self,
                attribute_getter="main_brush_lid",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="consumable_edge_brush",
                name="Edge brush time",
                container=self,
                attribute_getter="edge_brush",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="consumable_roll_brush",
                name="Roll brush time",
                container=self,
                attribute_getter="roll_brush",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="consumable_filter",
                name="Filter time",
                container=self,
                attribute_getter="filter",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="consumable_rag",
                name="Rag time",
                container=self,
                attribute_getter="rag",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="consumable_sensor",
                name="Sensor time",
                container=self,
                attribute_getter="sensor",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )

    @property
    def charge_contact(self) -> int:
        """Time disconnected from charger?"""
        return self.data["charge_contact_time"]

    @property
    def main_brush_lid(self) -> int:
        """Main brush time? Or something else?"""
        return self.data["main_brush_lid_time"]

    @property
    def edge_brush(self) -> int:
        """Edge brush time."""
        return self.data["edge_brush_time"]

    @property
    def roll_brush(self) -> int:
        """Roll brush time."""
        return self.data["roll_brush_time"]

    @property
    def filter(self) -> int:
        """Filter time."""
        return self.data["filter_time"]

    @property
    def rag(self) -> int:
        """Rag time."""
        return self.data["rag_time"]

    @property
    def sensor(self) -> int:
        """Sensor time.."""
        return self.data["sensor_time"]
