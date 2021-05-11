import asyncio
import glob
import json
import os
from os.path import basename
from pathlib import Path, PurePath
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


PLUGS = {"HS100", "HS103", "HS105", "HS110", "HS200", "HS210"}
STRIPS = {"HS107", "HS300", "KP303", "KP400"}
DIMMERS = {"HS220"}

DIMMABLE = {*BULBS, *DIMMERS}
WITH_EMETER = {"HS110", "HS300", *BULBS, *STRIPS}

ALL_DEVICES = BULBS.union(PLUGS).union(STRIPS).union(DIMMERS)


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
    # if ids is None:
    #    ids = ["on", "off"]
    return pytest.mark.parametrize(
        "dev", filter_model(desc, devices), indirect=True, ids=ids
    )


has_emeter = parametrize("has emeter", WITH_EMETER)
no_emeter = parametrize("no emeter", ALL_DEVICES - WITH_EMETER)


def name_for_filename(x):
    from os.path import basename

    return basename(x)


bulb = parametrize("bulbs", BULBS, ids=name_for_filename)
plug = parametrize("plugs", PLUGS, ids=name_for_filename)
strip = parametrize("strips", STRIPS, ids=name_for_filename)
dimmer = parametrize("dimmers", DIMMERS, ids=name_for_filename)
lightstrip = parametrize("lightstrips", LIGHT_STRIPS, ids=name_for_filename)

# This ensures that every single file inside fixtures/ is being placed in some category
categorized_fixtures = set(
    dimmer.args[1] + strip.args[1] + plug.args[1] + bulb.args[1] + lightstrip.args[1]
)
diff = set(SUPPORTED_DEVICES) - set(categorized_fixtures)
if diff:
    for file in diff:
        print(
            "No category for file %s, add to the corresponding set (BULBS, PLUGS, ..)"
            % file
        )
    raise Exception("Missing category for %s" % diff)


# bulb types
dimmable = parametrize("dimmable", DIMMABLE)
non_dimmable = parametrize("non-dimmable", BULBS - DIMMABLE)
variable_temp = parametrize("variable color temp", VARIABLE_TEMP)
non_variable_temp = parametrize("non-variable color temp", BULBS - VARIABLE_TEMP)
color_bulb = parametrize("color bulbs", COLOR_BULBS)
non_color_bulb = parametrize("non-color bulbs", BULBS - COLOR_BULBS)

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


def get_device_for_file(file):
    # if the wanted file is not an absolute path, prepend the fixtures directory
    p = Path(file)
    if not p.is_absolute():
        p = Path(__file__).parent / "fixtures" / file

    with open(p) as f:
        sysinfo = json.load(f)
        model = basename(file)
        p = device_for_file(model)(host="123.123.123.123")
        p.protocol = FakeTransportProtocol(sysinfo)
        asyncio.run(p.update())
        return p


@pytest.fixture(params=SUPPORTED_DEVICES)
def dev(request):
    """Device fixture.

    Provides a device (given --ip) or parametrized fixture for the supported devices.
    The initial update is called automatically before returning the device.
    """
    file = request.param

    ip = request.config.getoption("--ip")
    if ip:
        d = asyncio.run(Discover.discover_single(ip))
        asyncio.run(d.update())
        if d.model in file:
            return d
        raise Exception("Unable to find type for %s" % ip)

    return get_device_for_file(file)


def pytest_addoption(parser):
    parser.addoption("--ip", action="store", default=None, help="run against device")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--ip"):
        print("Testing against fixtures.")
        return
    else:
        print("Running against ip %s" % config.getoption("--ip"))


# allow mocks to be awaited
# https://stackoverflow.com/questions/51394411/python-object-magicmock-cant-be-used-in-await-expression/51399767#51399767


async def async_magic():
    pass


MagicMock.__await__ = lambda x: async_magic().__await__()
