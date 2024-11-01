"""This script generates devinfo files for the test suite.

If you have new, yet unsupported device or a device with no devinfo file under
 kasa/tests/fixtures, feel free to run this script and create a PR to add the file
 to the repository.

Executing this script will several modules and methods one by one,
and finally execute a query to query all of them at once.
"""

from __future__ import annotations

import base64
import collections.abc
import dataclasses
import json
import logging
import re
import sys
import traceback
from collections import defaultdict, namedtuple
from pathlib import Path
from pprint import pprint

import asyncclick as click

from devtools.helpers.smartcamerarequests import SMARTCAMERA_REQUESTS
from devtools.helpers.smartrequests import SmartRequest, get_component_requests
from kasa import (
    AuthenticationError,
    Credentials,
    Device,
    DeviceConfig,
    DeviceConnectionParameters,
    Discover,
    KasaException,
    TimeoutError,
)
from kasa.device_factory import get_protocol
from kasa.deviceconfig import DeviceEncryptionType, DeviceFamily
from kasa.discover import DiscoveryResult
from kasa.exceptions import SmartErrorCode
from kasa.experimental.smartcameraprotocol import (
    SmartCameraProtocol,
    _ChildCameraProtocolWrapper,
)
from kasa.smart import SmartChildDevice
from kasa.smartprotocol import SmartProtocol, _ChildProtocolWrapper

Call = namedtuple("Call", "module method")
FixtureResult = namedtuple("FixtureResult", "filename, folder, data")

SMART_FOLDER = "kasa/tests/fixtures/smart/"
SMARTCAMERA_FOLDER = "kasa/tests/fixtures/smartcamera/"
SMART_CHILD_FOLDER = "kasa/tests/fixtures/smart/child/"
IOT_FOLDER = "kasa/tests/fixtures/"

ENCRYPT_TYPES = [encrypt_type.value for encrypt_type in DeviceEncryptionType]

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class SmartCall:
    """Class for smart and smartcamera calls."""

    module: str
    request: dict
    should_succeed: bool
    child_device_id: str
    supports_multiple: bool = True


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
        "la",  # lat on ks240
        "lo",  # lon on ks240
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
        "original_device_id",  # for child devices on strips
        "parent_device_id",  # for hub children
        "setup_code",  # matter
        "setup_payload",  # matter
        "mfi_setup_code",  # mfi_ for homekit
        "mfi_setup_id",
        "mfi_token_token",
        "mfi_token_uuid",
        "dev_id",
        "device_name",
        "device_alias",
        "connect_ssid",
        "encrypt_info",
        "local_ip",
    ]

    for k, v in res.items():
        if isinstance(v, collections.abc.Mapping):
            if k == "encrypt_info":
                if "data" in v:
                    v["data"] = ""
                if "key" in v:
                    v["key"] = ""
            else:
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
                elif k in ["ip", "local_ip"]:
                    v = "127.0.0.123"
                elif k in ["ssid"]:
                    # Need a valid base64 value here
                    v = base64.b64encode(b"#MASKED_SSID#").decode()
                elif k in ["nickname"]:
                    v = base64.b64encode(b"#MASKED_NAME#").decode()
                elif k in ["alias", "device_alias", "device_name"]:
                    v = "#MASKED_NAME#"
                elif isinstance(res[k], int):
                    v = 0
                elif k in ["device_id", "dev_id"] and "SCRUBBED" in v:
                    pass  # already scrubbed
                elif k == ["device_id", "dev_id"] and len(v) > 40:
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


async def handle_device(
    basedir, autosave, protocol, *, discovery_info=None, batch_size: int
):
    """Create a fixture for a single device instance."""
    if isinstance(protocol, SmartProtocol):
        fixture_results: list[FixtureResult] = await get_smart_fixtures(
            protocol, discovery_info=discovery_info, batch_size=batch_size
        )
    else:
        fixture_results = [
            await get_legacy_fixture(protocol, discovery_info=discovery_info)
        ]

    for fixture_result in fixture_results:
        save_filename = Path(basedir) / fixture_result.folder / fixture_result.filename

        pprint(scrub(fixture_result.data))
        if autosave:
            save = "y"
        else:
            save = click.prompt(
                f"Do you want to save the above content to {save_filename} (y/n)"
            )
        if save == "y":
            click.echo(f"Saving info to {save_filename}")

            with save_filename.open("w") as f:
                json.dump(fixture_result.data, f, sort_keys=True, indent=4)
                f.write("\n")
        else:
            click.echo("Not saving.")


@click.command()
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
@click.option(
    "-di",
    "--discovery-info",
    help=(
        "Bypass discovery by passing an accurate discovery result json escaped string."
        + " Do not use this flag unless you are sure you know what it means."
    ),
)
@click.option(
    "--discovery-timeout",
    envvar="KASA_DISCOVERY_TIMEOUT",
    default=10,
    required=False,
    show_default=True,
    help="Timeout for discovery.",
)
@click.option(
    "-e",
    "--encrypt-type",
    envvar="KASA_ENCRYPT_TYPE",
    default=None,
    type=click.Choice(ENCRYPT_TYPES, case_sensitive=False),
)
@click.option(
    "-df",
    "--device-family",
    envvar="KASA_DEVICE_FAMILY",
    default="SMART.TAPOPLUG",
    help="Device family type, e.g. `SMART.KASASWITCH`.",
)
@click.option(
    "-lv",
    "--login-version",
    envvar="KASA_LOGIN_VERSION",
    default=2,
    type=int,
    help="The login version for device authentication. Defaults to 2",
)
@click.option(
    "--https/--no-https",
    envvar="KASA_HTTPS",
    default=False,
    is_flag=True,
    type=bool,
    help="Set flag if the device encryption uses https.",
)
@click.option("--port", help="Port override", type=int)
async def cli(
    host,
    target,
    basedir,
    autosave,
    debug,
    username,
    discovery_timeout,
    password,
    batch_size,
    discovery_info,
    encrypt_type,
    https,
    device_family,
    login_version,
    port,
):
    """Generate devinfo files for devices.

    Use --host (for a single device) or --target (for a complete network).
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    from kasa.experimental import Experimental

    Experimental.set_enabled(True)

    credentials = Credentials(username=username, password=password)
    if host is not None:
        if discovery_info:
            click.echo("Host and discovery info given, trying connect on %s." % host)

            di = json.loads(discovery_info)
            dr = DiscoveryResult(**di)
            connection_type = DeviceConnectionParameters.from_values(
                dr.device_type,
                dr.mgt_encrypt_schm.encrypt_type,
                dr.mgt_encrypt_schm.lv,
            )
            dc = DeviceConfig(
                host=host,
                connection_type=connection_type,
                port_override=port,
                credentials=credentials,
            )
            device = await Device.connect(config=dc)
            await handle_device(
                basedir,
                autosave,
                device.protocol,
                discovery_info=dr.get_dict(),
                batch_size=batch_size,
            )
        elif device_family and encrypt_type:
            ctype = DeviceConnectionParameters(
                DeviceFamily(device_family),
                DeviceEncryptionType(encrypt_type),
                login_version,
                https,
            )
            config = DeviceConfig(
                host=host,
                port_override=port,
                credentials=credentials,
                connection_type=ctype,
            )
            if protocol := get_protocol(config):
                await handle_device(basedir, autosave, protocol, batch_size=batch_size)
            else:
                raise KasaException(
                    "Could not find a protocol for the given parameters. "
                    + "Maybe you need to enable --experimental."
                )
        else:
            click.echo("Host given, performing discovery on %s." % host)
            device = await Discover.discover_single(
                host,
                credentials=credentials,
                port=port,
                discovery_timeout=discovery_timeout,
            )
            await handle_device(
                basedir,
                autosave,
                device.protocol,
                discovery_info=device._discovery_info,
                batch_size=batch_size,
            )
    else:
        click.echo(
            "No --host given, performing discovery on %s. Use --target to override."
            % target
        )
        devices = await Discover.discover(
            target=target, credentials=credentials, discovery_timeout=discovery_timeout
        )
        click.echo("Detected %s devices" % len(devices))
        for dev in devices.values():
            await handle_device(
                basedir,
                autosave,
                dev.protocol,
                discovery_info=dev._discovery_info,
                batch_size=batch_size,
            )


async def get_legacy_fixture(protocol, *, discovery_info):
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
        Call(module="smartlife.iot.LAS", method="get_current_brt"),
        Call(module="smartlife.iot.PIR", method="get_config"),
    ]

    successes = []

    for test_call in items:
        try:
            click.echo(f"Testing {test_call}..", nl=False)
            info = await protocol.query({test_call.module: {test_call.method: {}}})
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
            await protocol.close()

    final_query = defaultdict(defaultdict)
    final = defaultdict(defaultdict)
    for succ, resp in successes:
        final_query[succ.module][succ.method] = {}
        final[succ.module][succ.method] = resp

    final = default_to_regular(final)

    try:
        final = await protocol.query(final_query)
    except Exception as ex:
        _echo_error(f"Unable to query all successes at once: {ex}", bold=True, fg="red")
    finally:
        await protocol.close()
    if discovery_info and not discovery_info.get("system"):
        # Need to recreate a DiscoverResult here because we don't want the aliases
        # in the fixture, we want the actual field names as returned by the device.
        dr = DiscoveryResult(**protocol._discovery_info)
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
    return FixtureResult(filename=save_filename, folder=copy_folder, data=final)


def _echo_error(msg: str):
    click.echo(
        click.style(
            msg,
            bold=True,
            fg="red",
        )
    )


def format_exception(e):
    """Print full exception stack as if it hadn't been caught.

    https://stackoverflow.com/a/12539332
    """
    exception_list = traceback.format_stack()
    exception_list = exception_list[:-2]
    exception_list.extend(traceback.format_tb(sys.exc_info()[2]))
    exception_list.extend(
        traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
    )

    exception_str = "Traceback (most recent call last):\n"
    exception_str += "".join(exception_list)
    # Removing the last \n
    exception_str = exception_str[:-1]

    return exception_str


async def _make_final_calls(
    protocol: SmartProtocol,
    calls: list[SmartCall],
    name: str,
    batch_size: int,
    *,
    child_device_id: str,
) -> dict[str, dict]:
    """Call all successes again.

    After trying each call individually make the calls again either as a
    multiple request or as single requests for those that don't support
    multiple queries.
    """
    multiple_requests = {
        key: smartcall.request[key]
        for smartcall in calls
        if smartcall.supports_multiple and (key := next(iter(smartcall.request)))
    }
    final = await _make_requests_or_exit(
        protocol,
        multiple_requests,
        name + " - multiple",
        batch_size,
        child_device_id=child_device_id,
    )
    single_calls = [smartcall for smartcall in calls if not smartcall.supports_multiple]
    for smartcall in single_calls:
        final[smartcall.module] = await _make_requests_or_exit(
            protocol,
            smartcall.request,
            f"{name} + {smartcall.module}",
            batch_size,
            child_device_id=child_device_id,
        )
    return final


async def _make_requests_or_exit(
    protocol: SmartProtocol,
    requests: dict,
    name: str,
    batch_size: int,
    *,
    child_device_id: str,
) -> dict[str, dict]:
    final = {}
    # Calling close on child protocol wrappers is a noop
    protocol_to_close = protocol
    if child_device_id:
        if isinstance(protocol, SmartCameraProtocol):
            protocol = _ChildCameraProtocolWrapper(child_device_id, protocol)
        else:
            protocol = _ChildProtocolWrapper(child_device_id, protocol)
    try:
        end = len(requests)
        step = batch_size  # Break the requests down as there seems to be a size limit
        keys = [key for key in requests]
        for i in range(0, end, step):
            x = i
            requests_step = {key: requests[key] for key in keys[x : x + step]}
            responses = await protocol.query(requests_step)
            for method, result in responses.items():
                final[method] = result
        return final
    except AuthenticationError as ex:
        _echo_error(
            f"Unable to query the device due to an authentication error: {ex}",
        )
        exit(1)
    except KasaException as ex:
        _echo_error(
            f"Unable to query {name} at once: {ex}",
        )
        if isinstance(ex, TimeoutError):
            _echo_error(
                "Timeout, try reducing the batch size via --batch-size option.",
            )
        exit(1)
    except Exception as ex:
        _echo_error(
            f"Unexpected exception querying {name} at once: {ex}",
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _echo_error(format_exception(ex))
        exit(1)
    finally:
        await protocol_to_close.close()


async def get_smart_camera_test_calls(protocol: SmartProtocol):
    """Get the list of test calls to make."""
    test_calls: list[SmartCall] = []
    successes: list[SmartCall] = []

    test_calls = []
    for request in SMARTCAMERA_REQUESTS:
        method = next(iter(request))
        if method == "get":
            module = method + "_" + next(iter(request[method]))
        else:
            module = method
        test_calls.append(
            SmartCall(
                module=module,
                request=request,
                should_succeed=True,
                child_device_id="",
                supports_multiple=(method != "get"),
            )
        )

    # Now get the child device requests
    child_request = {
        "getChildDeviceList": {"childControl": {"start_index": 0}},
    }
    try:
        child_response = await protocol.query(child_request)
    except Exception:
        _LOGGER.debug("Device does not have any children.")
    else:
        successes.append(
            SmartCall(
                module="getChildDeviceList",
                request=child_request,
                should_succeed=True,
                child_device_id="",
                supports_multiple=True,
            )
        )
        child_list = child_response["getChildDeviceList"]["child_device_list"]
        for child in child_list:
            child_id = child.get("device_id") or child.get("dev_id")
            if not child_id:
                _LOGGER.error("Could not find child device id in %s", child)
            # If category is in the child device map the protocol is smart.
            if (
                category := child.get("category")
            ) and category in SmartChildDevice.CHILD_DEVICE_TYPE_MAP:
                child_protocol = _ChildCameraProtocolWrapper(child_id, protocol)
                try:
                    nego_response = await child_protocol.query({"component_nego": None})
                except Exception as ex:
                    _LOGGER.error("Error calling component_nego: %s", ex)
                    continue
                if "component_nego" not in nego_response:
                    _LOGGER.error(
                        "Could not find component_nego in device response: %s",
                        nego_response,
                    )
                    continue
                successes.append(
                    SmartCall(
                        module="component_nego",
                        request={"component_nego": None},
                        should_succeed=True,
                        child_device_id=child_id,
                    )
                )
                child_components = {
                    item["id"]: item["ver_code"]
                    for item in nego_response["component_nego"]["component_list"]
                }
                for component_id, ver_code in child_components.items():
                    if (
                        requests := get_component_requests(component_id, ver_code)
                    ) is not None:
                        component_test_calls = [
                            SmartCall(
                                module=component_id,
                                request={key: val},
                                should_succeed=True,
                                child_device_id=child_id,
                            )
                            for key, val in requests.items()
                        ]
                        test_calls.extend(component_test_calls)
                    else:
                        click.echo(f"Skipping {component_id}..", nl=False)
                        click.echo(click.style("UNSUPPORTED", fg="yellow"))
            else:  # Not a smart protocol device so assume camera protocol
                for request in SMARTCAMERA_REQUESTS:
                    method = next(iter(request))
                    if method == "get":
                        method = method + "_" + next(iter(request[method]))
                    test_calls.append(
                        SmartCall(
                            module=method,
                            request=request,
                            should_succeed=True,
                            child_device_id=child_id,
                        )
                    )
    finally:
        await protocol.close()
    return test_calls, successes


async def get_smart_test_calls(protocol: SmartProtocol):
    """Get the list of test calls to make."""
    test_calls = []
    successes = []
    child_device_components = {}

    extra_test_calls = [
        SmartCall(
            module="temp_humidity_records",
            request=SmartRequest.get_raw_request("get_temp_humidity_records").to_dict(),
            should_succeed=False,
            child_device_id="",
        ),
    ]

    click.echo("Testing component_nego call ..", nl=False)
    responses = await _make_requests_or_exit(
        protocol,
        SmartRequest.component_nego().to_dict(),
        "component_nego call",
        batch_size=1,
        child_device_id="",
    )
    component_info_response = responses["component_nego"]
    click.echo(click.style("OK", fg="green"))
    successes.append(
        SmartCall(
            module="component_nego",
            request=SmartRequest("component_nego").to_dict(),
            should_succeed=True,
            child_device_id="",
        )
    )
    components = {
        item["id"]: item["ver_code"]
        for item in component_info_response["component_list"]
    }

    if "child_device" in components:
        child_components = await _make_requests_or_exit(
            protocol,
            SmartRequest.get_child_device_component_list().to_dict(),
            "child device component list",
            batch_size=1,
            child_device_id="",
        )
        successes.append(
            SmartCall(
                module="child_component_list",
                request=SmartRequest.get_child_device_component_list().to_dict(),
                should_succeed=True,
                child_device_id="",
            )
        )
        test_calls.append(
            SmartCall(
                module="child_device_list",
                request=SmartRequest.get_child_device_list().to_dict(),
                should_succeed=True,
                child_device_id="",
            )
        )
        # Get list of child components to call
        if "control_child" in components:
            child_device_components = {
                child_component_list["device_id"]: {
                    item["id"]: item["ver_code"]
                    for item in child_component_list["component_list"]
                }
                for child_component_list in child_components[
                    "get_child_device_component_list"
                ]["child_component_list"]
            }

    # Get component calls
    for component_id, ver_code in components.items():
        if component_id == "child_device":
            continue
        if (requests := get_component_requests(component_id, ver_code)) is not None:
            component_test_calls = [
                SmartCall(
                    module=component_id,
                    request={key: val},
                    should_succeed=True,
                    child_device_id="",
                )
                for key, val in requests.items()
            ]
            test_calls.extend(component_test_calls)
        else:
            click.echo(f"Skipping {component_id}..", nl=False)
            click.echo(click.style("UNSUPPORTED", fg="yellow"))

    test_calls.extend(extra_test_calls)

    # Child component calls
    for child_device_id, child_components in child_device_components.items():
        test_calls.append(
            SmartCall(
                module="component_nego",
                request=SmartRequest("component_nego").to_dict(),
                should_succeed=True,
                child_device_id=child_device_id,
            )
        )
        for component_id, ver_code in child_components.items():
            if (requests := get_component_requests(component_id, ver_code)) is not None:
                component_test_calls = [
                    SmartCall(
                        module=component_id,
                        request={key: val},
                        should_succeed=True,
                        child_device_id=child_device_id,
                    )
                    for key, val in requests.items()
                ]
                test_calls.extend(component_test_calls)
            else:
                click.echo(f"Skipping {component_id}..", nl=False)
                click.echo(click.style("UNSUPPORTED", fg="yellow"))
        # Add the extra calls for each child
        for extra_call in extra_test_calls:
            extra_child_call = dataclasses.replace(
                extra_call, child_device_id=child_device_id
            )
            test_calls.append(extra_child_call)

    return test_calls, successes


def get_smart_child_fixture(response):
    """Get a seperate fixture for the child device."""
    info = response["get_device_info"]
    hw_version = info["hw_ver"]
    sw_version = info["fw_ver"]
    sw_version = sw_version.split(" ", maxsplit=1)[0]
    model = info["model"]
    if region := info.get("specs"):
        model += f"({region})"

    save_filename = f"{model}_{hw_version}_{sw_version}.json"
    return FixtureResult(
        filename=save_filename, folder=SMART_CHILD_FOLDER, data=response
    )


async def get_smart_fixtures(
    protocol: SmartProtocol, *, discovery_info=None, batch_size: int
):
    """Get fixture for new TAPO style protocol."""
    if isinstance(protocol, SmartCameraProtocol):
        test_calls, successes = await get_smart_camera_test_calls(protocol)
        child_wrapper: type[_ChildProtocolWrapper | _ChildCameraProtocolWrapper] = (
            _ChildCameraProtocolWrapper
        )
    else:
        test_calls, successes = await get_smart_test_calls(protocol)
        child_wrapper = _ChildProtocolWrapper

    for test_call in test_calls:
        click.echo(f"Testing  {test_call.module}..", nl=False)
        try:
            click.echo(f"Testing {test_call}..", nl=False)
            if test_call.child_device_id == "":
                response = await protocol.query(test_call.request)
            else:
                cp = child_wrapper(test_call.child_device_id, protocol)
                response = await cp.query(test_call.request)
        except AuthenticationError as ex:
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
                    SmartErrorCode.UNSPECIFIC_ERROR,
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
            await protocol.close()

    device_requests: dict[str, list[SmartCall]] = {}
    for success in successes:
        device_request = device_requests.setdefault(success.child_device_id, [])
        device_request.append(success)

    scrubbed_device_ids = {
        device_id: f"SCRUBBED_CHILD_DEVICE_ID_{index}"
        for index, device_id in enumerate(device_requests.keys())
        if device_id != ""
    }

    final = await _make_final_calls(
        protocol, device_requests[""], "All successes", batch_size, child_device_id=""
    )
    fixture_results = []
    for child_device_id, requests in device_requests.items():
        if child_device_id == "":
            continue
        response = await _make_final_calls(
            protocol,
            requests,
            "All child successes",
            batch_size,
            child_device_id=child_device_id,
        )

        scrubbed = scrubbed_device_ids[child_device_id]
        if "get_device_info" in response and "device_id" in response["get_device_info"]:
            response["get_device_info"]["device_id"] = scrubbed
        # If the child is a different model to the parent create a seperate fixture
        if "get_device_info" in final:
            parent_model = final["get_device_info"]["model"]
        elif "getDeviceInfo" in final:
            parent_model = final["getDeviceInfo"]["device_info"]["basic_info"][
                "device_model"
            ]
        else:
            raise KasaException("Cannot determine parent device model.")
        if (
            "component_nego" in response
            and "get_device_info" in response
            and (child_model := response["get_device_info"].get("model"))
            and child_model != parent_model
        ):
            fixture_results.append(get_smart_child_fixture(response))
        else:
            cd = final.setdefault("child_devices", {})
            cd[scrubbed] = response

    # Scrub the device ids in the parent for smart protocol
    if gc := final.get("get_child_device_component_list"):
        for child in gc["child_component_list"]:
            device_id = child["device_id"]
            child["device_id"] = scrubbed_device_ids[device_id]
        for child in final["get_child_device_list"]["child_device_list"]:
            device_id = child["device_id"]
            child["device_id"] = scrubbed_device_ids[device_id]

    # Scrub the device ids in the parent for the smart camera protocol
    if gc := final.get("getChildDeviceList"):
        for child in gc["child_device_list"]:
            if device_id := child.get("device_id"):
                child["device_id"] = scrubbed_device_ids[device_id]
                continue
            if device_id := child.get("dev_id"):
                child["dev_id"] = scrubbed_device_ids[device_id]
                continue
            _LOGGER.error("Could not find a device for the child device: %s", child)

    # Need to recreate a DiscoverResult here because we don't want the aliases
    # in the fixture, we want the actual field names as returned by the device.
    if discovery_info:
        dr = DiscoveryResult(**discovery_info)  # type: ignore
        final["discovery_result"] = dr.dict(
            by_alias=False, exclude_unset=True, exclude_none=True, exclude_defaults=True
        )

    click.echo("Got %s successes" % len(successes))
    click.echo(click.style("## device info file ##", bold=True))

    if "get_device_info" in final:
        # smart protocol
        hw_version = final["get_device_info"]["hw_ver"]
        sw_version = final["get_device_info"]["fw_ver"]
        if discovery_info:
            model = discovery_info["device_model"]
        else:
            model = final["get_device_info"]["model"] + "(XX)"
        sw_version = sw_version.split(" ", maxsplit=1)[0]
        copy_folder = SMART_FOLDER
    else:
        # smart camera protocol
        basic_info = final["getDeviceInfo"]["device_info"]["basic_info"]
        hw_version = basic_info["hw_version"]
        sw_version = basic_info["sw_version"]
        model = basic_info["device_model"]
        region = basic_info.get("region")
        sw_version = sw_version.split(" ", maxsplit=1)[0]
        if region is not None:
            model = f"{model}({region})"
        copy_folder = SMARTCAMERA_FOLDER

    save_filename = f"{model}_{hw_version}_{sw_version}.json"

    fixture_results.insert(
        0, FixtureResult(filename=save_filename, folder=copy_folder, data=final)
    )
    return fixture_results


if __name__ == "__main__":
    cli()
