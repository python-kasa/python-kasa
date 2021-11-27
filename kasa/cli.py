"""python-kasa cli tool."""
import logging
from datetime import datetime
from typing import List, cast

import asyncclick as click

from kasa import (
    Discover,
    SmartBulb,
    SmartDevice,
    SmartLightStrip,
    SmartPlug,
    SmartStrip,
)
from kasa.exceptions import SmartDeviceException
from kasa.printmanager import (
    DataWrapper,
    HumanMessenger,
    JsonMessenger,
    Messenger,
    StyleFlag,
)

click.anyio_backend = "asyncio"


class CliData:
    """Holds context data."""

    pass


@click.group(invoke_without_command=True)
@click.option(
    "--host",
    envvar="KASA_HOST",
    required=False,
    help="The host name or IP address of the device to connect to.",
)
@click.option(
    "--alias",
    envvar="KASA_NAME",
    required=False,
    help="The device name, or alias, of the device to connect to.",
)
@click.option(
    "--output-format",
    "-f",
    default="human",
    required=False,
    help="The format for the output. Can be 'json', 'json-ws'. 'Human' is default.",
)
@click.option(
    "--target",
    default="255.255.255.255",
    required=False,
    help="The broadcast address to be used for discovery.",
)
@click.option("-d", "--debug", default=False, is_flag=True)
@click.option("--bulb", default=False, is_flag=True)
@click.option("--plug", default=False, is_flag=True)
@click.option("--lightstrip", default=False, is_flag=True)
@click.option("--strip", default=False, is_flag=True)
@click.version_option()
@click.pass_context
async def cli(
    ctx, host, alias, output_format, target, debug, bulb, plug, lightstrip, strip
):
    """A tool for controlling TP-Link smart home devices."""  # noqa
    ctx.obj = CliData()
    output_format = output_format.lower()
    if output_format == "json":
        msgr = JsonMessenger(whitespace=False)
    elif output_format == "json-ws":
        msgr = JsonMessenger(whitespace=True)
    else:
        msgr = HumanMessenger()
    ctx.obj.msgr = msgr

    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if ctx.invoked_subcommand == "discover":
        return
    elif not ctx.invoked_subcommand:
        raise click.UsageError(
            "Nothing to do. Type 'kasa --help' for a list of available commands."
        )

    try:
        if alias is not None and host is None:
            msgr.prog(f"Alias is given, using discovery to find host {alias}")
            dev = await find_device_from_alias(alias=alias, target=target)
            if dev:
                ctx.obj.dev = dev
                msgr.prog(f"Found hostname is {dev.host}")
                await dev.update()
            else:
                msgr.err(f"No device with name {alias} found", fatal=True)
                exit()
        elif host is not None:
            if bulb:
                dev = SmartBulb(host)
            elif plug:
                dev = SmartPlug(host)
            elif strip:
                dev = SmartStrip(host)
            elif lightstrip:
                dev = SmartLightStrip(host)
            else:
                msgr.prog("No --strip nor --bulb nor --plug given, discovering..")
                dev = await Discover.discover_single(host)

            ctx.obj.dev = dev
            await dev.update()
    except SmartDeviceException as e:
        msgr.err(str(e), fatal=True)
        exit()


# Produces error: '@cli.result_callback() TypeError: 'NoneType' object is not callable' (Python 3.7)
# @cli.result_callback()
# def callback(ctx, host, alias, output_format, target, debug, bulb, plug, lightstrip, strip, res):
#     ctx.obj.msgr.print_data()


@cli.group()
@click.pass_context
def wifi(ctx):
    """Commands to control wifi settings."""


@wifi.command()
@click.pass_context
async def scan(ctx):
    """Scan for available wifi networks."""
    msgr: Messenger = ctx.obj.msgr
    msgr.prog("Scanning for wifi networks, wait a second..")
    devs = await ctx.obj.dev.wifi_scan()
    msgr.prog(f"Found {len(devs)} wifi networks!")
    dw = msgr.data_wrapper
    for idx, nw in enumerate(devs):
        dw.add_point(f"network_{idx}", str(nw))

    msgr.print_data()
    return devs


@wifi.command()
@click.argument("ssid")
@click.option("--password", prompt=True, hide_input=True)
@click.option("--keytype", default=3)
@click.pass_context
async def join(ctx, ssid, password, keytype):
    """Join the given wifi network."""
    msgr: Messenger = ctx.obj.msgr
    msgr.prog(f"Asking the device to connect to {ssid}..")
    res = await ctx.obj.dev.wifi_join(ssid, password, keytype=keytype)
    msgr.prog(
        "If the device is not able to join the network, \
        it will revert back to its previous state."
    )
    msgr.data_wrapper.add_point("res", res, "Result", StyleFlag.BOLD)
    msgr.print_data()
    return res


@cli.command()
@click.option("--timeout", default=3, required=False)
@click.option("--discover-only", default=False)
@click.option("--dump-raw", is_flag=True)
@click.pass_context
async def discover(ctx, timeout, discover_only, dump_raw):
    """Discover devices in the network."""
    msgr = ctx.obj.msgr
    dw = msgr.data_wrapper
    target = ctx.parent.params["target"]
    msgr.prog(f"Discovering devices on {target} for {timeout} seconds")
    found_devs = await Discover.discover(target=target, timeout=timeout)
    if not discover_only:
        for dev in found_devs.values():
            if dump_raw:
                dw = dw.add_categorie(dev.host, name=dev.alias, style=StyleFlag.BOLD)
                wrap_dev_sysinfo(dw, dev)
            else:
                await wrap_dev_state(dw, dev)

    msgr.print_data()
    return found_devs


async def find_device_from_alias(
    alias, target="255.255.255.255", timeout=1, attempts=3
):
    """Discover a device identified by its alias."""
    for attempt in range(1, attempts):
        found_devs = await Discover.discover(target=target, timeout=timeout)
        for ip, dev in found_devs.items():
            if dev.alias.lower() == alias.lower():
                return dev

    return None


@cli.command()
@click.pass_context
async def sysinfo(ctx):
    """Print out full system information."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    wrap_dev_sysinfo(msgr.data_wrapper, dev)
    msgr.print_data()


@cli.command()
@click.pass_context
async def state(ctx):
    """Print out device state and versions."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    await wrap_dev_state(msgr.data_wrapper, dev)
    msgr.print_data()


@cli.command()
@click.pass_context
@click.argument("new_alias", required=False, default=None)
@click.option("--index", type=int)
async def alias(ctx, new_alias, index):
    """Get or set the device (or plug) alias."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    dw = msgr.data_wrapper
    if index is not None:
        if not dev.is_strip:
            msgr.err("Index can only used for power strips!", fatal=True)
            return
        dev = cast(SmartStrip, dev)
        dev = dev.get_plug_by_index(index)

    if new_alias is not None:
        msgr.prog("Setting new alias..")
        try:
            res = await dev.set_alias(new_alias)
            dw.add_point("res", res, "Result")
        except Exception as e:
            msgr.err(str(e), fatal=True)
            return

    dw.add_point("alias", dev.alias)
    if dev.is_strip:
        dw.add_point("plugs", list(map(lambda p: p.alias, dev.children)))
    msgr.print_data()


@cli.command()
@click.pass_context
@click.argument("module")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
async def raw_command(ctx, module, command, parameters):
    """Run a raw command on the device."""
    import ast

    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    if parameters is not None:
        parameters = ast.literal_eval(parameters)

    try:
        res = await dev._query_helper(module, command, parameters)
        msgr.data_wrapper.add_point("res", res, "Result")
        msgr.print_data()
    except Exception as e:
        msgr.err(str(e), fatal=True)


@cli.command()
@click.option(
    "--year", type=click.DateTime(["%Y"]), default=None, required=False, multiple=True
)
@click.option(
    "--month",
    type=click.DateTime(["%Y-%m"]),
    default=None,
    required=False,
    multiple=True,
)
@click.option("--realtime", "-r", is_flag=True)
@click.option("--erase", is_flag=True)
@click.pass_context
async def emeter(ctx, year, month, realtime, erase):
    """Query emeter for historical consumption.

    Daily and monthly data provided in CSV format.
    The year and month flags can be specified multiple times.
    """
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    dw = msgr.data_wrapper

    if erase:
        msgr.prog("Erasing emeter statistics..")
        try:
            await dev.erase_emeter_stats()
            msgr.print_data()
        except Exception as e:
            msgr.err(str(e), fatal=True)
        return

    if not year and not month:
        realtime = True
    await wrap_dev_emeter(dw, dev, year, month, realtime)
    msgr.print_data()


@cli.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
async def brightness(ctx, brightness: int, transition: int):
    """Get or set brightness."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    if not dev.is_dimmable:
        msgr.err("This device does not support brightness.", fatal=True)
        return

    if brightness is None:
        msgr.data_wrapper.add_point("brightness", dev.brightness, style=StyleFlag.BOLD)
    else:
        msgr.prog(f"Setting brightness to {brightness}")
        try:
            await dev.set_brightness(brightness, transition=transition)
        except Exception as e:
            msgr.err(str(e), fatal=True)
            return

    msgr.print_data()


@cli.command()
@click.argument(
    "temperature", type=click.IntRange(2500, 9000), default=None, required=False
)
@click.option("--transition", type=int, required=False)
@click.pass_context
async def temperature(ctx, temperature: int, transition: int):
    """Get or set color temperature."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    if not dev.is_variable_color_temp:
        msgr.err("Device does not support color temperature", fatal=True)
        return

    dw = msgr.data_wrapper
    if temperature is None:
        dw.add_point("color_temperature", dev.color_temp, StyleFlag.BOLD)
        valid_temperature_range = dev.valid_temperature_range
        if valid_temperature_range != (0, 0):
            dw.add_point("min", valid_temperature_range[0])
            dw.add_point("max", valid_temperature_range[1])
        else:
            msgr.prog(
                "Temperature range unknown, please open a github issue"
                f" or a pull request for model '{dev.model}'"
            )
    else:
        msgr.prog(f"Setting color temperature to {temperature}")
        try:
            await dev.set_color_temp(temperature, transition=transition)
        except Exception as e:
            msgr.err(str(e), fatal=True)
            return

    msgr.print_data()


@cli.command()
@click.argument("h", type=click.IntRange(0, 360), default=None, required=False)
@click.argument("s", type=click.IntRange(0, 100), default=None, required=False)
@click.argument("v", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
async def hsv(ctx, h, s, v, transition):
    """Get or set color in HSV."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    if not dev.is_color:
        msgr.err("Device does not support colors", fatal=True)
        return

    if h is None or s is None or v is None:
        msgr.data_wrapper.add_point("current_hsv", dev.hsv, "Current HSV")
    elif s is None or v is None:
        msgr.err("Setting a color requires 3 values.", fatal=True)
    else:
        msgr.prog(f"Setting HSV: {h} {s} {v}")
        try:
            await dev.set_hsv(h, s, v, transition=transition)
        except Exception as e:
            msgr.err(str(e), fatal=True)
            return
    msgr.print_data()


@cli.command()
@click.argument("state", type=bool, required=False)
@click.pass_context
async def led(ctx, state):
    """Get or set (Plug's) led state."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    if state is not None:
        msgr.prog(f"Turning led to {state}")
        try:
            await dev.set_led(state)
        except Exception as e:
            msgr.err(str(e), fatal=True)
            return
    else:
        msgr.data_wrapper.add_point("led_state", dev.led, "LED state")
    msgr.print_data()


@cli.command()
@click.pass_context
async def time(ctx):
    """Get the device time."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    res = await dev.get_time()
    msgr.data_wrapper.add_point("current_time", res)
    msgr.print_data()


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
async def on(ctx, index: int, name: str, transition: int):
    """Turn the device on."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    try:
        if dev.is_strip and (index is not None or name is not None):
            dev = cast(SmartStrip, dev)
            if index is not None:
                dev = dev.get_plug_by_index(index)
            elif name:
                dev = dev.get_plug_by_name(name)

        msgr.prog(f"Turning on {dev.alias}")
        await dev.turn_on(transition=transition)
    except Exception as e:
        msgr.err(str(e), fatal=True)
        return
    msgr.print_data()


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
async def off(ctx, index: int, name: str, transition: int):
    """Turn the device off."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    try:
        if dev.is_strip and (index is not None or name is not None):
            dev = cast(SmartStrip, dev)
            if index is not None:
                dev = dev.get_plug_by_index(index)
            elif name:
                dev = dev.get_plug_by_name(name)

        msgr.prog(f"Turning off {dev.alias}")
        await dev.turn_off(transition=transition)
    except Exception as e:
        msgr.err(str(e), fatal=True)
        return
    msgr.print_data()


@cli.command()
@click.option("--delay", default=1)
@click.pass_context
async def reboot(ctx, delay):
    """Reboot the device."""
    dev, msgr = ctx.obj.dev, ctx.obj.msgr
    msgr.prog("Rebooting the device..")
    try:
        await dev.reboot(delay)
    except Exception as e:
        msgr.err(str(e), fatal=True)
        return
    msgr.print_data()


def wrap_dev_sysinfo(dw: DataWrapper, dev: SmartDevice):
    """Add device system informaton to the data wrapper."""
    dw.add_categorie("sys_info", dev.sys_info, "System Information", StyleFlag.BOLD)


async def wrap_dev_state(dw: DataWrapper, dev: SmartDevice):
    """Add various state info to the specified data wrapper."""
    dw = dw.add_categorie(
        dev.host, name=f"{dev.alias} - {dev.model}", style=StyleFlag.BOLD
    )
    dw.add_point("host", dev.host)
    if dev.is_on:
        dw.add_point("device_state", "on", style=StyleFlag.GREEN | StyleFlag.BOLD)
    else:
        dw.add_point("device_state", "off", style=StyleFlag.RED | StyleFlag.BOLD)

    if dev.is_strip:
        plug_data = dw.add_categorie("plugs", style=StyleFlag.BOLD)
        for plug in dev.children:  # type: ignore
            if plug.is_on:
                plug_data.add_point("device_state", "on", style=StyleFlag.GREEN)
            else:
                plug_data.add_point("device_state", "off", style=StyleFlag.RED)
            plug_data.add_point("alias", plug.alias)
            plug_data.add_point("on_since", plug.on_since)

    generic = dw.add_categorie(
        "generic_info", name="Generic Information", style=StyleFlag.BOLD
    )
    generic.add_point("time", await dev.get_time())
    generic.add_point("hardware", dev.hw_info["hw_ver"])
    generic.add_point("software", dev.hw_info["sw_ver"])
    generic.add_point("mac", dev.mac, "MAC")
    generic.add_point("rssi", dev.rssi, "RSSI")
    generic.add_categorie("location", dev.location)

    dw.add_categorie(
        "specific_info",
        dev.state_information,
        "Device specific information",
        StyleFlag.BOLD,
    )

    if dev.has_emeter:
        dw.add_categorie(
            "emeter", await dev.get_emeter_realtime(), style=StyleFlag.BOLD
        )


async def wrap_dev_emeter(
    dw: DataWrapper,
    dev: SmartDevice,
    years: List[datetime],
    months: List[datetime],
    realtime: bool,
):
    """Add device emter data to the data wrapper."""
    dw = dw.add_categorie(dev.host, name=(dev.alias or dev.host), style=StyleFlag.BOLD)

    if not dev.has_emeter:
        dw.add_point("error", "Device has no emeter", style=StyleFlag.RED)
        return

    if len(years) > 0:
        all_years = dw.add_categorie(
            "year", name="Monthly Usage (kWh)", style=StyleFlag.BOLD
        )
        for y in years:
            all_years.add_categorie(str(y.year), await dev.get_emeter_monthly(y.year))
    if len(months) > 0:
        all_months = dw.add_categorie(
            "month", name="Daily Usage (kWh)", style=StyleFlag.BOLD
        )
        for m in months:
            all_months.add_categorie(
                str(m.year) + "-" + str(m.month),
                await dev.get_emeter_daily(year=m.year, month=m.month),
            )
    if realtime:
        emeter_status = dev.emeter_realtime
        current = dw.add_categorie("realtime", style=StyleFlag.BOLD)
        current.add_point("current", emeter_status["current"], "Current (A)")
        current.add_point("voltage", emeter_status["voltage"], "Voltage (V)")
        current.add_point("power", emeter_status["power"], "Power (A)")
        current.add_point("total", emeter_status["total"], "Total consumption (kWh)")
        current.add_point("today", dev.emeter_today, "Today (kWh)")
        current.add_point("this_month", dev.emeter_this_month, "This month (kWh)")


if __name__ == "__main__":
    cli()
