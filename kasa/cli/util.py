"""python-kasa cli tool."""

from __future__ import annotations

import ast
import asyncio
import json
import logging

import asyncclick as click

from kasa import (
    Device,
    KasaException,
)
from kasa.cli.common import (
    echo,
    pass_dev_or_child,
)
from kasa.iot import (
    IotDevice,
)
from kasa.smart import SmartDevice


@click.command()
@pass_dev_or_child
async def shell(dev: Device):
    """Open interactive shell."""
    echo("Opening shell for %s" % dev)
    from ptpython.repl import embed

    logging.getLogger("parso").setLevel(logging.WARNING)  # prompt parsing
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    loop = asyncio.get_event_loop()
    try:
        await embed(  # type: ignore[func-returns-value]
            globals=globals(),
            locals=locals(),
            return_asyncio_coroutine=True,
            patch_stdout=True,
        )
    except EOFError:
        loop.stop()


@click.command()
@click.pass_context
@click.argument("module")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
async def raw_command(ctx, module, command, parameters):
    """Run a raw command on the device."""
    logging.warning("Deprecated, use 'kasa command --module %s %s'", module, command)
    return await ctx.forward(cmd_command)


@click.command(name="command")
@click.option("--module", required=False, help="Module for IOT protocol.")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
@pass_dev_or_child
async def cmd_command(dev: Device, module, command, parameters):
    """Run a raw command on the device."""
    if parameters is not None:
        parameters = ast.literal_eval(parameters)

    if isinstance(dev, IotDevice):
        res = await dev._query_helper(module, command, parameters)
    elif isinstance(dev, SmartDevice):
        res = await dev._query_helper(command, parameters)
    else:
        raise KasaException("Unexpected device type %s.", dev)
    echo(json.dumps(res))
    return res
