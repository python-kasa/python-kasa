from __future__ import annotations

import copy
from dataclasses import dataclass
from json import dumps as json_dumps

import pytest

from kasa.xortransport import XorEncryption

from .fakeprotocol_iot import FakeIotProtocol
from .fakeprotocol_smart import FakeSmartProtocol, FakeSmartTransport
from .fixtureinfo import FixtureInfo, filter_fixtures, idgenerator


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
    yield patch_discovery({"127.0.0.123": fixture_info}, mocker)


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
        _datagram: bytes
        login_version: int | None = None
        port_override: int | None = None

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
            ip,
            80,
            20002,
            discovery_data,
            fixture_data,
            device_type,
            encrypt_type,
            datagram,
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
            ip,
            9999,
            9999,
            discovery_data,
            fixture_data,
            device_type,
            encrypt_type,
            datagram,
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
        if "SMART" in fixture_info.protocol
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
                if "SMART" in fixture_info.protocol
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
