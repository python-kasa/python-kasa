"""Module for cli schedule commands.."""

from __future__ import annotations

import asyncclick as click

from ..iot.modules.rulemodule import Action, CountdownRule, Rule, TimeOption
from .common import (
    echo,
    error,
    pass_dev,
    pass_dev_or_child,
)

RULE_TYPES = click.Choice(["schedule", "countdown", "anti_theft"])
DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
ACTIONS = {"on": Action.TurnOn, "off": Action.TurnOff}


def _module(dev, type: str):
    """Return the rule module of the given type, or exit with an error."""
    if (module := dev.modules.get(type)) is None:
        error(f"Device does not support {type} rules")
    return module


def _find_rule(module, id: str):
    """Return the rule with the given id, or exit with an error."""
    if (rule := next((r for r in module.rules if r.id == id), None)) is None:
        error(f"No rule with id {id} was found")
    return rule


def _parse_time(value: str) -> tuple[TimeOption, int]:
    """Parse HH:MM, sunrise or sunset into a time option and minutes."""
    if value.lower() == "sunrise":
        return TimeOption.AtSunrise, 0
    if value.lower() == "sunset":
        return TimeOption.AtSunset, 0
    try:
        hours, minutes = (int(part) for part in value.split(":"))
    except ValueError:
        raise click.BadParameter(f"{value} is not HH:MM, sunrise or sunset") from None
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise click.BadParameter(f"{value} is not a valid time")
    return TimeOption.Enabled, hours * 60 + minutes


def _parse_days(value: str) -> list[int]:
    """Parse a comma separated list of weekdays into the device's day flags."""
    days = {day.strip().lower()[:3] for day in value.split(",")}
    if "all" in days:
        return [1] * 7
    if unknown := days - set(DAYS):
        raise click.BadParameter(f"Unknown days: {', '.join(sorted(unknown))}")
    return [int(day in days) for day in DAYS]


@click.group()
@pass_dev
async def schedule(dev) -> None:
    """Scheduling commands."""


@schedule.command(name="list")
@click.argument("type", default="schedule", type=RULE_TYPES)
@pass_dev_or_child
async def _schedule_list(dev, type):
    """Return the list of schedule actions for the given type."""
    module = _module(dev, type)
    if not (rules := module.rules):
        error(f"No rules of type {type}")
    for rule in rules:
        echo(rule)

    return rules


@schedule.command(name="add")
@click.option("--action", type=click.Choice(list(ACTIONS)), required=True)
@click.option("--time", "time_", required=True, help="HH:MM, sunrise or sunset.")
@click.option(
    "--days",
    default="all",
    show_default=True,
    help="Comma separated weekdays, e.g. mon,tue,wed.",
)
@click.option("--disabled", is_flag=True, help="Add the rule disabled.")
@pass_dev_or_child
async def add_rule(dev, action, time_, days, disabled):
    """Add a schedule rule."""
    time_option, minutes = _parse_time(time_)
    rule = Rule(
        id="",
        name="",
        enable=int(not disabled),
        wday=_parse_days(days),
        repeat=1,
        sact=ACTIONS[action],
        stime_opt=time_option,
        smin=minutes,
        eact=Action.Disabled,
        etime_opt=TimeOption.Disabled,
        emin=0,
    )
    res = await _module(dev, "schedule").add_rule(rule)
    echo(f"Added rule id {res.get('id')}")
    return res


@schedule.command(name="countdown")
@click.option("--action", type=click.Choice(list(ACTIONS)), required=True)
@click.option("--delay", type=int, required=True, help="Seconds until the action.")
@pass_dev_or_child
async def add_countdown(dev, action, delay):
    """Turn the device on or off after a delay."""
    rule = CountdownRule(id="", name="", enable=1, delay=delay, act=ACTIONS[action])
    res = await _module(dev, "countdown").add_rule(rule)
    echo(f"Added countdown rule id {res.get('id')}")
    return res


@schedule.command(name="enable")
@click.option("--id", type=str, help="Rule id. Without it, enable the whole service.")
@click.option("--type", "type_", default="schedule", type=RULE_TYPES)
@pass_dev_or_child
async def enable_rule(dev, id, type_):
    """Enable a rule, or the whole schedule."""
    return await _set_enabled(dev, id, type_, True)


@schedule.command(name="disable")
@click.option("--id", type=str, help="Rule id. Without it, disable the whole service.")
@click.option("--type", "type_", default="schedule", type=RULE_TYPES)
@pass_dev_or_child
async def disable_rule(dev, id, type_):
    """Disable a rule, or the whole schedule."""
    return await _set_enabled(dev, id, type_, False)


async def _set_enabled(dev, id: str | None, type: str, state: bool):
    module = _module(dev, type)
    word = "Enabling" if state else "Disabling"
    if id is None:
        echo(f"{word} {type}")
        return await module.set_enabled(state)
    rule = _find_rule(module, id)
    echo(f"{word} {type} rule id {id}")
    return await module.set_rule_enabled(rule, state)


@schedule.command(name="delete")
@click.option("--id", type=str, required=True)
@click.option("--type", "type_", default="schedule", type=RULE_TYPES)
@pass_dev_or_child
async def delete_rule(dev, id, type_):
    """Delete rule from device."""
    module = _module(dev, type_)
    rule = _find_rule(module, id)
    echo(f"Deleting rule id {id}")
    return await module.delete_rule(rule)
