from __future__ import annotations

import asyncio
import copy
from collections.abc import Coroutine
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


UNSUPPORTED_HOMEWIFISYSTEM = {
    "error_code": 0,
    "result": {
        "channel_2g": "10",
        "channel_5g": "44",
        "device_id": "REDACTED_51f72a752213a6c45203530",
        "device_model": "X20",
        "device_type": "HOMEWIFISYSTEM",
        "factory_default": False,
        "group_id": "REDACTED_07d902da02fa9beab8a64",
        "group_name": "I01BU0tFRF9TU0lEIw==",  # '#MASKED_SSID#'
        "hardware_version": "3.0",
        "ip": "127.0.0.1",
        "mac": "24:2F:D0:00:00:00",
        "master_device_id": "REDACTED_51f72a752213a6c45203530",
        "need_account_digest": True,
        "owner": "REDACTED_341c020d7e8bda184e56a90",
        "role": "master",
        "tmp_port": [20001],
    },
}


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
        omit_keys={"device_id": None},
    ),
    "invalidinstance": _make_unsupported(
        "IOT.SMARTPLUGSWITCH",
        "KLAP",
        https=True,
    ),
    "homewifi": UNSUPPORTED_HOMEWIFISYSTEM,
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

smart_discovery = parametrize_discovery("smart discovery", protocol_filter={"SMART"})


@pytest.fixture(
    params=filter_fixtures(
        "discoverable", protocol_filter={"SMART", "SMARTCAM", "IOT"}
    ),
    ids=idgenerator,
)
async def discovery_mock(request, mocker):
    """Mock discovery and patch protocol queries to use Fake protocols."""
    fi: FixtureInfo = request.param
    fixture_info = FixtureInfo(fi.name, fi.protocol, copy.deepcopy(fi.data))
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
        http_port: int | None = None
        new_klap: int | None = None

        @property
        def model(self) -> str:
            dd = self.discovery_data
            model_region = (
                dd["result"]["device_model"]
                if self.discovery_port == 20002
                else dd["system"]["get_sysinfo"]["model"]
            )
            model, _, _ = model_region.partition("(")
            return model

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
        discovery_data = fixture_data["discovery_result"].copy()
        discovery_result = fixture_data["discovery_result"]["result"]
        device_type = discovery_result["device_type"]
        encrypt_type = discovery_result["mgt_encrypt_schm"].get(
            "encrypt_type", discovery_result.get("encrypt_info", {}).get("sym_schm")
        )

        if not (login_version := discovery_result["mgt_encrypt_schm"].get("lv")) and (
            et := discovery_result.get("encrypt_type")
        ):
            login_version = max([int(i) for i in et])
        https = discovery_result["mgt_encrypt_schm"]["is_support_https"]
        http_port = discovery_result["mgt_encrypt_schm"].get("http_port")
        if not http_port:  # noqa: SIM108
            # Not all discovery responses set the http port, i.e. smartcam.
            default_port = 443 if https else 80
        else:
            default_port = http_port
        new_klap = discovery_result["mgt_encrypt_schm"].get("new_klap", None)
        dm = _DiscoveryMock(
            ip,
            default_port,
            20002,
            discovery_data,
            fixture_data,
            device_type,
            encrypt_type,
            https,
            login_version,
            http_port=http_port,
            new_klap=new_klap,
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
            new_klap=None,
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

    # Mock _run_callback_task so the tasks complete in the order they started.
    # Otherwise test output is non-deterministic which affects readme examples.
    callback_queue: asyncio.Queue = asyncio.Queue()
    exception_queue: asyncio.Queue = asyncio.Queue()

    async def process_callback_queue(finished_event: asyncio.Event) -> None:
        while (finished_event.is_set() is False) or callback_queue.qsize():
            coro = await callback_queue.get()
            try:
                await coro
            except Exception as ex:
                await exception_queue.put(ex)
            else:
                await exception_queue.put(None)
            callback_queue.task_done()

    async def wait_for_coro():
        await callback_queue.join()
        if ex := exception_queue.get_nowait():
            raise ex

    def _run_callback_task(self, coro: Coroutine) -> None:
        callback_queue.put_nowait(coro)
        task = asyncio.create_task(wait_for_coro())
        self.callback_tasks.append(task)

    mocker.patch(
        "kasa.discover._DiscoverProtocol._run_callback_task", _run_callback_task
    )

    # do_discover_mock
    async def mock_discover(self):
        """Call datagram_received for all mock fixtures.

        Handles test cases modifying the ip and hostname of the first fixture
        for discover_single testing.
        """
        finished_event = asyncio.Event()
        asyncio.create_task(process_callback_queue(finished_event))

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
        # Setting this event will stop the processing of callbacks
        finished_event.set()

    mocker.patch("kasa.discover._DiscoverProtocol.do_discover", mock_discover)

    # query_mock
    async def _query(self, request, retry_count: int = 3):
        return await protos[self._host].query(request)

    mocker.patch("kasa.IotProtocol.query", _query)
    mocker.patch("kasa.SmartProtocol.query", _query)

    def _getaddrinfo(host, *_, **__):
        nonlocal first_host, first_ip
        first_host = host  # Store the hostname used by discover single
        first_ip = list(discovery_mocks.values())[
            0
        ].ip  # ip could have been overridden in test
        return [(None, None, None, None, (first_ip, 0))]

    mocker.patch("socket.getaddrinfo", side_effect=_getaddrinfo)

    # Mock decrypt so it doesn't error with unencryptable empty data in the
    # fixtures. The discovery result will already contain the decrypted data
    # deserialized from the fixture
    mocker.patch("kasa.discover.Discover._decrypt_discovery_data")

    # Only return the first discovery mock to be used for testing discover single
    return discovery_mocks[first_ip]


@pytest.fixture(
    params=filter_fixtures(
        "discoverable", protocol_filter={"SMART", "SMARTCAM", "IOT"}
    ),
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
        return fixture_data["discovery_result"].copy()
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
