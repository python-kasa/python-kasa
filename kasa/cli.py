"""python-kasa cli tool."""
import asyncio
import json
import logging
import re
from pprint import pformat as pf
from typing import cast

import asyncclick as click

from kasa import Discover, SmartBulb, SmartDevice, SmartPlug, SmartStrip

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
    default="255.255.255.255",
    required=False,
    help="The broadcast address to be used for discovery.",
)
@click.option("-d", "--debug", default=False, is_flag=True)
@click.option("--bulb", default=False, is_flag=True)
@click.option("--plug", default=False, is_flag=True)
@click.option("--strip", default=False, is_flag=True)
@click.version_option()
@click.pass_context
async def cli(ctx, host, alias, target, debug, bulb, plug, strip):
    """A cli tool for controlling TP-Link smart home plugs."""  # noqa
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
    else:
        if not bulb and not plug and not strip:
            click.echo("No --strip nor --bulb nor --plug given, discovering..")
            dev = await Discover.discover_single(host)
        elif bulb:
            dev = SmartBulb(host)
        elif plug:
            dev = SmartPlug(host)
        elif strip:
            dev = SmartStrip(host)
        else:
            click.echo("Unable to detect type, use --strip or --bulb or --plug!")
            return
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


@cli.command()
@click.option("--scrub/--no-scrub", default=True)
@click.pass_context
async def dump_discover(ctx, scrub):
    """Dump discovery information.

    Useful for dumping into a file to be added to the test suite.
    """
    target = ctx.parent.params["target"]
    keys_to_scrub = [
        "deviceId",
        "fwId",
        "hwId",
        "oemId",
        "mac",
        "latitude_i",
        "longitude_i",
        "latitude",
        "longitude",
    ]
    devs = await Discover.discover(target=target, return_raw=True)
    if scrub:
        click.echo("Scrubbing personal data before writing")
    for dev in devs.values():
        if scrub:
            for key in keys_to_scrub:
                if key in dev["system"]["get_sysinfo"]:
                    val = dev["system"]["get_sysinfo"][key]
                    if key in ["latitude_i", "longitude_i"]:
                        val = 0
                    else:
                        val = re.sub(r"\w", "0", val)
                    dev["system"]["get_sysinfo"][key] = val

        model = dev["system"]["get_sysinfo"]["model"]
        hw_version = dev["system"]["get_sysinfo"]["hw_ver"]
        save_to = f"{model}_{hw_version}.json"
        click.echo(f"Saving info to {save_to}")
        with open(save_to, "w") as f:
            json.dump(dev, f, sort_keys=True, indent=4)
            f.write("\n")


@cli.command()
@click.option("--timeout", default=3, required=False)
@click.option("--discover-only", default=False)
@click.option("--dump-raw", is_flag=True)
@click.pass_context
async def discover(ctx, timeout, discover_only, dump_raw):
    """Discover devices in the network."""
    target = ctx.parent.params["target"]
    click.echo(f"Discovering devices for {timeout} seconds")
    found_devs = await Discover.discover(
        target=target, timeout=timeout, return_raw=dump_raw
    )
    if not discover_only:
        for ip, dev in found_devs.items():
            await dev.update()
            if dump_raw:
                click.echo(dev)
                continue
            ctx.obj = dev
            await ctx.invoke(state)
            click.echo()

    return found_devs


async def find_host_from_alias(alias, target="255.255.255.255", timeout=1, attempts=3):
    """Discover a device identified by its alias."""
    click.echo(
        f"Trying to discover {alias} using {attempts} attempts of {timeout} seconds"
    )
    for attempt in range(1, attempts):
        click.echo(f"Attempt {attempt} of {attempts}")
        found_devs = await Discover.discover(target=target, timeout=timeout)
        found_devs = found_devs.items()
        for ip, dev in found_devs:
            if dev.alias.lower() == alias.lower():
                host = dev.host
                return host
    return None


@cli.command()
@pass_dev
async def sysinfo(dev):
    """Print out full system information."""
    await dev.update()
    click.echo(click.style("== System info ==", bold=True))
    click.echo(pf(dev.sys_info))


@cli.command()
@pass_dev
@click.pass_context
async def state(ctx, dev: SmartDevice):
    """Print out device state and versions."""
    await dev.update()
    click.echo(click.style(f"== {dev.alias} - {dev.model} ==", bold=True))

    click.echo(
        click.style(
            "Device state: {}".format("ON" if dev.is_on else "OFF"),
            fg="green" if dev.is_on else "red",
        )
    )
    if dev.is_strip:
        for plug in dev.plugs:  # type: ignore
            is_on = plug.is_on
            alias = plug.alias
            click.echo(
                click.style(
                    "  * Socket '{}' state: {} on_since: {}".format(
                        alias, ("ON" if is_on else "OFF"), plug.on_since
                    ),
                    fg="green" if is_on else "red",
                )
            )

    click.echo(f"Host/IP: {dev.host}")
    for k, v in dev.state_information.items():
        click.echo(f"{k}: {v}")
    click.echo(click.style("== Generic information ==", bold=True))
    click.echo(f"Time:         {await dev.get_time()}")
    click.echo(f"Hardware:     {dev.hw_info['hw_ver']}")
    click.echo(f"Software:     {dev.hw_info['sw_ver']}")
    click.echo(f"MAC (rssi):   {dev.mac} ({dev.rssi})")
    click.echo(f"Location:     {dev.location}")

    await ctx.invoke(emeter)


@cli.command()
@pass_dev
@click.argument("new_alias", required=False, default=None)
@click.option("--index", type=int)
async def alias(dev, new_alias, index):
    """Get or set the device (or plug) alias."""
    await dev.update()
    if index is not None:
        if not dev.is_strip:
            click.echo("Index can only used for power strips!")
            return
        dev = cast(SmartStrip, dev)
        dev = dev.get_plug_by_index(index)

    if new_alias is not None:
        click.echo(f"Setting alias to {new_alias}")
        click.echo(await dev.set_alias(new_alias))

    click.echo(f"Alias: {dev.alias}")
    if dev.is_strip:
        for plug in dev.plugs:
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
    await dev.update()  # TODO: is this needed?
    click.echo(res)


@cli.command()
@pass_dev
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
async def emeter(dev: SmartDevice, year, month, erase):
    """Query emeter for historical consumption."""
    click.echo(click.style("== Emeter ==", bold=True))
    await dev.update()
    if not dev.has_emeter:
        click.echo("Device has no emeter")
        return

    if erase:
        click.echo("Erasing emeter statistics..")
        click.echo(await dev.erase_emeter_stats())
        return

    if year:
        click.echo(f"== For year {year.year} ==")
        emeter_status = await dev.get_emeter_monthly(year.year)
    elif month:
        click.echo(f"== For month {month.month} of {month.year} ==")
        emeter_status = await dev.get_emeter_daily(year=month.year, month=month.month)
    else:
        emeter_status = dev.emeter_realtime

    if isinstance(emeter_status, list):
        for plug in emeter_status:
            index = emeter_status.index(plug) + 1
            click.echo(f"Plug {index}: {plug}")
    else:
        click.echo("Current: %s A" % emeter_status["current"])
        click.echo("Voltage: %s V" % emeter_status["voltage"])
        click.echo("Power: %s W" % emeter_status["power"])
        click.echo("Total consumption: %s kWh" % emeter_status["total"])

        click.echo("Today: %s kWh" % dev.emeter_today)
        click.echo("This month: %s kWh" % dev.emeter_this_month)


@cli.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@pass_dev
async def brightness(dev, brightness):
    """Get or set brightness."""
    await dev.update()
    if not dev.is_dimmable:
        click.echo("This device does not support brightness.")
        return
    if brightness is None:
        click.echo(f"Brightness: {dev.brightness}")
    else:
        click.echo(f"Setting brightness to {brightness}")
        click.echo(await dev.set_brightness(brightness))


@cli.command()
@click.argument(
    "temperature", type=click.IntRange(2500, 9000), default=None, required=False
)
@pass_dev
async def temperature(dev: SmartBulb, temperature):
    """Get or set color temperature."""
    await dev.update()
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
        asyncio.run(dev.set_color_temp(temperature))


@cli.command()
@click.argument("h", type=click.IntRange(0, 360), default=None, required=False)
@click.argument("s", type=click.IntRange(0, 100), default=None, required=False)
@click.argument("v", type=click.IntRange(0, 100), default=None, required=False)
@click.pass_context
@pass_dev
async def hsv(dev, ctx, h, s, v):
    """Get or set color in HSV. (Bulb only)."""
    await dev.update()
    if h is None or s is None or v is None:
        click.echo(f"Current HSV: {dev.hsv}")
    elif s is None or v is None:
        raise click.BadArgumentUsage("Setting a color requires 3 values.", ctx)
    else:
        click.echo(f"Setting HSV: {h} {s} {v}")
        click.echo(await dev.set_hsv(h, s, v))


@cli.command()
@click.argument("state", type=bool, required=False)
@pass_dev
async def led(dev, state):
    """Get or set (Plug's) led state."""
    await dev.update()
    if state is not None:
        click.echo(f"Turning led to {state}")
        click.echo(await dev.set_led(state))
    else:
        click.echo(f"LED state: {dev.led}")


@cli.command()
@pass_dev
async def time(dev):
    """Get the device time."""
    click.echo(await dev.get_time())


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@pass_dev
async def on(dev: SmartDevice, index, name):
    """Turn the device on."""
    await dev.update()
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
    await dev.turn_on()


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@pass_dev
async def off(dev, index, name):
    """Turn the device off."""
    await dev.update()
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
    await dev.turn_off()


@cli.command()
@click.option("--delay", default=1)
@pass_dev
async def reboot(plug, delay):
    """Reboot the device."""
    click.echo("Rebooting the device..")
    click.echo(await plug.reboot(delay))


if __name__ == "__main__":
    cli()
