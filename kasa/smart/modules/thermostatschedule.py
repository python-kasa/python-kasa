"""Implementation of the thermostat (smart control) schedule module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import TYPE_CHECKING, Any

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice

MINUTES_PER_DAY = 24 * 60


class ScheduleMode(Enum):
    """How the week is split into schedules."""

    #: One schedule used for every day.
    Everyday = "everyday"
    #: One schedule for weekdays, one for Saturday and one for Sunday.
    WeekdaySatSun = "weekday_sat_sun"
    #: A separate schedule for each day of the week.
    SingleDay = "single_day"


@dataclass
class ScheduleSlot:
    """A period of the day with a target temperature.

    ``start`` and ``end`` are minutes from midnight, both inclusive,
    so a full day ends at minute 1439.
    """

    start: int
    end: int
    target_temperature: float
    frost_protection: bool = False

    @property
    def start_time(self) -> time:
        """Return the start of the slot as a time."""
        return time(self.start // 60, self.start % 60)

    @property
    def end_time(self) -> time:
        """Return the last minute of the slot as a time."""
        return time(self.end // 60, self.end % 60)

    @classmethod
    def _from_rule(cls, rule: dict[str, Any]) -> ScheduleSlot:
        states = rule["desired_states"]
        if (temp_float := states.get("target_temp_float")) is not None:
            target = temp_float / 10
        else:
            target = float(states["target_temp"])
        return cls(
            start=rule["start_min"],
            end=rule["end_min"],
            target_temperature=target,
            frost_protection=bool(states.get("frost_protection_on", False)),
        )

    def _to_rule(self, *, use_float: bool) -> dict[str, Any]:
        states: dict[str, Any] = {
            "frost_protection_on": self.frost_protection,
            "temp_unit": "celsius",
        }
        if use_float:
            states["target_temp_float"] = round(self.target_temperature * 10)
        else:
            states["target_temp"] = int(self.target_temperature)
        return {"start_min": self.start, "end_min": self.end, "desired_states": states}


@dataclass
class DaySchedule:
    """The slots for one schedule, e.g. ``weekday_sat_sun:saturday``."""

    id: str
    slots: list[ScheduleSlot] = field(default_factory=list)

    @property
    def day(self) -> str:
        """Return the day part of the id, e.g. ``saturday`` or ``everyday``."""
        return self.id.split(":", 1)[-1]

    def slot_at(self, minute: int) -> ScheduleSlot | None:
        """Return the slot active at the given minute of the day."""
        return next((s for s in self.slots if s.start <= minute <= s.end), None)


class ThermostatSchedule(SmartModule):
    """Implementation of the thermostat schedule (smart control) module.

    The schedule mode and whether the schedule is enabled are read during
    the update cycle. The schedules themselves are only fetched on request
    via :meth:`get_schedules`, as they depend on the mode and are paginated.
    """

    REQUIRED_COMPONENT = "smart_control_schedule"
    QUERY_GETTER_NAME = "get_sc_schedule_info"

    def __init__(self, device: SmartDevice, module: str) -> None:
        super().__init__(device, module)
        self._max_slots: int | None = None
        self._uses_float: bool | None = None

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="thermostat_schedule",
                name="Schedule",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="thermostat_schedule_mode",
                name="Schedule mode",
                container=self,
                attribute_getter=lambda m: m.mode.value,
                attribute_setter="set_mode",
                choices_getter=lambda: [mode.value for mode in ScheduleMode],
                type=Feature.Type.Choice,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return True if the schedule is controlling the thermostat."""
        return self.data["enable"]

    @property
    def mode(self) -> ScheduleMode:
        """Return the active schedule mode."""
        return ScheduleMode(self.data["mode"])

    @property
    def max_slots(self) -> int | None:
        """Return the maximum number of slots per day, once schedules are fetched."""
        return self._max_slots

    async def set_enabled(self, enabled: bool) -> dict:
        """Enable or disable the schedule."""
        return await self._set_info(enable=enabled, mode=self.mode)

    async def set_mode(self, mode: ScheduleMode | str) -> dict:
        """Set the schedule mode."""
        return await self._set_info(enable=self.enabled, mode=ScheduleMode(mode))

    async def _set_info(self, *, enable: bool, mode: ScheduleMode) -> dict:
        res = await self.call(
            "set_sc_schedule_info", {"enable": enable, "mode": mode.value}
        )
        # Keep the cached state current, as hub children update infrequently.
        self.data.update({"enable": enable, "mode": mode.value})
        self._last_update_time = None
        return res

    async def get_schedules(
        self, mode: ScheduleMode | str | None = None
    ) -> list[DaySchedule]:
        """Fetch the schedules for a mode, defaulting to the active mode."""
        mode = ScheduleMode(mode) if mode is not None else self.mode
        rules: list[dict] = []
        while True:
            resp = await self.call(
                "get_sc_schedule_rules",
                {"schedule_mode": mode.value, "start_index": len(rules)},
            )
            page = resp["get_sc_schedule_rules"]
            rules.extend(page["schedule_list"])
            self._max_slots = page.get("day_segment", self._max_slots)
            if not page["schedule_list"] or len(rules) >= page["sum"]:
                break

        schedules = [
            DaySchedule(
                id=rule["id"],
                # Devices do not always return the slots in time order.
                slots=sorted(
                    (ScheduleSlot._from_rule(r) for r in rule["rule_list"]),
                    key=lambda s: s.start,
                ),
            )
            for rule in rules
        ]
        if self._uses_float is None:
            self._uses_float = any(
                "target_temp_float" in r["desired_states"]
                for rule in rules
                for r in rule["rule_list"]
            )
        return schedules

    async def set_schedule(self, schedule_id: str, slots: list[ScheduleSlot]) -> dict:
        """Replace the slots of one schedule, e.g. ``everyday:everyday``.

        Only schedules of the active mode can be edited, so use
        :meth:`set_mode` first to edit another mode's schedules.
        The slots must cover the whole day without gaps or overlaps.
        """
        mode = self.mode
        if not schedule_id.startswith(f"{mode.value}:"):
            raise ValueError(
                f"Schedule {schedule_id} is not in the active mode {mode.value}, "
                "use set_mode() first"
            )
        slots = sorted(slots, key=lambda s: s.start)
        self._validate_slots(slots)
        if self._uses_float is None:
            await self.get_schedules(mode)

        return await self.call(
            "edit_sc_schedule_rule",
            {
                "schedule_mode": mode.value,
                "id": schedule_id,
                "rule_list": [
                    s._to_rule(use_float=bool(self._uses_float)) for s in slots
                ],
            },
        )

    def _validate_slots(self, slots: list[ScheduleSlot]) -> None:
        if not slots:
            raise ValueError("A schedule needs at least one slot")
        if self._max_slots and len(slots) > self._max_slots:
            raise ValueError(f"A schedule can have at most {self._max_slots} slots")
        if slots[0].start != 0 or slots[-1].end != MINUTES_PER_DAY - 1:
            raise ValueError("Slots must cover the whole day, from 00:00 to 23:59")
        for prev, cur in zip(slots, slots[1:], strict=False):
            if cur.start != prev.end + 1:
                raise ValueError(
                    f"Slot starting at {cur.start_time} must start the minute "
                    f"after the previous slot ends ({prev.end_time})"
                )

        info = self._device.sys_info
        low, high = info.get("min_control_temp"), info.get("max_control_temp")
        for slot in slots:
            if slot.end < slot.start:
                raise ValueError(f"Slot at {slot.start_time} ends before it starts")
            if (
                low is not None
                and high is not None
                and not low <= slot.target_temperature <= high
            ):
                raise ValueError(
                    f"Target {slot.target_temperature} outside {low}-{high}"
                )

    async def _check_supported(self) -> bool:
        """Only thermostats provide schedules through this component."""
        return "target_temp" in self._device.sys_info
