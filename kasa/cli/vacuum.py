"""Module for cli vacuum commands.."""

from __future__ import annotations

import asyncclick as click

from kasa import (
    Device,
    Module,
)

from .common import (
    error,
    pass_dev_or_child,
)


@click.group(invoke_without_command=False)
@click.pass_context
async def vacuum(ctx: click.Context) -> None:
    """Vacuum commands."""


@vacuum.group(invoke_without_command=True, name="records")
@pass_dev_or_child
async def records_group(dev: Device) -> None:
    """Access cleaning records."""
    if not (rec := dev.modules.get(Module.CleanRecords)):
        error("This device does not support records.")

    data = rec.parsed_data
    latest = data.last_clean
    click.echo(
        f"Totals: {rec.total_clean_area} {rec.area_unit} in {rec.total_clean_time} "
        f"(cleaned {rec.total_clean_count} times)"
    )
    click.echo(f"Last clean: {latest.clean_area} {rec.area_unit} @ {latest.clean_time}")
    click.echo("Execute `kasa vacuum records list` to list all records.")


@records_group.command(name="list")
@pass_dev_or_child
async def records_list(dev: Device) -> None:
    """List all cleaning records."""
    if not (rec := dev.modules.get(Module.CleanRecords)):
        error("This device does not support records.")

    data = rec.parsed_data
    for record in data.records:
        click.echo(
            f"* {record.timestamp}: cleaned {record.clean_area} {rec.area_unit}"
            f" in {record.clean_time}"
        )


@vacuum.group(invoke_without_command=True, name="consumables")
@pass_dev_or_child
@click.pass_context
async def consumables(ctx: click.Context, dev: Device) -> None:
    """List device consumables."""
    if not (cons := dev.modules.get(Module.Consumables)):
        error("This device does not support consumables.")

    if not ctx.invoked_subcommand:
        for c in cons.consumables.values():
            click.echo(f"{c.name} ({c.id}): {c.used} used, {c.remaining} remaining")


@consumables.command(name="reset")
@click.argument("consumable_id", required=True)
@pass_dev_or_child
async def reset_consumable(dev: Device, consumable_id: str) -> None:
    """Reset the consumable used/remaining time."""
    cons = dev.modules[Module.Consumables]

    if consumable_id not in cons.consumables:
        error(
            f"Consumable {consumable_id} not found in "
            f"device consumables: {', '.join(cons.consumables.keys())}."
        )

    await cons.reset_consumable(consumable_id)

    click.echo(f"Consumable {consumable_id} reset")
