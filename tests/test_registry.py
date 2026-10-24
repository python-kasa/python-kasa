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
)
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.iot import IotBulb, IotPlug
from kasa.registry import Registry
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
def _restore_encryption_types():
    """Plugins add encryption types to the enum, which is shared by registries."""
    maps = (
        dict(ET._value2member_map_),
        dict(ET._member_map_),
        list(ET._member_names_),
    )
    yield
    ET._value2member_map_.clear()
    ET._value2member_map_.update(maps[0])
    ET._member_map_.clear()
    ET._member_map_.update(maps[1])
    ET._member_names_[:] = maps[2]


@pytest.fixture
def registry() -> Registry:
    return Registry()


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
async def test_most_specific_entry_wins(
    registry, conn_params, protocol, transport
) -> None:
    """The family, then the encryption, then https decide which entry matches."""
    protocol_obj = registry.get_protocol(
        DeviceConfig("127.0.0.1", connection_type=conn_params)
    )
    assert protocol_obj is not None
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
async def test_no_entry(registry, conn_params) -> None:
    config = DeviceConfig("127.0.0.1", connection_type=conn_params)
    assert registry.get_protocol(config) is None
    assert registry.get_device_class(conn_params) is None


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
def test_get_device_class(registry, conn_params, device_class) -> None:
    assert registry.get_device_class(conn_params) is device_class


def transport_type(registry: Registry, config: DeviceConfig) -> type:
    """Return the type of the transport chosen for the config."""
    protocol = registry.get_protocol(config)
    assert protocol is not None
    return type(protocol._transport)


def register_foo(registry: Registry) -> None:
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


async def test_plugin_adds_encryption_type(registry, plugins) -> None:
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

    protocol = registry.get_protocol(config)
    assert type(protocol) is SmartProtocol
    assert type(protocol._transport) is KlapTransportV2
    assert registry.get_device_class(ctype) is SmartDevice


@pytest.mark.parametrize(
    "exception",
    [RuntimeError("boom"), SystemExit(1)],
    ids=["exception", "system-exit"],
)
async def test_failing_plugin_is_skipped(registry, exception, plugins, caplog) -> None:
    def register_broken(registry: Registry) -> None:
        registry.register_transport("SMART", "BAR", SmartProtocol, XorTransport)
        registry.register_transport("SMART", "KLAP", SmartProtocol, XorTransport)
        raise exception

    plugins(register_broken, register_foo)

    with caplog.at_level(logging.ERROR):
        registry.load_plugins()

    assert "register_broken" in caplog.text
    assert ET("FOO").value == "FOO"
    assert not any(entry.encryption == "BAR" for entry in registry._entries)
    config = DeviceConfig(
        "127.0.0.1",
        connection_type=CP(
            device_family=DF.SmartTapoPlug, encryption_type=ET.Klap, login_version=2
        ),
    )
    assert transport_type(registry, config) is KlapTransportV2


async def test_interrupt_is_not_swallowed(registry, plugins) -> None:
    def register_interrupted(registry: Registry) -> None:
        raise KeyboardInterrupt

    plugins(register_interrupted, register_foo)

    with pytest.raises(KeyboardInterrupt):
        registry.load_plugins()


@pytest.mark.parametrize(
    ("family", "bulb_transport"),
    [
        pytest.param("SMART", XorTransport, id="same-parameters"),
        pytest.param("SMART.TAPOPLUG", KlapTransportV2, id="more-specific"),
    ],
)
async def test_plugin_overrides_existing_transport(
    registry, family, bulb_transport, plugins, caplog
) -> None:
    def register_override(registry: Registry) -> None:
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
    assert transport_type(registry, plug) is XorTransport
    assert transport_type(registry, bulb) is bulb_transport
    assert "Plugin register_override overrides" in caplog.text


async def test_plugin_override_warns_once_for_the_replaced_entry(
    registry, plugins, caplog
) -> None:
    """Entries already shadowed for the overridden devices are not reported."""

    def register_camera(registry: Registry) -> None:
        registry.register_transport(
            "SMART.IPCAMERA", "AES", SmartCamProtocol, XorTransport
        )

    plugins(register_camera)

    with caplog.at_level(logging.WARNING):
        registry.load_plugins()

    [record] = caplog.records
    assert "(SMART.IPCAMERA None https=None)" in record.getMessage()


async def test_plugin_without_override_does_not_warn(registry, plugins, caplog) -> None:
    """A new encryption type or a less specific entry does not take over devices."""

    def register_less_specific(registry: Registry) -> None:
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
    assert transport_type(registry, config) is AesTransport


async def test_disable_plugins(registry, plugins, monkeypatch) -> None:
    entry_points = plugins(register_foo)
    monkeypatch.setenv("KASA_DISABLE_PLUGINS", "1")

    registry.load_plugins()

    entry_points.assert_not_called()
    with pytest.raises(ValueError, match="FOO"):
        ET("FOO")


async def test_registration_replaces_same_parameters(registry) -> None:
    registry.register_transport("IOT", "XOR", IotProtocol, KlapTransport, https=True)
    registry.register_transport("IOT", "XOR", IotProtocol, XorTransport, https=True)

    config = DeviceConfig(
        "127.0.0.1",
        connection_type=CP(
            device_family=DF.IotSmartPlugSwitch,
            encryption_type=ET.Xor,
            https=True,
        ),
    )
    assert transport_type(registry, config) is XorTransport
