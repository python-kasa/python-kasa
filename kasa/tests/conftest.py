import glob
import json
import os
import warnings
from collections import namedtuple
from dataclasses import dataclass
from json import dumps as json_dumps
from os.path import basename
from pathlib import Path
from typing import Dict, List, Optional, Set
from unittest.mock import MagicMock

import pytest  # type: ignore # see https://github.com/pytest-dev/pytest/issues/3342

from kasa import (
    Credentials,
    Device,
    DeviceConfig,
    Discover,
    SmartProtocol,
)
from kasa.iot import IotBulb, IotDimmer, IotLightStrip, IotPlug, IotStrip
from kasa.protocol import BaseTransport
from kasa.smart import SmartBulb, SmartDevice
from kasa.xortransport import XorEncryption

from .fakeprotocol_iot import FakeIotProtocol
from .fakeprotocol_smart import FakeSmartProtocol

FixtureInfo = namedtuple("FixtureInfo", "data protocol name")
FixtureInfo.__hash__ = lambda x: hash((x.name, x.protocol))  # type: ignore[attr-defined, method-assign]
FixtureInfo.__eq__ = lambda x, y: hash(x) == hash(y)  # type: ignore[method-assign]

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
# P135 supports dimming, but its not currently support
# by the library
PLUGS_SMART = {
    "P100",
    "P110",
    "KP125M",
    "EP25",
    "KS205",
    "P125M",
    "S505",
    "TP15",
}
PLUGS = {
    *PLUGS_IOT,
    *PLUGS_SMART,
}
STRIPS_IOT = {"HS107", "HS300", "KP303", "KP200", "KP400", "EP40"}
STRIPS_SMART = {"P300", "TP25"}
STRIPS = {*STRIPS_IOT, *STRIPS_SMART}

DIMMERS_IOT = {"ES20M", "HS220", "KS220M", "KS230", "KP405"}
DIMMERS_SMART = {"KS225", "S500D", "P135"}
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


def get_fixture_info() -> List[FixtureInfo]:
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_data = []
    for file, protocol in SUPPORTED_DEVICES:
        p = Path(file)
        if not p.is_absolute():
            folder = Path(__file__).parent / "fixtures"
            if protocol == "SMART":
                folder = folder / "smart"
            p = folder / file

        with open(p) as f:
            data = json.load(f)

        fixture_name = basename(p)
        fixture_data.append(
            FixtureInfo(data=data, protocol=protocol, name=fixture_name)
        )
    return fixture_data


FIXTURE_DATA: List[FixtureInfo] = get_fixture_info()


def filter_fixtures(
    desc,
    *,
    data_root_filter: Optional[str] = None,
    protocol_filter: Optional[Set[str]] = None,
    model_filter: Optional[Set[str]] = None,
    component_filter: Optional[str] = None,
):
    filtered = []
    if protocol_filter is None:
        protocol_filter = {"IOT", "SMART"}
    for fixture_data in FIXTURE_DATA:
        match = True
        if data_root_filter and data_root_filter not in fixture_data.data:
            match = False
        if fixture_data.protocol not in protocol_filter:
            match = False
        if model_filter is not None:
            file_model_region = fixture_data.name.split("_")[0]
            file_model = file_model_region.split("(")[0]
            if file_model not in model_filter:
                match = False
        if component_filter:
            if (component_nego := fixture_data.data.get("component_nego")) is None:
                match = False
            else:
                components = {
                    component["id"]: component["ver_code"]
                    for component in component_nego["component_list"]
                }
                if component_filter not in components:
                    match = False
        if match:
            filtered.append(fixture_data)

    print(f"# {desc}")
    for value in filtered:
        print(f"\t{value.name}")
    return filtered


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


def idgenerator(paramtuple: FixtureInfo):
    try:
        return paramtuple.name + (
            "" if paramtuple.protocol == "IOT" else "-" + paramtuple.protocol
        )
    except:  # TODO: HACK as idgenerator is now used by default  # noqa: E722
        return None


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
plug = parametrize("plugs", model_filter=PLUGS, protocol_filter={"IOT"})
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
device_smart = parametrize(
    "devices smart", model_filter=ALL_DEVICES_SMART, protocol_filter={"SMART"}
)
device_iot = parametrize(
    "devices iot", model_filter=ALL_DEVICES_IOT, protocol_filter={"IOT"}
)

brightness_smart = parametrize(
    "brightness smart", component_filter="brightness", protocol_filter={"SMART"}
)


def parametrize_discovery(desc, root_key):
    filtered_fixtures = filter_fixtures(desc, data_root_filter=root_key)
    return pytest.mark.parametrize(
        "discovery_mock",
        filtered_fixtures,
        indirect=True,
        ids=idgenerator,
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
        + dimmers_smart.args[1]
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

# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


async def handle_turn_on(dev, turn_on):
    if turn_on:
        await dev.turn_on()
    else:
        await dev.turn_off()


def device_for_fixture_name(model, protocol):
    if protocol == "SMART":
        for d in PLUGS_SMART:
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
    else:
        for d in STRIPS_IOT:
            if d in model:
                return IotStrip

        for d in PLUGS_IOT:
            if d in model:
                return IotPlug

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
    await _update_and_close(d)
    return d


async def get_device_for_fixture_protocol(fixture, protocol):
    # loop = asyncio.get_running_loop()

    finfo = FixtureInfo(name=fixture, protocol=protocol, data={})
    for fixture_info in FIXTURE_DATA:
        if finfo == fixture_info:
            # return await loop.run_in_executor(None, get_device_for_fixture(fixture_info))
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


@pytest.fixture(params=FIXTURE_DATA, ids=idgenerator)
def discovery_mock(request, mocker):
    fixture_info: FixtureInfo = request.param
    fixture_data = fixture_info.data

    @dataclass
    class _DiscoveryMock:
        ip: str
        default_port: int
        discovery_port: int
        discovery_data: dict
        query_data: dict
        device_type: str
        encrypt_type: str
        login_version: Optional[int] = None
        port_override: Optional[int] = None

    if "discovery_result" in fixture_data:
        discovery_data = {"result": fixture_data["discovery_result"]}
        device_type = fixture_data["discovery_result"]["device_type"]
        encrypt_type = fixture_data["discovery_result"]["mgt_encrypt_schm"][
            "encrypt_type"
        ]
        login_version = fixture_data["discovery_result"]["mgt_encrypt_schm"].get("lv")
        datagram = (
            b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
            + json_dumps(discovery_data).encode()
        )
        dm = _DiscoveryMock(
            "127.0.0.123",
            80,
            20002,
            discovery_data,
            fixture_data,
            device_type,
            encrypt_type,
            login_version,
        )
    else:
        sys_info = fixture_data["system"]["get_sysinfo"]
        discovery_data = {"system": {"get_sysinfo": sys_info}}
        device_type = sys_info.get("mic_type") or sys_info.get("type")
        encrypt_type = "XOR"
        login_version = None
        datagram = XorEncryption.encrypt(json_dumps(discovery_data))[4:]
        dm = _DiscoveryMock(
            "127.0.0.123",
            9999,
            9999,
            discovery_data,
            fixture_data,
            device_type,
            encrypt_type,
            login_version,
        )

    async def mock_discover(self):
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

    if fixture_info.protocol == "SMART":
        proto = FakeSmartProtocol(fixture_data, fixture_info.name)
    else:
        proto = FakeIotProtocol(fixture_data)

    async def _query(request, retry_count: int = 3):
        return await proto.query(request)

    mocker.patch("kasa.IotProtocol.query", side_effect=_query)
    mocker.patch("kasa.SmartProtocol.query", side_effect=_query)

    yield dm


@pytest.fixture(params=FIXTURE_DATA, ids=idgenerator)
def discovery_data(request):
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_info = request.param
    if "discovery_result" in fixture_info.data:
        return {"result": fixture_info.data["discovery_result"]}
    else:
        return {"system": {"get_sysinfo": fixture_info.data["system"]["get_sysinfo"]}}


@pytest.fixture(params=FIXTURE_DATA, ids=idgenerator)
def all_fixture_data(request):
    """Return raw fixture file contents as JSON. Used for discovery tests."""
    fixture_info = request.param
    return fixture_info.data


@pytest.fixture(params=UNSUPPORTED_DEVICES.values(), ids=UNSUPPORTED_DEVICES.keys())
def unsupported_device_info(request, mocker):
    """Return unsupported devices for cli and discovery tests."""
    discovery_data = request.param
    host = "127.0.0.1"

    async def mock_discover(self):
        if discovery_data:
            data = (
                b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
                + json_dumps(discovery_data).encode()
            )
            self.datagram_received(data, (host, 20002))

    mocker.patch("kasa.discover._DiscoverProtocol.do_discover", mock_discover)

    yield discovery_data


@pytest.fixture()
def dummy_protocol():
    """Return a smart protocol instance with a mocking-ready dummy transport."""

    class DummyTransport(BaseTransport):
        @property
        def default_port(self) -> int:
            return -1

        @property
        def credentials_hash(self) -> str:
            return "dummy hash"

        async def send(self, request: str) -> Dict:
            return {}

        async def close(self) -> None:
            pass

        async def reset(self) -> None:
            pass

    transport = DummyTransport(config=DeviceConfig(host="127.0.0.123"))
    protocol = SmartProtocol(transport=transport)

    return protocol


def pytest_configure():
    pytest.fixtures_missing_methods = {}


def pytest_sessionfinish(session, exitstatus):
    msg = "\n"
    for fixture, methods in sorted(pytest.fixtures_missing_methods.items()):
        method_list = ", ".join(methods)
        msg += f"Fixture {fixture} missing: {method_list}\n"

    warnings.warn(
        UserWarning(msg),
        stacklevel=1,
    )


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
