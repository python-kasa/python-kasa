import asyncio
import glob
import json
import os
from os.path import basename
from pathlib import Path, PurePath
from typing import Dict
from unittest.mock import MagicMock

import pytest  # type: ignore # see https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    Discover,
    SmartBulb,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
    SmartStrip,
)

from .newfakes import FakeTransportProtocol

SUPPORTED_DEVICES = glob.glob(
    os.path.dirname(os.path.abspath(__file__)) + "/fixtures/*.json"
)


LIGHT_STRIPS = {"KL430"}
VARIABLE_TEMP = {"LB120", "LB130", "KL120", "KL125", "KL130", "KL430", *LIGHT_STRIPS}
COLOR_BULBS = {"LB130", "KL125", "KL130", *LIGHT_STRIPS}
BULBS = {"KL60", "LB100", *VARIABLE_TEMP, *COLOR_BULBS, *LIGHT_STRIPS}


PLUGS = {"HS100", "HS103", "HS105", "HS110", "HS200", "HS210", "EP10", "KP115"}
STRIPS = {"HS107", "HS300", "KP303", "KP400"}
DIMMERS = {"HS220"}

DIMMABLE = {*BULBS, *DIMMERS}
WITH_EMETER = {"HS110", "HS300", "KP115", *BULBS}

ALL_DEVICES = BULBS.union(PLUGS).union(STRIPS).union(DIMMERS)

IP_MODEL_CACHE: Dict[str, str] = {}


def filter_model(desc, filter):
    filtered = list()
    for dev in SUPPORTED_DEVICES:
        for filt in filter:
            if filt in basename(dev):
                filtered.append(dev)

    filtered_basenames = [basename(f) for f in filtered]
    print(f"{desc}: {filtered_basenames}")
    return filtered


def parametrize(desc, devices, ids=None):
    return pytest.mark.parametrize(
        "dev", filter_model(desc, devices), indirect=True, ids=ids
    )


has_emeter = parametrize("has emeter", WITH_EMETER)
no_emeter = parametrize("no emeter", ALL_DEVICES - WITH_EMETER)

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


def check_categories():
    """Check that every fixture file is categorized."""
    categorized_fixtures = set(
        dimmer.args[1]
        + strip.args[1]
        + plug.args[1]
        + bulb.args[1]
        + lightstrip.args[1]
    )
    diff = set(SUPPORTED_DEVICES) - set(categorized_fixtures)
    if diff:
        for file in diff:
            print(
                "No category for file %s, add to the corresponding set (BULBS, PLUGS, ..)"
                % file
            )
        raise Exception("Missing category for %s" % diff)


check_categories()

# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


async def handle_turn_on(dev, turn_on):
    if turn_on:
        await dev.turn_on()
    else:
        await dev.turn_off()


# to avoid adding this for each async function separately
pytestmark = pytest.mark.asyncio


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

    raise Exception("Unable to find type for %s", model)


async def _update_and_close(d):
    await d.update()
    await d.protocol.close()
    return d


async def _discover_update_and_close(ip):
    d = await Discover.discover_single(ip)
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


@pytest.fixture(params=SUPPORTED_DEVICES, scope="session")
def discovery_data(request):
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    file = request.param
    p = Path(file)
    if not p.is_absolute():
        p = Path(__file__).parent / "fixtures" / file

    with open(p) as f:
        return json.load(f)


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
