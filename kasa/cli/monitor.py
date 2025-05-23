"""Module for cli monitor commands.."""

from __future__ import annotations

import asyncio

import asyncclick as click

from kasa import (
    Device,
    Module,
)

from .common import (
    echo,
    error,
    pass_dev_or_child,
)

CELL_PADDING = 2  # Number of spaces to use for padding between header entries
NUM_ROWS_BEFORE_PRINTING_HEADER = 20  # How often we re-print the header


def _get_column_header_str(dev_or_plug, extra_padding=CELL_PADDING):
    header_size = len(dev_or_plug.alias) + extra_padding
    value_max_size = len("1234.56") + extra_padding
    return dev_or_plug.alias.rjust(max(header_size, value_max_size), " ")


def _get_power_str(dev_or_plug, extra_padding=CELL_PADDING):
    header_size = len(dev_or_plug.alias) + extra_padding
    value_max_size = len("1234.56") + extra_padding
    power = dev_or_plug.modules.get(Module.Energy).status["power"]
    return f"{power:.3f}".rjust(max(header_size, value_max_size), " ")


def _print_header(dev):
    line = _get_column_header_str(dev, 0)
    for plug in dev.children:
        line += _get_column_header_str(plug)
    echo(line)


async def _update_and_print_power(dev):
    await dev.update()

    line_to_print = _get_power_str(dev, 0)
    for plug in dev.children:
        line_to_print += _get_power_str(plug)

    echo(line_to_print)


@click.command()
@pass_dev_or_child
async def monitor(dev: Device):
    """Monitor Power usage in the terminal.

    Continuously query and print power usage in the terminal for the given
    device and its children, until the user presses Ctrl+C
    """
    if not dev.modules.get(Module.Energy):
        error("Device has no energy module.")
        return

    for plug in dev.children:
        if not plug.modules.get(Module.Energy):
            error("Plug has no energy module.")
            return

    echo("[bold]Monitoring power. Press Ctrl-C to exit.[/bold]")

    periodic_loop_count = 0
    while True:
        if periodic_loop_count == 0:
            _print_header(dev)
        periodic_loop_count += 1
        periodic_loop_count %= NUM_ROWS_BEFORE_PRINTING_HEADER
        await asyncio.gather(asyncio.sleep(1), _update_and_print_power(dev))
