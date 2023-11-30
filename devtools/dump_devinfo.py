"""This script generates devinfo files for the test suite.

If you have new, yet unsupported device or a device with no devinfo file under
 kasa/tests/fixtures, feel free to run this script and create a PR to add the file
 to the repository.

Executing this script will several modules and methods one by one,
and finally execute a query to query all of them at once.
"""
import base64
import collections.abc
import json
import logging
import re
from collections import defaultdict, namedtuple
from pprint import pprint

import asyncclick as click

from kasa import Credentials, Discover, SmartDevice
from kasa.discover import DiscoveryResult
from kasa.tapo.tapodevice import TapoDevice

Call = namedtuple("Call", "module method")


def scrub(res):
    """Remove identifiers from the given dict."""
    keys_to_scrub = [
        "deviceId",
        "fwId",
        "hwId",
        "oemId",
        "mac",
        "mic_mac",
        "latitude_i",
        "longitude_i",
        "latitude",
        "longitude",
        "owner",
        "device_id",
        "ip",
        "ssid",
        "hw_id",
        "fw_id",
        "oem_id",
    ]

    for k, v in res.items():
        if isinstance(v, collections.abc.Mapping):
            res[k] = scrub(res.get(k))
        else:
            if k in keys_to_scrub:
                if k in ["latitude", "latitude_i", "longitude", "longitude_i"]:
                    v = 0
                elif k in ["ip"]:
                    v = "127.0.0.123"
                elif k in ["ssid"]:
                    # Need a valid base64 value here
                    v = base64.b64encode(b"##MASKEDNAME##").decode()
                else:
                    v = re.sub(r"\w", "0", v)

            res[k] = v
    return res


def default_to_regular(d):
    """Convert nested defaultdicts to regular ones.

    From https://stackoverflow.com/a/26496899
    """
    if isinstance(d, defaultdict):
        d = {k: default_to_regular(v) for k, v in d.items()}
    return d


@click.command()
@click.argument("host")
@click.option(
    "--username",
    default=None,
    required=False,
    envvar="TPLINK_CLOUD_USERNAME",
    help="Username/email address to authenticate to device.",
)
@click.option(
    "--password",
    default=None,
    required=False,
    envvar="TPLINK_CLOUD_PASSWORD",
    help="Password to use to authenticate to device.",
)
@click.option("-d", "--debug", is_flag=True)
async def cli(host, debug, username, password):
    """Generate devinfo file for given device."""
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    credentials = Credentials(username=username, password=password)
    device = await Discover.discover_single(host, credentials=credentials)

    if isinstance(device, TapoDevice):
        save_to, final = await get_smart_fixture(device)
    else:
        save_to, final = await get_legacy_fixture(device)

    pprint(scrub(final))
    save = click.prompt(f"Do you want to save the above content to {save_to} (y/n)")
    if save == "y":
        click.echo(f"Saving info to {save_to}")

        with open(save_to, "w") as f:
            json.dump(final, f, sort_keys=True, indent=4)
            f.write("\n")
    else:
        click.echo("Not saving.")


async def get_legacy_fixture(device):
    """Get fixture for legacy IOT style protocol."""
    items = [
        Call(module="system", method="get_sysinfo"),
        Call(module="emeter", method="get_realtime"),
        Call(module="smartlife.iot.dimmer", method="get_dimmer_parameters"),
        Call(module="smartlife.iot.common.emeter", method="get_realtime"),
        Call(
            module="smartlife.iot.smartbulb.lightingservice", method="get_light_state"
        ),
        Call(module="smartlife.iot.LAS", method="get_config"),
        Call(module="smartlife.iot.PIR", method="get_config"),
    ]

    successes = []

    for test_call in items:
        try:
            click.echo(f"Testing {test_call}..", nl=False)
            info = await device.protocol.query(
                {test_call.module: {test_call.method: None}}
            )
            resp = info[test_call.module]
        except Exception as ex:
            click.echo(click.style(f"FAIL {ex}", fg="red"))
        else:
            if "err_msg" in resp:
                click.echo(click.style(f"FAIL {resp['err_msg']}", fg="red"))
            else:
                click.echo(click.style("OK", fg="green"))
                successes.append((test_call, info))

    final_query = defaultdict(defaultdict)
    final = defaultdict(defaultdict)
    for succ, resp in successes:
        final_query[succ.module][succ.method] = None
        final[succ.module][succ.method] = resp

    final = default_to_regular(final)

    try:
        final = await device.protocol.query(final_query)
    except Exception as ex:
        click.echo(
            click.style(
                f"Unable to query all successes at once: {ex}", bold=True, fg="red"
            )
        )

    if device._discovery_info:
        # Need to recreate a DiscoverResult here because we don't want the aliases
        # in the fixture, we want the actual field names as returned by the device.
        dr = DiscoveryResult(**device._discovery_info)
        final["discovery_result"] = dr.dict(
            by_alias=False, exclude_unset=True, exclude_none=True, exclude_defaults=True
        )

    click.echo("Got %s successes" % len(successes))
    click.echo(click.style("## device info file ##", bold=True))

    sysinfo = final["system"]["get_sysinfo"]
    model = sysinfo["model"]
    hw_version = sysinfo["hw_ver"]
    sw_version = sysinfo["sw_ver"]
    sw_version = sw_version.split(" ", maxsplit=1)[0]
    save_to = f"{model}_{hw_version}_{sw_version}.json"
    return save_to, final


async def get_smart_fixture(device: SmartDevice):
    """Get fixture for new TAPO style protocol."""
    items = [
        Call(
            module="child_device_component_list",
            method="get_child_device_component_list",
        ),
        Call(module="device_info", method="get_device_info"),
        Call(module="device_usage", method="get_device_usage"),
    ]

    successes = []

    for test_call in items:
        try:
            click.echo(f"Testing {test_call}..", nl=False)
            response = await device.protocol.query(test_call.method)
        except Exception as ex:
            click.echo(click.style(f"FAIL {ex}", fg="red"))
        else:
            if not response:
                click.echo(click.style("FAIL not suported", fg="red"))
            else:
                click.echo(click.style("OK", fg="green"))
                successes.append(test_call)

    requests = []
    for succ in successes:
        requests.append({"method": succ.method})

    final_query = {"multipleRequest": {"requests": requests}}

    try:
        responses = await device.protocol.query(final_query)
    except Exception as ex:
        click.echo(
            click.style(
                f"Unable to query all successes at once: {ex}", bold=True, fg="red"
            )
        )
    final = {}
    for response in responses["responses"]:
        final[response["method"]] = response["result"]

    if device._discovery_info:
        # Need to recreate a DiscoverResult here because we don't want the aliases
        # in the fixture, we want the actual field names as returned by the device.
        dr = DiscoveryResult(**device._discovery_info)
        final["discovery_result"] = dr.dict(
            by_alias=False, exclude_unset=True, exclude_none=True, exclude_defaults=True
        )

    click.echo("Got %s successes" % len(successes))
    click.echo(click.style("## device info file ##", bold=True))

    hw_version = final["get_device_info"]["hw_ver"]
    sw_version = final["get_device_info"]["fw_ver"]
    model = final["get_device_info"]["model"]
    sw_version = sw_version.split(" ", maxsplit=1)[0]

    return f"{model}_{hw_version}_{sw_version}.json", final


if __name__ == "__main__":
    cli()
