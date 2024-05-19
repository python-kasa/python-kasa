"""Tests for all devices."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from unittest.mock import Mock, patch

import pytest

import kasa
from kasa import Credentials, Device, DeviceConfig, DeviceType, KasaException, Module
from kasa.iot import IotDevice
from kasa.iot.modules import IotLightPreset
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
                and module.__package__ != "kasa.interfaces"
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


deprecated_is_device_type = {
    "is_bulb": DeviceType.Bulb,
    "is_plug": DeviceType.Plug,
    "is_dimmer": DeviceType.Dimmer,
    "is_light_strip": DeviceType.LightStrip,
    "is_wallswitch": DeviceType.WallSwitch,
    "is_strip": DeviceType.Strip,
    "is_strip_socket": DeviceType.StripSocket,
}
deprecated_is_light_function_smart_module = {
    "is_color": "Color",
    "is_dimmable": "Brightness",
    "is_variable_color_temp": "ColorTemperature",
}


def test_deprecated_device_type_attributes(dev: SmartDevice):
    """Test deprecated attributes on all devices."""

    def _test_attr(attribute):
        msg = f"{attribute} is deprecated"
        if module := Device._deprecated_device_type_attributes[attribute][0]:
            msg += f", use: {module} in device.modules instead"
        with pytest.deprecated_call(match=msg):
            val = getattr(dev, attribute)
        return val

    for attribute in deprecated_is_device_type:
        val = _test_attr(attribute)
        expected_val = dev.device_type == deprecated_is_device_type[attribute]
        assert val == expected_val


async def _test_attribute(
    dev: Device, attribute_name, is_expected, module_name, *args, will_raise=False
):
    if is_expected and will_raise:
        ctx = pytest.raises(will_raise)
    elif is_expected:
        ctx = pytest.deprecated_call(
            match=(
                f"{attribute_name} is deprecated, use: Module."
                + f"{module_name} in device.modules instead"
            )
        )
    else:
        ctx = pytest.raises(
            AttributeError, match=f"Device has no attribute '{attribute_name}'"
        )

    with ctx:
        if args:
            await getattr(dev, attribute_name)(*args)
        else:
            attribute_val = getattr(dev, attribute_name)
            assert attribute_val is not None


async def test_deprecated_light_effect_attributes(dev: Device):
    light_effect = dev.modules.get(Module.LightEffect)

    await _test_attribute(dev, "effect", bool(light_effect), "LightEffect")
    await _test_attribute(dev, "effect_list", bool(light_effect), "LightEffect")
    await _test_attribute(dev, "set_effect", bool(light_effect), "LightEffect", "Off")
    exc = (
        NotImplementedError
        if light_effect and not light_effect.has_custom_effects
        else None
    )
    await _test_attribute(
        dev,
        "set_custom_effect",
        bool(light_effect),
        "LightEffect",
        {"enable": 0, "name": "foo", "id": "bar"},
        will_raise=exc,
    )


async def test_deprecated_light_attributes(dev: Device):
    light = dev.modules.get(Module.Light)

    await _test_attribute(dev, "is_dimmable", bool(light), "Light")
    await _test_attribute(dev, "is_color", bool(light), "Light")
    await _test_attribute(dev, "is_variable_color_temp", bool(light), "Light")

    exc = KasaException if light and not light.is_dimmable else None
    await _test_attribute(dev, "brightness", bool(light), "Light", will_raise=exc)
    await _test_attribute(
        dev, "set_brightness", bool(light), "Light", 50, will_raise=exc
    )

    exc = KasaException if light and not light.is_color else None
    await _test_attribute(dev, "hsv", bool(light), "Light", will_raise=exc)
    await _test_attribute(
        dev, "set_hsv", bool(light), "Light", 50, 50, 50, will_raise=exc
    )

    exc = KasaException if light and not light.is_variable_color_temp else None
    await _test_attribute(dev, "color_temp", bool(light), "Light", will_raise=exc)
    await _test_attribute(
        dev, "set_color_temp", bool(light), "Light", 2700, will_raise=exc
    )
    await _test_attribute(
        dev, "valid_temperature_range", bool(light), "Light", will_raise=exc
    )

    await _test_attribute(dev, "has_effects", bool(light), "Light")


async def test_deprecated_other_attributes(dev: Device):
    led_module = dev.modules.get(Module.Led)

    await _test_attribute(dev, "led", bool(led_module), "Led")
    await _test_attribute(dev, "set_led", bool(led_module), "Led", True)


async def test_deprecated_light_preset_attributes(dev: Device):
    preset = dev.modules.get(Module.LightPreset)

    exc: type[AttributeError] | type[KasaException] | None = (
        AttributeError if not preset else None
    )
    await _test_attribute(dev, "presets", bool(preset), "LightPreset", will_raise=exc)

    exc = None
    # deprecated save_preset not implemented for smart devices as it's unlikely anyone
    # has an existing reliance on this for the newer devices.
    if not preset or isinstance(dev, SmartDevice):
        exc = AttributeError
    elif len(preset.preset_states_list) == 0:
        exc = KasaException
    await _test_attribute(
        dev,
        "save_preset",
        bool(preset),
        "LightPreset",
        IotLightPreset(index=0, hue=100, brightness=100, saturation=0, color_temp=0),  # type: ignore[call-arg]
        will_raise=exc,
    )
