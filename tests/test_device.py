"""Tests for all devices."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
import zoneinfo
from contextlib import AbstractContextManager, nullcontext
from unittest.mock import AsyncMock, patch

import pytest

import kasa
from kasa import Credentials, Device, DeviceConfig, DeviceType, KasaException, Module
from kasa.iot import (
    IotBulb,
    IotDevice,
    IotDimmer,
    IotLightStrip,
    IotPlug,
    IotStrip,
    IotWallSwitch,
)
from kasa.iot.iottimezone import (
    TIMEZONE_INDEX,
    get_timezone,
    get_timezone_index,
)
from kasa.iot.modules import IotLightPreset
from kasa.smart import SmartChildDevice, SmartDevice
from kasa.smartcam import SmartCamDevice


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
    return sorted(subclasses)


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


@device_classes
async def test_device_class_repr(device_class_name_obj):
    """Test device repr when update() not called and no discovery info."""
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

    CLASS_TO_DEFAULT_TYPE = {
        IotDevice: DeviceType.Unknown,
        IotBulb: DeviceType.Bulb,
        IotPlug: DeviceType.Plug,
        IotDimmer: DeviceType.Dimmer,
        IotStrip: DeviceType.Strip,
        IotWallSwitch: DeviceType.WallSwitch,
        IotLightStrip: DeviceType.LightStrip,
        SmartChildDevice: DeviceType.Unknown,
        SmartDevice: DeviceType.Unknown,
        SmartCamDevice: DeviceType.Camera,
    }
    type_ = CLASS_TO_DEFAULT_TYPE[klass]
    child_repr = "<DeviceType.Unknown(child) of <DeviceType.Unknown at 127.0.0.2 - update() needed>>"
    not_child_repr = f"<{type_} at 127.0.0.2 - update() needed>"
    expected_repr = child_repr if klass is SmartChildDevice else not_child_repr
    assert repr(dev) == expected_repr


async def test_create_device_with_timeout():
    """Make sure timeout is passed to the protocol."""
    host = "127.0.0.1"
    dev = IotDevice(host, config=DeviceConfig(host, timeout=100))
    assert dev.protocol._transport._timeout == 100
    dev = SmartDevice(host, config=DeviceConfig(host, timeout=100))
    assert dev.protocol._transport._timeout == 100


async def test_create_thin_wrapper():
    """Make sure thin wrapper is created with the correct device type."""
    mock = AsyncMock()
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
    ("device_class", "use_class"), kasa.deprecated_smart_devices.items()
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
    ("deprecated_class", "use_class"), kasa.deprecated_classes.items()
)
def test_deprecated_classes(deprecated_class, use_class):
    msg = f"{deprecated_class} is deprecated, use {use_class.__name__} instead"
    with pytest.deprecated_call(match=msg):
        getattr(kasa, deprecated_class)
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
        ctx: AbstractContextManager | nullcontext = pytest.raises(will_raise)
        dep_context: pytest.WarningsRecorder | nullcontext = pytest.deprecated_call(
            match=(f"{attribute_name} is deprecated, use:")
        )
    elif is_expected:
        ctx = nullcontext()
        dep_context = pytest.deprecated_call(
            match=(f"{attribute_name} is deprecated, use:")
        )
    else:
        ctx = pytest.raises(
            AttributeError, match=f"Device has no attribute '{attribute_name}'"
        )
        dep_context = nullcontext()

    with dep_context, ctx:
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
    await _test_attribute(dev, "supported_modules", True, None)


async def test_deprecated_emeter_attributes(dev: Device):
    energy_module = dev.modules.get(Module.Energy)

    await _test_attribute(dev, "get_emeter_realtime", bool(energy_module), "Energy")
    await _test_attribute(dev, "emeter_realtime", bool(energy_module), "Energy")
    await _test_attribute(dev, "emeter_today", bool(energy_module), "Energy")
    await _test_attribute(dev, "emeter_this_month", bool(energy_module), "Energy")
    await _test_attribute(dev, "current_consumption", bool(energy_module), "Energy")
    await _test_attribute(dev, "get_emeter_daily", bool(energy_module), "Energy")
    await _test_attribute(dev, "get_emeter_monthly", bool(energy_module), "Energy")


async def test_deprecated_light_preset_attributes(dev: Device):
    preset = dev.modules.get(Module.LightPreset)

    exc: type[AttributeError] | type[KasaException] | None = (
        AttributeError if not preset else None
    )
    await _test_attribute(dev, "presets", bool(preset), "LightPreset", will_raise=exc)

    exc = None
    is_expected = bool(preset)
    # deprecated save_preset not implemented for smart devices as it's unlikely anyone
    # has an existing reliance on this for the newer devices.
    if isinstance(dev, SmartDevice):
        is_expected = False

    if preset and len(preset.preset_states_list) == 0:
        exc = KasaException

    await _test_attribute(
        dev,
        "save_preset",
        is_expected,
        "LightPreset",
        IotLightPreset(index=0, hue=100, brightness=100, saturation=0, color_temp=0),  # type: ignore[call-arg]
        will_raise=exc,
    )


async def test_device_type_aliases():
    """Test that the device type aliases in Device work."""

    def _mock_connect(config, *args, **kwargs):
        mock = AsyncMock()
        mock.config = config
        return mock

    with patch("kasa.device_factory.connect", side_effect=_mock_connect):
        dev = await Device.connect(
            config=Device.Config(
                host="127.0.0.1",
                credentials=Device.Credentials(username="user", password="foobar"),  # noqa: S106
                connection_type=Device.ConnectionParameters(
                    device_family=Device.Family.SmartKasaPlug,
                    encryption_type=Device.EncryptionType.Klap,
                    login_version=2,
                ),
            )
        )
        assert isinstance(dev.config, DeviceConfig)
        assert DeviceType.Dimmer == Device.Type.Dimmer


async def test_device_timezones():
    """Test the timezone data is good."""
    # Check all indexes return a zoneinfo
    for i in range(110):
        tz = await get_timezone(i)
        assert tz
        assert tz != zoneinfo.ZoneInfo("Etc/UTC"), f"{i} is default Etc/UTC"

    # Check an unexpected index returns a UTC default.
    tz = await get_timezone(110)
    assert tz == zoneinfo.ZoneInfo("Etc/UTC")

    # Get an index from a timezone
    for index, zone in TIMEZONE_INDEX.items():
        zone_info = zoneinfo.ZoneInfo(zone)
        found_index = await get_timezone_index(zone_info)
        assert found_index == index

    # Try a timezone not hardcoded finds another match
    index = await get_timezone_index(zoneinfo.ZoneInfo("Asia/Katmandu"))
    assert index == 77

    # Try a timezone not hardcoded no match
    with pytest.raises(zoneinfo.ZoneInfoNotFoundError):
        await get_timezone_index(zoneinfo.ZoneInfo("Foo/bar"))
