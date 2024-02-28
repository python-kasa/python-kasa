from typing import Dict, Set

import pytest

from kasa import (
    Credentials,
    Device,
    Discover,
)
from kasa.iot import IotBulb, IotDimmer, IotLightStrip, IotPlug, IotStrip, IotSwitch
from kasa.smart import SmartBulb, SmartDevice

from .fakeprotocol_iot import FakeIotProtocol
from .fakeprotocol_smart import FakeSmartProtocol
from .fixtureinfo import FIXTURE_DATA, FixtureInfo, filter_fixtures, idgenerator

# Tapo bulbs
BULBS_SMART_VARIABLE_TEMP = {"L530E", "L930-5"}
BULBS_SMART_LIGHT_STRIP = {"L900-5", "L900-10", "L920-5", "L930-5"}
BULBS_SMART_COLOR = {"L530E", *BULBS_SMART_LIGHT_STRIP}
BULBS_SMART_DIMMABLE = {"L510B", "L510E"}
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
    "EP10",
    "KP100",
    "KP105",
    "KP115",
    "KP125",
    "KP401",
}
# P135 supports dimming, but its not currently support
# by the library
PLUGS_SMART = {
    "P100",
    "P110",
    "KP125M",
    "EP25",
    "P125M",
    "TP15",
}
PLUGS = {
    *PLUGS_IOT,
    *PLUGS_SMART,
}
SWITCHES_IOT = {
    "HS200",
    "HS210",
    "KS200M",
}
SWITCHES_SMART = {
    "KS205",
    "KS225",
    "S500D",
    "S505",
}
SWITCHES = {*SWITCHES_IOT, *SWITCHES_SMART}
STRIPS_IOT = {"HS107", "HS300", "KP303", "KP200", "KP400", "EP40"}
STRIPS_SMART = {"P300", "TP25"}
STRIPS = {*STRIPS_IOT, *STRIPS_SMART}

DIMMERS_IOT = {"ES20M", "HS220", "KS220M", "KS230", "KP405"}
DIMMERS_SMART = {"KS225", "S500D", "P135"}
DIMMERS = {
    *DIMMERS_IOT,
    *DIMMERS_SMART,
}

HUBS_SMART = {"H100"}

WITH_EMETER_IOT = {"HS110", "HS300", "KP115", "KP125", *BULBS_IOT}
WITH_EMETER_SMART = {"P110", "KP125M", "EP25"}
WITH_EMETER = {*WITH_EMETER_IOT, *WITH_EMETER_SMART}

DIMMABLE = {*BULBS, *DIMMERS}

ALL_DEVICES_IOT = (
    BULBS_IOT.union(PLUGS_IOT).union(STRIPS_IOT).union(DIMMERS_IOT).union(SWITCHES_IOT)
)
ALL_DEVICES_SMART = (
    BULBS_SMART.union(PLUGS_SMART)
    .union(STRIPS_SMART)
    .union(DIMMERS_SMART)
    .union(HUBS_SMART)
    .union(SWITCHES_SMART)
)
ALL_DEVICES = ALL_DEVICES_IOT.union(ALL_DEVICES_SMART)

IP_MODEL_CACHE: Dict[str, str] = {}


def parametrize(
    desc,
    *,
    model_filter=None,
    protocol_filter=None,
    component_filter=None,
    data_root_filter=None,
    ids=None,
):
    if ids is None:
        ids = idgenerator
    return pytest.mark.parametrize(
        "dev",
        filter_fixtures(
            desc,
            model_filter=model_filter,
            protocol_filter=protocol_filter,
            component_filter=component_filter,
            data_root_filter=data_root_filter,
        ),
        indirect=True,
        ids=ids,
    )


has_emeter = parametrize(
    "has emeter", model_filter=WITH_EMETER, protocol_filter={"SMART", "IOT"}
)
no_emeter = parametrize(
    "no emeter",
    model_filter=ALL_DEVICES - WITH_EMETER,
    protocol_filter={"SMART", "IOT"},
)
has_emeter_iot = parametrize(
    "has emeter iot", model_filter=WITH_EMETER_IOT, protocol_filter={"IOT"}
)
no_emeter_iot = parametrize(
    "no emeter iot",
    model_filter=ALL_DEVICES_IOT - WITH_EMETER_IOT,
    protocol_filter={"IOT"},
)

bulb = parametrize("bulbs", model_filter=BULBS, protocol_filter={"SMART", "IOT"})
plug = parametrize("plugs", model_filter=PLUGS, protocol_filter={"IOT", "SMART"})
plug_iot = parametrize("plugs", model_filter=PLUGS, protocol_filter={"IOT"})
switch = parametrize("plugs", model_filter=SWITCHES, protocol_filter={"IOT", "SMART"})
switch_iot = parametrize("plugs", model_filter=SWITCHES, protocol_filter={"IOT"})
strip = parametrize("strips", model_filter=STRIPS, protocol_filter={"SMART", "IOT"})
dimmer = parametrize("dimmers", model_filter=DIMMERS, protocol_filter={"IOT"})
lightstrip = parametrize(
    "lightstrips", model_filter=LIGHT_STRIPS, protocol_filter={"IOT"}
)

# bulb types
dimmable = parametrize("dimmable", model_filter=DIMMABLE, protocol_filter={"IOT"})
non_dimmable = parametrize(
    "non-dimmable", model_filter=BULBS - DIMMABLE, protocol_filter={"IOT"}
)
variable_temp = parametrize(
    "variable color temp",
    model_filter=BULBS_VARIABLE_TEMP,
    protocol_filter={"SMART", "IOT"},
)
non_variable_temp = parametrize(
    "non-variable color temp",
    model_filter=BULBS - BULBS_VARIABLE_TEMP,
    protocol_filter={"SMART", "IOT"},
)
color_bulb = parametrize(
    "color bulbs", model_filter=BULBS_COLOR, protocol_filter={"SMART", "IOT"}
)
non_color_bulb = parametrize(
    "non-color bulbs",
    model_filter=BULBS - BULBS_COLOR,
    protocol_filter={"SMART", "IOT"},
)

color_bulb_iot = parametrize(
    "color bulbs iot", model_filter=BULBS_IOT_COLOR, protocol_filter={"IOT"}
)
variable_temp_iot = parametrize(
    "variable color temp iot",
    model_filter=BULBS_IOT_VARIABLE_TEMP,
    protocol_filter={"IOT"},
)
bulb_iot = parametrize(
    "bulb devices iot", model_filter=BULBS_IOT, protocol_filter={"IOT"}
)

strip_iot = parametrize(
    "strip devices iot", model_filter=STRIPS_IOT, protocol_filter={"IOT"}
)
strip_smart = parametrize(
    "strip devices smart", model_filter=STRIPS_SMART, protocol_filter={"SMART"}
)

plug_smart = parametrize(
    "plug devices smart", model_filter=PLUGS_SMART, protocol_filter={"SMART"}
)
bulb_smart = parametrize(
    "bulb devices smart", model_filter=BULBS_SMART, protocol_filter={"SMART"}
)
dimmers_smart = parametrize(
    "dimmer devices smart", model_filter=DIMMERS_SMART, protocol_filter={"SMART"}
)
hubs_smart = parametrize(
    "hubs smart", model_filter=HUBS_SMART, protocol_filter={"SMART"}
)
device_smart = parametrize(
    "devices smart", model_filter=ALL_DEVICES_SMART, protocol_filter={"SMART"}
)
device_iot = parametrize(
    "devices iot", model_filter=ALL_DEVICES_IOT, protocol_filter={"IOT"}
)

brightness = parametrize("brightness smart", component_filter="brightness")


def check_categories():
    """Check that every fixture file is categorized."""
    categorized_fixtures = set(
        dimmer.args[1]
        + strip.args[1]
        + plug.args[1]
        + bulb.args[1]
        + switch.args[1]
        + lightstrip.args[1]
        + bulb_smart.args[1]
        + dimmers_smart.args[1]
        + hubs_smart.args[1]
    )
    diffs: Set[FixtureInfo] = set(FIXTURE_DATA) - set(categorized_fixtures)
    if diffs:
        print(diffs)
        for diff in diffs:
            print(
                f"No category for file {diff.name} protocol {diff.protocol}, add to the corresponding set (BULBS, PLUGS, ..)"
            )
        raise Exception(f"Missing category for {diff.name}")


check_categories()


def device_for_fixture_name(model, protocol):
    if protocol == "SMART":
        for d in PLUGS_SMART:
            if d in model:
                return SmartDevice
        for d in SWITCHES_SMART:
            if d in model:
                return SmartDevice
        for d in BULBS_SMART:
            if d in model:
                return SmartBulb
        for d in DIMMERS_SMART:
            if d in model:
                return SmartBulb
        for d in STRIPS_SMART:
            if d in model:
                return SmartDevice
        for d in HUBS_SMART:
            if d in model:
                return SmartDevice
    else:
        for d in STRIPS_IOT:
            if d in model:
                return IotStrip

        for d in PLUGS_IOT:
            if d in model:
                return IotPlug
        for d in SWITCHES_IOT:
            if d in model:
                return IotSwitch

        # Light strips are recognized also as bulbs, so this has to go first
        for d in BULBS_IOT_LIGHT_STRIP:
            if d in model:
                return IotLightStrip

        for d in BULBS_IOT:
            if d in model:
                return IotBulb

        for d in DIMMERS_IOT:
            if d in model:
                return IotDimmer

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


async def get_device_for_fixture(fixture_data: FixtureInfo):
    # if the wanted file is not an absolute path, prepend the fixtures directory

    d = device_for_fixture_name(fixture_data.name, fixture_data.protocol)(
        host="127.0.0.123"
    )
    if fixture_data.protocol == "SMART":
        d.protocol = FakeSmartProtocol(fixture_data.data, fixture_data.name)
    else:
        d.protocol = FakeIotProtocol(fixture_data.data)
    if "discovery_result" in fixture_data.data:
        discovery_data = {"result": fixture_data.data["discovery_result"]}
    else:
        discovery_data = {
            "system": {"get_sysinfo": fixture_data.data["system"]["get_sysinfo"]}
        }
    d.update_from_discover_info(discovery_data)
    await _update_and_close(d)
    return d


async def get_device_for_fixture_protocol(fixture, protocol):
    finfo = FixtureInfo(name=fixture, protocol=protocol, data={})
    for fixture_info in FIXTURE_DATA:
        if finfo == fixture_info:
            return await get_device_for_fixture(fixture_info)


@pytest.fixture(params=FIXTURE_DATA, ids=idgenerator)
async def dev(request):
    """Device fixture.

    Provides a device (given --ip) or parametrized fixture for the supported devices.
    The initial update is called automatically before returning the device.
    """
    fixture_data: FixtureInfo = request.param

    ip = request.config.getoption("--ip")
    username = request.config.getoption("--username")
    password = request.config.getoption("--password")
    if ip:
        model = IP_MODEL_CACHE.get(ip)
        d = None
        if not model:
            d = await _discover_update_and_close(ip, username, password)
            IP_MODEL_CACHE[ip] = model = d.model
        if model not in fixture_data.name:
            pytest.skip(f"skipping file {fixture_data.name}")
        dev: Device = (
            d if d else await _discover_update_and_close(ip, username, password)
        )
    else:
        dev: Device = await get_device_for_fixture(fixture_data)

    yield dev

    await dev.disconnect()
