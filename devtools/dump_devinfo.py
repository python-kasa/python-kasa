"""This script generates devinfo files for the test suite.

If you have new, yet unsupported device or a device with no devinfo file under
 tests/fixtures, feel free to run this script and create a PR to add the file
 to the repository.

Executing this script will several modules and methods one by one,
and finally execute a query to query all of them at once.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import sys
import traceback
from collections import defaultdict, namedtuple
from collections.abc import Callable
from pathlib import Path
from pprint import pprint
from typing import Any

import asyncclick as click

from devtools.helpers.smartcamrequests import SMARTCAM_REQUESTS
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
from kasa.discover import (
    NEW_DISCOVERY_REDACTORS,
    DiscoveredRaw,
    DiscoveryResult,
)
from kasa.exceptions import SmartErrorCode
from kasa.protocols import IotProtocol
from kasa.protocols.iotprotocol import REDACTORS as IOT_REDACTORS
from kasa.protocols.protocol import redact_data
from kasa.protocols.smartcamprotocol import (
    SmartCamProtocol,
    _ChildCameraProtocolWrapper,
)
from kasa.protocols.smartprotocol import REDACTORS as SMART_REDACTORS
from kasa.protocols.smartprotocol import SmartProtocol, _ChildProtocolWrapper
from kasa.smart import SmartChildDevice, SmartDevice
from kasa.smartcam import SmartCamChild, SmartCamDevice
from kasa.smartcam.smartcamchild import CHILD_INFO_FROM_PARENT

Call = namedtuple("Call", "module method")
FixtureResult = namedtuple("FixtureResult", "filename, folder, data, protocol_suffix")

SMART_FOLDER = "tests/fixtures/smart/"
SMARTCAM_FOLDER = "tests/fixtures/smartcam/"
SMART_CHILD_FOLDER = "tests/fixtures/smart/child/"
SMARTCAM_CHILD_FOLDER = "tests/fixtures/smartcam/child/"
IOT_FOLDER = "tests/fixtures/iot/"

SMART_PROTOCOL_SUFFIX = "SMART"
SMARTCAM_SUFFIX = "SMARTCAM"
SMART_CHILD_SUFFIX = "SMART.CHILD"
SMARTCAM_CHILD_SUFFIX = "SMARTCAM.CHILD"
IOT_SUFFIX = "IOT"

NO_GIT_FIXTURE_FOLDER = "kasa-fixtures"

ENCRYPT_TYPES = [encrypt_type.value for encrypt_type in DeviceEncryptionType]

_LOGGER = logging.getLogger(__name__)


def _wrap_redactors(redactors: dict[str, Callable[[Any], Any] | None]):
    """Wrap the redactors for dump_devinfo.

    Will replace all partial REDACT_ values with zeros.
    If the data item is already scrubbed by dump_devinfo will leave as-is.
    """

    def _wrap(key: str) -> Any:
        def _wrapped(redactor: Callable[[Any], Any] | None) -> Any | None:
            if redactor is None:
                return lambda x: "**SCRUBBED**"

            def _redact_to_zeros(x: Any) -> Any:
                if isinstance(x, str) and "REDACT" in x:
                    return re.sub(r"\w", "0", x)
                if isinstance(x, dict):
                    for k, v in x.items():
                        x[k] = _redact_to_zeros(v)
                return x

            def _scrub(x: Any) -> Any:
                if key in {"ip", "local_ip"}:
                    return "127.0.0.123"
                # Already scrubbed by dump_devinfo
                if isinstance(x, str) and "SCRUBBED" in x:
                    return x
                default = redactor(x)
                return _redact_to_zeros(default)

            return _scrub

        return _wrapped(redactors[key])

    return {key: _wrap(key) for key in redactors}


@dataclasses.dataclass
class SmartCall:
    """Class for smart and smartcam calls."""

    module: str
    request: dict
    should_succeed: bool
    child_device_id: str
    supports_multiple: bool = True


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
        save_folder = Path(basedir) / fixture_result.folder
        if save_folder.exists():
            save_filename = save_folder / f"{fixture_result.filename}.json"
        else:
            # If being run without git clone
            save_folder = Path(basedir) / NO_GIT_FIXTURE_FOLDER
            save_folder.mkdir(exist_ok=True)
            save_filename = (
                save_folder
                / f"{fixture_result.filename}-{fixture_result.protocol_suffix}.json"
            )

        pprint(fixture_result.data)
        if autosave:
            save = "y"
        else:
            save = await click.prompt(
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
@click.option(
    "--timeout",
    required=False,
    default=15,
    help="Timeout for queries.",
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
    timeout,
):
    """Generate devinfo files for devices.

    Use --host (for a single device) or --target (for a complete network).
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    raw_discovery = {}

    def capture_raw(discovered: DiscoveredRaw):
        raw_discovery[discovered["meta"]["ip"]] = discovered["discovery_response"]

    credentials = Credentials(username=username, password=password)
    if host is not None:
        if discovery_info:
            click.echo(f"Host and discovery info given, trying connect on {host}.")

            di = json.loads(discovery_info)
            dr = DiscoveryResult.from_dict(di)
            connection_type = DeviceConnectionParameters.from_values(
                dr.device_type,
                dr.mgt_encrypt_schm.encrypt_type,
                login_version=dr.mgt_encrypt_schm.lv,
                https=dr.mgt_encrypt_schm.is_support_https,
                http_port=dr.mgt_encrypt_schm.http_port,
            )
            dc = DeviceConfig(
                host=host,
                connection_type=connection_type,
                port_override=port,
                credentials=credentials,
                timeout=timeout,
            )
            device = await Device.connect(config=dc)
            await handle_device(
                basedir,
                autosave,
                device.protocol,
                discovery_info=dr.to_dict(),
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
                timeout=timeout,
            )
            if protocol := get_protocol(config):
                await handle_device(basedir, autosave, protocol, batch_size=batch_size)
            else:
                raise KasaException(
                    "Could not find a protocol for the given parameters."
                )
        else:
            click.echo(f"Host given, performing discovery on {host}.")
            device = await Discover.discover_single(
                host,
                credentials=credentials,
                port=port,
                discovery_timeout=discovery_timeout,
                timeout=timeout,
                on_discovered_raw=capture_raw,
            )
            discovery_info = raw_discovery[device.host]
            if decrypted_data := device._discovery_info.get("decrypted_data"):
                discovery_info["result"]["decrypted_data"] = decrypted_data
            await handle_device(
                basedir,
                autosave,
                device.protocol,
                discovery_info=discovery_info,
                batch_size=batch_size,
            )
    else:
        click.echo(
            "No --host given, performing discovery on"
            f" {target}. Use --target to override."
        )
        devices = await Discover.discover(
            target=target,
            credentials=credentials,
            discovery_timeout=discovery_timeout,
            timeout=timeout,
            on_discovered_raw=capture_raw,
        )
        click.echo(f"Detected {len(devices)} devices")
        for dev in devices.values():
            discovery_info = raw_discovery[dev.host]
            if decrypted_data := dev._discovery_info.get("decrypted_data"):
                discovery_info["result"]["decrypted_data"] = decrypted_data

            await handle_device(
                basedir,
                autosave,
                dev.protocol,
                discovery_info=discovery_info,
                batch_size=batch_size,
            )


async def get_legacy_fixture(
    protocol: IotProtocol, *, discovery_info: dict[str, dict[str, Any]] | None
) -> FixtureResult:
    """Get fixture for legacy IOT style protocol."""
    items = [
        Call(module="system", method="get_sysinfo"),
        Call(module="emeter", method="get_realtime"),
        Call(module="cnCloud", method="get_info"),
        Call(module="cnCloud", method="get_intl_fw_list"),
        Call(module="smartlife.iot.common.cloud", method="get_info"),
        Call(module="smartlife.iot.common.cloud", method="get_intl_fw_list"),
        Call(module="smartlife.iot.common.schedule", method="get_next_action"),
        Call(module="smartlife.iot.common.schedule", method="get_rules"),
        Call(module="schedule", method="get_next_action"),
        Call(module="schedule", method="get_rules"),
        Call(module="smartlife.iot.dimmer", method="get_dimmer_parameters"),
        Call(module="smartlife.iot.dimmer", method="get_default_behavior"),
        Call(module="smartlife.iot.common.emeter", method="get_realtime"),
        Call(
            module="smartlife.iot.smartbulb.lightingservice", method="get_light_state"
        ),
        Call(
            module="smartlife.iot.smartbulb.lightingservice",
            method="get_default_behavior",
        ),
        Call(
            module="smartlife.iot.smartbulb.lightingservice", method="get_light_details"
        ),
        Call(module="smartlife.iot.lightStrip", method="get_default_behavior"),
        Call(module="smartlife.iot.lightStrip", method="get_light_state"),
        Call(module="smartlife.iot.lightStrip", method="get_light_details"),
        Call(module="smartlife.iot.LAS", method="get_config"),
        Call(module="smartlife.iot.LAS", method="get_current_brt"),
        Call(module="smartlife.iot.LAS", method="get_dark_status"),
        Call(module="smartlife.iot.LAS", method="get_adc_value"),
        Call(module="smartlife.iot.PIR", method="get_config"),
        Call(module="smartlife.iot.PIR", method="get_adc_value"),
        Call(module="smartlife.iot.homekit", method="setup_info_get"),
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

    final_query: dict = defaultdict(defaultdict)
    final: dict = defaultdict(defaultdict)
    for succ, resp in successes:
        final_query[succ.module][succ.method] = {}
        final[succ.module][succ.method] = resp

    final = default_to_regular(final)

    try:
        final = await protocol.query(final_query)
    except Exception as ex:
        _echo_error(f"Unable to query all successes at once: {ex}")
    finally:
        await protocol.close()

    final = redact_data(final, _wrap_redactors(IOT_REDACTORS))

    # Scrub the child device ids
    if children := final.get("system", {}).get("get_sysinfo", {}).get("children"):
        for index, child in enumerate(children):
            if "id" not in child:
                _LOGGER.error("Could not find a device for the child device: %s", child)
            else:
                child["id"] = f"SCRUBBED_CHILD_DEVICE_ID_{index + 1}"

    if discovery_info and not discovery_info.get("system"):
        final["discovery_result"] = redact_data(
            discovery_info, _wrap_redactors(NEW_DISCOVERY_REDACTORS)
        )

    click.echo(f"Got {len(successes)} successes")
    click.echo(click.style("## device info file ##", bold=True))

    sysinfo = final["system"]["get_sysinfo"]
    model = sysinfo["model"]
    hw_version = sysinfo["hw_ver"]
    sw_version = sysinfo["sw_ver"]
    sw_version = sw_version.split(" ", maxsplit=1)[0]
    save_filename = f"{model}_{hw_version}_{sw_version}"
    copy_folder = IOT_FOLDER
    return FixtureResult(
        filename=save_filename,
        folder=copy_folder,
        data=final,
        protocol_suffix=IOT_SUFFIX,
    )


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
        if isinstance(protocol, SmartCamProtocol):
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
    for request in SMARTCAM_REQUESTS:
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
                for request in SMARTCAM_REQUESTS:
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

    return test_calls, successes


def get_smart_child_fixture(response, model_info, folder, suffix):
    """Get a seperate fixture for the child device."""
    hw_version = model_info.hardware_version
    fw_version = model_info.firmware_version
    model = model_info.long_name
    if model_info.region is not None:
        model = f"{model}({model_info.region})"
    save_filename = f"{model}_{hw_version}_{fw_version}"
    return FixtureResult(
        filename=save_filename,
        folder=folder,
        data=response,
        protocol_suffix=suffix,
    )


def scrub_child_device_ids(
    main_response: dict, child_responses: dict
) -> dict[str, str]:
    """Scrub all the child device ids in the responses."""
    # Make the scrubbed id map
    scrubbed_child_id_map = {
        device_id: f"SCRUBBED_CHILD_DEVICE_ID_{index + 1}"
        for index, device_id in enumerate(child_responses.keys())
        if device_id != ""
    }

    for child_id, response in child_responses.items():
        scrubbed_child_id = scrubbed_child_id_map[child_id]
        # scrub the device id in the child's get info response
        # The checks for the device_id will ensure we can get a fixture
        # even if the data is unexpectedly not available although it should
        # always be there
        if "get_device_info" in response and "device_id" in response["get_device_info"]:
            response["get_device_info"]["device_id"] = scrubbed_child_id
        elif (
            basic_info := response.get("getDeviceInfo", {})
            .get("device_info", {})
            .get("basic_info")
        ) and "dev_id" in basic_info:
            basic_info["dev_id"] = scrubbed_child_id
        else:
            _LOGGER.error(
                "Cannot find device id in child get device info: %s", child_id
            )

    # Scrub the device ids in the parent for smart protocol
    if gc := main_response.get("get_child_device_component_list"):
        for child in gc["child_component_list"]:
            device_id = child["device_id"]
            child["device_id"] = scrubbed_child_id_map[device_id]
        for child in main_response["get_child_device_list"]["child_device_list"]:
            device_id = child["device_id"]
            child["device_id"] = scrubbed_child_id_map[device_id]

    # Scrub the device ids in the parent for the smart camera protocol
    if gc := main_response.get("getChildDeviceComponentList"):
        for child in gc["child_component_list"]:
            device_id = child["device_id"]
            child["device_id"] = scrubbed_child_id_map[device_id]
        for child in main_response["getChildDeviceList"]["child_device_list"]:
            if device_id := child.get("device_id"):
                child["device_id"] = scrubbed_child_id_map[device_id]
                continue
            elif dev_id := child.get("dev_id"):
                child["dev_id"] = scrubbed_child_id_map[dev_id]
                continue
            _LOGGER.error("Could not find a device id for the child device: %s", child)

    return scrubbed_child_id_map


async def get_smart_fixtures(
    protocol: SmartProtocol,
    *,
    discovery_info: dict[str, dict[str, Any]] | None,
    batch_size: int,
) -> list[FixtureResult]:
    """Get fixture for new TAPO style protocol."""
    if isinstance(protocol, SmartCamProtocol):
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

    # Put all the successes into a dict[child_device_id or "", successes[]]
    device_requests: dict[str, list[SmartCall]] = {}
    for success in successes:
        device_request = device_requests.setdefault(success.child_device_id, [])
        device_request.append(success)

    final = await _make_final_calls(
        protocol, device_requests[""], "All successes", batch_size, child_device_id=""
    )
    fixture_results = []

    # Make the final child calls
    child_responses = {}
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
        child_responses[child_device_id] = response

    # scrub the child ids
    scrubbed_child_id_map = scrub_child_device_ids(final, child_responses)

    # Redact data from the main device response. _wrap_redactors ensure we do
    # not redact the scrubbed child device ids and replaces REDACTED_partial_id
    # with zeros
    final = redact_data(final, _wrap_redactors(SMART_REDACTORS))

    # smart cam child devices provide more information in getChildDeviceList on the
    # parent than they return when queried directly for getDeviceInfo so we will store
    # it in the child fixture.
    if smart_cam_child_list := final.get("getChildDeviceList"):
        child_infos_on_parent = {
            info["device_id"]: info
            for info in smart_cam_child_list["child_device_list"]
        }

    for child_id, response in child_responses.items():
        scrubbed_child_id = scrubbed_child_id_map[child_id]

        # Get the parent model for checking whether to create a seperate child fixture
        if model := final.get("get_device_info", {}).get("model"):
            parent_model = model
        elif (
            device_model := final.get("getDeviceInfo", {})
            .get("device_info", {})
            .get("basic_info", {})
            .get("device_model")
        ):
            parent_model = device_model
        else:
            parent_model = None
            _LOGGER.error("Cannot determine parent device model.")

        # different model smart child device
        if (
            (child_model := response.get("get_device_info", {}).get("model"))
            and parent_model
            and child_model != parent_model
        ):
            response = redact_data(response, _wrap_redactors(SMART_REDACTORS))
            model_info = SmartDevice._get_device_info(response, None)
            fixture_results.append(
                get_smart_child_fixture(
                    response, model_info, SMART_CHILD_FOLDER, SMART_CHILD_SUFFIX
                )
            )
        # different model smartcam child device
        elif (
            (
                child_model := response.get("getDeviceInfo", {})
                .get("device_info", {})
                .get("basic_info", {})
                .get("device_model")
            )
            and parent_model
            and child_model != parent_model
        ):
            response = redact_data(response, _wrap_redactors(SMART_REDACTORS))
            # There is more info in the childDeviceList on the parent
            # particularly the region is needed here.
            child_info_from_parent = child_infos_on_parent[scrubbed_child_id]
            response[CHILD_INFO_FROM_PARENT] = child_info_from_parent
            model_info = SmartCamChild._get_device_info(response, None)
            fixture_results.append(
                get_smart_child_fixture(
                    response, model_info, SMARTCAM_CHILD_FOLDER, SMARTCAM_CHILD_SUFFIX
                )
            )
        # same model child device
        else:
            cd = final.setdefault("child_devices", {})
            cd[scrubbed_child_id] = response

    discovery_result = None
    if discovery_info:
        final["discovery_result"] = redact_data(
            discovery_info, _wrap_redactors(NEW_DISCOVERY_REDACTORS)
        )
        discovery_result = discovery_info["result"]

    click.echo(f"Got {len(successes)} successes")
    click.echo(click.style("## device info file ##", bold=True))

    if "get_device_info" in final:
        # smart protocol
        model_info = SmartDevice._get_device_info(final, discovery_result)
        copy_folder = SMART_FOLDER
        protocol_suffix = SMART_PROTOCOL_SUFFIX
    else:
        # smart camera protocol
        model_info = SmartCamDevice._get_device_info(final, discovery_result)
        copy_folder = SMARTCAM_FOLDER
        protocol_suffix = SMARTCAM_SUFFIX
    hw_version = model_info.hardware_version
    sw_version = model_info.firmware_version
    model = model_info.long_name
    if model_info.region is not None:
        model = f"{model}({model_info.region})"

    save_filename = f"{model}_{hw_version}_{sw_version}"

    fixture_results.insert(
        0,
        FixtureResult(
            filename=save_filename,
            folder=copy_folder,
            data=final,
            protocol_suffix=protocol_suffix,
        ),
    )
    return fixture_results


if __name__ == "__main__":
    cli()
