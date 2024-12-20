"""Module for cli usage commands.."""

from __future__ import annotations

from typing import cast

import asyncclick as click

from kasa import (
    Device,
    Module,
)
from kasa.interfaces import Energy
from kasa.iot.modules import Usage

from .common import (
    echo,
    error,
    pass_dev_or_child,
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
    echo("[bold]== Energy ==[/bold]")
    if not (energy := dev.modules.get(Module.Energy)):
        error("Device has no energy module.")
        return

    if (year or month or erase) and not energy.supports(
        Energy.ModuleFeature.PERIODIC_STATS
    ):
        error("Device does not support historical statistics")
        return

    if erase:
        echo("Erasing emeter statistics..")
        return await energy.erase_stats()

    if year:
        echo(f"== For year {year.year} ==")
        echo("Month, usage (kWh)")
        usage_data = await energy.get_monthly_stats(year=year.year)
    elif month:
        echo(f"== For month {month.month} of {month.year} ==")
        echo("Day, usage (kWh)")
        usage_data = await energy.get_daily_stats(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        emeter_status = energy.status

        echo("Current: {} A".format(emeter_status["current"]))
        echo("Voltage: {} V".format(emeter_status["voltage"]))
        echo("Power: {} W".format(emeter_status["power"]))
        echo("Total consumption: {} kWh".format(emeter_status["total"]))

        echo(f"Today: {energy.consumption_today} kWh")
        echo(f"This month: {energy.consumption_this_month} kWh")

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
        echo(f"Today: {usage.usage_today} minutes")
        echo(f"This month: {usage.usage_this_month} minutes")

        return usage

    # output any detailed usage data
    for index, usage in usage_data.items():
        echo(f"{index}, {usage}")

    return usage_data
