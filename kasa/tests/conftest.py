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
BULBS_SMART_VARIABLE_TEMP = {"L530"}
BULBS_SMART_COLOR = {"L530"}
BULBS_SMART_LIGHT_STRIP: Set[str] = set()
BULBS_SMART_DIMMABLE: Set[str] = set()
BULBS_SMART = (
    BULBS_SMART_VARIABLE_TEMP.union(BULBS_SMART_COLOR)
    .union(BULBS_SMART_DIMMABLE)
    .union(BULBS_SMART_LIGHT_STRIP)
)

# Kasa (IOT-prefixed) bulbs
BULBS_IOT_LIGHT_STRIP = {"KL400", "KL430", "KL420"}
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
BULBS_LIGHT_STRIP = {*BULBS_SMART_LIGHT_STRIP, *BULBS_IOT_LIGHT_STRIP}

BULBS = {
    *BULBS_IOT,
    *BULBS_SMART,
}


PLUGS = {
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

STRIPS = {"HS107", "HS300", "KP303", "KP200", "KP400", "EP40"}
DIMMERS = {"ES20M", "HS220", "KS220M", "KS230", "KP405"}

DIMMABLE = {*BULBS, *DIMMERS}
WITH_EMETER = {"HS110", "HS300", "KP115", "KP125", *BULBS}

ALL_DEVICES_IOT = BULBS.union(PLUGS).union(STRIPS).union(DIMMERS)

PLUGS_SMART = {"P110"}
ALL_DEVICES_SMART = BULBS_SMART.union(PLUGS_SMART)

ALL_DEVICES = ALL_DEVICES_IOT.union(ALL_DEVICES_SMART)

IP_MODEL_CACHE: Dict[str, str] = {}


def idgenerator(paramtuple):
    try:
        return basename(paramtuple[0]) + (
            "" if paramtuple[1] == "IOT" else "-" + paramtuple[1]
        )
    except:  # TODO: HACK as idgenerator is now used by default  # noqa: E722
        return None


def filter_model(desc, model_filter, protocol_filter=None):
    if not protocol_filter:
        protocol_filter = {"IOT"}
    filtered = list()
    for file, protocol in SUPPORTED_DEVICES:
        if protocol in protocol_filter:
            file_model = basename(file).split("_")[0]
            for model in model_filter:
                if model in file_model:
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


has_emeter = parametrize("has emeter", WITH_EMETER)
no_emeter = parametrize("no emeter", ALL_DEVICES_IOT - WITH_EMETER)

bulb = parametrize("bulbs", BULBS, protocol_filter={"SMART", "IOT"})
plug = parametrize("plugs", PLUGS)
strip = parametrize("strips", STRIPS)
dimmer = parametrize("dimmers", DIMMERS)
lightstrip = parametrize("lightstrips", BULBS_LIGHT_STRIP)

# bulb types
dimmable = parametrize("dimmable", DIMMABLE)
non_dimmable = parametrize("non-dimmable", BULBS - DIMMABLE)
variable_temp = parametrize(
    "variable color temp", BULBS_VARIABLE_TEMP, {"SMART", "IOT"}
)
non_variable_temp = parametrize(
    "non-variable color temp", BULBS - BULBS_VARIABLE_TEMP, {"SMART", "IOT"}
)
color_bulb = parametrize("color bulbs", BULBS_COLOR, {"SMART", "IOT"})
non_color_bulb = parametrize("non-color bulbs", BULBS - BULBS_COLOR, {"SMART", "IOT"})

color_bulb_iot = parametrize("color bulbs iot", BULBS_COLOR, {"IOT"})
variable_temp_iot = parametrize("variable color temp iot", BULBS_VARIABLE_TEMP, {"IOT"})
bulb_iot = parametrize("bulb devices iot", BULBS_IOT)

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

    print(f"{desc}: {filtered.keys()}")
    return filtered


def parametrize_discovery(desc, root_key):
    filtered_fixtures = filter_fixtures(desc, root_key)
    return pytest.mark.parametrize(
        "discovery_data",
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
        for d in STRIPS:
            if d in model:
                return SmartStrip

        for d in PLUGS:
            if d in model:
                return SmartPlug

        # Light strips are recognized also as bulbs, so this has to go first
        for d in BULBS_IOT_LIGHT_STRIP:
            if d in model:
                return SmartLightStrip

        for d in BULBS:
            if d in model:
                return SmartBulb

        for d in DIMMERS:
            if d in model:
                return SmartDimmer

    raise Exception("Unable to find type for %s", model)


async def _update_and_close(d):
    await d.update()
    await d.protocol.close()
    return d


async def _discover_update_and_close(ip):
    d = await Discover.discover_single(ip, timeout=10)
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
        d.credentials = Credentials("", "")
    else:
        d.protocol = FakeTransportProtocol(sysinfo)
    await _update_and_close(d)
    return d


@pytest.fixture(params=SUPPORTED_DEVICES)
async def dev(request):
    """Device fixture.

    Provides a device (given --ip) or parametrized fixture for the supported devices.
    The initial update is called automatically before returning the device.
    """
    file, protocol = request.param

    ip = request.config.getoption("--ip")
    if ip:
        model = IP_MODEL_CACHE.get(ip)
        d = None
        if not model:
            d = await _discover_update_and_close(ip)
            IP_MODEL_CACHE[ip] = model = d.model
        if model not in file:
            pytest.skip(f"skipping file {file}")
        return d if d else await _discover_update_and_close(ip)

    return await get_device_for_file(file, protocol)


@pytest.fixture
def discovery_mock(discovery_data, mocker):
    @dataclass
    class _DiscoveryMock:
        ip: str
        default_port: int
        discovery_data: dict
        port_override: Optional[int] = None

    if "result" in discovery_data:
        datagram = (
            b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
            + json_dumps(discovery_data).encode()
        )
        dm = _DiscoveryMock("127.0.0.123", 20002, discovery_data)
    else:
        datagram = TPLinkSmartHomeProtocol.encrypt(json_dumps(discovery_data))[4:]
        dm = _DiscoveryMock("127.0.0.123", 9999, discovery_data)

    def mock_discover(self):
        port = (
            dm.port_override
            if dm.port_override and dm.default_port != 20002
            else dm.default_port
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
    yield dm


@pytest.fixture(params=FIXTURE_DATA.values(), ids=FIXTURE_DATA.keys(), scope="session")
def discovery_data(request):
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_data = request.param
    if "discovery_result" in fixture_data:
        return {"result": fixture_data["discovery_result"]}
    else:
        return {"system": {"get_sysinfo": fixture_data["system"]["get_sysinfo"]}}


@pytest.fixture(params=FIXTURE_DATA.values(), ids=FIXTURE_DATA.keys(), scope="session")
def all_fixture_data(request):
    """Return raw fixture file contents as JSON. Used for discovery tests."""
    fixture_data = request.param
    return fixture_data


def pytest_addoption(parser):
    parser.addoption(
        "--ip", action="store", default=None, help="run against device on given ip"
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
