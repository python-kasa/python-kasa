from dataclasses import dataclass
from json import dumps as json_dumps
from typing import Optional

import pytest  # type: ignore # see https://github.com/pytest-dev/pytest/issues/3342

from kasa.xortransport import XorEncryption

from .common import FIXTURE_DATA, FixtureInfo, filter_fixtures, idgenerator
from .fakeprotocol_iot import FakeIotProtocol
from .fakeprotocol_smart import FakeSmartProtocol


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


def parametrize_discovery(desc, root_key):
    filtered_fixtures = filter_fixtures(desc, data_root_filter=root_key)
    return pytest.mark.parametrize(
        "discovery_mock",
        filtered_fixtures,
        indirect=True,
        ids=idgenerator,
    )


new_discovery = parametrize_discovery("new discovery", "discovery_result")


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
def discovery_data(request, mocker):
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_info = request.param
    mocker.patch("kasa.IotProtocol.query", return_value=fixture_info.data)
    mocker.patch("kasa.SmartProtocol.query", return_value=fixture_info.data)
    if "discovery_result" in fixture_info.data:
        return {"result": fixture_info.data["discovery_result"]}
    else:
        return {"system": {"get_sysinfo": fixture_info.data["system"]["get_sysinfo"]}}


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
