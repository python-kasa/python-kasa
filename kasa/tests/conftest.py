import asyncio
import glob
import json
import os
from os.path import basename

import pytest

from kasa import Discover, SmartBulb, SmartPlug, SmartStrip

from .newfakes import FakeTransportProtocol

SUPPORTED_DEVICES = glob.glob(
    os.path.dirname(os.path.abspath(__file__)) + "/fixtures/*.json"
)

BULBS = {"LB100", "LB120", "LB130", "KL120"}
VARIABLE_TEMP = {"LB120", "LB130", "KL120"}
PLUGS = {"HS100", "HS105", "HS110", "HS200", "HS210", "HS220", "HS300"}
STRIPS = {"HS107", "HS300", "KP303"}
COLOR_BULBS = {"LB130"}
DIMMABLE = {*BULBS, "HS220"}
EMETER = {"HS110", "HS300", *BULBS}

ALL_DEVICES = BULBS.union(PLUGS)


def filter_model(desc, filter):
    filtered = list()
    for dev in SUPPORTED_DEVICES:
        for filt in filter:
            if filt in basename(dev):
                filtered.append(dev)

    filtered_basenames = [basename(f) for f in filtered]
    print(f"{desc}: {filtered_basenames}")
    return filtered


has_emeter = pytest.mark.parametrize(
    "dev", filter_model("has emeter", EMETER), indirect=True
)
no_emeter = pytest.mark.parametrize(
    "dev", filter_model("no emeter", ALL_DEVICES - EMETER), indirect=True
)

bulb = pytest.mark.parametrize("dev", filter_model("bulbs", BULBS), indirect=True)
plug = pytest.mark.parametrize("dev", filter_model("plugs", PLUGS), indirect=True)
strip = pytest.mark.parametrize("dev", filter_model("strips", STRIPS), indirect=True)

dimmable = pytest.mark.parametrize(
    "dev", filter_model("dimmable", DIMMABLE), indirect=True
)
non_dimmable = pytest.mark.parametrize(
    "dev", filter_model("non-dimmable", ALL_DEVICES - DIMMABLE - STRIPS), indirect=True
)

variable_temp = pytest.mark.parametrize(
    "dev", filter_model("variable color temp", VARIABLE_TEMP), indirect=True
)
non_variable_temp = pytest.mark.parametrize(
    "dev", filter_model("non-variable color temp", BULBS - VARIABLE_TEMP), indirect=True
)

color_bulb = pytest.mark.parametrize(
    "dev", filter_model("color bulbs", COLOR_BULBS), indirect=True
)
non_color_bulb = pytest.mark.parametrize(
    "dev", filter_model("non-color bulbs", BULBS - COLOR_BULBS), indirect=True
)


# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


async def handle_turn_on(dev, turn_on):
    if turn_on:
        await dev.turn_on()
    else:
        await dev.turn_off()


@pytest.fixture(params=SUPPORTED_DEVICES)
def dev(request):
    """Device fixture.

    Provides a device (given --ip) or parametrized fixture for the supported devices.
    The initial update is called automatically before returning the device.
    """
    loop = asyncio.get_event_loop()
    file = request.param

    ip = request.config.getoption("--ip")
    if ip:
        d = loop.run_until_complete(Discover.discover_single(ip))
        loop.run_until_complete(d.update())
        print(d.model)
        if d.model in file:
            return d
        return

    def device_for_file(model):
        for d in STRIPS:
            if d in model:
                return SmartStrip
        for d in PLUGS:
            if d in model:
                return SmartPlug
        for d in BULBS:
            if d in model:
                return SmartBulb

        raise Exception("Unable to find type for %s", model)

    with open(file) as f:
        sysinfo = json.load(f)
        model = basename(file)
        params = {"host": "123.123.123.123", "cache_ttl": 0}
        p = device_for_file(model)(**params)
        p.protocol = FakeTransportProtocol(sysinfo)
        loop.run_until_complete(p.update())
        yield p


def pytest_addoption(parser):
    parser.addoption("--ip", action="store", default=None, help="run against device")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--ip"):
        print("Testing against fixtures.")
        return
    else:
        print("Running against ip %s" % config.getoption("--ip"))
