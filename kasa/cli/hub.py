"""Hub-specific commands."""

import asyncio

import asyncclick as click

from kasa import DeviceType, Module, SmartDevice
from kasa.smart import SmartChildDevice

from .common import (
    echo,
    error,
    pass_dev,
)


def pretty_category(cat: str):
    """Return pretty category for paired devices."""
    return SmartChildDevice.CHILD_DEVICE_TYPE_MAP.get(cat)


@click.group()
@pass_dev
async def hub(dev: SmartDevice):
    """Commands controlling hub child device pairing."""
    if dev.device_type is not DeviceType.Hub:
        error(f"{dev} is not a hub.")

    if dev.modules.get(Module.ChildSetup) is None:
        error(f"{dev} does not have child setup module.")


@hub.command(name="list")
@pass_dev
async def hub_list(dev: SmartDevice):
    """List hub paired child devices."""
    for c in dev.children:
        echo(f"{c.device_id}: {c}")


@hub.command(name="supported")
@pass_dev
async def hub_supported(dev: SmartDevice):
    """List supported hub child device categories."""
    cs = dev.modules[Module.ChildSetup]

    for cat in cs.supported_categories:
        echo(f"Supports: {cat}")


@hub.command(name="pair")
@click.option("--timeout", default=10)
@pass_dev
async def hub_pair(dev: SmartDevice, timeout: int):
    """Pair all pairable device.

    This will pair any child devices currently in pairing mode.
    """
    cs = dev.modules[Module.ChildSetup]

    echo(f"Finding new devices for {timeout} seconds...")

    pair_res = await cs.pair(timeout=timeout)
    if not pair_res:
        echo("No devices found.")

    for child in pair_res:
        echo(
            f"Paired {child['name']} ({child['device_model']}, "
            f"{pretty_category(child['category'])}) with id {child['device_id']}"
        )


@hub.command(name="unpair")
@click.argument("device_id")
@pass_dev
async def hub_unpair(dev, device_id: str):
    """Unpair given device."""
    cs = dev.modules[Module.ChildSetup]

    # Accessing private here, as the property exposes only values
    if device_id not in dev._children:
        error(f"{dev} does not have children with identifier {device_id}")

    res = await cs.unpair(device_id=device_id)
    # Give the device some time to update its internal state, just in case.
    await asyncio.sleep(1)
    await dev.update()

    if device_id not in dev._children:
        echo(f"Unpaired {device_id}")
    else:
        error(f"Failed to unpair {device_id}")

    return res
