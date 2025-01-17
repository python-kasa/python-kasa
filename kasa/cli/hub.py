"""Hub-specific commands."""

import asyncclick as click

from kasa import Module
from kasa.smart import SmartChildDevice

from .common import (
    echo,
    pass_dev,
)


def pretty_category(cat: str):
    """Return pretty category for paired devices."""
    return SmartChildDevice.CHILD_DEVICE_TYPE_MAP.get(cat)


@click.group()
async def hub():
    """Commands controlling hub child device pairing."""


@hub.command(name="list")
@pass_dev
async def hub_list(dev):
    """List hub paired child devices."""
    for c in dev.children:
        echo(f"{c.device_id}: {c}")


@hub.command(name="supported")
@pass_dev
async def hub_supported(dev):
    """List supported hub child device categories."""
    if (cs := dev.modules.get(Module.ChildSetup)) is None:
        echo(f"{dev} is not a hub.")
        return

    for cat in await cs.get_supported_device_categories():
        echo(f"Supports: {cat['category']}")


@hub.command(name="pair")
@click.option("--timeout", default=10)
@pass_dev
async def hub_pair(dev, timeout):
    """Pair all pairable device.
    
    This will pair any child devices currently in pairing mode.
    """
    if (cs := dev.modules.get(Module.ChildSetup)) is None:
        echo(f"{dev} is not a hub.")
        return

    echo(f"Finding new devices for {timeout} seconds...")

    pair_res = await cs.pair(timeout=timeout)
    if not pair_res:
        echo("No devices found.")

    for dev in pair_res:
        echo(
            f'Paired {dev["name"]} ({dev["device_model"]}, '
            f'{pretty_category(dev["category"])}) with id {dev["device_id"]}'
        )


@hub.command(name="unpair")
@click.argument("device_id")
@pass_dev
async def hub_unpair(dev, device_id: str):
    """Unpair given device."""
    if (cs := dev.modules.get(Module.ChildSetup)) is None:
        echo(f"{dev} is not a hub.")
        return

    res = await cs.unpair(device_id=device_id)
    echo(f"Unpaired {device_id} (if it was paired)")
    return res
