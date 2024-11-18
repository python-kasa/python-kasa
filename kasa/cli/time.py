"""Module for cli time commands.."""

from __future__ import annotations

import zoneinfo
from datetime import datetime

import asyncclick as click

from kasa import (
    Device,
    Module,
)
from kasa.iot import IotDevice
from kasa.iot.iottimezone import get_matching_timezones

from .common import (
    echo,
    error,
    pass_dev,
)


@click.group(invoke_without_command=True)
@click.pass_context
async def time(ctx: click.Context) -> None:
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
    help="IANA timezone name, will use current device timezone if not provided.",
)
@click.option(
    "--skip-confirm",
    type=str,
    required=False,
    default=False,
    is_flag=True,
    help="Do not ask to confirm the timezone if an exact match is not found.",
)
@pass_dev
async def time_sync(dev: Device, timezone: str | None, skip_confirm: bool):
    """Set the device time to current time."""
    if (time := dev.modules.get(Module.Time)) is None:
        echo("Device does not have time module")
        return

    now = datetime.now()

    tzinfo: zoneinfo.ZoneInfo | None = None
    if timezone:
        tzinfo = await _get_timezone(dev, timezone, skip_confirm)
        if tzinfo.utcoffset(now) != now.astimezone().utcoffset():
            error(
                f"{timezone} has a different utc offset to local time,"
                + "syncing will produce unexpected results."
            )
        now = now.replace(tzinfo=tzinfo)

    echo(f"Old time: {time.time} ({time.timezone})")

    await time.set_time(now)

    await dev.update()
    echo(f"New time: {time.time} ({time.timezone})")


@time.command(name="set")
@click.argument("year", type=int)
@click.argument("month", type=int)
@click.argument("day", type=int)
@click.argument("hour", type=int)
@click.argument("minute", type=int)
@click.argument("seconds", type=int, required=False, default=0)
@click.option(
    "--timezone",
    type=str,
    required=False,
    default=None,
    help="IANA timezone name, will use current device timezone if not provided.",
)
@click.option(
    "--skip-confirm",
    type=bool,
    required=False,
    default=False,
    is_flag=True,
    help="Do not ask to confirm the timezone if an exact match is not found.",
)
@pass_dev
async def time_set(
    dev: Device,
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    seconds: int,
    timezone: str | None,
    skip_confirm: bool,
):
    """Set the device time to the provided time."""
    if (time := dev.modules.get(Module.Time)) is None:
        echo("Device does not have time module")
        return

    tzinfo: zoneinfo.ZoneInfo | None = None
    if timezone:
        tzinfo = await _get_timezone(dev, timezone, skip_confirm)

    echo(f"Old time: {time.time} ({time.timezone})")

    await time.set_time(datetime(year, month, day, hour, minute, seconds, 0, tzinfo))

    await dev.update()
    echo(f"New time: {time.time} ({time.timezone})")


async def _get_timezone(dev, timezone, skip_confirm) -> zoneinfo.ZoneInfo:
    """Get the tzinfo from the timezone or return none."""
    tzinfo: zoneinfo.ZoneInfo | None = None

    if timezone not in zoneinfo.available_timezones():
        error(f"{timezone} is not a valid IANA timezone.")

    tzinfo = zoneinfo.ZoneInfo(timezone)
    if skip_confirm is False and isinstance(dev, IotDevice):
        matches = await get_matching_timezones(tzinfo)
        if not matches:
            error(f"Device cannot support {timezone} timezone.")
        first = matches[0]
        msg = (
            f"An exact match for {timezone} could not be found, "
            + f"timezone will be set to {first}"
        )
        if len(matches) == 1:
            click.confirm(msg, abort=True)
        else:
            msg = (
                f"Supported timezones matching {timezone} are {', '.join(matches)}\n"
                + msg
            )
            click.confirm(msg, abort=True)
    return tzinfo
