import pytest
from asyncclick.testing import CliRunner
from pytest_mock import MockerFixture

from kasa import Device, Module
from kasa.cli.schedule import schedule
from kasa.iot.modules.rulemodule import Action, CountdownRule, Rule, TimeOption

from ..device_fixtures import plug_iot, strip_iot


@plug_iot
async def test_schedule_list(dev: Device, runner: CliRunner) -> None:
    res = await runner.invoke(schedule, ["list"], obj=dev)
    rules = dev.modules[Module.IotSchedule].rules
    if rules:
        assert res.exit_code == 0
        assert f"id='{rules[0].id}'" in res.output
        assert "No rules" not in res.output
    else:
        assert "No rules of type schedule" in res.output


@strip_iot
async def test_schedule_list_countdown_empty(dev: Device, runner: CliRunner) -> None:
    res = await runner.invoke(schedule, ["list", "countdown", "--index", "0"], obj=dev)
    assert "No rules of type countdown" in res.output
    assert res.exit_code == 1


@plug_iot
@pytest.mark.parametrize(
    ("args", "wday", "stime_opt", "smin", "enable"),
    [
        (["--time", "15:35"], [1] * 7, TimeOption.Enabled, 935, 1),
        (
            ["--time", "06:55", "--days", "mon,tue,wed,thu,fri"],
            [0, 1, 1, 1, 1, 1, 0],
            TimeOption.Enabled,
            415,
            1,
        ),
        (
            ["--time", "sunset", "--days", "Sat,sun", "--disabled"],
            [1, 0, 0, 0, 0, 0, 1],
            TimeOption.AtSunset,
            0,
            0,
        ),
    ],
)
async def test_schedule_add(
    dev: Device,
    mocker: MockerFixture,
    runner: CliRunner,
    args,
    wday,
    stime_opt,
    smin,
    enable,
) -> None:
    module = dev.modules[Module.IotSchedule]
    add_rule = mocker.patch.object(module, "add_rule", return_value={"id": "07"})

    res = await runner.invoke(
        schedule, ["add", "--action", "on", *args], obj=dev, catch_exceptions=False
    )

    assert res.exit_code == 0, res.output
    assert "Added rule id 07" in res.output
    rule: Rule = add_rule.call_args.args[0]
    assert rule.wday == wday
    assert rule.sact is Action.TurnOn
    assert (rule.stime_opt, rule.smin, rule.enable) == (stime_opt, smin, enable)


@plug_iot
@pytest.mark.parametrize(
    "args",
    [["--time", "25:00"], ["--time", "noon"], ["--time", "1:00", "--days", "xyz"]],
)
async def test_schedule_add_invalid(
    dev: Device, mocker: MockerFixture, runner: CliRunner, args
) -> None:
    add_rule = mocker.patch.object(dev.modules[Module.IotSchedule], "add_rule")
    res = await runner.invoke(schedule, ["add", "--action", "off", *args], obj=dev)
    assert res.exit_code == 2
    add_rule.assert_not_called()


@strip_iot
async def test_schedule_countdown(
    dev: Device, mocker: MockerFixture, runner: CliRunner
) -> None:
    module = dev.children[0].modules[Module.IotCountdown]
    add_rule = mocker.patch.object(module, "add_rule", return_value={"id": "32"})

    res = await runner.invoke(
        schedule,
        ["countdown", "--index", "0", "--action", "off", "--delay", "60"],
        obj=dev,
        catch_exceptions=False,
    )

    assert res.exit_code == 0, res.output
    assert "Added countdown rule id 32" in res.output
    add_rule.assert_awaited_with(
        CountdownRule(id="", name="", enable=1, delay=60, act=Action.TurnOff)
    )


@plug_iot
@pytest.mark.parametrize("command", ["enable", "disable"])
async def test_schedule_enable_disable(
    dev: Device, mocker: MockerFixture, runner: CliRunner, command: str
) -> None:
    module = dev.modules[Module.IotSchedule]
    state = command == "enable"

    set_enabled = mocker.patch.object(module, "set_enabled")
    res = await runner.invoke(schedule, [command], obj=dev, catch_exceptions=False)
    assert res.exit_code == 0, res.output
    set_enabled.assert_awaited_with(state)

    if not (rules := module.rules):
        return
    set_rule_enabled = mocker.patch.object(module, "set_rule_enabled")
    res = await runner.invoke(
        schedule, [command, "--id", rules[0].id], obj=dev, catch_exceptions=False
    )
    assert res.exit_code == 0, res.output
    set_rule_enabled.assert_awaited_with(rules[0], state)

    res = await runner.invoke(schedule, [command, "--id", "nope"], obj=dev)
    assert "No rule with id nope was found" in res.output
    assert res.exit_code == 1


@plug_iot
async def test_schedule_delete(
    dev: Device, mocker: MockerFixture, runner: CliRunner
) -> None:
    module = dev.modules[Module.IotSchedule]
    delete_rule = mocker.patch.object(module, "delete_rule")

    res = await runner.invoke(schedule, ["delete", "--id", "nope"], obj=dev)
    assert "No rule with id nope was found" in res.output
    delete_rule.assert_not_called()

    if not (rules := module.rules):
        return
    res = await runner.invoke(
        schedule, ["delete", "--id", rules[0].id], obj=dev, catch_exceptions=False
    )
    assert res.exit_code == 0, res.output
    delete_rule.assert_awaited_with(rules[0])
