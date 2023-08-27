"""python-kasa cli tool."""
import asyncio
import json
import logging
import re
import sys
from functools import singledispatch, wraps
from pprint import pformat as pf
from typing import Any, Dict, cast

import asyncclick as click

try:
    from rich import print as echo
except ImportError:

    def _strip_rich_formatting(echo_func):
        """Strip rich formatting from messages."""

        @wraps(echo_func)
        def wrapper(message=None, *args, **kwargs):
            if message is not None:
                message = re.sub(r"\[/?.+?]", "", message)
            echo_func(message, *args, **kwargs)

        return wrapper

    echo = _strip_rich_formatting(click.echo)


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


class ExceptionHandlerGroup(click.Group):
    """Group to capture all exceptions and print them nicely.

    Idea from https://stackoverflow.com/a/44347763
    """

    def __call__(self, *args, **kwargs):
        """Run the coroutine in the event loop and print any exceptions."""
        try:
            asyncio.get_event_loop().run_until_complete(self.main(*args, **kwargs))
        except Exception as ex:
            echo(f"Got error: {ex!r}")


def json_formatter_cb(result, **kwargs):
    """Format and output the result as JSON, if requested."""
    if not kwargs.get("json"):
        return

    @singledispatch
    def to_serializable(val):
        """Regular obj-to-string for json serialization.

        The singledispatch trick is from hynek: https://hynek.me/articles/serialization/
        """
        return str(val)

    @to_serializable.register(SmartDevice)
    def _device_to_serializable(val: SmartDevice):
        """Serialize smart device data, just using the last update raw payload."""
        return val.internal_state

    json_content = json.dumps(result, indent=4, default=to_serializable)
    print(json_content)


@click.group(
    invoke_without_command=True,
    cls=ExceptionHandlerGroup,
    result_callback=json_formatter_cb,
)
@click.option(
    "--host",
    envvar="KASA_HOST",
    required=False,
    help="The host name or IP address of the device to connect to.",
)
@click.option(
    "--port",
    envvar="KASA_PORT",
    required=False,
    help="The port of the device to connect to.",
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
    type=click.Choice(list(TYPE_TO_CLASS), case_sensitive=False),
)
@click.option(
    "--json", default=False, is_flag=True, help="Output raw device response as JSON."
)
@click.option(
    "--discovery-timeout",
    envvar="KASA_DISCOVERY_TIMEOUT",
    default=3,
    required=False,
    help="Timeout for discovery.",
)
@click.version_option(package_name="python-kasa")
@click.pass_context
async def cli(ctx, host, port, alias, target, debug, type, json, discovery_timeout):
    """A tool for controlling TP-Link smart home devices."""  # noqa
    # no need to perform any checks if we are just displaying the help
    if sys.argv[-1] == "--help":
        # Context object is required to avoid crashing on sub-groups
        ctx.obj = SmartDevice(None)
        return

    # If JSON output is requested, disable echo
    if json:
        global echo

        def _nop_echo(*args, **kwargs):
            pass

        echo = _nop_echo

    logging_config: Dict[str, Any] = {
        "level": logging.DEBUG if debug > 0 else logging.INFO
    }
    try:
        from rich.logging import RichHandler

        rich_config = {
            "show_time": False,
        }
        logging_config["handlers"] = [RichHandler(**rich_config)]
        logging_config["format"] = "%(message)s"
    except ImportError:
        pass

    # The configuration should be converted to use dictConfig, but this keeps mypy happy for now
    logging.basicConfig(**logging_config)  # type: ignore

    if ctx.invoked_subcommand == "discover":
        return

    if alias is not None and host is None:
        echo(f"Alias is given, using discovery to find host {alias}")
        host = await find_host_from_alias(alias=alias, target=target)
        if host:
            echo(f"Found hostname is {host}")
        else:
            echo(f"No device with name {alias} found")
            return

    if host is None:
        echo("No host name given, trying discovery..")
        return await ctx.invoke(discover, timeout=discovery_timeout)

    if type is not None:
        dev = TYPE_TO_CLASS[type](host)
    else:
        echo("No --type defined, discovering..")
        dev = await Discover.discover_single(host, port=port)

    await dev.update()
    ctx.obj = dev

    if ctx.invoked_subcommand is None:
        return await ctx.invoke(state)


@cli.group()
@pass_dev
def wifi(dev):
    """Commands to control wifi settings."""


@wifi.command()
@pass_dev
async def scan(dev):
    """Scan for available wifi networks."""
    echo("Scanning for wifi networks, wait a second..")
    devs = await dev.wifi_scan()
    echo(f"Found {len(devs)} wifi networks!")
    for dev in devs:
        echo(f"\t {dev}")

    return devs


@wifi.command()
@click.argument("ssid")
@click.option("--password", prompt=True, hide_input=True)
@click.option("--keytype", default=3)
@pass_dev
async def join(dev: SmartDevice, ssid, password, keytype):
    """Join the given wifi network."""
    echo(f"Asking the device to connect to {ssid}..")
    res = await dev.wifi_join(ssid, password, keytype=keytype)
    echo(
        f"Response: {res} - if the device is not able to join the network, it will revert back to its previous state."
    )

    return res


@cli.command()
@click.option("--timeout", default=3, required=False)
@click.pass_context
async def discover(ctx, timeout):
    """Discover devices in the network."""
    target = ctx.parent.params["target"]
    echo(f"Discovering devices on {target} for {timeout} seconds")
    sem = asyncio.Semaphore()
    discovered = dict()

    async def print_discovered(dev: SmartDevice):
        await dev.update()
        async with sem:
            discovered[dev.host] = dev.internal_state
            ctx.obj = dev
            await ctx.invoke(state)
            echo()

    await Discover.discover(
        target=target, timeout=timeout, on_discovered=print_discovered
    )

    return discovered


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
    echo("== System info ==")
    echo(pf(dev.sys_info))
    return dev.sys_info


@cli.command()
@pass_dev
async def state(dev: SmartDevice):
    """Print out device state and versions."""
    echo(f"[bold]== {dev.alias} - {dev.model} ==[/bold]")
    echo(f"\tHost: {dev.host}")
    echo(f"\tPort: {dev.port}")
    echo(f"\tDevice state: {dev.is_on}")
    if dev.is_strip:
        echo("\t[bold]== Plugs ==[/bold]")
        for plug in dev.children:  # type: ignore
            echo(f"\t* Socket '{plug.alias}' state: {plug.is_on} since {plug.on_since}")
        echo()

    echo("\t[bold]== Generic information ==[/bold]")
    echo(f"\tTime:         {dev.time} (tz: {dev.timezone}")
    echo(f"\tHardware:     {dev.hw_info['hw_ver']}")
    echo(f"\tSoftware:     {dev.hw_info['sw_ver']}")
    echo(f"\tMAC (rssi):   {dev.mac} ({dev.rssi})")
    echo(f"\tLocation:     {dev.location}")

    echo("\n\t[bold]== Device specific information ==[/bold]")
    for info_name, info_data in dev.state_information.items():
        if isinstance(info_data, list):
            echo(f"\t{info_name}:")
            for item in info_data:
                echo(f"\t\t{item}")
        else:
            echo(f"\t{info_name}: {info_data}")

    if dev.has_emeter:
        echo("\n\t[bold]== Current State ==[/bold]")
        emeter_status = dev.emeter_realtime
        echo(f"\t{emeter_status}")

    echo("\n\t[bold]== Modules ==[/bold]")
    for module in dev.modules.values():
        if module.is_supported:
            echo(f"\t[green]+ {module}[/green]")
        else:
            echo(f"\t[red]- {module}[/red]")

    return dev.internal_state


@cli.command()
@pass_dev
@click.argument("new_alias", required=False, default=None)
@click.option("--index", type=int)
async def alias(dev, new_alias, index):
    """Get or set the device (or plug) alias."""
    if index is not None:
        if not dev.is_strip:
            echo("Index can only used for power strips!")
            return
        dev = cast(SmartStrip, dev)
        dev = dev.get_plug_by_index(index)

    if new_alias is not None:
        echo(f"Setting alias to {new_alias}")
        res = await dev.set_alias(new_alias)
        return res

    echo(f"Alias: {dev.alias}")
    if dev.is_strip:
        for plug in dev.children:
            echo(f"  * {plug.alias}")

    return dev.alias


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
    echo(json.dumps(res))
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
    echo("[bold]== Emeter ==[/bold]")
    if not dev.has_emeter:
        echo("Device has no emeter")
        return

    if erase:
        echo("Erasing emeter statistics..")
        return await dev.erase_emeter_stats()

    if year:
        echo(f"== For year {year.year} ==")
        echo("Month, usage (kWh)")
        usage_data = await dev.get_emeter_monthly(year=year.year)
    elif month:
        echo(f"== For month {month.month} of {month.year} ==")
        echo("Day, usage (kWh)")
        usage_data = await dev.get_emeter_daily(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        emeter_status = dev.emeter_realtime

        echo("Current: %s A" % emeter_status["current"])
        echo("Voltage: %s V" % emeter_status["voltage"])
        echo("Power: %s W" % emeter_status["power"])
        echo("Total consumption: %s kWh" % emeter_status["total"])

        echo("Today: %s kWh" % dev.emeter_today)
        echo("This month: %s kWh" % dev.emeter_this_month)

        return emeter_status

    # output any detailed usage data
    for index, usage in usage_data.items():
        echo(f"{index}, {usage}")

    return usage_data


@cli.command()
@pass_dev
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
async def usage(dev: SmartDevice, year, month, erase):
    """Query usage for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    echo("[bold]== Usage ==[/bold]")
    usage = dev.modules["usage"]

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
        echo("Today: %s minutes" % usage.usage_today)
        echo("This month: %s minutes" % usage.usage_this_month)

        return usage

    # output any detailed usage data
    for index, usage in usage_data.items():
        echo(f"{index}, {usage}")

    return usage_data


@cli.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def brightness(dev: SmartBulb, brightness: int, transition: int):
    """Get or set brightness."""
    if not dev.is_dimmable:
        echo("This device does not support brightness.")
        return

    if brightness is None:
        echo(f"Brightness: {dev.brightness}")
        return dev.brightness
    else:
        echo(f"Setting brightness to {brightness}")
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
        echo("Device does not support color temperature")
        return

    if temperature is None:
        echo(f"Color temperature: {dev.color_temp}")
        valid_temperature_range = dev.valid_temperature_range
        if valid_temperature_range != (0, 0):
            echo("(min: {}, max: {})".format(*valid_temperature_range))
        else:
            echo(
                "Temperature range unknown, please open a github issue"
                f" or a pull request for model '{dev.model}'"
            )
        return dev.valid_temperature_range
    else:
        echo(f"Setting color temperature to {temperature}")
        return await dev.set_color_temp(temperature, transition=transition)


@cli.command()
@click.argument("effect", type=click.STRING, default=None, required=False)
@click.pass_context
@pass_dev
async def effect(dev, ctx, effect):
    """Set an effect."""
    if not dev.has_effects:
        echo("Device does not support effects")
        return
    if effect is None:
        raise click.BadArgumentUsage(
            f"Setting an effect requires a named built-in effect: {dev.effect_list}",
            ctx,
        )
    if effect not in dev.effect_list:
        raise click.BadArgumentUsage(f"Effect must be one of: {dev.effect_list}", ctx)

    echo(f"Setting Effect: {effect}")
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
        echo("Device does not support colors")
        return

    if h is None or s is None or v is None:
        echo(f"Current HSV: {dev.hsv}")
        return dev.hsv
    elif s is None or v is None:
        raise click.BadArgumentUsage("Setting a color requires 3 values.", ctx)
    else:
        echo(f"Setting HSV: {h} {s} {v}")
        return await dev.set_hsv(h, s, v, transition=transition)


@cli.command()
@click.argument("state", type=bool, required=False)
@pass_dev
async def led(dev, state):
    """Get or set (Plug's) led state."""
    if state is not None:
        echo(f"Turning led to {state}")
        return await dev.set_led(state)
    else:
        echo(f"LED state: {dev.led}")
        return dev.led


@cli.command()
@pass_dev
async def time(dev):
    """Get the device time."""
    res = dev.time
    echo(f"Current time: {res}")
    return res


@cli.command()
@click.option("--list", is_flag=True)
@click.argument("index", type=int, required=False)
@pass_dev
async def set_timezone(dev, list, index):
    """Set the device timezone.

    pass --list to see valid timezones
    """
    if list:
        timezones = [
            {
                "index": 0,
                "zone_str": "(UTC-12:00) International Date Line West",
                "tz_str": "<GMT+12>12",
                "dst_offset": 0,
            },
            {
                "index": 1,
                "zone_str": "(UTC-11:00) Coordinated Universal Time-11",
                "tz_str": "<GMT+11>11",
                "dst_offset": 0,
            },
            {
                "index": 2,
                "zone_str": "(UTC-10:00) Hawaii",
                "tz_str": "HST10",
                "dst_offset": 0,
            },
            {
                "index": 3,
                "zone_str": "(UTC-09:00) Alaska",
                "tz_str": "AKST9AKDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 4,
                "zone_str": "(UTC-08:00) Baja California",
                "tz_str": "PST8PDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 5,
                "zone_str": "(UTC-08:00) Pacific Standard Time (US & Canada)",
                "tz_str": "PST8",
                "dst_offset": 0,
            },
            {
                "index": 6,
                "zone_str": "(UTC-08:00) Pacific Daylight Time (US & Canada)",
                "tz_str": "PST8PDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 7,
                "zone_str": "(UTC-07:00) Arizona",
                "tz_str": "MST7",
                "dst_offset": 0,
            },
            {
                "index": 8,
                "zone_str": "(UTC-07:00) Chihuahua, La Paz, Mazatlan",
                "tz_str": "MST7MDT,M4.1.0,M10.5.0",
                "dst_offset": 60,
            },
            {
                "index": 9,
                "zone_str": "(UTC-07:00) Mountain Standard Time (US & Canada)",
                "tz_str": "MST7",
                "dst_offset": 0,
            },
            {
                "index": 10,
                "zone_str": "(UTC-07:00) Mountain Daylight Time (US & Canada)",
                "tz_str": "MST7MDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 11,
                "zone_str": "(UTC-06:00) Central America",
                "tz_str": "CST6",
                "dst_offset": 0,
            },
            {
                "index": 12,
                "zone_str": "(UTC-06:00) Central Standard Time (US & Canada)",
                "tz_str": "CST6",
                "dst_offset": 0,
            },
            {
                "index": 13,
                "zone_str": "(UTC-06:00) Central Daylight Time (US & Canada)",
                "tz_str": "CST6CDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 14,
                "zone_str": "(UTC-06:00) Guadalajara, Mexico City, Monterrey",
                "tz_str": "CST6CDT,M4.1.0,M10.5.0",
                "dst_offset": 60,
            },
            {
                "index": 15,
                "zone_str": "(UTC-06:00) Saskatchewan",
                "tz_str": "<GMT+6>6",
                "dst_offset": 0,
            },
            {
                "index": 16,
                "zone_str": "(UTC-05:00) Bogota, Lima, Quito, Rio Branco",
                "tz_str": "COT5",
                "dst_offset": 0,
            },
            {
                "index": 17,
                "zone_str": "(UTC-05:00) Eastern Standard Time (US & Canada)",
                "tz_str": "EST5",
                "dst_offset": 0,
            },
            {
                "index": 18,
                "zone_str": "(UTC-05:00) Eastern Daylight Time (US & Canada)",
                "tz_str": "EST5EDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 19,
                "zone_str": "(UTC-05:00) Indiana (East)",
                "tz_str": "EST5EDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 20,
                "zone_str": "(UTC-04:30) Caracas",
                "tz_str": "VET4:30",
                "dst_offset": 0,
            },
            {
                "index": 21,
                "zone_str": "(UTC-04:00) Asuncion",
                "tz_str": "PYT4PYST,M10.1.0/0,M3.4.0/0",
                "dst_offset": 60,
            },
            {
                "index": 22,
                "zone_str": "(UTC-04:00) Atlantic Standard Time (Canada)",
                "tz_str": "AST4",
                "dst_offset": 0,
            },
            {
                "index": 23,
                "zone_str": "(UTC-04:00) Atlantic Daylight Time (Canada)",
                "tz_str": "AST4ADT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 24,
                "zone_str": "(UTC-04:00) Cuiaba",
                "tz_str": "AMT4AMST,M10.3.0/0,M2.3.0/0",
                "dst_offset": 60,
            },
            {
                "index": 25,
                "zone_str": "(UTC-04:00) Georgetown, La Paz, Manaus, San Juan",
                "tz_str": "BOT4",
                "dst_offset": 0,
            },
            {
                "index": 26,
                "zone_str": "(UTC-04:00) Santiago",
                "tz_str": "AMT4AMST,M10.3.0/0,M2.3.0/0",
                "dst_offset": 60,
            },
            {
                "index": 27,
                "zone_str": "(UTC-03:30) Newfoundland",
                "tz_str": "NST3:30NDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 28,
                "zone_str": "(UTC-03:00) Brasilia",
                "tz_str": "BRT3BRST,M10.3.0/0,M2.3.0/0",
                "dst_offset": 60,
            },
            {
                "index": 29,
                "zone_str": "(UTC-03:00) Buenos Aires",
                "tz_str": "<GMT+3>3",
                "dst_offset": 0,
            },
            {
                "index": 30,
                "zone_str": "(UTC-03:00) Cayenne, Fortaleza",
                "tz_str": "<GMT+3>3",
                "dst_offset": 0,
            },
            {
                "index": 31,
                "zone_str": "(UTC-03:00) Greenland",
                "tz_str": "PMST3PMDT,M3.2.0,M11.1.0",
                "dst_offset": 60,
            },
            {
                "index": 32,
                "zone_str": "(UTC-03:00) Montevideo",
                "tz_str": "UYT3UYST,M10.1.0,M3.2.0",
                "dst_offset": 60,
            },
            {
                "index": 33,
                "zone_str": "(UTC-03:00) Salvador",
                "tz_str": "<GMT+3>3",
                "dst_offset": 0,
            },
            {
                "index": 34,
                "zone_str": "(UTC-02:00) Coordinated Universal Time-02",
                "tz_str": "<GMT+2>2",
                "dst_offset": 0,
            },
            {
                "index": 35,
                "zone_str": "(UTC-01:00) Azores",
                "tz_str": "AZOT1AZOST,M3.5.0/0,M10.5.0/1",
                "dst_offset": 60,
            },
            {
                "index": 36,
                "zone_str": "(UTC-01:00) Cabo Verde Is.",
                "tz_str": "CVT1",
                "dst_offset": 0,
            },
            {
                "index": 37,
                "zone_str": "(UTC) Casablanca",
                "tz_str": "WET0WEST,M3.5.0,M10.5.0/3",
                "dst_offset": 60,
            },
            {
                "index": 38,
                "zone_str": "(UTC) Coordinated Universal Time",
                "tz_str": "GMT0",
                "dst_offset": 0,
            },
            {
                "index": 39,
                "zone_str": "(UTC) Dublin, Edinburgh, Lisbon, London",
                "tz_str": "GMT0BST,M3.5.0/1,M10.5.0",
                "dst_offset": 60,
            },
            {
                "index": 40,
                "zone_str": "(UTC) Monrovia, Reykjavik",
                "tz_str": "GMT0",
                "dst_offset": 0,
            },
            {
                "index": 41,
                "zone_str": "(UTC+01:00) Amsterdam, Berlin, Bern, Rome, Stockholm, Vienna",
                "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
                "dst_offset": 60,
            },
            {
                "index": 42,
                "zone_str": "(UTC+01:00) Belgrade, Bratislava, Budapest, Ljubljana, Prague",
                "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
                "dst_offset": 60,
            },
            {
                "index": 43,
                "zone_str": "(UTC+01:00) Brussels, Copenhagen, Madrid, Paris",
                "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
                "dst_offset": 60,
            },
            {
                "index": 44,
                "zone_str": "(UTC+01:00) Sarajevo, Skopje, Warsaw, Zagreb",
                "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
                "dst_offset": 60,
            },
            {
                "index": 45,
                "zone_str": "(UTC+01:00) West Central Africa",
                "tz_str": "WAT-1",
                "dst_offset": 0,
            },
            {
                "index": 46,
                "zone_str": "(UTC+01:00) Windhoek",
                "tz_str": "WAT-1WAST,M9.1.0,M4.1.0",
                "dst_offset": 60,
            },
            {
                "index": 47,
                "zone_str": "(UTC+02:00) Amman",
                "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
                "dst_offset": 60,
            },
            {
                "index": 48,
                "zone_str": "(UTC+02:00) Athens, Bucharest",
                "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
                "dst_offset": 60,
            },
            {
                "index": 49,
                "zone_str": "(UTC+02:00) Beirut",
                "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
                "dst_offset": 60,
            },
            {
                "index": 50,
                "zone_str": "(UTC+02:00) Cairo",
                "tz_str": "<GMT-2>-2",
                "dst_offset": 0,
            },
            {
                "index": 51,
                "zone_str": "(UTC+02:00) Damascus",
                "tz_str": "EET-2EEST,M3.5.5/0,M10.5.5/0",
                "dst_offset": 60,
            },
            {
                "index": 52,
                "zone_str": "(UTC+02:00) E. Europe",
                "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
                "dst_offset": 60,
            },
            {
                "index": 53,
                "zone_str": "(UTC+02:00) Harare, Pretoria",
                "tz_str": "<GMT-2>-2",
                "dst_offset": 0,
            },
            {
                "index": 54,
                "zone_str": "(UTC+02:00) Helsinki, Kyiv, Riga, Sofia, Tallinn, Vilnius",
                "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
                "dst_offset": 60,
            },
            {
                "index": 55,
                "zone_str": "(UTC+02:00) Istanbul",
                "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
                "dst_offset": 60,
            },
            {
                "index": 56,
                "zone_str": "(UTC+02:00) Jerusalem",
                "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
                "dst_offset": 60,
            },
            {
                "index": 57,
                "zone_str": "(UTC+02:00) Kaliningrad (RTZ 1)",
                "tz_str": "EET-2",
                "dst_offset": 0,
            },
            {
                "index": 58,
                "zone_str": "(UTC+02:00) Tripoli",
                "tz_str": "<GMT-2>-2",
                "dst_offset": 0,
            },
            {
                "index": 59,
                "zone_str": "(UTC+03:00) Baghdad",
                "tz_str": "AST-3",
                "dst_offset": 0,
            },
            {
                "index": 60,
                "zone_str": "(UTC+03:00) Kuwait, Riyadh",
                "tz_str": "AST-3",
                "dst_offset": 0,
            },
            {
                "index": 61,
                "zone_str": "(UTC+03:00) Minsk",
                "tz_str": "MSK-3",
                "dst_offset": 0,
            },
            {
                "index": 62,
                "zone_str": "(UTC+03:00) Moscow, St. Petersburg, Volgograd (RTZ 2)",
                "tz_str": "MSK-3",
                "dst_offset": 0,
            },
            {
                "index": 63,
                "zone_str": "(UTC+03:00) Nairobi",
                "tz_str": "<GMT-3>-3",
                "dst_offset": 0,
            },
            {
                "index": 64,
                "zone_str": "(UTC+03:30) Tehran",
                "tz_str": "AZT-3:30AZST,M3.5.0/4,M10.5.0/5",
                "dst_offset": 60,
            },
            {
                "index": 65,
                "zone_str": "(UTC+04:00) Abu Dhabi, Muscat",
                "tz_str": "GST-4",
                "dst_offset": 0,
            },
            {
                "index": 66,
                "zone_str": "(UTC+04:00) Baku",
                "tz_str": "AZT-4AZST,M3.5.0/4,M10.5.0/5",
                "dst_offset": 60,
            },
            {
                "index": 67,
                "zone_str": "(UTC+04:00) Izhevsk, Samara (RTZ 3)",
                "tz_str": "SAMT-4",
                "dst_offset": 0,
            },
            {
                "index": 68,
                "zone_str": "(UTC+04:00) Port Louis",
                "tz_str": "<GMT-4>-4",
                "dst_offset": 0,
            },
            {
                "index": 69,
                "zone_str": "(UTC+04:00) Tbilisi",
                "tz_str": "GET-4",
                "dst_offset": 0,
            },
            {
                "index": 70,
                "zone_str": "(UTC+04:00) Yerevan",
                "tz_str": "AMT-4",
                "dst_offset": 0,
            },
            {
                "index": 71,
                "zone_str": "(UTC+04:30) Kabul",
                "tz_str": "AFT-4:30",
                "dst_offset": 0,
            },
            {
                "index": 72,
                "zone_str": "(UTC+05:00) Ashgabat, Tashkent",
                "tz_str": "TMT-5",
                "dst_offset": 0,
            },
            {
                "index": 73,
                "zone_str": "(UTC+05:00) Ekaterinburg (RTZ 4)",
                "tz_str": "YEKT-5",
                "dst_offset": 0,
            },
            {
                "index": 74,
                "zone_str": "(UTC+05:00) Islamabad, Karachi",
                "tz_str": "PKT-5",
                "dst_offset": 0,
            },
            {
                "index": 75,
                "zone_str": "(UTC+05:30) Chennai, Kolkata, Mumbai, New Delhi",
                "tz_str": "IST-5:30",
                "dst_offset": 0,
            },
            {
                "index": 76,
                "zone_str": "(UTC+05:30) Sri Jayawardenepura",
                "tz_str": "IST-5:30",
                "dst_offset": 0,
            },
            {
                "index": 77,
                "zone_str": "(UTC+05:45) Kathmandu",
                "tz_str": "NPT-5:45",
                "dst_offset": 0,
            },
            {
                "index": 78,
                "zone_str": "(UTC+06:00) Astana",
                "tz_str": "<GMT-6>-6",
                "dst_offset": 0,
            },
            {
                "index": 79,
                "zone_str": "(UTC+06:00) Dhaka",
                "tz_str": "BDT-6",
                "dst_offset": 0,
            },
            {
                "index": 80,
                "zone_str": "(UTC+06:00) Novosibirsk (RTZ 5)",
                "tz_str": "NOVT-6",
                "dst_offset": 0,
            },
            {
                "index": 81,
                "zone_str": "(UTC+06:30) Yangon (Rangoon)",
                "tz_str": "MMT-6:30",
                "dst_offset": 0,
            },
            {
                "index": 82,
                "zone_str": "(UTC+07:00) Bangkok, Hanoi, Jakarta",
                "tz_str": "ICT-7",
                "dst_offset": 0,
            },
            {
                "index": 83,
                "zone_str": "(UTC+07:00) Krasnoyarsk (RTZ 6)",
                "tz_str": "KRAT-7",
                "dst_offset": 0,
            },
            {
                "index": 84,
                "zone_str": "(UTC+08:00) Beijing, Chongqing, Hong Kong, Urumqi",
                "tz_str": "CST-8",
                "dst_offset": 0,
            },
            {
                "index": 85,
                "zone_str": "(UTC+08:00) Irkutsk (RTZ 7)",
                "tz_str": "IRKT-8",
                "dst_offset": 0,
            },
            {
                "index": 86,
                "zone_str": "(UTC+08:00) Kuala Lumpur, Singapore",
                "tz_str": "MYT-8",
                "dst_offset": 0,
            },
            {
                "index": 87,
                "zone_str": "(UTC+08:00) Perth",
                "tz_str": "<GMT-8>-8",
                "dst_offset": 0,
            },
            {
                "index": 88,
                "zone_str": "(UTC+08:00) Taipei",
                "tz_str": "CST-8",
                "dst_offset": 0,
            },
            {
                "index": 89,
                "zone_str": "(UTC+08:00) Ulaanbaatar",
                "tz_str": "<GMT-8>-8",
                "dst_offset": 0,
            },
            {
                "index": 90,
                "zone_str": "(UTC+09:00) Osaka, Sapporo, Tokyo",
                "tz_str": "JST-9",
                "dst_offset": 0,
            },
            {
                "index": 91,
                "zone_str": "(UTC+09:00) Seoul",
                "tz_str": "KST-9",
                "dst_offset": 0,
            },
            {
                "index": 92,
                "zone_str": "(UTC+09:00) Yakutsk (RTZ 8)",
                "tz_str": "YAKT-9",
                "dst_offset": 0,
            },
            {
                "index": 93,
                "zone_str": "(UTC+09:30) Adelaide",
                "tz_str": "ACST-9:30ACDT,M10.1.0,M4.1.0/3",
                "dst_offset": 60,
            },
            {
                "index": 94,
                "zone_str": "(UTC+09:30) Darwin",
                "tz_str": "ACST-9:30",
                "dst_offset": 0,
            },
            {
                "index": 95,
                "zone_str": "(UTC+10:00) Brisbane",
                "tz_str": "<GMT-10>-10",
                "dst_offset": 0,
            },
            {
                "index": 96,
                "zone_str": "(UTC+10:00) Canberra, Melbourne, Sydney",
                "tz_str": "AEST-10AEDT,M10.1.0,M4.1.0/3",
                "dst_offset": 60,
            },
            {
                "index": 97,
                "zone_str": "(UTC+10:00) Guam, Port Moresby",
                "tz_str": "ChST-10",
                "dst_offset": 0,
            },
            {
                "index": 98,
                "zone_str": "(UTC+10:00) Hobart",
                "tz_str": "AEST-10AEDT,M10.1.0,M4.1.0/3",
                "dst_offset": 60,
            },
            {
                "index": 99,
                "zone_str": "(UTC+10:00) Magadan",
                "tz_str": "MAGT-10",
                "dst_offset": 0,
            },
            {
                "index": 100,
                "zone_str": "(UTC+10:00) Vladivostok, Magadan (RTZ 9)",
                "tz_str": "VLAT-10",
                "dst_offset": 0,
            },
            {
                "index": 101,
                "zone_str": "(UTC+11:00) Chokurdakh (RTZ 10)",
                "tz_str": "<GMT-11>-11",
                "dst_offset": 0,
            },
            {
                "index": 102,
                "zone_str": "(UTC+11:00) Solomon Is., New Caledonia",
                "tz_str": "SBT-11",
                "dst_offset": 0,
            },
            {
                "index": 103,
                "zone_str": "(UTC+12:00) Anadyr, Petropavlovsk-Kamchatsky (RTZ 11)",
                "tz_str": "ANAT-12",
                "dst_offset": 0,
            },
            {
                "index": 104,
                "zone_str": "(UTC+12:00) Auckland, Wellington",
                "tz_str": "NZST-12NZDT,M9.5.0,M4.1.0/3",
                "dst_offset": 60,
            },
            {
                "index": 105,
                "zone_str": "(UTC+12:00) Coordinated Universal Time+12",
                "tz_str": "<GMT-12>-12",
                "dst_offset": 0,
            },
            {
                "index": 106,
                "zone_str": "(UTC+12:00) Fiji",
                "tz_str": "NZST-12NZDT,M9.5.0,M4.1.0/3",
                "dst_offset": 60,
            },
            {
                "index": 107,
                "zone_str": "(UTC+13:00) Nuku'alofa",
                "tz_str": "TKT-13",
                "dst_offset": 0,
            },
            {
                "index": 108,
                "zone_str": "(UTC+13:00) Samoa",
                "tz_str": "WSST-13WSDT,M9.5.0/3,M4.1.0/4",
                "dst_offset": 60,
            },
            {
                "index": 109,
                "zone_str": "(UTC+14:00) Kiritimati Island",
                "tz_str": "LINT-14",
                "dst_offset": 0,
            },
        ]
        for item in timezones:
            echo(
                f"Index: {item['index']:3}\tName: {item['zone_str']:65}\tRule: {item['tz_str']}"
            )
        return
    if index:
        return await dev.modules["time"].set_timezone(index)


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def on(dev: SmartDevice, index: int, name: str, transition: int):
    """Turn the device on."""
    if index is not None or name is not None:
        if not dev.is_strip:
            echo("Index and name are only for power strips!")
            return

        dev = cast(SmartStrip, dev)
        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    echo(f"Turning on {dev.alias}")
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
            echo("Index and name are only for power strips!")
            return

        dev = cast(SmartStrip, dev)
        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    echo(f"Turning off {dev.alias}")
    return await dev.turn_off(transition=transition)


@cli.command()
@click.option("--delay", default=1)
@pass_dev
async def reboot(plug, delay):
    """Reboot the device."""
    echo("Rebooting the device..")
    return await plug.reboot(delay)


@cli.group()
@pass_dev
async def schedule(dev):
    """Scheduling commands."""


@schedule.command(name="list")
@pass_dev
@click.option("--json", is_flag=True)
@click.argument("type", default="schedule")
def _schedule_list(dev, json, type):
    """Return the list of schedule actions for the given type."""
    sched = dev.modules[type]
    if sched.rules == []:
        echo(f"No rules of type {type}")
    for rule in sched.rules:
        if json:
            print(rule.json())
        else:
            print(rule)

    return sched.rules


@schedule.command(name="enable")
@pass_dev
@click.argument("enable", type=click.BOOL)
async def _schedule_enable(dev, enable):
    """Enable or disable schedule."""
    schedule = dev.modules["schedule"]
    return await schedule.set_enabled(1 if state else 0)


@schedule.command(name="add")
@pass_dev
@click.option("--name", type=str, required=True)
@click.option("--enable", type=click.BOOL, default=True, show_default=True)
@click.option("--repeat", type=click.BOOL, default=True, show_default=True)
@click.option("--days", type=str, required=True)
@click.option("--start-action", type=click.IntRange(-1, 2), default=None, required=True)
@click.option("--start-sun", type=click.IntRange(-1, 2), default=None, required=True)
@click.option(
    "--start-minutes", type=click.IntRange(0, 1440), default=None, required=True
)
@click.option("--end-action", type=click.IntRange(-1, 2), default=-1)
@click.option("--end-sun", type=click.IntRange(-1, 2), default=-1)
@click.option("--end-minutes", type=click.IntRange(0, 1440), default=None)
async def add_rule(
    dev,
    name,
    enable,
    repeat,
    days,
    start_action,
    start_sun,
    start_minutes,
    end_action,
    end_sun,
    end_minutes,
):
    """Add rule to device."""
    schedule = dev.modules["schedule"]
    rule_to_add = schedule.Rule(
        name=name,
        enable=enable,
        repeat=repeat,
        days=list(map(int, days.split(","))),
        start_action=start_action,
        start_sun=start_sun,
        start_minutes=start_minutes,
        end_action=end_action,
        end_sun=end_sun,
        end_minutes=end_minutes,
    )
    if rule_to_add:
        echo("Adding rule")
        return await schedule.add_rule(rule_to_add)
    else:
        echo("Invalid rule")


@schedule.command(name="edit")
@pass_dev
@click.option("--id", type=str, required=True)
@click.option("--name", type=str)
@click.option("--enable", type=click.BOOL)
@click.option("--repeat", type=click.BOOL)
@click.option("--days", type=str)
@click.option("--start-action", type=click.IntRange(-1, 2))
@click.option("--start-sun", type=click.IntRange(-1, 2))
@click.option("--start-minutes", type=click.IntRange(0, 1440))
@click.option("--end-action", type=click.IntRange(-1, 2))
@click.option("--end-sun", type=click.IntRange(-1, 2))
@click.option("--end-minutes", type=click.IntRange(0, 1440))
async def edit_rule(
    dev,
    id,
    name,
    enable,
    repeat,
    days,
    start_action,
    start_sun,
    start_minutes,
    end_action,
    end_sun,
    end_minutes,
):
    """Edit rule from device."""
    schedule = dev.modules["schedule"]
    rule_to_edit = next(filter(lambda rule: (rule.id == id), schedule.rules), None)
    if rule_to_edit:
        echo(f"Editing rule id {id}")
        if name is not None:
            rule_to_edit.name = name
        if enable is not None:
            rule_to_edit.enable = 1 if enable else 0
        if repeat is not None:
            rule_to_edit.repeat = 1 if repeat else 0
        if days is not None:
            rule_to_edit.wday = list(map(int, days.split(",")))
        if start_action is not None:
            rule_to_edit.sact = start_action
        if start_sun is not None:
            rule_to_edit.stime_opt = start_sun
        if start_minutes is not None:
            rule_to_edit.smin = start_minutes
        if end_action is not None:
            rule_to_edit.eact = end_action
        if end_sun is not None:
            rule_to_edit.etime_opt = end_sun
        if end_minutes is not None:
            rule_to_edit.emin = end_minutes
        return await schedule.edit_rule(rule_to_edit)
    else:
        echo(f"No rule with id {id} was found")


@schedule.command(name="delete")
@pass_dev
@click.option("--id", type=str, required=True)
async def delete_rule(dev, id):
    """Delete rule from device."""
    schedule = dev.modules["schedule"]
    rule_to_delete = next(filter(lambda rule: (rule.id == id), schedule.rules), None)
    if rule_to_delete:
        echo(f"Deleting rule id {id}")
        return await schedule.delete_rule(rule_to_delete)
    else:
        echo(f"No rule with id {id} was found")


@schedule.command()
@pass_dev
@click.option("--prompt", type=click.BOOL, prompt=True, help="Are you sure?")
async def delete_all(dev, prompt):
    """Delete all rules from device."""
    schedule = dev.modules["schedule"]
    if prompt:
        echo("Deleting all rules")
        return await schedule.delete_all_rules()


@cli.group(invoke_without_command=True)
@click.pass_context
async def presets(ctx):
    """List and modify bulb setting presets."""
    if ctx.invoked_subcommand is None:
        return await ctx.invoke(presets_list)


@presets.command(name="list")
@pass_dev
def presets_list(dev: SmartBulb):
    """List presets."""
    if not dev.is_bulb:
        echo("Presets only supported on bulbs")
        return

    for preset in dev.presets:
        echo(preset)

    return dev.presets


@presets.command(name="modify")
@click.argument("index", type=int)
@click.option("--brightness", type=int)
@click.option("--hue", type=int)
@click.option("--saturation", type=int)
@click.option("--temperature", type=int)
@pass_dev
async def presets_modify(
    dev: SmartBulb, index, brightness, hue, saturation, temperature
):
    """Modify a preset."""
    for preset in dev.presets:
        if preset.index == index:
            break
    else:
        echo(f"No preset found for index {index}")
        return

    if brightness is not None:
        preset.brightness = brightness
    if hue is not None:
        preset.hue = hue
    if saturation is not None:
        preset.saturation = saturation
    if temperature is not None:
        preset.color_temp = temperature

    echo(f"Going to save preset: {preset}")

    return await dev.save_preset(preset)


@cli.command()
@pass_dev
@click.option("--type", type=click.Choice(["soft", "hard"], case_sensitive=False))
@click.option("--last", is_flag=True)
@click.option("--preset", type=int)
async def turn_on_behavior(dev: SmartBulb, type, last, preset):
    """Modify bulb turn-on behavior."""
    settings = await dev.get_turn_on_behavior()
    echo(f"Current turn on behavior: {settings}")

    # Return if we are not setting the value
    if not type and not last and not preset:
        return settings

    # If we are setting the value, the type has to be specified
    if (last or preset) and type is None:
        echo("To set the behavior, you need to define --type")
        return

    behavior = getattr(settings, type)

    if last:
        echo(f"Going to set {type} to last")
        behavior.preset = None
    elif preset is not None:
        echo(f"Going to set {type} to preset {preset}")
        behavior.preset = preset

    return await dev.set_turn_on_behavior(settings)


if __name__ == "__main__":
    cli()
