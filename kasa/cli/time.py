"""Module for cli time commands.."""

from __future__ import annotations

from datetime import datetime

import asyncclick as click
import zoneinfo

from kasa import (
    Device,
    Module,
)

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
    echo(f"Current time: {dev.time} ({dev.timezone})")
    return res


@time.command(name="sync")
@click.option(
    "--timezone",
    type=str,
    required=False,
    default=None,
    help="IANA timezone name, will default to local if not provided.",
)
@pass_dev
async def time_sync(dev: Device, timezone: str | None):
    """Set the device time to current time."""
    if (time := dev.modules.get(Module.Time)) is None:
        echo("Device does not have time module")
        return

    if not timezone:
        tzinfo = datetime.now().astimezone().tzinfo
    elif timezone not in zoneinfo.available_timezones():
        echo(f"{timezone} is not a valid IANA timezone.")
        return
    else:
        tzinfo = zoneinfo.ZoneInfo(timezone)

    echo(f"Old time: {time.time} ({time.timezone})")

    await time.set_time(datetime.now(tz=tzinfo))

    await dev.update()
    echo(f"New time: {time.time} ({time.timezone})")


@time.command(name="set")
@click.argument("year", type=int)
@click.argument("month", type=int)
@click.argument("day", type=int)
@click.argument("hour", type=int)
@click.argument("minute", type=int)
@click.option(
    "--timezone",
    type=str,
    required=False,
    default=None,
    help="IANA timezone name, will default to local if not provided.",
)
@pass_dev
async def time_set(
    dev: Device,
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    timezone: str | None,
):
    """Set the device time to current time."""
    if (time := dev.modules.get(Module.Time)) is None:
        echo("Device does not have time module")
        return

    if not timezone:
        tzinfo = datetime.now().astimezone().tzinfo
    elif timezone not in zoneinfo.available_timezones():
        echo(f"{timezone} is not a valid IANA timezone.")
        return
    else:
        tzinfo = zoneinfo.ZoneInfo(timezone)

    echo(f"Old time: {time.time} ({time.timezone})")

    await time.set_time(datetime(year, month, day, hour, minute, 0, 0, tzinfo))

    await dev.update()
    echo(f"New time: {time.time} ({time.timezone})")
