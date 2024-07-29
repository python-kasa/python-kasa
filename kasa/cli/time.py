"""Module for cli time commands.."""

from __future__ import annotations

from datetime import datetime

import asyncclick as click

from kasa import (
    Device,
    Module,
)
from kasa.smart import SmartDevice

from .common import (
    echo,
    pass_dev,
)


@click.group(invoke_without_command=True)
@click.pass_context
async def time(ctx: click.Context):
    """Get and set time."""
    if ctx.invoked_subcommand is None:
        await ctx.invoke(time_get)


@time.command(name="get")
@pass_dev
async def time_get(dev: Device):
    """Get the device time."""
    res = dev.time
    echo(f"Current time: {res}")
    return res


@time.command(name="sync")
@pass_dev
async def time_sync(dev: Device):
    """Set the device time to current time."""
    if not isinstance(dev, SmartDevice):
        raise NotImplementedError("setting time currently only implemented on smart")

    if (time := dev.modules.get(Module.Time)) is None:
        echo("Device does not have time module")
        return

    echo("Old time: %s" % time.time)

    local_tz = datetime.now().astimezone().tzinfo
    await time.set_time(datetime.now(tz=local_tz))

    await dev.update()
    echo("New time: %s" % time.time)
