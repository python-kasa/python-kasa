from dataclasses import replace
from datetime import timedelta

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Module
from kasa.iot import IotStrip
from kasa.iot.iotstrip import IotStripPlug
from kasa.iot.modules.rulemodule import Action, CountdownRule, Rule, TimeOption

from ...device_fixtures import device_iot, plug_iot, strip_iot


@device_iot
@pytest.mark.xdist_group(name="caplog")
def test_schedule(dev: Device, caplog: pytest.LogCaptureFixture) -> None:
    schedule = dev.modules.get(Module.IotSchedule)
    assert schedule
    if rules := schedule.rules:
        first = rules[0]
        assert isinstance(first.sact, Action)
        assert isinstance(first.stime_opt, TimeOption)
    assert "Unable to read rule list" not in caplog.text


def _rule(**kwargs) -> Rule:
    rule = Rule(
        id="00",
        name="",
        enable=1,
        wday=[1, 1, 1, 1, 1, 1, 1],
        repeat=1,
        sact=Action.TurnOn,
        stime_opt=TimeOption.Enabled,
        smin=935,
    )
    return replace(rule, **kwargs)


@plug_iot
async def test_add_edit_rule(dev: Device, mocker: MockerFixture) -> None:
    schedule = dev.modules[Module.IotSchedule]
    query_helper = mocker.patch.object(dev, "_query_helper", return_value={})

    rule = _rule(eact=Action.Disabled, etime_opt=TimeOption.Disabled, emin=0)
    await schedule.add_rule(rule)
    params = {
        "name": "",
        "enable": 1,
        "wday": [1, 1, 1, 1, 1, 1, 1],
        "repeat": 1,
        "sact": 1,
        "stime_opt": 0,
        "smin": 935,
        "eact": -1,
        "etime_opt": -1,
        "emin": 0,
    }
    query_helper.assert_called_with("schedule", "add_rule", params)

    await schedule.edit_rule(rule)
    query_helper.assert_called_with("schedule", "edit_rule", {"id": "00", **params})

    await schedule.set_rule_enabled(rule, False)
    query_helper.assert_called_with(
        "schedule", "edit_rule", {"id": "00", **params, "enable": 0}
    )

    await schedule.set_enabled(False)
    query_helper.assert_called_with("schedule", "set_overall_enable", {"enable": 0})


@plug_iot
async def test_edit_listed_rule(dev: Device, mocker: MockerFixture) -> None:
    """Listed rules lack the unused end action, which the device requires."""
    schedule = dev.modules[Module.IotSchedule]
    query_helper = mocker.patch.object(dev, "_query_helper", return_value={})

    listed = Rule.from_dict(
        {
            "id": "01",
            "name": "",
            "enable": 1,
            "wday": [0, 0, 0, 0, 0, 0, 1],
            "stime_opt": 2,
            "smin": 1000,
            "soffset": 0,
            "sact": 1,
            "eact": -1,
            "repeat": 1,
        }
    )
    await schedule.set_rule_enabled(listed, False)
    query_helper.assert_called_with(
        "schedule",
        "edit_rule",
        {
            "id": "01",
            "name": "",
            "enable": 0,
            "wday": [0, 0, 0, 0, 0, 0, 1],
            "repeat": 1,
            "sact": 1,
            "stime_opt": 2,
            "smin": 1000,
            "soffset": 0,
            "eact": -1,
            "etime_opt": -1,
            "emin": 0,
        },
    )


@plug_iot
async def test_schedule_features(dev: Device, mocker: MockerFixture) -> None:
    schedule = dev.modules[Module.IotSchedule]
    next_action = schedule.data["get_next_action"]

    assert dev.features["schedule_enabled"].value is schedule.enabled
    if next_action.get("type", -1) == -1:
        assert dev.features["next_schedule_time"].value is None
        assert dev.features["next_schedule_action"].value is None
    else:
        midnight = dev.time.replace(hour=0, minute=0, second=0, microsecond=0)
        expected = midnight + timedelta(seconds=next_action["schd_time"])
        assert dev.features["next_schedule_time"].value == expected
        state = {0: "off", 1: "on"}[next_action["action"]]
        assert dev.features["next_schedule_action"].value == state

    query_helper = mocker.patch.object(dev, "_query_helper", return_value={})
    await dev.features["schedule_enabled"].set_value(False)
    query_helper.assert_called_with("schedule", "set_overall_enable", {"enable": 0})


@plug_iot
async def test_no_next_action(dev: Device) -> None:
    schedule = dev.modules[Module.IotSchedule]
    schedule.data["get_next_action"] = {"type": -1, "err_code": 0}
    assert schedule.next_action is None
    assert schedule.next_action_time is None
    assert schedule.next_action_state is None


@strip_iot
async def test_strip_schedule_features(dev: IotStrip, mocker: MockerFixture) -> None:
    """Strips expose schedule features per socket, not on the strip itself."""
    assert "schedule_enabled" not in dev.features
    for child in dev.children:
        assert isinstance(child, IotStripPlug)
        assert "schedule_enabled" in child.features
        query_helper = mocker.patch.object(dev, "_query_helper", return_value={})
        await child.features["schedule_enabled"].set_value(True)
        query_helper.assert_called_with(
            "schedule", "set_overall_enable", {"enable": 1}, child_ids=[child.child_id]
        )


@strip_iot
async def test_countdown_rules(dev: IotStrip, mocker: MockerFixture) -> None:
    child = dev.children[0]
    assert isinstance(child, IotStripPlug)
    countdown = child.modules[Module.IotCountdown]
    countdown.data["get_rules"] = {
        "rule_list": [
            {"id": "32", "name": "", "enable": 1, "delay": 5, "act": 1, "remain": 3}
        ],
        "err_code": 0,
    }
    [rule] = countdown.rules
    assert rule == CountdownRule(
        id="32", name="", enable=1, delay=5, act=Action.TurnOn, remain=3
    )

    query_helper = mocker.patch.object(dev, "_query_helper", return_value={})
    await countdown.edit_rule(rule)
    query_helper.assert_called_with(
        "count_down",
        "edit_rule",
        {"id": "32", "name": "", "enable": 1, "delay": 5, "act": 1},
        child_ids=[child.child_id],
    )
