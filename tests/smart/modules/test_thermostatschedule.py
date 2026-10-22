import pytest

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules.thermostatschedule import ScheduleMode, ScheduleSlot

from ...device_fixtures import parametrize
from ...fakeprotocol_smart import FakeSmartTransport

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
    transport = dev.protocol._transport
    assert isinstance(transport, FakeSmartTransport)
    transport.list_return_size = 1

    schedules = await schedule.get_schedules()

    raw = transport.info["get_sc_schedule_rules"]
    assert [s.id for s in schedules] == [r["id"] for r in raw["schedule_list"]]
    assert len(schedules) == raw["sum"]
    assert schedule.max_slots == raw["day_segment"]
    for day, rules in zip(schedules, raw["schedule_list"], strict=True):
        assert day.day == rules["id"].split(":")[1]
        assert len(day.slots) == len(rules["rule_list"])
        assert [s.start for s in day.slots] == sorted(s.start for s in day.slots)
        # Every minute of the day is covered by exactly one slot
        assert all(day.slot_at(minute) for minute in range(24 * 60))


@thermostat_schedule
async def test_get_schedules_module_paging(dev: SmartDevice, mocker) -> None:
    """Test the module fetches further pages itself, keeping schedule_mode.

    Hub children do not page in the protocol, so the module has to.
    """
    schedule = dev.modules[Module.ThermostatSchedule]
    rule = {
        "start_min": 0,
        "end_min": 1439,
        "desired_states": {"target_temp": 20, "temp_unit": "celsius"},
    }

    def page(start: int, ids: list[str], total: int = 3) -> dict:
        return {
            "get_sc_schedule_rules": {
                "schedule_mode": "weekday_sat_sun",
                "day_segment": 6,
                "start_index": start,
                "sum": total,
                "schedule_list": [{"id": i, "rule_list": [rule]} for i in ids],
            }
        }

    call = mocker.patch.object(
        schedule,
        "call",
        side_effect=[
            page(0, ["weekday_sat_sun:sunday"]),
            page(1, ["weekday_sat_sun:weekday", "weekday_sat_sun:saturday"]),
        ],
    )
    schedules = await schedule.get_schedules(ScheduleMode.WeekdaySatSun)

    assert [s.day for s in schedules] == ["sunday", "weekday", "saturday"]
    assert schedules[0].slots[0].target_temperature == 20
    assert call.call_args_list[1].args == (
        "get_sc_schedule_rules",
        {"schedule_mode": "weekday_sat_sun", "start_index": 1},
    )

    # An empty page ends the fetch rather than looping forever
    call.side_effect = [page(0, ["weekday_sat_sun:sunday"]), page(1, [])]
    assert len(await schedule.get_schedules(ScheduleMode.WeekdaySatSun)) == 1


@thermostat_schedule
async def test_set_schedule(dev: SmartDevice) -> None:
    """Test replacing the slots of one schedule."""
    schedule = dev.modules[Module.ThermostatSchedule]
    schedule_id = (await schedule.get_schedules())[-1].id
    new = _day((0, 359, 17), (360, 1289, 20.5), (1290, 1439, 16))

    await schedule.set_schedule(schedule_id, new)

    updated = next(s for s in await schedule.get_schedules() if s.id == schedule_id)
    assert updated.slots == new


@thermostat_schedule
async def test_set_schedule_detects_float_support(dev: SmartDevice, mocker) -> None:
    """Test set_schedule fetches the schedules first to pick the temp format."""
    schedule = dev.modules[Module.ThermostatSchedule]
    raw = await schedule.call(
        "get_sc_schedule_rules",
        {"schedule_mode": schedule.mode.value, "start_index": 0},
    )
    first = raw["get_sc_schedule_rules"]["schedule_list"][0]
    uses_float = any(
        "target_temp_float" in r["desired_states"] for r in first["rule_list"]
    )
    assert schedule._uses_float is None
    get = mocker.spy(schedule, "get_schedules")
    call = mocker.spy(schedule, "call")

    await schedule.set_schedule(first["id"], _day((0, 1439, 20.5)))

    get.assert_called_once()
    edit = next(c for c in call.call_args_list if c.args[0] == "edit_sc_schedule_rule")
    states = edit.args[1]["rule_list"][0]["desired_states"]
    if uses_float:
        assert states["target_temp_float"] == 205
    else:
        assert states["target_temp"] == 20


@thermostat_schedule
@pytest.mark.parametrize(
    ("slots", "match"),
    [
        pytest.param([], "at least one slot", id="empty"),
        pytest.param(_day((1, 1439, 20)), "whole day", id="late-start"),
        pytest.param(_day((0, 1400, 20)), "whole day", id="early-end"),
        pytest.param(_day((0, 600, 20), (602, 1439, 18)), "minute after", id="gap"),
        pytest.param(_day((0, 600, 20), (500, 1439, 18)), "minute after", id="overlap"),
        pytest.param(
            _day((0, 100, 20), (101, 100, 19), (101, 1439, 18)),
            "ends before it starts",
            id="backwards",
        ),
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
