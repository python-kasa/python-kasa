"""Tests for all devices."""

import importlib
import inspect
import pkgutil
import sys
from unittest.mock import Mock, patch

import pytest

import kasa
from kasa import Credentials, Device, DeviceConfig
from kasa.iot import IotDevice
from kasa.smart import SmartChildDevice, SmartDevice


def _get_subclasses(of_class):
    package = sys.modules["kasa"]
    subclasses = set()
    for _, modname, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module("." + modname, package="kasa")
        module = sys.modules["kasa." + modname]
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, of_class)
                and module.__package__ != "kasa"
            ):
                subclasses.add((module.__package__ + "." + name, obj))
    return subclasses


device_classes = pytest.mark.parametrize(
    "device_class_name_obj", _get_subclasses(Device), ids=lambda t: t[0]
)


async def test_alias(dev):
    test_alias = "TEST1234"
    original = dev.alias

    assert isinstance(original, str)
    await dev.set_alias(test_alias)
    await dev.update()
    assert dev.alias == test_alias

    await dev.set_alias(original)
    await dev.update()
    assert dev.alias == original


@device_classes
async def test_device_class_ctors(device_class_name_obj):
    """Make sure constructor api not broken for new and existing SmartDevices."""
    host = "127.0.0.2"
    port = 1234
    credentials = Credentials("foo", "bar")
    config = DeviceConfig(host, port_override=port, credentials=credentials)
    klass = device_class_name_obj[1]
    if issubclass(klass, SmartChildDevice):
        parent = SmartDevice(host, config=config)
        dev = klass(
            parent, {"dummy": "info", "device_id": "dummy"}, {"dummy": "components"}
        )
    else:
        dev = klass(host, config=config)
    assert dev.host == host
    assert dev.port == port
    assert dev.credentials == credentials


async def test_create_device_with_timeout():
    """Make sure timeout is passed to the protocol."""
    host = "127.0.0.1"
    dev = IotDevice(host, config=DeviceConfig(host, timeout=100))
    assert dev.protocol._transport._timeout == 100
    dev = SmartDevice(host, config=DeviceConfig(host, timeout=100))
    assert dev.protocol._transport._timeout == 100


async def test_create_thin_wrapper():
    """Make sure thin wrapper is created with the correct device type."""
    mock = Mock()
    config = DeviceConfig(
        host="test_host",
        port_override=1234,
        timeout=100,
        credentials=Credentials("username", "password"),
    )
    with patch("kasa.device_factory.connect", return_value=mock) as connect:
        dev = await Device.connect(config=config)
        assert dev is mock

    connect.assert_called_once_with(
        host=None,
        config=config,
    )


@pytest.mark.parametrize(
    "device_class, use_class", kasa.deprecated_smart_devices.items()
)
def test_deprecated_devices(device_class, use_class):
    package_name = ".".join(use_class.__module__.split(".")[:-1])
    msg = f"{device_class} is deprecated, use {use_class.__name__} from package {package_name} instead"
    with pytest.deprecated_call(match=msg):
        getattr(kasa, device_class)
    packages = package_name.split(".")
    module = __import__(packages[0])
    for _ in packages[1:]:
        module = importlib.import_module(package_name, package=module.__name__)
    getattr(module, use_class.__name__)


@pytest.mark.parametrize(
    "exceptions_class, use_class", kasa.deprecated_exceptions.items()
)
def test_deprecated_exceptions(exceptions_class, use_class):
    msg = f"{exceptions_class} is deprecated, use {use_class.__name__} instead"
    with pytest.deprecated_call(match=msg):
        getattr(kasa, exceptions_class)
    getattr(kasa, use_class.__name__)
