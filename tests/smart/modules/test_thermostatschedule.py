import pytest

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules.thermostatschedule import ScheduleMode, ScheduleSlot

from ...device_fixtures import parametrize

thermostat_schedule = parametrize(
    "has thermostat schedule",
    component_filter="smart_control_schedule",
    protocol_filter={"SMART.CHILD"},
)


def _day(*slots: tuple[int, int, float]) -> list[ScheduleSlot]:
    return [ScheduleSlot(start, end, temp) for start, end, temp in slots]


@thermostat_schedule
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("thermostat_schedule", "enabled", bool),
    ],
)
async def test_features(
    dev: SmartDevice, feature: str, prop_name: str, type: type
) -> None:
    """Test that features are registered and work as expected."""
    schedule = dev.modules[Module.ThermostatSchedule]

    prop = getattr(schedule, prop_name)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop

    mode_feat = dev.features["thermostat_schedule_mode"]
    assert mode_feat.value == schedule.mode.value
    assert mode_feat.choices == [mode.value for mode in ScheduleMode]


@thermostat_schedule
async def test_set_enabled_and_mode(dev: SmartDevice) -> None:
    """Test enabling the schedule and changing its mode."""
    schedule = dev.modules[Module.ThermostatSchedule]

    await schedule.set_enabled(False)
    await dev.update()
    assert schedule.enabled is False

    await schedule.set_mode(ScheduleMode.SingleDay)
    await dev.update()
    assert schedule.mode is ScheduleMode.SingleDay
    assert schedule.enabled is False

    await dev.features["thermostat_schedule_mode"].set_value("everyday")
    await dev.update()
    assert schedule.mode is ScheduleMode.Everyday


@thermostat_schedule
async def test_get_schedules_pages(dev: SmartDevice) -> None:
    """Test all schedules are fetched across pages."""
    schedule = dev.modules[Module.ThermostatSchedule]
    dev.protocol._transport.list_return_size = 1

    schedules = await schedule.get_schedules()

    assert len(schedules) == 3
    assert {s.day for s in schedules} == {"sunday", "weekday", "saturday"}
    assert schedule.max_slots == 6
    weekday = next(s for s in schedules if s.day == "weekday")
    assert weekday.slot_at(8 * 60).target_temperature == 21
    assert weekday.slot_at(23 * 60).target_temperature == 18
    for day in schedules:
        assert [s.start for s in day.slots] == sorted(s.start for s in day.slots)


@thermostat_schedule
async def test_set_schedule(dev: SmartDevice) -> None:
    """Test replacing the slots of one schedule."""
    schedule = dev.modules[Module.ThermostatSchedule]
    mode = (await schedule.get_schedules())[0].id.split(":")[0]
    new = _day((0, 359, 17), (360, 1289, 20.5), (1290, 1439, 16))

    await schedule.set_schedule(f"{mode}:weekday", new)

    weekday = next(s for s in await schedule.get_schedules() if s.day == "weekday")
    assert weekday.slots == new


@thermostat_schedule
@pytest.mark.parametrize(
    ("slots", "match"),
    [
        pytest.param([], "at least one slot", id="empty"),
        pytest.param(_day((1, 1439, 20)), "whole day", id="late-start"),
        pytest.param(_day((0, 1400, 20)), "whole day", id="early-end"),
        pytest.param(_day((0, 600, 20), (602, 1439, 18)), "minute after", id="gap"),
        pytest.param(_day((0, 600, 20), (500, 1439, 18)), "minute after", id="overlap"),
        pytest.param(_day((0, 1439, 99)), "outside", id="too-hot"),
        pytest.param(
            _day(*[(i * 200, i * 200 + 199, 20) for i in range(7)], (1400, 1439, 18)),
            "at most",
            id="too-many",
        ),
    ],
)
async def test_set_schedule_validation(
    dev: SmartDevice, slots: list[ScheduleSlot], match: str
) -> None:
    """Test invalid schedules are rejected before being sent."""
    schedule = dev.modules[Module.ThermostatSchedule]
    schedule_id = (await schedule.get_schedules())[0].id

    with pytest.raises(ValueError, match=match):
        await schedule.set_schedule(schedule_id, slots)


@thermostat_schedule
async def test_set_schedule_inactive_mode(dev: SmartDevice) -> None:
    """Test only schedules of the active mode can be edited."""
    schedule = dev.modules[Module.ThermostatSchedule]
    schedule_id = (await schedule.get_schedules())[0].id
    active = schedule.mode
    other = next(m for m in ScheduleMode if m is not active)

    await schedule.set_mode(other)
    assert schedule.mode is other  # Cached state updates without an update()
    with pytest.raises(ValueError, match="not in the active mode"):
        await schedule.set_schedule(schedule_id, _day((0, 1439, 20)))

    await schedule.set_mode(active)
    await schedule.set_schedule(schedule_id, _day((0, 1439, 20)))


def test_slot_rule_round_trip() -> None:
    """Test converting slots to and from the device format."""
    slot = ScheduleSlot(420, 1319, 20.5, frost_protection=False)

    as_float = slot._to_rule(use_float=True)
    assert as_float["desired_states"]["target_temp_float"] == 205
    assert "target_temp" not in as_float["desired_states"]
    assert ScheduleSlot._from_rule(as_float) == slot

    as_int = slot._to_rule(use_float=False)
    assert as_int["desired_states"]["target_temp"] == 20
    assert ScheduleSlot._from_rule(as_int).target_temperature == 20
    assert str(slot.start_time) == "07:00:00"
    assert str(slot.end_time) == "21:59:00"
