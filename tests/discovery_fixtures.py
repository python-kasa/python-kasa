from __future__ import annotations

import copy
from dataclasses import dataclass
from json import dumps as json_dumps
from typing import Any, TypedDict

import pytest

from kasa.transports.xortransport import XorEncryption

from .fakeprotocol_iot import FakeIotProtocol
from .fakeprotocol_smart import FakeSmartProtocol, FakeSmartTransport
from .fakeprotocol_smartcam import FakeSmartCamProtocol
from .fixtureinfo import FixtureInfo, filter_fixtures, idgenerator

DISCOVERY_MOCK_IP = "127.0.0.123"


class DiscoveryResponse(TypedDict):
    result: dict[str, Any]
    error_code: int


def _make_unsupported(
    device_family,
    encrypt_type,
    *,
    https: bool = False,
    omit_keys: dict[str, Any] | None = None,
) -> DiscoveryResponse:
    if omit_keys is None:
        omit_keys = {"encrypt_info": None}
    result: DiscoveryResponse = {
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
                "is_support_https": https,
                "encrypt_type": encrypt_type,
                "http_port": 80,
                "lv": 2,
            },
            "encrypt_info": {"data": "", "key": "", "sym_schm": encrypt_type},
        },
        "error_code": 0,
    }
    for key, val in omit_keys.items():
        if val is None:
            result["result"].pop(key)
        else:
            result["result"][key].pop(val)

    return result


UNSUPPORTED_DEVICES = {
    "unknown_device_family": _make_unsupported("SMART.TAPOXMASTREE", "AES"),
    "unknown_iot_device_family": _make_unsupported("IOT.IOTXMASTREE", "AES"),
    "wrong_encryption_iot": _make_unsupported("IOT.SMARTPLUGSWITCH", "AES"),
    "wrong_encryption_smart": _make_unsupported("SMART.TAPOBULB", "IOT"),
    "unknown_encryption": _make_unsupported("IOT.SMARTPLUGSWITCH", "FOO"),
    "missing_encrypt_type": _make_unsupported(
        "SMART.TAPOBULB",
        "FOO",
        omit_keys={"mgt_encrypt_schm": "encrypt_type", "encrypt_info": None},
    ),
    "unable_to_parse": _make_unsupported(
        "SMART.TAPOBULB",
        "FOO",
        omit_keys={"mgt_encrypt_schm": None},
    ),
    "invalidinstance": _make_unsupported(
        "IOT.SMARTPLUGSWITCH",
        "KLAP",
        https=True,
    ),
}


def parametrize_discovery(
    desc, *, data_root_filter=None, protocol_filter=None, model_filter=None
):
    filtered_fixtures = filter_fixtures(
        desc,
        data_root_filter=data_root_filter,
        protocol_filter=protocol_filter,
        model_filter=model_filter,
    )
    return pytest.mark.parametrize(
        "discovery_mock",
        filtered_fixtures,
        indirect=True,
        ids=idgenerator,
    )


new_discovery = parametrize_discovery(
    "new discovery", data_root_filter="discovery_result"
)


@pytest.fixture(
    params=filter_fixtures("discoverable", protocol_filter={"SMART", "IOT"}),
    ids=idgenerator,
)
async def discovery_mock(request, mocker):
    """Mock discovery and patch protocol queries to use Fake protocols."""
    fixture_info: FixtureInfo = request.param
    return patch_discovery({DISCOVERY_MOCK_IP: fixture_info}, mocker)


def create_discovery_mock(ip: str, fixture_data: dict):
    """Mock discovery and patch protocol queries to use Fake protocols."""

    @dataclass
    class _DiscoveryMock:
        ip: str
        default_port: int
        discovery_port: int
        discovery_data: dict
        query_data: dict
        device_type: str
        encrypt_type: str
        https: bool
        login_version: int | None = None
        port_override: int | None = None

        @property
        def _datagram(self) -> bytes:
            if self.default_port == 9999:
                return XorEncryption.encrypt(json_dumps(self.discovery_data))[4:]
            else:
                return (
                    b"\x02\x00\x00\x01\x01[\x00\x00\x00\x00\x00\x00W\xcev\xf8"
                    + json_dumps(self.discovery_data).encode()
                )

    if "discovery_result" in fixture_data:
        discovery_data = {"result": fixture_data["discovery_result"].copy()}
        discovery_result = fixture_data["discovery_result"]
        device_type = discovery_result["device_type"]
        encrypt_type = discovery_result["mgt_encrypt_schm"].get(
            "encrypt_type", discovery_result.get("encrypt_info", {}).get("sym_schm")
        )

        login_version = discovery_result["mgt_encrypt_schm"].get("lv")
        https = discovery_result["mgt_encrypt_schm"]["is_support_https"]
        dm = _DiscoveryMock(
            ip,
            80,
            20002,
            discovery_data,
            fixture_data,
            device_type,
            encrypt_type,
            https,
            login_version,
        )
    else:
        sys_info = fixture_data["system"]["get_sysinfo"]
        discovery_data = {"system": {"get_sysinfo": sys_info.copy()}}
        device_type = sys_info.get("mic_type") or sys_info.get("type")
        encrypt_type = "XOR"
        login_version = None
        dm = _DiscoveryMock(
            ip,
            9999,
            9999,
            discovery_data,
            fixture_data,
            device_type,
            encrypt_type,
            False,
            login_version,
        )

    return dm


def patch_discovery(fixture_infos: dict[str, FixtureInfo], mocker):
    """Mock discovery and patch protocol queries to use Fake protocols."""
    discovery_mocks = {
        ip: create_discovery_mock(ip, fixture_info.data)
        for ip, fixture_info in fixture_infos.items()
    }
    protos = {
        ip: FakeSmartProtocol(fixture_info.data, fixture_info.name)
        if fixture_info.protocol in {"SMART", "SMART.CHILD"}
        else FakeSmartCamProtocol(fixture_info.data, fixture_info.name)
        if fixture_info.protocol in {"SMARTCAM", "SMARTCAM.CHILD"}
        else FakeIotProtocol(fixture_info.data, fixture_info.name)
        for ip, fixture_info in fixture_infos.items()
    }
    first_ip = list(fixture_infos.keys())[0]
    first_host = None

    async def mock_discover(self):
        """Call datagram_received for all mock fixtures.

        Handles test cases modifying the ip and hostname of the first fixture
        for discover_single testing.
        """
        for ip, dm in discovery_mocks.items():
            first_ip = list(discovery_mocks.values())[0].ip
            fixture_info = fixture_infos[ip]
            # Ip of first fixture could have been modified by a test
            if dm.ip == first_ip:
                # hostname could have been used
                host = first_host if first_host else first_ip
            else:
                host = dm.ip
            # update the protos for any host testing or the test overriding the first ip
            protos[host] = (
                FakeSmartProtocol(fixture_info.data, fixture_info.name)
                if fixture_info.protocol in {"SMART", "SMART.CHILD"}
                else FakeSmartCamProtocol(fixture_info.data, fixture_info.name)
                if fixture_info.protocol in {"SMARTCAM", "SMARTCAM.CHILD"}
                else FakeIotProtocol(fixture_info.data, fixture_info.name)
            )
            port = (
                dm.port_override
                if dm.port_override and dm.discovery_port != 20002
                else dm.discovery_port
            )
            self.datagram_received(
                dm._datagram,
                (dm.ip, port),
            )

    async def _query(self, request, retry_count: int = 3):
        return await protos[self._host].query(request)

    def _getaddrinfo(host, *_, **__):
        nonlocal first_host, first_ip
        first_host = host  # Store the hostname used by discover single
        first_ip = list(discovery_mocks.values())[
            0
        ].ip  # ip could have been overridden in test
        return [(None, None, None, None, (first_ip, 0))]

    mocker.patch("kasa.IotProtocol.query", _query)
    mocker.patch("kasa.SmartProtocol.query", _query)
    mocker.patch("kasa.discover._DiscoverProtocol.do_discover", mock_discover)
    mocker.patch(
        "socket.getaddrinfo",
        # side_effect=lambda *_, **__: [(None, None, None, None, (first_ip, 0))],
        side_effect=_getaddrinfo,
    )
    # Only return the first discovery mock to be used for testing discover single
    return discovery_mocks[first_ip]


@pytest.fixture(
    params=filter_fixtures("discoverable", protocol_filter={"SMART", "IOT"}),
    ids=idgenerator,
)
def discovery_data(request, mocker):
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_info = request.param
    fixture_data = copy.deepcopy(fixture_info.data)
    # Add missing queries to fixture data
    if "component_nego" in fixture_data:
        components = {
            comp["id"]: int(comp["ver_code"])
            for comp in fixture_data["component_nego"]["component_list"]
        }
        for k, v in FakeSmartTransport.FIXTURE_MISSING_MAP.items():
            # Value is a tuple of component,reponse
            if k not in fixture_data and v[0] in components:
                fixture_data[k] = v[1]
    mocker.patch("kasa.IotProtocol.query", return_value=fixture_data)
    mocker.patch("kasa.SmartProtocol.query", return_value=fixture_data)
    if "discovery_result" in fixture_data:
        return {"result": fixture_data["discovery_result"]}
    else:
        return {"system": {"get_sysinfo": fixture_data["system"]["get_sysinfo"]}}


@pytest.fixture(
    params=UNSUPPORTED_DEVICES.values(), ids=list(UNSUPPORTED_DEVICES.keys())
)
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

    return discovery_data
