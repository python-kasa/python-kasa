from __future__ import annotations

import json
import os

import pytest

from kasa import Credentials, IotProtocol
from kasa.device_factory import connect
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.iot import IotStrip
from kasa.transports import KlapTransportV2

from .conftest import load_fixture
from .fakeprotocol_iot import FakeIotTransport


def _get_credentials_from_request(request) -> Credentials:
    username = request.config.getoption("--username") or os.environ.get("KASA_USERNAME")
    password = request.config.getoption("--password") or os.environ.get("KASA_PASSWORD")

    if not username or not password:
        pytest.skip(
            "requires --username/--password or KASA_USERNAME/KASA_PASSWORD"
        )

    return Credentials(username=username, password=password)


@pytest.mark.requires_dummy
async def test_hs300_iot_klap_lv2_connect_uses_strip_fixture(mocker):
    """Verify direct connect uses KLAP v2 and creates an IotStrip for HS300."""
    fixture_data = FakeIotTransport._build_fake_proto(
        json.loads(load_fixture("iot", "HS300(US)_2.0_1.0.12.json"))
    )
    config = DeviceConfig(
        host="127.0.0.123",
        credentials=Credentials("dummy_user", "dummy_password"),
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.IotSmartPlugSwitch,
            encryption_type=DeviceEncryptionType.Klap,
            login_version=2,
            http_port=80,
        ),
    )

    async def _query(self, *_args, **_kwargs):
        assert isinstance(self, IotProtocol)
        assert isinstance(self._transport, KlapTransportV2)
        return fixture_data

    async def _update(self, *_args, **_kwargs):
        return None

    mocker.patch("kasa.IotProtocol.query", new=_query)
    mocker.patch.object(IotStrip, "update", new=_update)

    dev = await connect(config=config)
    try:
        assert isinstance(dev, IotStrip)
        assert isinstance(dev.protocol, IotProtocol)
        assert isinstance(dev.protocol._transport, KlapTransportV2)
        assert dev.model == "HS300"
        assert dev.port == 80
        assert dev.sys_info["child_num"] == 6
        assert dev.config.connection_type.login_version == 2
    finally:
        await dev.disconnect()


async def test_hs300_iot_klap_lv2_direct_connect_real_device(request):
    """Verify the explicit HS300 KLAP lv2 config reconnects correctly."""
    ip = request.config.getoption("--ip")
    if not ip:
        pytest.skip("requires --ip to run against a real device")

    credentials = _get_credentials_from_request(request)
    config = DeviceConfig(
        host=ip,
        credentials=credentials,
        timeout=10,
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.IotSmartPlugSwitch,
            encryption_type=DeviceEncryptionType.Klap,
            login_version=2,
            http_port=80,
        ),
    )

    dev = await connect(config=config)
    try:
        assert isinstance(dev, IotStrip)
        assert isinstance(dev.protocol, IotProtocol)
        assert isinstance(dev.protocol._transport, KlapTransportV2)
        assert dev.model == "HS300"
        assert dev.port == 80
        assert len(dev.children) == 6
        assert dev.config.connection_type.login_version == 2
    finally:
        await dev.disconnect()
