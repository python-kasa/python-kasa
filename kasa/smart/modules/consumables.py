"""Implementation of vacuum consumables."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


@dataclass
class _ConsumableMeta:
    """Consumable meta container."""

    #: Name of the consumable.
    name: str
    #: Internal id of the consumable
    id: str
    #: Data key in the device reported data
    data_key: str
    #: Lifetime
    lifetime: timedelta


@dataclass
class Consumable:
    """Consumable container."""

    #: Name of the consumable.
    name: str
    #: Id of the consumable
    id: str
    #: Lifetime
    lifetime: timedelta
    #: Used
    used: timedelta
    #: Remaining
    remaining: timedelta
    #: Device data key
    _data_key: str


CONSUMABLE_METAS = [
    _ConsumableMeta(
        "Main brush",
        id="main_brush",
        data_key="roll_brush_time",
        lifetime=timedelta(hours=400),
    ),
    _ConsumableMeta(
        "Side brush",
        id="side_brush",
        data_key="edge_brush_time",
        lifetime=timedelta(hours=200),
    ),
    _ConsumableMeta(
        "Filter",
        id="filter",
        data_key="filter_time",
        lifetime=timedelta(hours=200),
    ),
    _ConsumableMeta(
        "Sensor",
        id="sensor",
        data_key="sensor_time",
        lifetime=timedelta(hours=30),
    ),
    _ConsumableMeta(
        "Charging contacts",
        id="charging_contacts",
        data_key="charge_contact_time",
        lifetime=timedelta(hours=30),
    ),
    # Unknown keys: main_brush_lid_time, rag_time
]


class Consumables(SmartModule):
    """Implementation of vacuum consumables."""

    REQUIRED_COMPONENT = "consumables"
    QUERY_GETTER_NAME = "getConsumablesInfo"

    _consumables: dict[str, Consumable] = {}

    def _initialize_features(self) -> None:
        """Initialize features."""
        for c_meta in CONSUMABLE_METAS:
            if c_meta.data_key not in self.data:
                continue

            self._add_feature(
                Feature(
                    self._device,
                    id=f"{c_meta.id}_used",
                    name=f"{c_meta.name} used",
                    container=self,
                    attribute_getter=lambda _, c_id=c_meta.id: self._consumables[
                        c_id
                    ].used,
                    category=Feature.Category.Debug,
                    type=Feature.Type.Sensor,
                )
            )

            self._add_feature(
                Feature(
                    self._device,
                    id=f"{c_meta.id}_remaining",
                    name=f"{c_meta.name} remaining",
                    container=self,
                    attribute_getter=lambda _, c_id=c_meta.id: self._consumables[
                        c_id
                    ].remaining,
                    category=Feature.Category.Info,
                    type=Feature.Type.Sensor,
                )
            )

            self._add_feature(
                Feature(
                    self._device,
                    id=f"{c_meta.id}_reset",
                    name=f"Reset {c_meta.name.lower()} consumable",
                    container=self,
                    attribute_setter=lambda c_id=c_meta.id: self.reset_consumable(c_id),
                    category=Feature.Category.Debug,
                    type=Feature.Type.Action,
                )
            )

    async def _post_update_hook(self) -> None:
        """Update the consumables."""
        if not self._consumables:
            for consumable_meta in CONSUMABLE_METAS:
                if consumable_meta.data_key not in self.data:
                    continue
                used = timedelta(minutes=self.data[consumable_meta.data_key])
                consumable = Consumable(
                    id=consumable_meta.id,
                    name=consumable_meta.name,
                    lifetime=consumable_meta.lifetime,
                    used=used,
                    remaining=consumable_meta.lifetime - used,
                    _data_key=consumable_meta.data_key,
                )
                self._consumables[consumable_meta.id] = consumable
        else:
            for consumable in self._consumables.values():
                consumable.used = timedelta(minutes=self.data[consumable._data_key])
                consumable.remaining = consumable.lifetime - consumable.used

    async def reset_consumable(self, consumable_id: str) -> dict:
        """Reset consumable stats."""
        consumable_name = self._consumables[consumable_id]._data_key.removesuffix(
            "_time"
        )
        return await self.call(
            "resetConsumablesTime", {"reset_list": [consumable_name]}
        )

    @property
    def consumables(self) -> Mapping[str, Consumable]:
        """Get list of consumables on the device."""
        return self._consumables
