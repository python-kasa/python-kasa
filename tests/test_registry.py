"""Tests for choosing protocol, transport and device class, and for plugins."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from kasa import (
    IotProtocol,
    KasaException,
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
    """Plugins change global state: the entries and the encryption type enum."""
    entries = list(registry._ENTRIES)
    maps = (
        dict(ET._value2member_map_),
        dict(ET._member_map_),
        list(ET._member_names_),
    )
    yield
    registry._ENTRIES[:] = entries
    ET._value2member_map_.clear()
    ET._value2member_map_.update(maps[0])
    ET._member_map_.clear()
    ET._member_map_.update(maps[1])
    ET._member_names_[:] = maps[2]


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


def register_foo() -> None:
    registry.register_transport("SMART", "FOO", SmartProtocol, KlapTransportV2)


@pytest.fixture
def plugins(mocker):
    """Patch the installed plugins, each given as the function it registers with."""

    def _install(*registers):
        entry_points = mocker.patch("kasa.registry.entry_points")
        entry_points.return_value = [
            SimpleNamespace(name=register.__name__, load=lambda r=register: r)
            for register in registers
        ]
        return entry_points

    return _install


async def test_plugin_adds_encryption_type(plugins) -> None:
    entry_points = plugins(register_foo)

    with pytest.raises(KasaException, match="Invalid connection parameters"):
        CP.from_values("SMART.TAPOPLUG", "FOO")

    registry.load_plugins()

    entry_points.assert_called_once_with(group="kasa.plugins")
    ctype = CP.from_values("SMART.TAPOPLUG", "FOO", login_version=2)
    assert ctype.encryption_type is ET("FOO")
    assert ctype.encryption_type.value == "FOO"
    assert "FOO" in [encryption.value for encryption in ET]

    config = DeviceConfig("127.0.0.1", connection_type=ctype)
    assert DeviceConfig.from_dict(config.to_dict()) == config

    protocol = get_protocol(config)
    assert type(protocol) is SmartProtocol
    assert type(protocol._transport) is KlapTransportV2
    assert get_device_class(ctype) is SmartDevice


@pytest.mark.parametrize(
    "exception",
    [RuntimeError("boom"), SystemExit(1)],
    ids=["exception", "system-exit"],
)
async def test_failing_plugin_is_skipped(exception, plugins, caplog) -> None:
    def register_broken() -> None:
        raise exception

    plugins(register_broken, register_foo)

    with caplog.at_level(logging.ERROR):
        registry.load_plugins()

    assert "register_broken" in caplog.text
    assert ET("FOO").value == "FOO"


async def test_interrupt_is_not_swallowed(plugins) -> None:
    def register_interrupted() -> None:
        raise KeyboardInterrupt

    plugins(register_interrupted, register_foo)

    with pytest.raises(KeyboardInterrupt):
        registry.load_plugins()


@pytest.mark.parametrize(
    ("family", "bulb_transport", "message"),
    [
        pytest.param("SMART", XorTransport, "Replacing", id="same-parameters"),
        pytest.param(
            "SMART.TAPOPLUG",
            KlapTransportV2,
            "Plugin register_override overrides",
            id="more-specific",
        ),
    ],
)
async def test_plugin_overrides_existing_transport(
    family, bulb_transport, message, plugins, caplog
) -> None:
    def register_override() -> None:
        registry.register_transport(family, "KLAP", SmartProtocol, XorTransport)

    plugins(register_override)

    with caplog.at_level(logging.WARNING):
        registry.load_plugins()

    plug = DeviceConfig(
        "127.0.0.1",
        connection_type=CP(
            device_family=DF.SmartTapoPlug, encryption_type=ET.Klap, login_version=2
        ),
    )
    bulb = DeviceConfig(
        "127.0.0.1",
        connection_type=CP(
            device_family=DF.SmartTapoBulb, encryption_type=ET.Klap, login_version=2
        ),
    )
    assert type(get_protocol(plug)._transport) is XorTransport
    assert type(get_protocol(bulb)._transport) is bulb_transport
    assert message in caplog.text


async def test_plugin_without_override_does_not_warn(plugins, caplog) -> None:
    """A new encryption type or a less specific entry does not take over devices."""

    def register_less_specific() -> None:
        registry.register_transport("SMART", "AES", SmartProtocol, XorTransport)

    plugins(register_foo, register_less_specific)

    with caplog.at_level(logging.WARNING):
        registry.load_plugins()

    assert caplog.records == []
    config = DeviceConfig(
        "127.0.0.1",
        connection_type=CP(
            device_family=DF.SmartTapoPlug, encryption_type=ET.Aes, login_version=2
        ),
    )
    assert type(get_protocol(config)._transport) is AesTransport


async def test_disable_plugins(plugins, monkeypatch) -> None:
    entry_points = plugins(register_foo)
    monkeypatch.setenv("KASA_DISABLE_PLUGINS", "1")

    registry.load_plugins()

    entry_points.assert_not_called()
    with pytest.raises(ValueError, match="FOO"):
        ET("FOO")


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
