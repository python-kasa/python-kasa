import asyncio
import glob
import json
import os
from dataclasses import dataclass
from json import dumps as json_dumps
from os.path import basename
from pathlib import Path, PurePath
from typing import Dict, Optional
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
from kasa.tapo import TapoPlug

from .newfakes import FakeSmartProtocol, FakeTransportProtocol

SUPPORTED_DEVICES = glob.glob(
    os.path.dirname(os.path.abspath(__file__)) + "/fixtures/*.json"
)


LIGHT_STRIPS = {"KL400", "KL430", "KL420"}
VARIABLE_TEMP = {"LB120", "LB130", "KL120", "KL125", "KL130", "KL135", "KL430"}
COLOR_BULBS = {"LB130", "KL125", "KL130", "KL135", *LIGHT_STRIPS}
BULBS = {
    "KL50",
    "KL60",
    "LB100",
    "LB110",
    "KL110",
    *VARIABLE_TEMP,
    *COLOR_BULBS,
    *LIGHT_STRIPS,
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
ALL_DEVICES_SMART = PLUGS_SMART

ALL_DEVICES = ALL_DEVICES_IOT.union(ALL_DEVICES_SMART)

IP_MODEL_CACHE: Dict[str, str] = {}


def filter_model(desc, filter, is_smart_protocol=False):
    filtered = list()
    for dev in SUPPORTED_DEVICES:
        for filt in filter:
            model_name = filt
            if is_smart_protocol:
                model_name = model_name + ".smart"
            if model_name in basename(dev).split("_")[0]:
                filtered.append(dev)

    filtered_basenames = [basename(f) for f in filtered]
    print(f"{desc}: {filtered_basenames}")
    return filtered


def parametrize(desc, devices, ids=None, is_smart_protocol=False):
    return pytest.mark.parametrize(
        "dev", filter_model(desc, devices), indirect=True, ids=ids
    )


has_emeter = parametrize("has emeter", WITH_EMETER)
no_emeter = parametrize("no emeter", ALL_DEVICES_IOT - WITH_EMETER)

bulb = parametrize("bulbs", BULBS, ids=basename)
plug = parametrize("plugs", PLUGS, ids=basename)
strip = parametrize("strips", STRIPS, ids=basename)
dimmer = parametrize("dimmers", DIMMERS, ids=basename)
lightstrip = parametrize("lightstrips", LIGHT_STRIPS, ids=basename)

# bulb types
dimmable = parametrize("dimmable", DIMMABLE)
non_dimmable = parametrize("non-dimmable", BULBS - DIMMABLE)
variable_temp = parametrize("variable color temp", VARIABLE_TEMP)
non_variable_temp = parametrize("non-variable color temp", BULBS - VARIABLE_TEMP)
color_bulb = parametrize("color bulbs", COLOR_BULBS)
non_color_bulb = parametrize("non-color bulbs", BULBS - COLOR_BULBS)

plug_smart = parametrize(
    "plug devices smart", PLUGS_SMART, ids=basename, is_smart_protocol=True
)
device_smart = parametrize(
    "devices smart", ALL_DEVICES_SMART, ids=basename, is_smart_protocol=True
)
device_iot = parametrize(
    "devices iot", ALL_DEVICES_IOT, ids=basename, is_smart_protocol=False
)


def get_fixture_data():
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_data = {}
    for file in SUPPORTED_DEVICES:
        p = Path(file)
        if not p.is_absolute():
            p = Path(__file__).parent / "fixtures" / file

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
    )
    diff = set(SUPPORTED_DEVICES) - set(categorized_fixtures)
    if diff:
        for file in diff:
            print(
                "No category for file %s, add to the corresponding set (BULBS, PLUGS, ..)"
                % file
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


def device_for_file(model):
    for d in STRIPS:
        if d in model:
            return SmartStrip

    for d in PLUGS:
        if d in model:
            return SmartPlug

    # Light strips are recognized also as bulbs, so this has to go first
    for d in LIGHT_STRIPS:
        if d in model:
            return SmartLightStrip

    for d in BULBS:
        if d in model:
            return SmartBulb

    for d in DIMMERS:
        if d in model:
            return SmartDimmer

    for d in PLUGS_SMART:
        if d + ".smart" in model:
            return TapoPlug

    raise Exception("Unable to find type for %s", model)


async def _update_and_close(d):
    await d.update()
    await d.protocol.close()
    return d


async def _discover_update_and_close(ip):
    d = await Discover.discover_single(ip, timeout=10)
    return await _update_and_close(d)


async def get_device_for_file(file):
    # if the wanted file is not an absolute path, prepend the fixtures directory
    p = Path(file)
    if not p.is_absolute():
        p = Path(__file__).parent / "fixtures" / file

    def load_file():
        with open(p) as f:
            return json.load(f)

    loop = asyncio.get_running_loop()
    sysinfo = await loop.run_in_executor(None, load_file)

    model = basename(file)
    d = device_for_file(model)(host="127.0.0.123")
    if ".smart" in model.split("_")[0]:
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
    file = request.param

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

    return await get_device_for_file(file)


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
