"""Implementation of vacuum cleaning records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import Annotated, cast

from mashumaro import DataClassDictMixin, field_options
from mashumaro.config import ADD_DIALECT_SUPPORT
from mashumaro.dialect import Dialect
from mashumaro.types import SerializationStrategy

from ...feature import Feature
from ...module import FeatureAttribute
from ..smartmodule import Module, SmartModule
from .clean import AreaUnit, Clean

_LOGGER = logging.getLogger(__name__)


@dataclass
class Record(DataClassDictMixin):
    """Historical cleanup result."""

    class Config:
        """Configuration class."""

        code_generation_options = [ADD_DIALECT_SUPPORT]

    #: Total time cleaned (in minutes)
    clean_time: timedelta = field(
        metadata=field_options(deserialize=lambda x: timedelta(minutes=x))
    )
    #: Total area cleaned
    clean_area: int
    dust_collection: bool
    timestamp: datetime

    info_num: int | None = None
    message: int | None = None
    map_id: int | None = None
    start_type: int | None = None
    task_type: int | None = None
    record_index: int | None = None

    #: Error code from cleaning
    error: int = field(default=0)


class _DateTimeSerializationStrategy(SerializationStrategy):
    def __init__(self, tz: tzinfo) -> None:
        self.tz = tz

    def deserialize(self, value: float) -> datetime:
        return datetime.fromtimestamp(value, self.tz)


def _get_tz_strategy(tz: tzinfo) -> type[Dialect]:
    """Return a timezone aware de-serialization strategy."""

    class TimezoneDialect(Dialect):
        serialization_strategy = {datetime: _DateTimeSerializationStrategy(tz)}

    return TimezoneDialect


@dataclass
class Records(DataClassDictMixin):
    """Response payload for getCleanRecords."""

    class Config:
        """Configuration class."""

        code_generation_options = [ADD_DIALECT_SUPPORT]

    total_time: timedelta = field(
        metadata=field_options(deserialize=lambda x: timedelta(minutes=x))
    )
    total_area: int
    total_count: int = field(metadata=field_options(alias="total_number"))

    records: list[Record] = field(metadata=field_options(alias="record_list"))
    last_clean: Record = field(metadata=field_options(alias="lastest_day_record"))

    @classmethod
    def __pre_deserialize__(cls, d: dict) -> dict:
        if ldr := d.get("lastest_day_record"):
            d["lastest_day_record"] = {
                "timestamp": ldr[0],
                "clean_time": ldr[1],
                "clean_area": ldr[2],
                "dust_collection": ldr[3],
            }
        return d


class CleanRecords(SmartModule):
    """Implementation of vacuum cleaning records."""

    REQUIRED_COMPONENT = "clean_percent"
    _parsed_data: Records

    async def _post_update_hook(self) -> None:
        """Cache parsed data after an update."""
        self._parsed_data = Records.from_dict(
            self.data, dialect=_get_tz_strategy(self._device.timezone)
        )

    def _initialize_features(self) -> None:
        """Initialize features."""
        for type_ in ["total", "last"]:
            self._add_feature(
                Feature(
                    self._device,
                    id=f"{type_}_clean_area",
                    name=f"{type_.capitalize()} area cleaned",
                    container=self,
                    attribute_getter=f"{type_}_clean_area",
                    unit_getter="area_unit",
                    category=Feature.Category.Debug,
                    type=Feature.Type.Sensor,
                )
            )
            self._add_feature(
                Feature(
                    self._device,
                    id=f"{type_}_clean_time",
                    name=f"{type_.capitalize()} time cleaned",
                    container=self,
                    attribute_getter=f"{type_}_clean_time",
                    category=Feature.Category.Debug,
                    type=Feature.Type.Sensor,
                )
            )
        self._add_feature(
            Feature(
                self._device,
                id="total_clean_count",
                name="Total clean count",
                container=self,
                attribute_getter="total_clean_count",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="last_clean_timestamp",
                name="Last clean timestamp",
                container=self,
                attribute_getter="last_clean_timestamp",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getCleanRecords": {},
        }

    @property
    def total_clean_area(self) -> Annotated[int, FeatureAttribute()]:
        """Return total cleaning area."""
        return self._parsed_data.total_area

    @property
    def total_clean_time(self) -> timedelta:
        """Return total cleaning time."""
        return self._parsed_data.total_time

    @property
    def total_clean_count(self) -> int:
        """Return total clean count."""
        return self._parsed_data.total_count

    @property
    def last_clean_area(self) -> Annotated[int, FeatureAttribute()]:
        """Return latest cleaning area."""
        return self._parsed_data.last_clean.clean_area

    @property
    def last_clean_time(self) -> timedelta:
        """Return total cleaning time."""
        return self._parsed_data.last_clean.clean_time

    @property
    def last_clean_timestamp(self) -> datetime:
        """Return latest cleaning timestamp."""
        return self._parsed_data.last_clean.timestamp

    @property
    def area_unit(self) -> AreaUnit:
        """Return area unit."""
        clean = cast(Clean, self._device.modules[Module.Clean])
        return clean.area_unit

    @property
    def parsed_data(self) -> Records:
        """Return parsed records data."""
        return self._parsed_data
