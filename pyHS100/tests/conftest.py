import pytest
import glob
import json
import os
from .newfakes import FakeTransportProtocol
from os.path import basename
from pyHS100 import SmartPlug, SmartBulb, SmartStrip, Discover

SUPPORTED_DEVICES = glob.glob(
    os.path.dirname(os.path.abspath(__file__)) + "/fixtures/*.json"
)

BULBS = {"LB100", "LB120", "LB130", "KL120"}
VARIABLE_TEMP = {"LB120", "LB130", "KL120"}
PLUGS = {"HS100", "HS105", "HS110", "HS200", "HS220", "HS300"}
STRIPS = {"HS300"}
COLOR_BULBS = {"LB130"}
DIMMABLE = {*BULBS, "HS220"}
EMETER = {"HS110", "HS300", *BULBS}

ALL_DEVICES = BULBS.union(PLUGS)


def filter_model(filter):
    print(filter)
    filtered = list()
    for dev in SUPPORTED_DEVICES:
        for filt in filter:
            if filt in basename(dev):
                filtered.append(dev)

    return filtered


has_emeter = pytest.mark.parametrize("dev", filter_model(EMETER), indirect=True)
no_emeter = pytest.mark.parametrize(
    "dev", filter_model(ALL_DEVICES - EMETER), indirect=True
)

bulb = pytest.mark.parametrize("dev", filter_model(BULBS), indirect=True)
plug = pytest.mark.parametrize("dev", filter_model(PLUGS), indirect=True)
strip = pytest.mark.parametrize("dev", filter_model(STRIPS), indirect=True)

dimmable = pytest.mark.parametrize("dev", filter_model(DIMMABLE), indirect=True)
non_dimmable = pytest.mark.parametrize(
    "dev", filter_model(ALL_DEVICES - DIMMABLE), indirect=True
)

variable_temp = pytest.mark.parametrize(
    "dev", filter_model(VARIABLE_TEMP), indirect=True
)
non_variable_temp = pytest.mark.parametrize(
    "dev", filter_model(BULBS - VARIABLE_TEMP), indirect=True
)

color_bulb = pytest.mark.parametrize("dev", filter_model(COLOR_BULBS), indirect=True)
non_color_bulb = pytest.mark.parametrize(
    "dev", filter_model(BULBS - COLOR_BULBS), indirect=True
)


# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


def handle_turn_on(dev, turn_on):
    if turn_on:
        dev.turn_on()
    else:
        dev.turn_off()


@pytest.fixture(params=SUPPORTED_DEVICES)
def dev(request):
    file = request.param

    ip = request.config.getoption("--ip")
    if ip:
        d = Discover.discover_single(ip)
        print(d.model)
        if d.model in file:
            return d
        return

    with open(file) as f:
        sysinfo = json.load(f)
        model = basename(file)
        params = {
            "host": "123.123.123.123",
            "protocol": FakeTransportProtocol(sysinfo),
            "cache_ttl": 0,
        }
        if "LB" in model or "KL" in model:
            p = SmartBulb(**params)
        elif "HS300" in model:
            p = SmartStrip(**params)
        elif "HS" in model:
            p = SmartPlug(**params)
        else:
            raise Exception("No tests for %s" % model)
        yield p


def pytest_addoption(parser):
    parser.addoption("--ip", action="store", default=None, help="run against device")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--ip"):
        print("Testing against fixtures.")
        return
    else:
        print("Running against ip %s" % config.getoption("--ip"))
