import asyncio
import glob
import json
import os
from dataclasses import dataclass
from json import dumps as json_dumps
from os.path import basename
from pathlib import Path, PurePath
from typing import Dict, Optional, Set
from unittest.mock import MagicMock

import pytest  # type: ignore # see https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    Credentials,
    Discover,
    SmartBulb,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
    SmartStrip,
    TPLinkSmartHomeProtocol,
)
from kasa.tapo import TapoBulb, TapoDevice, TapoPlug

from .newfakes import FakeSmartProtocol, FakeTransportProtocol

SUPPORTED_IOT_DEVICES = [
    (device, "IOT")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/*.json"
    )
]

SUPPORTED_SMART_DEVICES = [
    (device, "SMART")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/smart/*.json"
    )
]


SUPPORTED_DEVICES = SUPPORTED_IOT_DEVICES + SUPPORTED_SMART_DEVICES

# Tapo bulbs
BULBS_SMART_VARIABLE_TEMP = {"L530E"}
BULBS_SMART_COLOR = {"L530E"}
BULBS_SMART_LIGHT_STRIP: Set[str] = set()
BULBS_SMART_DIMMABLE = {"KS225"}
BULBS_SMART = (
    BULBS_SMART_VARIABLE_TEMP.union(BULBS_SMART_COLOR)
    .union(BULBS_SMART_DIMMABLE)
    .union(BULBS_SMART_LIGHT_STRIP)
)

# Kasa (IOT-prefixed) bulbs
BULBS_IOT_LIGHT_STRIP = {"KL400L5", "KL430", "KL420L5"}
BULBS_IOT_VARIABLE_TEMP = {
    "LB120",
    "LB130",
    "KL120",
    "KL125",
    "KL130",
    "KL135",
    "KL430",
}
BULBS_IOT_COLOR = {"LB130", "KL125", "KL130", "KL135", *BULBS_IOT_LIGHT_STRIP}
BULBS_IOT_DIMMABLE = {"KL50", "KL60", "LB100", "LB110", "KL110"}
BULBS_IOT = (
    BULBS_IOT_VARIABLE_TEMP.union(BULBS_IOT_COLOR)
    .union(BULBS_IOT_DIMMABLE)
    .union(BULBS_IOT_LIGHT_STRIP)
)

BULBS_VARIABLE_TEMP = {*BULBS_SMART_VARIABLE_TEMP, *BULBS_IOT_VARIABLE_TEMP}
BULBS_COLOR = {*BULBS_SMART_COLOR, *BULBS_IOT_COLOR}


LIGHT_STRIPS = {*BULBS_SMART_LIGHT_STRIP, *BULBS_IOT_LIGHT_STRIP}
BULBS = {
    *BULBS_IOT,
    *BULBS_SMART,
}


PLUGS_IOT = {
    "HS100",
    "HS103",
    "HS105",
    "HS110",
    "HS200",
    "HS210",
    "EP10",
    "KP100",
    "KP105",
    "KP115",
    "KP125",
    "KP401",
    "KS200M",
}
PLUGS_SMART = {"P110", "KP125M", "EP25", "KS205"}
PLUGS = {
    *PLUGS_IOT,
    *PLUGS_SMART,
}
STRIPS_IOT = {"HS107", "HS300", "KP303", "KP200", "KP400", "EP40"}
STRIPS_SMART = {}  # type: ignore[var-annotated]
STRIPS = {*STRIPS_IOT, *STRIPS_SMART}

DIMMERS_IOT = {"ES20M", "HS220", "KS220M", "KS230", "KP405"}
DIMMERS_SMART = {}  # type: ignore[var-annotated]
DIMMERS = {
    *DIMMERS_IOT,
    *DIMMERS_SMART,
}

WITH_EMETER_IOT = {"HS110", "HS300", "KP115", "KP125", *BULBS_IOT}
WITH_EMETER_SMART = {"P110", "KP125M", "EP25"}
WITH_EMETER = {*WITH_EMETER_IOT, *WITH_EMETER_SMART}

DIMMABLE = {*BULBS, *DIMMERS}

ALL_DEVICES_IOT = BULBS_IOT.union(PLUGS_IOT).union(STRIPS_IOT).union(DIMMERS_IOT)
ALL_DEVICES_SMART = (
    BULBS_SMART.union(PLUGS_SMART).union(STRIPS_SMART).union(DIMMERS_SMART)
)
ALL_DEVICES = ALL_DEVICES_IOT.union(ALL_DEVICES_SMART)

IP_MODEL_CACHE: Dict[str, str] = {}


def _make_unsupported(device_family, encrypt_type):
    return {
        "result": {
            "device_id": "xx",
            "owner": "xx",
            "device_type": device_family,
            "device_model": "P110(EU)",
            "ip": "127.0.0.1",
            "mac": "48-22xxx",
            "is_support_iot_cloud": True,
            "obd_src": "tplink",
            "factory_default": False,
            "mgt_encrypt_schm": {
                "is_support_https": False,
                "encrypt_type": encrypt_type,
                "http_port": 80,
                "lv": 2,
            },
        },
        "error_code": 0,
    }


UNSUPPORTED_DEVICES = {
    "unknown_device_family": _make_unsupported("SMART.TAPOXMASTREE", "AES"),
    "wrong_encryption_iot": _make_unsupported("IOT.SMARTPLUGSWITCH", "AES"),
    "wrong_encryption_smart": _make_unsupported("SMART.TAPOBULB", "IOT"),
    "unknown_encryption": _make_unsupported("IOT.SMARTPLUGSWITCH", "FOO"),
}


def idgenerator(paramtuple):
    try:
        return basename(paramtuple[0]) + (
            "" if paramtuple[1] == "IOT" else "-" + paramtuple[1]
        )
    except:  # TODO: HACK as idgenerator is now used by default  # noqa: E722
        return None


def filter_model(desc, model_filter, protocol_filter=None):
    if protocol_filter is None:
        protocol_filter = {"IOT", "SMART"}
    filtered = list()
    for file, protocol in SUPPORTED_DEVICES:
        if protocol in protocol_filter:
            file_model_region = basename(file).split("_")[0]
            file_model = file_model_region.split("(")[0]
            for model in model_filter:
                if model == file_model:
                    filtered.append((file, protocol))

    filtered_basenames = [basename(f) + "-" + p for f, p in filtered]
    print(f"# {desc}")
    for file in filtered_basenames:
        print(f"\t{file}")
    return filtered


def parametrize(desc, devices, protocol_filter=None, ids=None):
    if ids is None:
        ids = idgenerator
    return pytest.mark.parametrize(
        "dev", filter_model(desc, devices, protocol_filter), indirect=True, ids=ids
    )


has_emeter = parametrize("has emeter", WITH_EMETER, protocol_filter={"SMART", "IOT"})
no_emeter = parametrize(
    "no emeter", ALL_DEVICES - WITH_EMETER, protocol_filter={"SMART", "IOT"}
)
has_emeter_iot = parametrize("has emeter iot", WITH_EMETER_IOT, protocol_filter={"IOT"})
no_emeter_iot = parametrize(
    "no emeter iot", ALL_DEVICES_IOT - WITH_EMETER_IOT, protocol_filter={"IOT"}
)

bulb = parametrize("bulbs", BULBS, protocol_filter={"SMART", "IOT"})
plug = parametrize("plugs", PLUGS, protocol_filter={"IOT"})
strip = parametrize("strips", STRIPS, protocol_filter={"IOT"})
dimmer = parametrize("dimmers", DIMMERS, protocol_filter={"IOT"})
lightstrip = parametrize("lightstrips", LIGHT_STRIPS, protocol_filter={"IOT"})

# bulb types
dimmable = parametrize("dimmable", DIMMABLE, protocol_filter={"IOT"})
non_dimmable = parametrize("non-dimmable", BULBS - DIMMABLE, protocol_filter={"IOT"})
variable_temp = parametrize(
    "variable color temp", BULBS_VARIABLE_TEMP, protocol_filter={"SMART", "IOT"}
)
non_variable_temp = parametrize(
    "non-variable color temp",
    BULBS - BULBS_VARIABLE_TEMP,
    protocol_filter={"SMART", "IOT"},
)
color_bulb = parametrize("color bulbs", BULBS_COLOR, protocol_filter={"SMART", "IOT"})
non_color_bulb = parametrize(
    "non-color bulbs", BULBS - BULBS_COLOR, protocol_filter={"SMART", "IOT"}
)

color_bulb_iot = parametrize(
    "color bulbs iot", BULBS_IOT_COLOR, protocol_filter={"IOT"}
)
variable_temp_iot = parametrize(
    "variable color temp iot", BULBS_IOT_VARIABLE_TEMP, protocol_filter={"IOT"}
)
bulb_iot = parametrize("bulb devices iot", BULBS_IOT, protocol_filter={"IOT"})

plug_smart = parametrize("plug devices smart", PLUGS_SMART, protocol_filter={"SMART"})
bulb_smart = parametrize("bulb devices smart", BULBS_SMART, protocol_filter={"SMART"})
device_smart = parametrize(
    "devices smart", ALL_DEVICES_SMART, protocol_filter={"SMART"}
)
device_iot = parametrize("devices iot", ALL_DEVICES_IOT, protocol_filter={"IOT"})


def get_fixture_data():
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_data = {}
    for file, protocol in SUPPORTED_DEVICES:
        p = Path(file)
        if not p.is_absolute():
            folder = Path(__file__).parent / "fixtures"
            if protocol == "SMART":
                folder = folder / "smart"
            p = folder / file

        with open(p) as f:
            fixture_data[basename(p)] = json.load(f)
    return fixture_data


FIXTURE_DATA = get_fixture_data()


def filter_fixtures(desc, root_filter):
    filtered = {}
    for key, val in FIXTURE_DATA.items():
        if root_filter in val:
            filtered[key] = val

    print(f"# {desc}")
    for key in filtered:
        print(f"\t{key}")
    return filtered


def parametrize_discovery(desc, root_key):
    filtered_fixtures = filter_fixtures(desc, root_key)
    return pytest.mark.parametrize(
        "all_fixture_data",
        filtered_fixtures.values(),
        indirect=True,
        ids=filtered_fixtures.keys(),
    )


new_discovery = parametrize_discovery("new discovery", "discovery_result")


def check_categories():
    """Check that every fixture file is categorized."""
    categorized_fixtures = set(
        dimmer.args[1]
        + strip.args[1]
        + plug.args[1]
        + bulb.args[1]
        + lightstrip.args[1]
        + plug_smart.args[1]
        + bulb_smart.args[1]
    )
    diff = set(SUPPORTED_DEVICES) - set(categorized_fixtures)
    if diff:
        for file, protocol in diff:
            print(
                f"No category for file {file} protocol {protocol}, add to the corresponding set (BULBS, PLUGS, ..)"
            )
        raise Exception(f"Missing category for {diff}")


check_categories()

# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


async def handle_turn_on(dev, turn_on):
    if turn_on:
        await dev.turn_on()
    else:
        await dev.turn_off()


def device_for_file(model, protocol):
    if protocol == "SMART":
        for d in PLUGS_SMART:
            if d in model:
                return TapoPlug
        for d in BULBS_SMART:
            if d in model:
                return TapoBulb
    else:
        for d in STRIPS_IOT:
            if d in model:
                return SmartStrip

        for d in PLUGS_IOT:
            if d in model:
                return SmartPlug

        # Light strips are recognized also as bulbs, so this has to go first
        for d in BULBS_IOT_LIGHT_STRIP:
            if d in model:
                return SmartLightStrip

        for d in BULBS_IOT:
            if d in model:
                return SmartBulb

        for d in DIMMERS_IOT:
            if d in model:
                return SmartDimmer

    raise Exception("Unable to find type for %s", model)


async def _update_and_close(d):
    await d.update()
    await d.protocol.close()
    return d


async def _discover_update_and_close(ip, username, password):
    if username and password:
        credentials = Credentials(username=username, password=password)
    else:
        credentials = None
    d = await Discover.discover_single(ip, timeout=10, credentials=credentials)
    return await _update_and_close(d)


async def get_device_for_file(file, protocol):
    # if the wanted file is not an absolute path, prepend the fixtures directory
    p = Path(file)
    if not p.is_absolute():
        folder = Path(__file__).parent / "fixtures"
        if protocol == "SMART":
            folder = folder / "smart"
        p = folder / file

    def load_file():
        with open(p) as f:
            return json.load(f)

    loop = asyncio.get_running_loop()
    sysinfo = await loop.run_in_executor(None, load_file)

    model = basename(file)
    d = device_for_file(model, protocol)(host="127.0.0.123")
    if protocol == "SMART":
        d.protocol = FakeSmartProtocol(sysinfo)
    else:
        d.protocol = FakeTransportProtocol(sysinfo)
    await _update_and_close(d)
    return d


@pytest.fixture(params=SUPPORTED_DEVICES, ids=idgenerator)
async def dev(request):
    """Device fixture.

    Provides a device (given --ip) or parametrized fixture for the supported devices.
    The initial update is called automatically before returning the device.
    """
    file, protocol = request.param

    ip = request.config.getoption("--ip")
    username = request.config.getoption("--username")
    password = request.config.getoption("--password")
    if ip:
        model = IP_MODEL_CACHE.get(ip)
        d = None
        if not model:
            d = await _discover_update_and_close(ip, username, password)
            IP_MODEL_CACHE[ip] = model = d.model
        if model not in file:
            pytest.skip(f"skipping file {file}")
        return d if d else await _discover_update_and_close(ip, username, password)

    return await get_device_for_file(file, protocol)


@pytest.fixture
def discovery_mock(all_fixture_data, mocker):
    @dataclass
    class _DiscoveryMock:
        ip: str
        default_port: int
        discovery_port: int
        discovery_data: dict
        query_data: dict
        device_type: str
        encrypt_type: str
        port_override: Optional[int] = None

    if "discovery_result" in all_fixture_data:
        discovery_data = {"result": all_fixture_data["discovery_result"]}
        device_type = all_fixture_data["discovery_result"]["device_type"]
        encrypt_type = all_fixture_data["discovery_result"]["mgt_encrypt_schm"][
            "encrypt_type"
        ]
        datagram = (
            b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
            + json_dumps(discovery_data).encode()
        )
        dm = _DiscoveryMock(
            "127.0.0.123",
            80,
            20002,
            discovery_data,
            all_fixture_data,
            device_type,
            encrypt_type,
        )
    else:
        sys_info = all_fixture_data["system"]["get_sysinfo"]
        discovery_data = {"system": {"get_sysinfo": sys_info}}
        device_type = sys_info.get("mic_type") or sys_info.get("type")
        encrypt_type = "XOR"
        datagram = TPLinkSmartHomeProtocol.encrypt(json_dumps(discovery_data))[4:]
        dm = _DiscoveryMock(
            "127.0.0.123",
            9999,
            9999,
            discovery_data,
            all_fixture_data,
            device_type,
            encrypt_type,
        )

    def mock_discover(self):
        port = (
            dm.port_override
            if dm.port_override and dm.discovery_port != 20002
            else dm.discovery_port
        )
        self.datagram_received(
            datagram,
            (dm.ip, port),
        )

    mocker.patch("kasa.discover._DiscoverProtocol.do_discover", mock_discover)
    mocker.patch(
        "socket.getaddrinfo",
        side_effect=lambda *_, **__: [(None, None, None, None, (dm.ip, 0))],
    )

    if "component_nego" in dm.query_data:
        proto = FakeSmartProtocol(dm.query_data)
    else:
        proto = FakeTransportProtocol(dm.query_data)

    async def _query(request, retry_count: int = 3):
        return await proto.query(request)

    mocker.patch("kasa.IotProtocol.query", side_effect=_query)
    mocker.patch("kasa.SmartProtocol.query", side_effect=_query)
    mocker.patch("kasa.TPLinkSmartHomeProtocol.query", side_effect=_query)

    yield dm


@pytest.fixture
def discovery_data(all_fixture_data):
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    if "discovery_result" in all_fixture_data:
        return {"result": all_fixture_data["discovery_result"]}
    else:
        return {"system": {"get_sysinfo": all_fixture_data["system"]["get_sysinfo"]}}


@pytest.fixture(params=FIXTURE_DATA.values(), ids=FIXTURE_DATA.keys(), scope="session")
def all_fixture_data(request):
    """Return raw fixture file contents as JSON. Used for discovery tests."""
    fixture_data = request.param
    return fixture_data


@pytest.fixture(params=UNSUPPORTED_DEVICES.values(), ids=UNSUPPORTED_DEVICES.keys())
def unsupported_device_info(request, mocker):
    """Return unsupported devices for cli and discovery tests."""
    discovery_data = request.param
    host = "127.0.0.1"

    def mock_discover(self):
        if discovery_data:
            data = (
                b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
                + json_dumps(discovery_data).encode()
            )
            self.datagram_received(data, (host, 20002))

    mocker.patch("kasa.discover._DiscoverProtocol.do_discover", mock_discover)

    yield discovery_data


def pytest_addoption(parser):
    parser.addoption(
        "--ip", action="store", default=None, help="run against device on given ip"
    )
    parser.addoption(
        "--username", action="store", default=None, help="authentication username"
    )
    parser.addoption(
        "--password", action="store", default=None, help="authentication password"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--ip"):
        print("Testing against fixtures.")
    else:
        print("Running against ip %s" % config.getoption("--ip"))
        requires_dummy = pytest.mark.skip(
            reason="test requires to be run against dummy data"
        )
        for item in items:
            if "requires_dummy" in item.keywords:
                item.add_marker(requires_dummy)


# allow mocks to be awaited
# https://stackoverflow.com/questions/51394411/python-object-magicmock-cant-be-used-in-await-expression/51399767#51399767


async def async_magic():
    pass


MagicMock.__await__ = lambda x: async_magic().__await__()
