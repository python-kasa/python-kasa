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
import traceback
from collections import defaultdict, namedtuple
from os import listdir
from os.path import isfile, join
from pathlib import Path
from pprint import pprint
from typing import Dict, List, Union

import asyncclick as click

from devtools.helpers.smartrequests import SmartRequest, get_component_requests
from kasa import (
    AuthenticationException,
    Credentials,
    Device,
    Discover,
    SmartDeviceException,
    TimeoutException,
)
from kasa.discover import DiscoveryResult
from kasa.exceptions import SmartErrorCode
from kasa.smart import SmartDevice

SupportedVersion = namedtuple("SupportedVersion", "region hw fw auth")


Call = namedtuple("Call", "module method")
SmartCall = namedtuple("SmartCall", "module request should_succeed")

_LOGGER = logging.getLogger(__name__)

IOT_FOLDER = "kasa/tests/fixtures/"
SMART_FOLDER = "kasa/tests/fixtures/smart/"
SUPPORTED_FILENAME = "SUPPORTED.md"

PLUGS = "Plugs"
POWER_STRIPS = "Power Strips"
WALL_SWITCHES = "Wall Switches"
BULBS = "Bulbs"
LIGHT_STRIPS = "Light Strips"


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
        "nickname",
        "alias",
        "bssid",
        "channel",
        "original_device_id",  # for child devices
    ]

    for k, v in res.items():
        if isinstance(v, collections.abc.Mapping):
            res[k] = scrub(res.get(k))
        elif (
            isinstance(v, list)
            and len(v) > 0
            and isinstance(v[0], collections.abc.Mapping)
        ):
            res[k] = [scrub(vi) for vi in v]
        else:
            if k in keys_to_scrub:
                if k in ["mac", "mic_mac"]:
                    # Some macs have : or - as a separator and others do not
                    if len(v) == 12:
                        v = f"{v[:6]}000000"
                    else:
                        delim = ":" if ":" in v else "-"
                        rest = delim.join(
                            format(s, "02x") for s in bytes.fromhex("000000")
                        )
                        v = f"{v[:8]}{delim}{rest}"
                elif k in ["latitude", "latitude_i", "longitude", "longitude_i"]:
                    v = 0
                elif k in ["ip"]:
                    v = "127.0.0.123"
                elif k in ["ssid"]:
                    # Need a valid base64 value here
                    v = base64.b64encode(b"#MASKED_SSID#").decode()
                elif k in ["nickname"]:
                    v = base64.b64encode(b"#MASKED_NAME#").decode()
                elif k in ["alias"]:
                    v = "#MASKED_NAME#"
                elif isinstance(res[k], int):
                    v = 0
                elif k == "device_id" and len(v) > 40:
                    # retain the last two chars when scrubbing child ids
                    end = v[-2:]
                    v = re.sub(r"\w", "0", v)
                    v = v[:40] + end
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


async def handle_device(basedir, autosave, device: Device, batch_size: int) -> bool:
    """Create a fixture for a single device instance."""
    if isinstance(device, SmartDevice):
        filename, copy_folder, final = await get_smart_fixture(device, batch_size)
    else:
        filename, copy_folder, final = await get_legacy_fixture(device)

    save_filename = Path(basedir) / copy_folder / filename

    pprint(scrub(final))
    if autosave:
        save = "y"
    else:
        save = click.prompt(
            f"Do you want to save the above content to {save_filename} (y/n)"
        )
    if save == "y":
        click.echo(f"Saving info to {save_filename}")

        with open(save_filename, "w") as f:
            json.dump(final, f, sort_keys=True, indent=4)
            f.write("\n")
        return True
    else:
        click.echo("Not saving.")
        return False


@click.group(invoke_without_command=True)
@click.option("--host", required=False, help="Target host.")
@click.option(
    "--target",
    required=False,
    default="255.255.255.255",
    help="Target network for discovery.",
)
@click.option(
    "--username",
    default="",
    required=False,
    envvar="KASA_USERNAME",
    help="Username/email address to authenticate to device.",
)
@click.option(
    "--password",
    default="",
    required=False,
    envvar="KASA_PASSWORD",
    help="Password to use to authenticate to device.",
)
@click.option("--basedir", help="Base directory for the git repository", default=".")
@click.option("--autosave", is_flag=True, default=False, help="Save without prompting")
@click.option(
    "--batch-size", default=5, help="Number of batched requests to send at once"
)
@click.option("-d", "--debug", is_flag=True)
@click.pass_context
async def cli(
    ctx, host, target, basedir, autosave, debug, username, password, batch_size
):
    """Generate devinfo files for devices.

    Use --host (for a single device) or --target (for a complete network).
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    if ctx.invoked_subcommand == "generate-supported":
        return

    credentials = Credentials(username=username, password=password)
    file_created = False
    if host is not None:
        click.echo("Host given, performing discovery on %s." % host)
        device = await Discover.discover_single(host, credentials=credentials)
        if await handle_device(basedir, autosave, device, batch_size):
            file_created = True
    else:
        click.echo(
            "No --host given, performing discovery on %s. Use --target to override."
            % target
        )
        devices = await Discover.discover(target=target, credentials=credentials)
        click.echo("Detected %s devices" % len(devices))
        for dev in devices.values():
            if await handle_device(basedir, autosave, dev, batch_size):
                file_created = True
    if file_created:
        generate_supported()


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
        finally:
            await device.protocol.close()

    final_query = defaultdict(defaultdict)
    final = defaultdict(defaultdict)
    for succ, resp in successes:
        final_query[succ.module][succ.method] = None
        final[succ.module][succ.method] = resp

    final = default_to_regular(final)

    try:
        final = await device.protocol.query(final_query)
    except Exception as ex:
        _echo_error(f"Unable to query all successes at once: {ex}", bold=True, fg="red")
    finally:
        await device.protocol.close()
    if device._discovery_info and not device._discovery_info.get("system"):
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
    save_filename = f"{model}_{hw_version}_{sw_version}.json"
    copy_folder = IOT_FOLDER
    return save_filename, copy_folder, final


def _echo_error(msg: str):
    click.echo(
        click.style(
            msg,
            bold=True,
            fg="red",
        )
    )


async def _make_requests_or_exit(
    device: SmartDevice,
    requests: List[SmartRequest],
    name: str,
    batch_size: int,
) -> Dict[str, Dict]:
    final = {}
    try:
        end = len(requests)
        step = batch_size  # Break the requests down as there seems to be a size limit
        for i in range(0, end, step):
            x = i
            requests_step = requests[x : x + step]
            request: Union[List[SmartRequest], SmartRequest] = (
                requests_step[0] if len(requests_step) == 1 else requests_step
            )
            responses = await device.protocol.query(
                SmartRequest._create_request_dict(request)
            )
            for method, result in responses.items():
                final[method] = result
        return final
    except AuthenticationException as ex:
        _echo_error(
            f"Unable to query the device due to an authentication error: {ex}",
        )
        exit(1)
    except SmartDeviceException as ex:
        _echo_error(
            f"Unable to query {name} at once: {ex}",
        )
        if (
            isinstance(ex, TimeoutException)
            or ex.error_code == SmartErrorCode.SESSION_TIMEOUT_ERROR
        ):
            _echo_error(
                "Timeout, try reducing the batch size via --batch-size option.",
            )
        exit(1)
    except Exception as ex:
        _echo_error(
            f"Unexpected exception querying {name} at once: {ex}",
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            traceback.print_stack()
        exit(1)
    finally:
        await device.protocol.close()


async def get_smart_fixture(device: SmartDevice, batch_size: int):
    """Get fixture for new TAPO style protocol."""
    extra_test_calls = [
        SmartCall(
            module="temp_humidity_records",
            request=SmartRequest.get_raw_request("get_temp_humidity_records"),
            should_succeed=False,
        ),
        SmartCall(
            module="child_device_list",
            request=SmartRequest.get_raw_request("get_child_device_list"),
            should_succeed=False,
        ),
        SmartCall(
            module="child_device_component_list",
            request=SmartRequest.get_raw_request("get_child_device_component_list"),
            should_succeed=False,
        ),
        SmartCall(
            module="trigger_logs",
            request=SmartRequest.get_raw_request(
                "get_trigger_logs", SmartRequest.GetTriggerLogsParams(5, 0)
            ),
            should_succeed=False,
        ),
    ]

    successes = []

    click.echo("Testing component_nego call ..", nl=False)
    responses = await _make_requests_or_exit(
        device, [SmartRequest.component_nego()], "component_nego call", batch_size
    )
    component_info_response = responses["component_nego"]
    click.echo(click.style("OK", fg="green"))
    successes.append(
        SmartCall(
            module="component_nego",
            request=SmartRequest("component_nego"),
            should_succeed=True,
        )
    )

    test_calls = []
    should_succeed = []

    for item in component_info_response["component_list"]:
        component_id = item["id"]
        ver_code = item["ver_code"]
        if (requests := get_component_requests(component_id, ver_code)) is not None:
            component_test_calls = [
                SmartCall(module=component_id, request=request, should_succeed=True)
                for request in requests
            ]
            test_calls.extend(component_test_calls)
            should_succeed.extend(component_test_calls)
        else:
            click.echo(f"Skipping {component_id}..", nl=False)
            click.echo(click.style("UNSUPPORTED", fg="yellow"))

    test_calls.extend(extra_test_calls)

    for test_call in test_calls:
        click.echo(f"Testing  {test_call.module}..", nl=False)
        try:
            click.echo(f"Testing {test_call}..", nl=False)
            response = await device.protocol.query(
                SmartRequest._create_request_dict(test_call.request)
            )
        except AuthenticationException as ex:
            _echo_error(
                f"Unable to query the device due to an authentication error: {ex}",
            )
            exit(1)
        except Exception as ex:
            if (
                not test_call.should_succeed
                and hasattr(ex, "error_code")
                and ex.error_code
                in [
                    SmartErrorCode.UNKNOWN_METHOD_ERROR,
                    SmartErrorCode.TRANSPORT_NOT_AVAILABLE_ERROR,
                ]
            ):
                click.echo(click.style("FAIL - EXPECTED", fg="green"))
            else:
                click.echo(click.style(f"FAIL {ex}", fg="red"))
        else:
            if not response:
                click.echo(click.style("FAIL no response", fg="red"))
            else:
                if not test_call.should_succeed:
                    click.echo(click.style("OK - EXPECTED FAIL", fg="red"))
                else:
                    click.echo(click.style("OK", fg="green"))
                successes.append(test_call)
        finally:
            await device.protocol.close()

    requests = []
    for succ in successes:
        requests.append(succ.request)

    final = await _make_requests_or_exit(
        device, requests, "all successes at once", batch_size
    )

    # Need to recreate a DiscoverResult here because we don't want the aliases
    # in the fixture, we want the actual field names as returned by the device.
    dr = DiscoveryResult(**device._discovery_info)  # type: ignore
    final["discovery_result"] = dr.dict(
        by_alias=False, exclude_unset=True, exclude_none=True, exclude_defaults=True
    )

    click.echo("Got %s successes" % len(successes))
    click.echo(click.style("## device info file ##", bold=True))

    hw_version = final["get_device_info"]["hw_ver"]
    sw_version = final["get_device_info"]["fw_ver"]
    model = final["discovery_result"]["device_model"]
    sw_version = sw_version.split(" ", maxsplit=1)[0]

    save_filename = f"{model}_{hw_version}_{sw_version}.json"
    copy_folder = SMART_FOLDER
    return save_filename, copy_folder, final


@cli.command(name="generate-supported")
async def generate_supported():
    """Generate the SUPPORTED.md from the fixtures."""
    brands = {"kasa": {}, "tapo": {}}
    supported = {
        PLUGS: {"kasa": {}, "tapo": {}},
        POWER_STRIPS: {"kasa": {}, "tapo": {}},
        WALL_SWITCHES: {"kasa": {}, "tapo": {}},
        BULBS: {"kasa": {}, "tapo": {}},
        LIGHT_STRIPS: {"kasa": {}, "tapo": {}},
    }
    _get_iot_supported(supported)
    _get_smart_supported(supported)

    lines = [
        "<sub>&#x25B8;&nbsp; Expand to see tested versions</sub><br>\n",
        "<sub><sup>*</sup>&nbsp; Model requires authentication</sub><br>\n",
        "<sub><sup>**</sup> Newer versions require authentication</sub>\n",
        "\n",
        "| **Type**  | **Kasa**  | **Tapo** <sup>\*</sup>  |\n",
        "|--- |--- |--- |\n",
    ]
    for type_, brands in supported.items():
        models_text = {"kasa": "", "tapo": ""}
        for brand, models in brands.items():
            for model, versions in sorted(models.items()):
                version_list = []
                auth_count = 0
                auth_symbol = ""
                for version in versions:
                    region_text = f"({version.region})" if version.region else ""
                    version_auth = (
                        "<sup> *</sup>" if version.auth and brand == "kasa" else ""
                    )
                    version_text = (
                        f"Hardware {version.hw}{region_text} "
                        + f"Firmare {version.fw}{version_auth}"
                    )
                    version_list.append(version_text)
                    if version.auth:
                        auth_symbol = " **"
                        auth_count += 1
                versions_text = "<br>".join(version_list)
                auth_symbol = " *" if auth_count == len(versions) else auth_symbol
                auth_text = f"<sup>{auth_symbol}</sup>" if brand == "kasa" else ""
                models_text[brand] += (
                    f"<details><summary>{model}{auth_text}"
                    + f"</summary>{versions_text}</details>"
                )
        line = (
            f"| {type_}  | {models_text.get('kasa')}  | {models_text.get('tapo')}  |\n"
        )
        lines.append(line)
    with open(SUPPORTED_FILENAME, "w") as the_file:
        for line in lines:
            the_file.write(line)


def _get_smart_supported(supported):
    smart_files = [
        f
        for f in listdir(SMART_FOLDER)
        if isfile(join(SMART_FOLDER, f)) and f.endswith(".json")
    ]
    for smart_file in smart_files:
        with open(join(SMART_FOLDER, smart_file)) as f:
            fixture_data = json.load(f)

        model, _, region = fixture_data["discovery_result"]["device_model"].partition(
            "("
        )
        # P100 doesn't have region HW
        region = region.replace(")", "") if region else ""
        device_type = fixture_data["discovery_result"]["device_type"]
        if device_type[:10] == "SMART.KASA":
            brand = "kasa"
        elif device_type[:10] == "SMART.TAPO":
            brand = "tapo"
        else:
            click.echo(
                click.style(
                    f"FAIL {smart_file} does not have a "
                    + f"supported device_type {device_type}",
                    fg="red",
                )
            )
            continue
        components = [
            component["id"]
            for component in fixture_data["component_nego"]["component_list"]
        ]
        if device_type[10:] == "BULB":
            supported_type = LIGHT_STRIPS if "light_strip" in components else BULBS
        elif device_type[10:] == "PLUG":
            supported_type = POWER_STRIPS if "child_device" in components else PLUGS
        elif device_type[10:] == "SWITCH":
            supported_type = WALL_SWITCHES
        else:
            click.echo(
                click.style(
                    f"FAIL {smart_file} does not have a "
                    + f"supported device_type {device_type}",
                    fg="red",
                )
            )
            continue

        hw_version = fixture_data["get_device_info"]["hw_ver"]
        fw_version = fixture_data["get_device_info"]["fw_ver"]
        fw_version = fw_version.split(" ", maxsplit=1)[0]

        smodel = supported[supported_type][brand].setdefault(model, [])
        smodel.append(
            SupportedVersion(region=region, hw=hw_version, fw=fw_version, auth=True)
        )


def _get_iot_supported(supported):
    iot_files = [
        f
        for f in listdir(IOT_FOLDER)
        if isfile(join(IOT_FOLDER, f)) and f.endswith(".json")
    ]
    for iot_file in iot_files:
        with open(join(IOT_FOLDER, iot_file)) as f:
            fixture_data = json.load(f)
        sysinfo = fixture_data["system"]["get_sysinfo"]
        model, _, region = sysinfo["model"][:-1].partition("(")
        auth = "discovery_result" in fixture_data
        type_ = sysinfo.get("type", sysinfo.get("mic_type"))
        if type_ == "IOT.SMARTBULB":
            supported_type = LIGHT_STRIPS if "length" in sysinfo else BULBS
        else:
            if "children" in sysinfo:
                supported_type = POWER_STRIPS
            else:
                if "dev_name" not in sysinfo:
                    click.echo(
                        click.style(f"FAIL {iot_file} does not have dev_name", fg="red")
                    )
                    continue
                if "light" in sysinfo["dev_name"].lower():
                    supported_type = WALL_SWITCHES
                else:
                    supported_type = PLUGS
        smodel = supported[supported_type]["kasa"].setdefault(model, [])
        fw = sysinfo["sw_ver"].split(" ", maxsplit=1)[0]
        smodel.append(
            SupportedVersion(region=region, hw=sysinfo["hw_ver"], fw=fw, auth=auth)
        )


if __name__ == "__main__":
    cli()
