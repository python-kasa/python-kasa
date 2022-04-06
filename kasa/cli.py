"""python-kasa cli tool."""
import asyncio
import logging
import sys
from pprint import pformat as pf
from typing import cast

import asyncclick as click

from kasa import (
    Discover,
    SmartBulb,
    SmartDevice,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
    SmartStrip,
)

TYPE_TO_CLASS = {
    "plug": SmartPlug,
    "bulb": SmartBulb,
    "dimmer": SmartDimmer,
    "strip": SmartStrip,
    "lightstrip": SmartLightStrip,
}

click.anyio_backend = "asyncio"


pass_dev = click.make_pass_decorator(SmartDevice)


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
    "--target",
    envvar="KASA_TARGET",
    default="255.255.255.255",
    required=False,
    show_default=True,
    help="The broadcast address to be used for discovery.",
)
@click.option("-d", "--debug", envvar="KASA_DEBUG", default=False, is_flag=True)
@click.option(
    "--type",
    envvar="KASA_TYPE",
    default=None,
    type=click.Choice(TYPE_TO_CLASS, case_sensitive=False),
)
@click.version_option(package_name="python-kasa")
@click.pass_context
async def cli(ctx, host, alias, target, debug, type):
    """A tool for controlling TP-Link smart home devices."""  # noqa
    # no need to perform any checks if we are just displaying the help
    if sys.argv[-1] == "--help":
        # Context object is required to avoid crashing on sub-groups
        ctx.obj = SmartDevice(None)
        return

    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if ctx.invoked_subcommand == "discover":
        return

    if alias is not None and host is None:
        click.echo(f"Alias is given, using discovery to find host {alias}")
        host = await find_host_from_alias(alias=alias, target=target)
        if host:
            click.echo(f"Found hostname is {host}")
        else:
            click.echo(f"No device with name {alias} found")
            return

    if host is None:
        click.echo("No host name given, trying discovery..")
        await ctx.invoke(discover)
        return

    if type is not None:
        dev = TYPE_TO_CLASS[type](host)
    else:
        click.echo("No --type defined, discovering..")
        dev = await Discover.discover_single(host)

    await dev.update()
    ctx.obj = dev

    if ctx.invoked_subcommand is None:
        await ctx.invoke(state)


@cli.group()
@pass_dev
def wifi(dev):
    """Commands to control wifi settings."""


@wifi.command()
@pass_dev
async def scan(dev):
    """Scan for available wifi networks."""
    click.echo("Scanning for wifi networks, wait a second..")
    devs = await dev.wifi_scan()
    click.echo(f"Found {len(devs)} wifi networks!")
    for dev in devs:
        click.echo(f"\t {dev}")

    return devs


@wifi.command()
@click.argument("ssid")
@click.option("--password", prompt=True, hide_input=True)
@click.option("--keytype", default=3)
@pass_dev
async def join(dev: SmartDevice, ssid, password, keytype):
    """Join the given wifi network."""
    click.echo(f"Asking the device to connect to {ssid}..")
    res = await dev.wifi_join(ssid, password, keytype=keytype)
    click.echo(
        f"Response: {res} - if the device is not able to join the network, it will revert back to its previous state."
    )

    return res


@cli.command()
@click.option("--timeout", default=3, required=False)
@click.pass_context
async def discover(ctx, timeout):
    """Discover devices in the network."""
    target = ctx.parent.params["target"]
    click.echo(f"Discovering devices on {target} for {timeout} seconds")
    sem = asyncio.Semaphore()

    async def print_discovered(dev: SmartDevice):
        await dev.update()
        async with sem:
            ctx.obj = dev
            await ctx.invoke(state)
            click.echo()

    await Discover.discover(
        target=target, timeout=timeout, on_discovered=print_discovered
    )


async def find_host_from_alias(alias, target="255.255.255.255", timeout=1, attempts=3):
    """Discover a device identified by its alias."""
    for attempt in range(1, attempts):
        found_devs = await Discover.discover(target=target, timeout=timeout)
        for ip, dev in found_devs.items():
            if dev.alias.lower() == alias.lower():
                host = dev.host
                return host

    return None


@cli.command()
@pass_dev
async def sysinfo(dev):
    """Print out full system information."""
    click.echo(click.style("== System info ==", bold=True))
    click.echo(pf(dev.sys_info))
    return dev.sys_info


@cli.command()
@pass_dev
async def state(dev: SmartDevice):
    """Print out device state and versions."""
    click.echo(click.style(f"== {dev.alias} - {dev.model} ==", bold=True))
    click.echo(f"\tHost: {dev.host}")
    click.echo(
        click.style(
            "\tDevice state: {}\n".format("ON" if dev.is_on else "OFF"),
            fg="green" if dev.is_on else "red",
        )
    )
    if dev.is_strip:
        click.echo(click.style("\t== Plugs ==", bold=True))
        for plug in dev.children:  # type: ignore
            is_on = plug.is_on
            alias = plug.alias
            click.echo(
                click.style(
                    "\t* Socket '{}' state: {} on_since: {}".format(
                        alias, ("ON" if is_on else "OFF"), plug.on_since
                    ),
                    fg="green" if is_on else "red",
                )
            )
        click.echo()

    click.echo(click.style("\t== Generic information ==", bold=True))
    click.echo(f"\tTime:         {dev.time} (tz: {dev.timezone}")
    click.echo(f"\tHardware:     {dev.hw_info['hw_ver']}")
    click.echo(f"\tSoftware:     {dev.hw_info['sw_ver']}")
    click.echo(f"\tMAC (rssi):   {dev.mac} ({dev.rssi})")
    click.echo(f"\tLocation:     {dev.location}")

    click.echo(click.style("\n\t== Device specific information ==", bold=True))
    for k, v in dev.state_information.items():
        click.echo(f"\t{k}: {v}")

    if dev.has_emeter:
        click.echo(click.style("\n\t== Current State ==", bold=True))
        emeter_status = dev.emeter_realtime
        click.echo(f"\t{emeter_status}")

    click.echo(click.style("\n\t== Modules ==", bold=True))
    for module in dev.modules.values():
        if module.is_supported:
            click.echo(click.style(f"\t+ {module}", fg="green"))
        else:
            click.echo(click.style(f"\t- {module}", fg="red"))


@cli.command()
@pass_dev
@click.argument("new_alias", required=False, default=None)
@click.option("--index", type=int)
async def alias(dev, new_alias, index):
    """Get or set the device (or plug) alias."""
    if index is not None:
        if not dev.is_strip:
            click.echo("Index can only used for power strips!")
            return
        dev = cast(SmartStrip, dev)
        dev = dev.get_plug_by_index(index)

    if new_alias is not None:
        click.echo(f"Setting alias to {new_alias}")
        res = await dev.set_alias(new_alias)
        return res

    click.echo(f"Alias: {dev.alias}")
    if dev.is_strip:
        for plug in dev.children:
            click.echo(f"  * {plug.alias}")


@cli.command()
@pass_dev
@click.argument("module")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
async def raw_command(dev: SmartDevice, module, command, parameters):
    """Run a raw command on the device."""
    import ast

    if parameters is not None:
        parameters = ast.literal_eval(parameters)

    res = await dev._query_helper(module, command, parameters)

    click.echo(res)
    return res


@cli.command()
@pass_dev
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
async def emeter(dev: SmartDevice, year, month, erase):
    """Query emeter for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    click.echo(click.style("== Emeter ==", bold=True))
    if not dev.has_emeter:
        click.echo("Device has no emeter")
        return

    if erase:
        click.echo("Erasing emeter statistics..")
        click.echo(await dev.erase_emeter_stats())
        return

    if year:
        click.echo(f"== For year {year.year} ==")
        click.echo("Month, usage (kWh)")
        usage_data = await dev.get_emeter_monthly(year.year)
    elif month:
        click.echo(f"== For month {month.month} of {month.year} ==")
        click.echo("Day, usage (kWh)")
        usage_data = await dev.get_emeter_daily(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        emeter_status = dev.emeter_realtime

        click.echo("Current: %s A" % emeter_status["current"])
        click.echo("Voltage: %s V" % emeter_status["voltage"])
        click.echo("Power: %s W" % emeter_status["power"])
        click.echo("Total consumption: %s kWh" % emeter_status["total"])

        click.echo("Today: %s kWh" % dev.emeter_today)
        click.echo("This month: %s kWh" % dev.emeter_this_month)

        return

    # output any detailed usage data
    for index, usage in usage_data.items():
        click.echo(f"{index}, {usage}")


@cli.command()
@pass_dev
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
async def usage(dev: SmartDevice, year, month, erase):
    """Query usage for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    click.echo(click.style("== Usage ==", bold=True))
    usage = dev.modules["usage"]

    if erase:
        click.echo("Erasing usage statistics..")
        click.echo(await usage.erase_stats())
        return

    if year:
        click.echo(f"== For year {year.year} ==")
        click.echo("Month, usage (minutes)")
        usage_data = await usage.get_monthstat(year.year)
    elif month:
        click.echo(f"== For month {month.month} of {month.year} ==")
        click.echo("Day, usage (minutes)")
        usage_data = await usage.get_daystat(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        click.echo("Today: %s minutes" % usage.usage_today)
        click.echo("This month: %s minutes" % usage.usage_this_month)

        return

    # output any detailed usage data
    for index, usage in usage_data.items():
        click.echo(f"{index}, {usage}")


@cli.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def brightness(dev: SmartBulb, brightness: int, transition: int):
    """Get or set brightness."""
    if not dev.is_dimmable:
        click.echo("This device does not support brightness.")
        return

    if brightness is None:
        click.echo(f"Brightness: {dev.brightness}")
    else:
        click.echo(f"Setting brightness to {brightness}")
        return await dev.set_brightness(brightness, transition=transition)


@cli.command()
@click.argument(
    "temperature", type=click.IntRange(2500, 9000), default=None, required=False
)
@click.option("--transition", type=int, required=False)
@pass_dev
async def temperature(dev: SmartBulb, temperature: int, transition: int):
    """Get or set color temperature."""
    if not dev.is_variable_color_temp:
        click.echo("Device does not support color temperature")
        return

    if temperature is None:
        click.echo(f"Color temperature: {dev.color_temp}")
        valid_temperature_range = dev.valid_temperature_range
        if valid_temperature_range != (0, 0):
            click.echo("(min: {}, max: {})".format(*valid_temperature_range))
        else:
            click.echo(
                "Temperature range unknown, please open a github issue"
                f" or a pull request for model '{dev.model}'"
            )
    else:
        click.echo(f"Setting color temperature to {temperature}")
        return await dev.set_color_temp(temperature, transition=transition)


@cli.command()
@click.argument("effect", type=click.STRING, default=None, required=False)
@click.pass_context
@pass_dev
async def effect(dev, ctx, effect):
    """Set an effect."""
    if not dev.has_effects:
        click.echo("Device does not support effects")
        return
    if effect is None:
        raise click.BadArgumentUsage(
            f"Setting an effect requires a named built-in effect: {dev.effect_list}",
            ctx,
        )
    if effect not in dev.effect_list:
        raise click.BadArgumentUsage(f"Effect must be one of: {dev.effect_list}", ctx)

    click.echo(f"Setting Effect: {effect}")
    return await dev.set_effect(effect)


@cli.command()
@click.argument("h", type=click.IntRange(0, 360), default=None, required=False)
@click.argument("s", type=click.IntRange(0, 100), default=None, required=False)
@click.argument("v", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
@pass_dev
async def hsv(dev, ctx, h, s, v, transition):
    """Get or set color in HSV."""
    if not dev.is_color:
        click.echo("Device does not support colors")
        return

    if h is None or s is None or v is None:
        click.echo(f"Current HSV: {dev.hsv}")
    elif s is None or v is None:
        raise click.BadArgumentUsage("Setting a color requires 3 values.", ctx)
    else:
        click.echo(f"Setting HSV: {h} {s} {v}")
        return await dev.set_hsv(h, s, v, transition=transition)


@cli.command()
@click.argument("state", type=bool, required=False)
@pass_dev
async def led(dev, state):
    """Get or set (Plug's) led state."""
    if state is not None:
        click.echo(f"Turning led to {state}")
        return await dev.set_led(state)
    else:
        click.echo(f"LED state: {dev.led}")


@cli.command()
@pass_dev
async def time(dev):
    """Get the device time."""
    res = dev.time
    click.echo(f"Current time: {res}")
    return res


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def on(dev: SmartDevice, index: int, name: str, transition: int):
    """Turn the device on."""
    if index is not None or name is not None:
        if not dev.is_strip:
            click.echo("Index and name are only for power strips!")
            return

        dev = cast(SmartStrip, dev)
        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    click.echo(f"Turning on {dev.alias}")
    return await dev.turn_on(transition=transition)


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def off(dev: SmartDevice, index: int, name: str, transition: int):
    """Turn the device off."""
    if index is not None or name is not None:
        if not dev.is_strip:
            click.echo("Index and name are only for power strips!")
            return

        dev = cast(SmartStrip, dev)
        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    click.echo(f"Turning off {dev.alias}")
    return await dev.turn_off(transition=transition)


@cli.command()
@click.option("--delay", default=1)
@pass_dev
async def reboot(plug, delay):
    """Reboot the device."""
    click.echo("Rebooting the device..")
    return await plug.reboot(delay)


@cli.group()
@pass_dev
async def schedule(dev):
    """Scheduling commands."""


@schedule.command(name="list")
@pass_dev
@click.argument("type", default="schedule")
def _schedule_list(dev, type):
    """Return the list of schedule actions for the given type."""
    sched = dev.modules[type]
    for rule in sched.rules:
        print(rule)
    else:
        click.echo(f"No rules of type {type}")


if __name__ == "__main__":
    cli()
