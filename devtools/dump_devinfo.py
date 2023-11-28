"""This script generates devinfo files for the test suite.

If you have new, yet unsupported device or a device with no devinfo file under
 kasa/tests/fixtures, feel free to run this script and create a PR to add the file
 to the repository.

Executing this script will several modules and methods one by one,
and finally execute a query to query all of them at once.
"""
import collections.abc
import json
import logging
import re
from collections import defaultdict, namedtuple
from pprint import pprint

import asyncclick as click

from kasa import Credentials, Discover

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
        "device_owner_hash",
        "device_id_hash",
    ]

    for k, v in res.items():
        if isinstance(v, collections.abc.Mapping):
            res[k] = scrub(res.get(k))
        else:
            if k in keys_to_scrub:
                if k in ["latitude", "latitude_i", "longitude", "longitude_i"]:
                    v = 0
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

    credentials = Credentials(username=username, password=password)
    device = await Discover.discover_single(host, credentials=credentials)

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

    if device.discovery_info:
        final["discovery_result"] = device.discovery_info

    click.echo("Got %s successes" % len(successes))
    click.echo(click.style("## device info file ##", bold=True))

    sysinfo = final["system"]["get_sysinfo"]
    model = sysinfo["model"]
    hw_version = sysinfo["hw_ver"]
    sw_version = sysinfo["sw_ver"]
    sw_version = sw_version.split(" ", maxsplit=1)[0]
    save_to = f"{model}_{hw_version}_{sw_version}.json"
    pprint(scrub(final))
    save = click.prompt(f"Do you want to save the above content to {save_to} (y/n)")
    if save == "y":
        click.echo(f"Saving info to {save_to}")

        with open(save_to, "w") as f:
            json.dump(final, f, sort_keys=True, indent=4)
            f.write("\n")
    else:
        click.echo("Not saving.")


if __name__ == "__main__":
    cli()
