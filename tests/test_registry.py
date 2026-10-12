"""Tests for choosing protocol, transport and device class, and for plugins."""

from __future__ import annotations

import logging

import pytest

from kasa import (
    IotProtocol,
    SmartCamProtocol,
    SmartProtocol,
    registry,
)
from kasa.device_factory import get_device_class, get_protocol
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.iot import IotBulb, IotPlug
from kasa.smart import SmartDevice
from kasa.smartcam import SmartCamDevice
from kasa.transports import (
    AesTransport,
    KlapTransport,
    KlapTransportV2,
    LinkieTransportV2,
    SslAesTransport,
    SslTransport,
    XorTransport,
)

CP = DeviceConnectionParameters
DF = DeviceFamily
ET = DeviceEncryptionType


@pytest.fixture(autouse=True)
def _restore_registry():
    """Registrations change global state."""
    entries = list(registry._ENTRIES)
    yield
    registry._ENTRIES[:] = entries


@pytest.mark.parametrize(
    ("conn_params", "protocol", "transport"),
    [
        pytest.param(
            CP(device_family=DF.SmartTapoRobovac, encryption_type=ET.Aes, https=True),
            SmartProtocol,
            SslTransport,
            id="robovac-aes-https",
        ),
        pytest.param(
            CP(device_family=DF.SmartTapoHub, encryption_type=ET.Aes, https=True),
            SmartCamProtocol,
            SslAesTransport,
            id="hub-aes-https",
        ),
        pytest.param(
            CP(device_family=DF.SmartTapoHub, encryption_type=ET.Aes, https=False),
            SmartProtocol,
            AesTransport,
            id="hub-aes",
        ),
        pytest.param(
            CP(device_family=DF.SmartIpCamera, encryption_type=ET.Klap, https=False),
            SmartCamProtocol,
            SslAesTransport,
            id="camera-ignores-encryption",
        ),
        pytest.param(
            CP(device_family=DF.IotIpCamera, encryption_type=ET.Klap, https=False),
            IotProtocol,
            LinkieTransportV2,
            id="linkie-ignores-encryption",
        ),
        pytest.param(
            CP(device_family=DF.SmartTapoChime, encryption_type=ET.Aes, https=False),
            SmartProtocol,
            AesTransport,
            id="unlisted-smart-family",
        ),
        pytest.param(
            CP(
                device_family=DF.IotSmartPlugSwitch,
                encryption_type=ET.Klap,
                login_version=1,
            ),
            IotProtocol,
            KlapTransport,
            id="iot-klap-v1",
        ),
        pytest.param(
            CP(
                device_family=DF.IotSmartPlugSwitch,
                encryption_type=ET.Klap,
                login_version=3,
            ),
            IotProtocol,
            KlapTransportV2,
            id="iot-klap-v3",
        ),
    ],
)
async def test_most_specific_entry_wins(conn_params, protocol, transport) -> None:
    """The family, then the encryption, then https decide which entry matches."""
    protocol_obj = get_protocol(DeviceConfig("127.0.0.1", connection_type=conn_params))
    assert type(protocol_obj) is protocol
    assert type(protocol_obj._transport) is transport


@pytest.mark.parametrize(
    "conn_params",
    [
        pytest.param(
            CP(device_family=DF.SmartTapoPlug, encryption_type=ET.Xor), id="smart-xor"
        ),
        pytest.param(
            CP(device_family=DF.IotSmartPlugSwitch, encryption_type=ET.Aes),
            id="iot-aes",
        ),
    ],
)
async def test_no_entry(conn_params) -> None:
    config = DeviceConfig("127.0.0.1", connection_type=conn_params)
    assert get_protocol(config) is None
    assert get_device_class(conn_params) is None


@pytest.mark.parametrize(
    ("conn_params", "device_class"),
    [
        pytest.param(
            CP(device_family=DF.SmartTapoPlug, encryption_type=ET.Aes),
            SmartDevice,
            id="smart",
        ),
        pytest.param(
            CP(device_family=DF.SmartTapoChime, encryption_type=ET.Klap),
            SmartDevice,
            id="smart-chime",
        ),
        pytest.param(
            CP(device_family=DF.SmartTapoRobovac, encryption_type=ET.Aes, https=True),
            SmartDevice,
            id="robovac",
        ),
        pytest.param(
            CP(device_family=DF.SmartTapoHub, encryption_type=ET.Aes, https=True),
            SmartCamDevice,
            id="hub-https",
        ),
        pytest.param(
            CP(device_family=DF.SmartIpCamera, encryption_type=ET.Aes, https=True),
            SmartCamDevice,
            id="cam",
        ),
        pytest.param(
            CP(device_family=DF.IotSmartPlugSwitch, encryption_type=ET.Klap),
            IotPlug,
            id="iot-plug",
        ),
        pytest.param(
            CP(device_family=DF.IotSmartBulb, encryption_type=ET.Xor),
            IotBulb,
            id="iot-bulb",
        ),
        pytest.param(
            CP(device_family=DF.IotIpCamera, encryption_type=ET.Xor, https=True),
            None,
            id="iot-camera",
        ),
    ],
)
def test_get_device_class(conn_params, device_class) -> None:
    assert get_device_class(conn_params) is device_class


async def test_registration_replaces_same_parameters(caplog) -> None:
    registry.register_transport("IOT", "XOR", IotProtocol, KlapTransport, https=True)
    with caplog.at_level(logging.WARNING):
        registry.register_transport("IOT", "XOR", IotProtocol, XorTransport, https=True)

    assert "Replacing" in caplog.text
    config = DeviceConfig(
        "127.0.0.1",
        connection_type=CP(
            device_family=DF.IotSmartPlugSwitch,
            encryption_type=ET.Xor,
            https=True,
        ),
    )
    assert type(get_protocol(config)._transport) is XorTransport
