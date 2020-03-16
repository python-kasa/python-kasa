"""python-kasa cli tool."""
import asyncio
import json
import logging
import re
from pprint import pformat as pf

import click

from kasa import Discover, SmartBulb, SmartDevice, SmartStrip

from kasa import SmartPlug  # noqa: E402; noqa: E402

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
@click.option("--debug/--normal", default=False)
@click.option("--bulb", default=False, is_flag=True)
@click.option("--plug", default=False, is_flag=True)
@click.option("--strip", default=False, is_flag=True)
@click.version_option()
@click.pass_context
def cli(ctx, host, alias, target, debug, bulb, plug, strip):
    """A cli tool for controlling TP-Link smart home plugs."""  # noqa
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if ctx.invoked_subcommand == "discover":
        return

    if alias is not None and host is None:
        click.echo("Alias is given, using discovery to find host %s" % alias)
        host = find_host_from_alias(alias=alias, target=target)
        if host:
            click.echo(f"Found hostname is {host}")
        else:
            click.echo(f"No device with name {alias} found")
            return

    if host is None:
        click.echo("No host name given, trying discovery..")
        ctx.invoke(discover)
        return
    else:
        if not bulb and not plug and not strip:
            click.echo("No --strip nor --bulb nor --plug given, discovering..")
            dev = asyncio.run(Discover.discover_single(host))
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
        ctx.invoke(state)


@cli.command()
@click.option("--scrub/--no-scrub", default=True)
@click.pass_context
def dump_discover(ctx, scrub):
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
    devs = asyncio.run(Discover.discover(target=target, return_raw=True))
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
        click.echo("Saving info to %s" % save_to)
        with open(save_to, "w") as f:
            json.dump(dev, f, sort_keys=True, indent=4)
            f.write("\n")


@cli.command()
@click.option("--timeout", default=3, required=False)
@click.option("--discover-only", default=False)
@click.option("--dump-raw", is_flag=True)
@click.pass_context
def discover(ctx, timeout, discover_only, dump_raw):
    """Discover devices in the network."""
    target = ctx.parent.params["target"]
    click.echo("Discovering devices for %s seconds" % timeout)
    found_devs = asyncio.run(
        Discover.discover(target=target, timeout=timeout, return_raw=dump_raw)
    )
    if not discover_only:
        for ip, dev in found_devs.items():
            asyncio.run(dev.update())
            if dump_raw:
                click.echo(dev)
                continue
            ctx.obj = dev
            ctx.invoke(state)
            print()

    return found_devs


def find_host_from_alias(alias, target="255.255.255.255", timeout=1, attempts=3):
    """Discover a device identified by its alias."""
    host = None
    click.echo(
        "Trying to discover %s using %s attempts of %s seconds"
        % (alias, attempts, timeout)
    )
    for attempt in range(1, attempts):
        click.echo(f"Attempt {attempt} of {attempts}")
        found_devs = Discover.discover(target=target, timeout=timeout).items()
        for ip, dev in found_devs:
            if dev.alias.lower() == alias.lower():
                host = dev.host
                return host
    return None


@cli.command()
@pass_dev
def sysinfo(dev):
    """Print out full system information."""
    asyncio.run(dev.update())
    click.echo(click.style("== System info ==", bold=True))
    click.echo(pf(dev.sys_info))


@cli.command()
@pass_dev
@click.pass_context
def state(ctx, dev: SmartDevice):
    """Print out device state and versions."""
    asyncio.run(dev.update())
    click.echo(click.style(f"== {dev.alias} - {dev.model} ==", bold=True))

    click.echo(
        click.style(
            "Device state: {}".format("ON" if dev.is_on else "OFF"),
            fg="green" if dev.is_on else "red",
        )
    )
    if dev.is_strip:
        for plug in dev.plugs:  # type: ignore
            asyncio.run(plug.update())
            is_on = plug.is_on
            alias = plug.alias
            click.echo(
                click.style(
                    "  * {} state: {}".format(alias, ("ON" if is_on else "OFF")),
                    fg="green" if is_on else "red",
                )
            )

    click.echo(f"Host/IP: {dev.host}")
    for k, v in dev.state_information.items():
        click.echo(f"{k}: {v}")
    click.echo(click.style("== Generic information ==", bold=True))
    click.echo("Time:         {}".format(asyncio.run(dev.get_time())))
    click.echo("Hardware:     {}".format(dev.hw_info["hw_ver"]))
    click.echo("Software:     {}".format(dev.hw_info["sw_ver"]))
    click.echo(f"MAC (rssi):   {dev.mac} ({dev.rssi})")
    click.echo(f"Location:     {dev.location}")

    ctx.invoke(emeter)


@cli.command()
@pass_dev
@click.argument("new_alias", required=False, default=None)
def alias(dev, new_alias):
    """Get or set the device alias."""
    if new_alias is not None:
        click.echo(f"Setting alias to {new_alias}")
        asyncio.run(dev.set_alias(new_alias))

    click.echo(f"Alias: {dev.alias}")


@cli.command()
@pass_dev
@click.argument("module")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
def raw_command(dev: SmartDevice, module, command, parameters):
    """Run a raw command on the device."""
    import ast

    if parameters is not None:
        parameters = ast.literal_eval(parameters)
    res = asyncio.run(dev._query_helper(module, command, parameters))
    asyncio.run(dev.update())
    click.echo(res)


@cli.command()
@pass_dev
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
def emeter(dev, year, month, erase):
    """Query emeter for historical consumption."""
    click.echo(click.style("== Emeter ==", bold=True))
    asyncio.run(dev.update())
    if not dev.has_emeter:
        click.echo("Device has no emeter")
        return

    if erase:
        click.echo("Erasing emeter statistics..")
        asyncio.run(dev.erase_emeter_stats())
        return

    if year:
        click.echo(f"== For year {year.year} ==")
        emeter_status = asyncio.run(dev.get_emeter_monthly(year.year))
    elif month:
        click.echo(f"== For month {month.month} of {month.year} ==")
        emeter_status = asyncio.run(
            dev.get_emeter_daily(year=month.year, month=month.month)
        )
    else:
        emeter_status = asyncio.run(dev.get_emeter_realtime())
        click.echo("== Current State ==")

    if isinstance(emeter_status, list):
        for plug in emeter_status:
            click.echo("Plug %d: %s" % (emeter_status.index(plug) + 1, plug))
    else:
        click.echo(str(emeter_status))


@cli.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@pass_dev
def brightness(dev, brightness):
    """Get or set brightness."""
    asyncio.run(dev.update())
    if not dev.is_dimmable:
        click.echo("This device does not support brightness.")
        return
    if brightness is None:
        click.echo("Brightness: %s" % dev.brightness)
    else:
        click.echo("Setting brightness to %s" % brightness)
        asyncio.run(dev.set_brightness(brightness))


@cli.command()
@click.argument(
    "temperature", type=click.IntRange(2500, 9000), default=None, required=False
)
@pass_dev
def temperature(dev: SmartBulb, temperature):
    """Get or set color temperature."""
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
def hsv(dev, ctx, h, s, v):
    """Get or set color in HSV. (Bulb only)."""
    if h is None or s is None or v is None:
        click.echo("Current HSV: %s %s %s" % dev.hsv)
    elif s is None or v is None:
        raise click.BadArgumentUsage("Setting a color requires 3 values.", ctx)
    else:
        click.echo(f"Setting HSV: {h} {s} {v}")
        asyncio.run(dev.set_hsv(h, s, v))


@cli.command()
@click.argument("state", type=bool, required=False)
@pass_dev
def led(dev, state):
    """Get or set (Plug's) led state."""
    if state is not None:
        click.echo("Turning led to %s" % state)
        asyncio.run(dev.set_led(state))
    else:
        click.echo("LED state: %s" % dev.led)


@cli.command()
@pass_dev
def time(dev):
    """Get the device time."""
    click.echo(asyncio.run(dev.get_time()))


@cli.command()
@click.argument("index", type=int, required=False)
@pass_dev
def on(plug, index):
    """Turn the device on."""
    click.echo("Turning on..")
    if index is None:
        asyncio.run(plug.turn_on())
    else:
        asyncio.run(plug.turn_on(index=(index - 1)))


@cli.command()
@click.argument("index", type=int, required=False)
@pass_dev
def off(plug, index):
    """Turn the device off."""
    click.echo("Turning off..")
    if index is None:
        asyncio.run(plug.turn_off())
    else:
        asyncio.run(plug.turn_off(index=(index - 1)))


@cli.command()
@click.option("--delay", default=1)
@pass_dev
def reboot(plug, delay):
    """Reboot the device."""
    click.echo("Rebooting the device..")
    asyncio.run(plug.reboot(delay))


if __name__ == "__main__":
    cli()
