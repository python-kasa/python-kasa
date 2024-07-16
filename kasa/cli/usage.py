"""Module for cli usage commands.."""

from __future__ import annotations

import logging
from typing import cast

import asyncclick as click

from kasa import (
    Device,
)
from kasa.iot import (
    IotDevice,
)
from kasa.iot.iotstrip import IotStripPlug
from kasa.iot.modules import Usage

from .common import (
    echo,
    error,
    pass_dev_or_child,
)


@click.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
@click.pass_context
async def emeter(ctx: click.Context, index, name, year, month, erase):
    """Query emeter for historical consumption."""
    logging.warning("Deprecated, use 'kasa energy'")
    return await ctx.invoke(
        energy, child_index=index, child=name, year=year, month=month, erase=erase
    )


@click.command()
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
@pass_dev_or_child
async def energy(dev: Device, year, month, erase):
    """Query energy module for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    echo("[bold]== Emeter ==[/bold]")
    if not dev.has_emeter:
        error("Device has no emeter")
        return

    if (year or month or erase) and not isinstance(dev, IotDevice):
        error("Device has no historical statistics")
        return
    else:
        dev = cast(IotDevice, dev)

    if erase:
        echo("Erasing emeter statistics..")
        return await dev.erase_emeter_stats()

    if year:
        echo(f"== For year {year.year} ==")
        echo("Month, usage (kWh)")
        usage_data = await dev.get_emeter_monthly(year=year.year)
    elif month:
        echo(f"== For month {month.month} of {month.year} ==")
        echo("Day, usage (kWh)")
        usage_data = await dev.get_emeter_daily(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        if isinstance(dev, IotStripPlug):
            emeter_status = await dev.get_emeter_realtime()
        else:
            emeter_status = dev.emeter_realtime

        echo("Current: %s A" % emeter_status["current"])
        echo("Voltage: %s V" % emeter_status["voltage"])
        echo("Power: %s W" % emeter_status["power"])
        echo("Total consumption: %s kWh" % emeter_status["total"])

        echo("Today: %s kWh" % dev.emeter_today)
        echo("This month: %s kWh" % dev.emeter_this_month)

        return emeter_status

    # output any detailed usage data
    for index, usage in usage_data.items():
        echo(f"{index}, {usage}")

    return usage_data


@click.command()
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
@pass_dev_or_child
async def usage(dev: Device, year, month, erase):
    """Query usage for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    echo("[bold]== Usage ==[/bold]")
    usage = cast(Usage, dev.modules["usage"])

    if erase:
        echo("Erasing usage statistics..")
        return await usage.erase_stats()

    if year:
        echo(f"== For year {year.year} ==")
        echo("Month, usage (minutes)")
        usage_data = await usage.get_monthstat(year=year.year)
    elif month:
        echo(f"== For month {month.month} of {month.year} ==")
        echo("Day, usage (minutes)")
        usage_data = await usage.get_daystat(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        echo("Today: %s minutes" % usage.usage_today)
        echo("This month: %s minutes" % usage.usage_this_month)

        return usage

    # output any detailed usage data
    for index, usage in usage_data.items():
        echo(f"{index}, {usage}")

    return usage_data
