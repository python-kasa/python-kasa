"""Module for cli schedule commands.."""

from __future__ import annotations

import asyncclick as click

from .common import (
    echo,
    error,
    pass_dev,
    pass_dev_or_child,
)


@click.group()
@pass_dev
async def schedule(dev) -> None:
    """Scheduling commands."""


@schedule.command(name="list")
@pass_dev_or_child
@click.argument("type", default="schedule")
async def _schedule_list(dev, type):
    """Return the list of schedule actions for the given type."""
    sched = dev.modules[type]
    for rule in sched.rules:
        print(rule)
    else:
        error(f"No rules of type {type}")

    return sched.rules


@schedule.command(name="delete")
@pass_dev_or_child
@click.option("--id", type=str, required=True)
async def delete_rule(dev, id):
    """Delete rule from device."""
    schedule = dev.modules["schedule"]
    rule_to_delete = next(filter(lambda rule: (rule.id == id), schedule.rules), None)
    if rule_to_delete:
        echo(f"Deleting rule id {id}")
        return await schedule.delete_rule(rule_to_delete)
    else:
        error(f"No rule with id {id} was found")
