import json
import re
from datetime import datetime
from unittest.mock import ANY, PropertyMock, patch
from zoneinfo import ZoneInfo

import asyncclick as click
import pytest
from asyncclick.testing import CliRunner
from pytest_mock import MockerFixture

from kasa import (
    AuthenticationError,
    ColorTempRange,
    Credentials,
    Device,
    DeviceError,
    DeviceType,
    DiscoveryAuthenticationError,
    EmeterStatus,
    KasaException,
    Module,
    UnsupportedAuthenticationError,
    UnsupportedDeviceError,
)
from kasa.cli.device import (
    alias,
    factory_reset,
    led,
    reboot,
    state,
    sysinfo,
    toggle,
    update_credentials,
)
from kasa.cli.discover import _format_connection_options, echo_discovery_info
from kasa.cli.light import (
    brightness,
    effect,
    hsv,
    presets,
    presets_modify,
    temperature,
)
from kasa.cli.main import TYPES, _iot_type_to_class, cli, cmd_command, raw_command
from kasa.cli.time import time
from kasa.cli.usage import energy
from kasa.cli.wifi import wifi
from kasa.device_factory import get_protocol
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.discover import DiscoveryResult, redact_data
from kasa.iot import IotDevice, IotPlug
from kasa.json import dumps as json_dumps
from kasa.smart import SmartDevice
from kasa.smartcam import SmartCamDevice
from kasa.transports import KlapTransport, KlapTransportV2

from .conftest import (
    device_iot,
    device_smart,
    device_smartcam,
    get_device_for_fixture_protocol,
    handle_turn_on,
    new_discovery,
    parametrize_combine,
    turn_on,
)
from .discovery_fixtures import get_device_class_from_discovery

# The cli tests should be testing the cli logic rather than a physical device
# so mark the whole file for skipping with real devices.
pytestmark = [pytest.mark.requires_dummy]


def _iot_klap_tdp_response(host: str = "127.0.0.1") -> dict:
    """Return a representative IOT KLAP TDP discovery response."""
    return {
        "discovery_response": {
            "result": {
                "device_type": "IOT.SMARTPLUGSWITCH",
                "device_model": "HS300(US)",
                "device_id": "device-id",
                "ip": host,
                "mac": "00-00-00-00-00-00",
                "mgt_encrypt_schm": {
                    "is_support_https": False,
                    "encrypt_type": "KLAP",
                    "http_port": 80,
                    "lv": 2,
                    "new_klap": 1,
                },
            },
            "error_code": 0,
        },
        "meta": {"ip": host, "port": 20002, "source": "tdp"},
    }


def test_echo_wrapped_tdp_discovery_info(mocker) -> None:
    """Wrapped TDP results use the structured CLI formatter."""
    echo = mocker.patch("kasa.cli.discover.echo")
    discovery_info = {
        "result": {
            "device_type": "IOT.SMARTPLUGSWITCH",
            "device_model": "KP115(US)",
            "device_id": "device-id",
            "ip": "127.0.0.1",
            "mac": "00-00-00-00-00-00",
            "mgt_encrypt_schm": {
                "is_support_https": False,
                "encrypt_type": "KLAP",
                "http_port": 80,
                "lv": 2,
            },
        },
        "error_code": 0,
    }

    echo_discovery_info(discovery_info)

    assert any("Discovery Result" in call.args[0] for call in echo.call_args_list)
    assert not any(
        "Discovery information" in call.args[0] for call in echo.call_args_list
    )


def test_connection_options_use_canonical_long_names() -> None:
    """Generated connection options use stable, descriptive names."""
    config = DeviceConfig(
        host="127.0.0.1",
        connection_type=DeviceConnectionParameters(
            DeviceFamily.IotSmartPlugSwitch,
            DeviceEncryptionType.Klap,
            login_version=2,
            klap_version=1,
        ),
    )
    assert _format_connection_options(config.connection_type) == (
        "--device-family IOT.SMARTPLUGSWITCH --encrypt-type KLAP "
        "--login-version 2 --klap-version 1 --no-https"
    )


async def test_help(runner):
    """Test that lazy modules and direct connection aliases are exposed."""
    res = await runner.invoke(cli, ["--help"])
    assert res.exit_code == 0, "--help failed, check lazy module names"
    for option_names in (
        "-df, --device-family",
        "-e, --encrypt-type",
        "-lv, --login-version",
        "-kv, --klap-version",
    ):
        assert option_names in res.output


async def test_update_called_by_cli(dev, mocker, runner):
    """Test that device update is called on main."""
    update = mocker.patch.object(dev, "update")

    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    mocker.patch("kasa.discover.Discover.discover_single", return_value=dev)

    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--username",
            "foo",
            "--password",
            "bar",
        ],
        catch_exceptions=False,
    )
    assert res.exit_code == 0
    update.assert_called()


@pytest.mark.parametrize(
    "option",
    [
        pytest.param(("--device-family", "SMART.TAPOPLUG"), id="device-family"),
        pytest.param(("--encrypt-type", "KLAP"), id="encrypt-type"),
        pytest.param(("--login-version", "2"), id="login-version"),
        pytest.param(("--klap-version", "1"), id="klap-version"),
        pytest.param(("--https",), id="https"),
    ],
)
async def test_incomplete_direct_connection_options_are_rejected(runner, option):
    """Advanced direct connection options must not be silently ignored."""
    res = await runner.invoke(cli, ["--host", "127.0.0.1", *option])

    assert res.exit_code == 2
    assert "require both --device-family and --encrypt-type" in res.output


async def test_list_devices(discovery_mock, runner):
    """Test that device update is called on main."""
    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar", "discover", "list"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0
    header = (
        f"{'HOST':<15} {'MODEL':<9} {'DEVICE FAMILY':<20} {'ENCRYPT':<7} "
        f"{'HTTPS':<5} {'LV':<3} {'KV':<3} {'SOURCE':<9} {'ALIAS / RESULT'}"
    )
    source = (
        "UDP/9999"
        if discovery_mock.discovery_port == 9999
        else f"TDP/{discovery_mock.discovery_port}"
    )
    row = (
        f"{discovery_mock.ip:<15} {discovery_mock.model:<9} {discovery_mock.device_type:<20} "
        f"{discovery_mock.encrypt_type:<7} {str(discovery_mock.https):<5} "
        f"{discovery_mock.login_version or '-':<3} "
        f"{discovery_mock.klap_version or '-':<3} "
        f"{source:<9}"
    )
    output = res.output.replace("\n", "")
    assert header in output
    assert row in output


async def test_list_hostname_uses_single_resolved_host(mocker, runner):
    """A targeted hostname produces one row keyed by the resolved address."""
    host = "device.local"
    ip = "127.0.0.1"
    connection_type = DeviceConnectionParameters(
        DeviceFamily.IotSmartPlugSwitch,
        DeviceEncryptionType.Xor,
    )
    device = mocker.MagicMock(spec=Device)
    device.host = ip
    device.model = "HS100"
    device.alias = "Plug"
    device.config = DeviceConfig(ip, connection_type=connection_type)
    device.update = mocker.AsyncMock()
    device.disconnect = mocker.AsyncMock()
    raw_response = {
        "meta": {"ip": ip, "port": 9999, "source": "udp"},
        "discovery_response": {
            "system": {
                "get_sysinfo": {
                    "type": DeviceFamily.IotSmartPlugSwitch.value,
                    "model": device.model,
                }
            }
        },
    }

    async def discover_single(requested_host, **kwargs):
        kwargs["on_discovered_raw"](raw_response)
        await kwargs["on_discovered"](device)
        device.host = requested_host
        return device

    mocker.patch(
        "kasa.cli.discover.Discover.discover_single",
        side_effect=discover_single,
    )

    res = await runner.invoke(
        cli,
        ["--host", host, "discover", "list"],
        catch_exceptions=False,
    )

    assert res.exit_code == 0
    expected = (
        f"{ip:<15} {'HS100':<9} {DeviceFamily.IotSmartPlugSwitch.value:<20} "
        f"{'XOR':<7} {'False':<5} {'-':<3} {'-':<3} "
        f"{'UDP/9999':<9} Plug"
    )
    output = res.output.replace("\n", "")
    assert expected in output
    assert output.count(DeviceFamily.IotSmartPlugSwitch.value) == 1
    device.disconnect.assert_awaited_once()


async def test_discover_raw(discovery_mock, runner, mocker):
    """Test the discover raw command."""
    redact_spy = mocker.patch("kasa.cli.discover.redact_data", side_effect=redact_data)
    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar", "discover", "raw"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0

    expected = {
        "discovery_response": discovery_mock.discovery_data,
        "meta": {
            "ip": "127.0.0.123",
            "port": discovery_mock.discovery_port,
            "source": "udp" if discovery_mock.discovery_port == 9999 else "tdp",
        },
    }
    assert res.output == json_dumps(expected, indent=True) + "\n"

    redact_spy.assert_not_called()

    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar", "discover", "raw", "--redact"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0

    redact_spy.assert_called()


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        pytest.param(
            AuthenticationError("Failed to authenticate"),
            "Authentication failed",
            id="auth",
        ),
        pytest.param(
            UnsupportedDeviceError("Unsupported after discovery"),
            "Unsupported device",
            id="unsupported",
        ),
        pytest.param(TimeoutError(), "Timed out", id="timeout"),
        pytest.param(Exception("Foobar"), "Error: Foobar", id="other-error"),
    ],
)
@new_discovery
async def test_list_update_failed(discovery_mock, mocker, runner, exception, expected):
    """Test that device update is called on main."""
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    mocker.patch.object(
        device_class,
        "update",
        side_effect=exception,
    )
    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar", "discover", "list"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0
    header = (
        f"{'HOST':<15} {'MODEL':<9} {'DEVICE FAMILY':<20} {'ENCRYPT':<7} "
        f"{'HTTPS':<5} {'LV':<3} {'KV':<3} {'SOURCE':<9} {'ALIAS / RESULT'}"
    )
    source = (
        "UDP/9999"
        if discovery_mock.discovery_port == 9999
        else f"TDP/{discovery_mock.discovery_port}"
    )
    row = (
        f"{discovery_mock.ip:<15} {discovery_mock.model:<9} {discovery_mock.device_type:<20} "
        f"{discovery_mock.encrypt_type:<7} {str(discovery_mock.https):<5} "
        f"{discovery_mock.login_version or '-':<3} "
        f"{discovery_mock.klap_version or '-':<3} "
        f"{source:<9} {expected}"
    )
    assert header in res.output.replace("\n", "")
    assert row in res.output.replace("\n", "")


async def test_list_unsupported(unsupported_device_info, runner):
    """Test that device update is called on main."""
    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar", "discover", "list"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0
    header = (
        f"{'HOST':<15} {'MODEL':<9} {'DEVICE FAMILY':<20} {'ENCRYPT':<7} "
        f"{'HTTPS':<5} {'LV':<3} {'KV':<3} {'SOURCE':<9} {'ALIAS / RESULT'}"
    )
    output = res.output.replace("\n", "")
    assert header in output
    assert "127.0.0.1" in res.output
    assert "TDP/20002" in res.output
    assert "Unsupported device" in res.output


async def test_list_authentication_failure_before_device_creation(mocker, runner):
    """List uses the same complete row when authentication blocks creation."""
    host = "127.0.0.1"
    raw_response = _iot_klap_tdp_response(host)

    async def discover(**kwargs):
        kwargs["on_discovered_raw"](raw_response)
        await kwargs["on_authentication_error"](
            DiscoveryAuthenticationError(
                "Authentication failed",
                host=host,
                discovery_result=raw_response["discovery_response"],
            )
        )
        return {}

    mocker.patch("kasa.cli.discover.Discover.discover", side_effect=discover)

    res = await runner.invoke(
        cli,
        ["--discovery-timeout", "0", "discover", "list"],
        catch_exceptions=False,
    )

    assert res.exit_code == 0
    expected = (
        f"{host:<15} {'HS300':<9} {'IOT.SMARTPLUGSWITCH':<20} "
        f"{'KLAP':<7} {'False':<5} {'2':<3} {'1':<3} "
        f"{'TDP/20002':<9} Authentication failed"
    )
    assert expected in res.output.replace("\n", "")


async def test_sysinfo(dev: Device, runner):
    res = await runner.invoke(sysinfo, obj=dev)
    assert "System info" in res.output
    assert dev.model in res.output


@turn_on
async def test_state(dev, turn_on, runner):
    await handle_turn_on(dev, turn_on)
    await dev.update()
    res = await runner.invoke(state, obj=dev)

    if dev.is_on:
        assert "Device state: True" in res.output
    else:
        assert "Device state: False" in res.output


@turn_on
async def test_toggle(dev, turn_on, runner):
    if isinstance(dev, SmartCamDevice) and dev.device_type == DeviceType.Hub:
        pytest.skip(reason="Hub cannot toggle state")

    await handle_turn_on(dev, turn_on)
    await dev.update()
    assert dev.is_on == turn_on

    await runner.invoke(toggle, obj=dev)
    await dev.update()
    assert dev.is_on != turn_on


async def test_alias(dev, runner):
    res = await runner.invoke(alias, obj=dev)
    assert f"Alias: {dev.alias}" in res.output

    old_alias = dev.alias

    new_alias = "new alias"
    res = await runner.invoke(alias, [new_alias], obj=dev)
    assert f"Setting alias to {new_alias}" in res.output
    await dev.update()

    res = await runner.invoke(alias, obj=dev)
    assert f"Alias: {new_alias}" in res.output

    # If alias is None set it back to empty string
    await dev.set_alias(old_alias or "")


async def test_raw_command(dev, mocker, runner):
    update = mocker.patch.object(dev, "update")
    from kasa.smart import SmartDevice

    if isinstance(dev, SmartCamDevice):
        params = [
            "na",
            "getDeviceInfo",
            '{"device_info": {"name": ["basic_info", "info"]}}',
        ]
    elif isinstance(dev, SmartDevice):
        params = ["na", "get_device_info"]
    else:
        params = ["system", "get_sysinfo"]
    res = await runner.invoke(raw_command, params, obj=dev)

    # Make sure that update was not called for wifi
    with pytest.raises(AssertionError):
        update.assert_called()

    assert res.exit_code == 0
    assert dev.model in res.output

    res = await runner.invoke(raw_command, obj=dev)
    assert res.exit_code != 0
    assert "Usage" in res.output


async def test_command_with_child(dev, mocker, runner):
    """Test 'command' command with --child."""
    update_mock = mocker.patch.object(dev, "update")

    # create_autospec for device slows tests way too much, so we use a dummy here
    class DummyDevice(dev.__class__):
        def __init__(self):
            super().__init__("127.0.0.1")
            # device_type and _info initialised for repr
            self._device_type = Device.Type.StripSocket
            self._info = {}

        async def _query_helper(*_, **__):
            return {"dummy": "response"}

    dummy_child = DummyDevice()

    mocker.patch.object(dev, "_children", {"XYZ": [dummy_child]})
    mocker.patch.object(dev, "get_child_device", return_value=dummy_child)

    res = await runner.invoke(
        cmd_command,
        ["--child", "XYZ", "command", "'params'"],
        obj=dev,
        catch_exceptions=False,
    )

    update_mock.assert_called()
    assert '{"dummy": "response"}' in res.output
    assert res.exit_code == 0


@device_smart
async def test_reboot(dev, mocker, runner):
    """Test that reboot works on SMART devices."""
    query_mock = mocker.patch.object(dev.protocol, "query")

    res = await runner.invoke(
        reboot,
        obj=dev,
    )

    query_mock.assert_called()
    assert res.exit_code == 0


@device_smart
async def test_factory_reset(dev, mocker, runner):
    """Test that factory reset works on SMART devices."""
    query_mock = mocker.patch.object(dev.protocol, "query")

    res = await runner.invoke(
        factory_reset,
        obj=dev,
        input="y\n",
    )

    query_mock.assert_called()
    assert res.exit_code == 0


@device_smart
async def test_wifi_scan(dev, runner):
    res = await runner.invoke(wifi, ["scan"], obj=dev)

    assert res.exit_code == 0
    assert re.search(r"Found [\d]+ wifi networks!", res.output)


@parametrize_combine([device_smart, device_iot])
async def test_wifi_join(dev, mocker, runner):
    update = mocker.patch.object(dev, "update")
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--keytype", "3", "--password", "foobar"],
        obj=dev,
    )

    # Make sure that update was not called for wifi
    with pytest.raises(AssertionError):
        update.assert_called()

    assert res.exit_code == 0
    assert "Asking the device to connect to FOOBAR" in res.output


@parametrize_combine([device_smart, device_iot])
async def test_wifi_join_missing_keytype(dev, mocker, runner):
    """Test that missing keytype raises KasaException and CLI echoes the message."""
    update = mocker.patch.object(dev, "update")
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--password", "foobar"],
        obj=dev,
    )

    # Make sure that update was not called for wifi
    with pytest.raises(AssertionError):
        update.assert_called()

    assert res.exit_code == 0
    assert "KeyType is required for this device." in res.output


@device_smartcam
async def test_wifi_join_smartcam(dev, mocker, runner):
    update = mocker.patch.object(dev, "update")
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--password", "foobar"],
        obj=dev,
    )

    # Make sure that update was not called for wifi
    with pytest.raises(AssertionError):
        update.assert_called()

    assert res.exit_code == 0
    assert "Asking the device to connect to FOOBAR" in res.output


@device_smart
async def test_wifi_join_no_creds(dev, runner):
    dev.protocol._transport._credentials = None
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--keytype", "wpa_psk", "--password", "foobar"],
        obj=dev,
    )

    assert res.exit_code != 0
    assert isinstance(res.exception, AuthenticationError)


@device_smart
async def test_wifi_join_exception(dev, mocker, runner):
    mocker.patch.object(dev.protocol, "query", side_effect=DeviceError(error_code=9999))
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--keytype", "wpa_psk", "--password", "foobar"],
        obj=dev,
    )

    assert res.exit_code != 0
    assert isinstance(res.exception, KasaException)


@device_smart
async def test_update_credentials(dev, runner):
    res = await runner.invoke(
        update_credentials,
        ["--username", "foo", "--password", "bar"],
        input="y\n",
        obj=dev,
    )

    assert res.exit_code == 0
    assert (
        "Do you really want to replace the existing credentials? [y/N]: y\n"
        in res.output
    )


async def test_time_get(dev, runner):
    """Test time get command."""
    res = await runner.invoke(
        time,
        obj=dev,
    )
    assert res.exit_code == 0
    assert "Current time: " in res.output


async def test_time_sync(dev, mocker, runner):
    """Test time sync command."""
    update = mocker.patch.object(dev, "update")
    set_time_mock = mocker.spy(dev.modules[Module.Time], "set_time")
    res = await runner.invoke(
        time,
        ["sync"],
        obj=dev,
    )
    set_time_mock.assert_called()
    update.assert_called()

    assert res.exit_code == 0
    assert "Old time: " in res.output
    assert "New time: " in res.output


@parametrize_combine([device_smart, device_iot])
async def test_time_set(dev: Device, mocker, runner):
    """Test time set command."""
    time_mod = dev.modules[Module.Time]
    set_time_mock = mocker.spy(time_mod, "set_time")
    dt = datetime(2024, 10, 15, 8, 15)
    res = await runner.invoke(
        time,
        ["set", str(dt.year), str(dt.month), str(dt.day), str(dt.hour), str(dt.minute)],
        obj=dev,
    )
    set_time_mock.assert_called()
    assert time_mod.time == dt.replace(tzinfo=time_mod.timezone)

    assert res.exit_code == 0
    assert "Old time: " in res.output
    assert "New time: " in res.output

    zone = ZoneInfo("Europe/Berlin")
    dt = dt.replace(tzinfo=zone)
    res = await runner.invoke(
        time,
        [
            "set",
            str(dt.year),
            str(dt.month),
            str(dt.day),
            str(dt.hour),
            str(dt.minute),
            "--timezone",
            zone.key,
        ],
        input="y\n",
        obj=dev,
    )

    assert time_mod.time == dt

    assert res.exit_code == 0
    assert "Old time: " in res.output
    assert "New time: " in res.output


async def test_emeter(dev: Device, mocker, runner):
    mocker.patch("kasa.Discover.discover_single", return_value=dev)
    base_cmd = ["--host", "dummy", "energy"]
    res = await runner.invoke(cli, base_cmd, obj=dev)
    if not (energy := dev.modules.get(Module.Energy)):
        assert "Device has no energy module." in res.output
        return

    assert "== Energy ==" in res.output

    if dev.device_type is not DeviceType.Strip:
        res = await runner.invoke(cli, [*base_cmd, "--index", "0"], obj=dev)
        assert f"Device: {dev.host} does not have children" in res.output
        res = await runner.invoke(cli, [*base_cmd, "--name", "mock"], obj=dev)
        assert f"Device: {dev.host} does not have children" in res.output

    if dev.device_type is DeviceType.Strip and len(dev.children) > 0:
        child_energy = dev.children[0].modules.get(Module.Energy)
        assert child_energy

        with patch.object(
            type(child_energy), "status", new_callable=PropertyMock
        ) as child_status:
            child_status.return_value = EmeterStatus({"voltage_mv": 122066})

            res = await runner.invoke(cli, [*base_cmd, "--index", "0"], obj=dev)
            assert "Voltage: 122.066 V" in res.output
            child_status.assert_called()
            assert child_status.call_count == 1

            res = await runner.invoke(
                cli, [*base_cmd, "--name", dev.children[0].alias], obj=dev
            )
            assert "Voltage: 122.066 V" in res.output
            assert child_status.call_count == 2

    if isinstance(dev, IotDevice):
        monthly = mocker.patch.object(energy, "get_monthly_stats")
        monthly.return_value = {1: 1234}
    res = await runner.invoke(cli, [*base_cmd, "--year", "1900"], obj=dev)
    if not isinstance(dev, IotDevice):
        assert "Device does not support historical statistics" in res.output
        return
    assert "For year" in res.output
    assert "1, 1234" in res.output
    monthly.assert_called_with(year=1900)

    if isinstance(dev, IotDevice):
        daily = mocker.patch.object(energy, "get_daily_stats")
        daily.return_value = {1: 1234}
    res = await runner.invoke(cli, [*base_cmd, "--month", "1900-12"], obj=dev)
    if not isinstance(dev, IotDevice):
        assert "Device has no historical statistics" in res.output
        return
    assert "For month" in res.output
    assert "1, 1234" in res.output
    daily.assert_called_with(year=1900, month=12)


async def test_brightness(dev: Device, runner):
    res = await runner.invoke(brightness, obj=dev)
    if not (light := dev.modules.get(Module.Light)) or not light.has_feature(
        "brightness"
    ):
        assert "This device does not support brightness." in res.output
        return

    res = await runner.invoke(brightness, obj=dev)
    assert f"Brightness: {light.brightness}" in res.output

    res = await runner.invoke(brightness, ["12"], obj=dev)
    assert "Setting brightness" in res.output
    await dev.update()

    res = await runner.invoke(brightness, obj=dev)
    assert "Brightness: 12" in res.output


async def test_color_temperature(dev: Device, runner):
    res = await runner.invoke(temperature, obj=dev)
    if not (light := dev.modules.get(Module.Light)) or not (
        color_temp_feat := light.get_feature("color_temp")
    ):
        assert "Device does not support color temperature" in res.output
        return

    res = await runner.invoke(temperature, obj=dev)
    assert f"Color temperature: {light.color_temp}" in res.output
    valid_range = color_temp_feat.range
    assert isinstance(valid_range, ColorTempRange)
    assert f"(min: {valid_range.min}, max: {valid_range.max})" in res.output

    val = int((valid_range.min + valid_range.max) / 2)
    res = await runner.invoke(temperature, [str(val)], obj=dev)
    assert "Setting color temperature to " in res.output
    await dev.update()

    res = await runner.invoke(temperature, obj=dev)
    assert f"Color temperature: {val}" in res.output
    assert res.exit_code == 0

    invalid_max = valid_range.max + 100
    # Lights that support the maximum range will not get past the click cli range check
    # So can't be tested for the internal range check.
    if invalid_max < 9000:
        res = await runner.invoke(temperature, [str(invalid_max)], obj=dev)
        assert res.exit_code == 1
        assert isinstance(res.exception, ValueError)

    res = await runner.invoke(temperature, [str(9100)], obj=dev)
    assert res.exit_code == 2


async def test_color_hsv(dev: Device, runner: CliRunner):
    res = await runner.invoke(hsv, obj=dev)
    if not (light := dev.modules.get(Module.Light)) or not light.has_feature("hsv"):
        assert "Device does not support colors" in res.output
        return

    res = await runner.invoke(hsv, obj=dev)
    assert f"Current HSV: {light.hsv}" in res.output

    res = await runner.invoke(hsv, ["180", "50", "50"], obj=dev)
    assert "Setting HSV: 180 50 50" in res.output
    assert res.exit_code == 0
    await dev.update()

    res = await runner.invoke(hsv, ["180", "50"], obj=dev)
    assert "Setting a color requires 3 values." in res.output
    assert res.exit_code == 2


async def test_light_effect(dev: Device, runner: CliRunner):
    res = await runner.invoke(effect, obj=dev)
    if not (light_effect := dev.modules.get(Module.LightEffect)):
        assert "Device does not support effects" in res.output
        return

    # Start off with a known state of off
    await light_effect.set_effect(light_effect.LIGHT_EFFECTS_OFF)
    await dev.update()
    assert light_effect.effect == light_effect.LIGHT_EFFECTS_OFF

    res = await runner.invoke(effect, obj=dev)
    assert f"Light effect: {light_effect.effect}" in res.output
    assert res.exit_code == 0

    res = await runner.invoke(effect, [light_effect.effect_list[1]], obj=dev)
    assert f"Setting Effect: {light_effect.effect_list[1]}" in res.output
    assert res.exit_code == 0
    await dev.update()
    assert light_effect.effect == light_effect.effect_list[1]

    res = await runner.invoke(effect, ["foobar"], obj=dev)
    assert f"Effect must be one of: {light_effect.effect_list}" in res.output
    assert res.exit_code == 2


async def test_light_preset(dev: Device, runner: CliRunner):
    res = await runner.invoke(presets, obj=dev)
    if not (light_preset := dev.modules.get(Module.LightPreset)):
        assert "Device does not support light presets" in res.output
        return

    if len(light_preset.preset_states_list) == 0:
        pytest.skip(
            "Some fixtures do not have presets and the api doesn'tsupport creating them"
        )
    # Start off with a known state
    first_name = light_preset.preset_list[1]
    await light_preset.set_preset(first_name)
    await dev.update()
    assert light_preset.preset == first_name

    res = await runner.invoke(presets, obj=dev)
    assert "Brightness" in res.output
    assert res.exit_code == 0

    res = await runner.invoke(
        presets_modify,
        [
            "0",
            "--brightness",
            "12",
        ],
        obj=dev,
    )
    await dev.update()
    assert light_preset.preset_states_list[0].brightness == 12

    res = await runner.invoke(
        presets_modify,
        [
            "0",
        ],
        obj=dev,
    )
    await dev.update()
    assert "Need to supply at least one option to modify." in res.output


async def test_led(dev: Device, runner: CliRunner):
    res = await runner.invoke(led, obj=dev)
    if not (led_module := dev.modules.get(Module.Led)):
        assert "Device does not support led" in res.output
        return

    res = await runner.invoke(led, obj=dev)
    assert f"LED state: {led_module.led}" in res.output
    assert res.exit_code == 0

    res = await runner.invoke(led, ["on"], obj=dev)
    assert "Turning led to True" in res.output
    assert res.exit_code == 0
    await dev.update()
    assert led_module.led is True

    res = await runner.invoke(led, ["off"], obj=dev)
    assert "Turning led to False" in res.output
    assert res.exit_code == 0
    await dev.update()
    assert led_module.led is False


async def test_json_output(dev: Device, mocker, runner):
    """Test that the json output produces correct output."""
    mocker.patch("kasa.Discover.discover_single", return_value=dev)
    # These will mock the features to avoid accessing non-existing ones
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    res = await runner.invoke(cli, ["--host", "127.0.0.1", "--json", "state"], obj=dev)
    assert res.exit_code == 0
    assert json.loads(res.output) == dev.internal_state


@new_discovery
async def test_credentials(discovery_mock, mocker, runner):
    """Test credentials are passed correctly from cli to device."""
    # Patch state to echo username and password
    pass_dev = click.make_pass_decorator(Device)

    @pass_dev
    async def _state(dev: Device):
        if dev.credentials:
            click.echo(
                f"Username:{dev.credentials.username} Password:{dev.credentials.password}"
            )

    mocker.patch("kasa.cli.device.state", new=_state)

    dr = DiscoveryResult.from_dict(discovery_mock.discovery_data["result"])
    connection_type = dr.to_connection_parameters()
    args = [
        "--host",
        "127.0.0.123",
        "--username",
        "foo",
        "--password",
        "bar",
        "--device-family",
        connection_type.device_family.value,
        "--encrypt-type",
        connection_type.encryption_type.value,
    ]
    if connection_type.login_version is not None:
        args += ["--login-version", str(connection_type.login_version)]
    if connection_type.klap_version is not None:
        args += ["--klap-version", str(connection_type.klap_version)]
    args.append("--https" if connection_type.https else "--no-https")

    res = await runner.invoke(
        cli,
        args,
    )
    assert res.exit_code == 0

    assert "Username:foo Password:bar\n" in res.output


async def test_without_device_type(dev, mocker, runner):
    """Test connecting without the device type."""
    discovery_mock = mocker.patch(
        "kasa.discover.Discover.discover_single", return_value=dev
    )
    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--username",
            "foo",
            "--password",
            "bar",
            "--discovery-timeout",
            "7",
        ],
    )
    assert res.exit_code == 0
    discovery_mock.assert_called_once_with(
        "127.0.0.1",
        port=None,
        credentials=Credentials("foo", "bar"),
        credentials_hash=None,
        timeout=5,
        discovery_timeout=7,
        on_discovered=ANY,
        on_unsupported=ANY,
        on_authentication_error=ANY,
        on_discovered_raw=ANY,
    )


async def test_credentials_hash_is_passed_to_discovery(mocker, runner):
    """The global credentials hash must not be ignored by discovery."""
    discover_single = mocker.patch(
        "kasa.discover.Discover.discover_single", return_value=None
    )

    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--credentials-hash",
            "hashed-credentials",
            "discover",
            "raw",
        ],
    )

    assert res.exit_code == 0, res.output
    assert discover_single.call_args.kwargs["credentials_hash"] == "hashed-credentials"


@pytest.mark.parametrize("auth_param", ["--username", "--password"])
async def test_invalid_credential_params(auth_param, runner):
    """Test for handling only one of username or password supplied."""
    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--type",
            "plug",
            auth_param,
            "foo",
        ],
    )
    assert res.exit_code == 2
    assert (
        "Error: Using authentication requires both --username and --password"
        in res.output
    )


async def test_duplicate_target_device(runner):
    """Test that defining both --host or --alias gives an error."""
    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--alias",
            "foo",
        ],
    )
    assert res.exit_code == 2
    assert "Error: Use either --alias or --host, not both." in res.output


async def test_discover(discovery_mock, mocker, runner):
    """Test discovery output."""
    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    res = await runner.invoke(
        cli,
        [
            "--discovery-timeout",
            0,
            "--username",
            "foo",
            "--password",
            "bar",
            "--verbose",
            "discover",
        ],
    )
    assert res.exit_code == 0


async def test_discover_host(discovery_mock, mocker, runner):
    """Test discovery output."""
    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    res = await runner.invoke(
        cli,
        [
            "--discovery-timeout",
            0,
            "--host",
            "127.0.0.123",
            "--username",
            "foo",
            "--password",
            "bar",
            "--verbose",
        ],
    )
    assert res.exit_code == 0


async def test_discover_unsupported(unsupported_device_info, runner):
    """Test discovery output."""
    res = await runner.invoke(
        cli,
        [
            "--discovery-timeout",
            0,
            "--username",
            "foo",
            "--password",
            "bar",
            "--verbose",
            "discover",
        ],
    )
    assert res.exit_code == 0
    assert "== Unsupported device ==" in res.output
    assert "Found 1 devices" in res.output
    assert "Found 1 unsupported devices" in res.output


async def test_host_unsupported(unsupported_device_info, runner):
    """Test discovery output."""
    host = "127.0.0.1"

    res = await runner.invoke(
        cli,
        [
            "--host",
            host,
            "--username",
            "foo",
            "--password",
            "bar",
            "--debug",
        ],
    )

    assert res.exit_code != 0
    assert "== Unsupported device ==" in res.output


@new_discovery
async def test_discover_auth_failed(discovery_mock, mocker, runner):
    """Test discovery output."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    mocker.patch.object(
        device_class,
        "update",
        side_effect=AuthenticationError("Failed to authenticate"),
    )
    res = await runner.invoke(
        cli,
        [
            "--discovery-timeout",
            0,
            "--username",
            "foo",
            "--password",
            "bar",
            "--verbose",
            "discover",
        ],
    )

    assert res.exit_code == 0
    assert "== Authentication failed for device ==" in res.output
    assert "== Discovery Result ==" in res.output
    assert "Found 1 devices" in res.output
    assert "Found 1 devices that failed to authenticate" in res.output


@new_discovery
async def test_discover_update_unsupported(discovery_mock, mocker, runner):
    """A regular unsupported update outcome remains in the device total."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    mocker.patch.object(
        device_class,
        "update",
        side_effect=UnsupportedDeviceError("Unsupported after discovery"),
    )

    res = await runner.invoke(
        cli,
        [
            "--discovery-timeout",
            0,
            "--username",
            "foo",
            "--password",
            "bar",
            "discover",
        ],
    )

    assert res.exit_code == 0
    assert "== Unsupported device ==" in res.output
    assert "Found 1 devices" in res.output
    assert "Found 1 unsupported devices" in res.output


@new_discovery
async def test_discover_update_unsupported_authentication(
    discovery_mock, mocker, runner
):
    """Unsupported onboarding receives specific reset and provisioning advice."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    mocker.patch.object(
        device_class,
        "update",
        side_effect=UnsupportedAuthenticationError(
            "Unsupported authentication",
            host=host,
            onboarding_source="amazon",
        ),
    )

    res = await runner.invoke(
        cli,
        [
            "--discovery-timeout",
            0,
            "--username",
            "foo",
            "--password",
            "bar",
            "discover",
        ],
    )

    assert res.exit_code == 0
    assert "== Unsupported device authentication ==" in res.output
    assert "Onboarding source: amazon" in res.output
    assert "Reset and provision this device" in res.output
    assert "Found 1 devices" in res.output
    assert "Found 1 unsupported devices" in res.output
    assert "failed to authenticate" not in res.output


@new_discovery
async def test_host_auth_failed(discovery_mock, mocker, runner):
    """Test discovery output."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = get_device_class_from_discovery(
        discovery_mock.discovery_data, discovery_mock.query_data
    )
    mocker.patch.object(
        device_class,
        "update",
        side_effect=AuthenticationError("Failed to authenticate"),
    )
    res = await runner.invoke(
        cli,
        [
            "--host",
            host,
            "--username",
            "foo",
            "--password",
            "bar",
            "--debug",
        ],
    )

    assert res.exit_code != 0
    assert "requested device could not be queried" in res.output


@pytest.mark.parametrize("device_type", TYPES)
async def test_type_param(device_type, mocker, runner):
    """Test for handling only one of username or password supplied."""
    result_device = FileNotFoundError
    pass_dev = click.make_pass_decorator(Device)

    @pass_dev
    async def _state(dev: Device):
        nonlocal result_device
        result_device = dev

    mocker.patch("kasa.cli.device.state", new=_state)
    if device_type == "camera":
        expected_type = SmartCamDevice
    elif device_type == "smart":
        expected_type = SmartDevice
    else:
        expected_type = _iot_type_to_class(device_type)
    mocker.patch.object(expected_type, "update")
    res = await runner.invoke(
        cli,
        ["--type", device_type, "--host", "127.0.0.1"],
    )
    assert res.exit_code == 0
    assert isinstance(result_device, expected_type)
    if device_type not in {"smart", "camera"}:
        expected_family = (
            DeviceFamily.IotSmartBulb
            if device_type in {"bulb", "lightstrip"}
            else DeviceFamily.IotSmartPlugSwitch
        )
        assert result_device.config.connection_type.device_family is expected_family


@pytest.mark.parametrize(
    ("cli_login_version", "expected_login_version"),
    [
        pytest.param(None, 2, id="No login-version defaults to 2"),
        pytest.param(3, 3, id="Explicit login-version 3 is preserved"),
        pytest.param(2, 2, id="Explicit login-version 2 is preserved"),
    ],
)
async def test_type_camera_login_version(
    cli_login_version, expected_login_version, mocker, runner
):
    """Test that --type camera respects an explicitly provided --login-version."""
    from kasa.deviceconfig import DeviceConfig

    captured_config: DeviceConfig | None = None

    mocker.patch("kasa.cli.device.state")

    async def _mock_connect(config: DeviceConfig):
        nonlocal captured_config
        captured_config = config
        dev = SmartCamDevice(host="127.0.0.1", config=config)
        return dev

    mocker.patch("kasa.device.Device.connect", side_effect=_mock_connect)
    mocker.patch.object(SmartCamDevice, "update")

    args = ["--type", "camera", "--host", "127.0.0.1"]
    if cli_login_version is not None:
        args += ["--login-version", str(cli_login_version)]

    res = await runner.invoke(cli, args)
    assert res.exit_code == 0, res.output
    assert captured_config is not None
    assert captured_config.connection_type.login_version == expected_login_version


@pytest.mark.parametrize(
    ("login_version", "klap_version", "expected_transport"),
    [
        pytest.param(None, None, KlapTransport, id="advertised-values-absent"),
        pytest.param(2, None, KlapTransport, id="login-version-is-not-klap-v2"),
        pytest.param(2, 1, KlapTransportV2, id="klap-version-selects-v2"),
    ],
)
async def test_iot_klap_direct_connection_versions(
    login_version, klap_version, expected_transport, mocker, runner
):
    """IOT KLAP generation is independent from the login version."""
    captured_config = None
    mocker.patch("kasa.cli.device.state")

    async def _mock_connect(config):
        nonlocal captured_config
        captured_config = config
        return IotPlug(config.host, config=config)

    mocker.patch("kasa.device.Device.connect", side_effect=_mock_connect)
    args = [
        "--host",
        "127.0.0.1",
        "-df",
        "IOT.SMARTPLUGSWITCH",
        "-e",
        "KLAP",
    ]
    if login_version is not None:
        args += ["-lv", str(login_version)]
    if klap_version is not None:
        args += ["-kv", str(klap_version)]

    res = await runner.invoke(cli, args)

    assert res.exit_code == 0, res.output
    assert captured_config is not None
    assert captured_config.connection_type.login_version == login_version
    assert captured_config.connection_type.klap_version == klap_version
    protocol = get_protocol(captured_config)
    assert protocol is not None
    assert isinstance(protocol._transport, expected_transport)
    await protocol.close()


@pytest.mark.parametrize(
    ("args", "expected_error"),
    [
        pytest.param(
            ["--type", "smart", "discover"],
            "--type configures a direct connection and cannot be used with discover",
            id="direct-type-discover",
        ),
        pytest.param(
            ["--type", "plug", "--encrypt-type", "KLAP"],
            "--encrypt-type is not used with IOT --type plug",
            id="iot-unused-encryption",
        ),
        pytest.param(
            [
                "--device-family",
                "SMART.TAPOPLUG",
                "--encrypt-type",
                "KLAP",
                "--klap-version",
                "1",
            ],
            "--klap-version is only used by IOT devices",
            id="smart-klap-version",
        ),
        pytest.param(
            [
                "--device-family",
                "IOT.SMARTPLUGSWITCH",
                "--encrypt-type",
                "XOR",
                "--klap-version",
                "1",
            ],
            "--klap-version requires --encrypt-type KLAP",
            id="non-klap-klap-version",
        ),
    ],
)
async def test_incompatible_direct_connection_options_are_rejected(
    runner, args, expected_error
):
    """Connection flags that cannot affect the selected path must fail."""
    if "discover" not in args:
        args = ["--host", "127.0.0.1", *args]

    res = await runner.invoke(cli, args)

    assert res.exit_code == 2
    assert expected_error in res.output


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["--port", "0"], id="invalid-port"),
        pytest.param(
            [
                "--device-family",
                "SMART.UNKNOWN",
                "--encrypt-type",
                "KLAP",
            ],
            id="unknown-family",
        ),
        pytest.param(
            [
                "--device-family",
                "SMART.IPCAMERA",
                "--encrypt-type",
                "KLAP",
                "--https",
            ],
            id="unsupported-exact-route",
        ),
        pytest.param(
            [
                "--device-family",
                "SMART.IPCAMERA",
                "--encrypt-type",
                "AES",
                "--no-https",
            ],
            id="unconstructible-exact-route",
        ),
    ],
)
async def test_invalid_connection_option_values_are_rejected(runner, args):
    """Direct connection values are constrained to routes the CLI can use."""
    res = await runner.invoke(cli, ["--host", "127.0.0.1", *args])

    assert res.exit_code == 2


@pytest.mark.skip(
    "Skip until pytest-asyncio supports pytest 8.0, https://github.com/pytest-dev/pytest-asyncio/issues/737"
)
async def test_shell(dev: Device, mocker, runner):
    """Test that the shell commands tries to embed a shell."""
    mocker.patch("kasa.Discover.discover", return_value=[dev])
    # repl = mocker.patch("ptpython.repl")
    mocker.patch.dict(
        "sys.modules",
        {"ptpython": mocker.MagicMock(), "ptpython.repl": mocker.MagicMock()},
    )
    embed = mocker.patch("ptpython.repl.embed")
    res = await runner.invoke(cli, ["shell"], obj=dev)
    assert res.exit_code == 0
    embed.assert_called()


async def test_errors(mocker, runner):
    err = KasaException("Foobar")

    # Test masking
    mocker.patch("kasa.Discover.discover", side_effect=err)
    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar"],
    )
    assert res.exit_code == 1
    assert "Raised error: Foobar" in res.output
    assert "Run with --debug enabled to see stacktrace" in res.output
    assert isinstance(res.exception, SystemExit)

    # Test --debug
    res = await runner.invoke(
        cli,
        ["--debug"],
    )
    assert res.exit_code == 1
    assert "Raised error: Foobar" in res.output
    assert res.exception == err

    # Test no device passed to subcommand
    mocker.patch("kasa.Discover.discover", return_value={})
    res = await runner.invoke(
        cli,
        ["sysinfo"],
    )
    assert res.exit_code == 1
    assert (
        "Only discover is available without --host or --alias"
        in res.output.replace("\n", "")  # Remove newlines from rich formatting
    )
    assert isinstance(res.exception, SystemExit)

    # Test click error
    res = await runner.invoke(
        cli,
        ["--foobar"],
    )
    assert res.exit_code == 2
    assert "Raised error:" not in res.output


async def test_feature(mocker, runner):
    """Test feature command."""
    dummy_device = await get_device_for_fixture_protocol(
        "P300(EU)_1.0_1.0.13.json", "SMART"
    )
    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)
    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature"],
        catch_exceptions=False,
    )
    assert "LED" in res.output
    assert "== Child " in res.output  # child listing

    assert res.exit_code == 0


async def test_features_all(discovery_mock, mocker, runner):
    """Test feature command on all fixtures."""
    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature"],
        catch_exceptions=False,
    )
    assert "== Primary features ==" in res.output
    assert "== Information ==" in res.output
    assert "== Configuration ==" in res.output
    assert "== Debug ==" in res.output
    assert res.exit_code == 0


async def test_feature_single(mocker, runner):
    """Test feature command returning single value."""
    dummy_device = await get_device_for_fixture_protocol(
        "P300(EU)_1.0_1.0.13.json", "SMART"
    )
    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)
    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature", "led"],
        catch_exceptions=False,
    )
    assert "LED" in res.output
    assert "== Features ==" not in res.output
    assert res.exit_code == 0


async def test_feature_missing(mocker, runner):
    """Test feature command returning single value."""
    dummy_device = await get_device_for_fixture_protocol(
        "P300(EU)_1.0_1.0.13.json", "SMART"
    )
    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)
    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature", "missing"],
        catch_exceptions=False,
    )
    assert "No feature by name 'missing'" in res.output
    assert "== Features ==" not in res.output
    assert res.exit_code == 1


async def test_feature_set(mocker, runner):
    """Test feature command's set value."""
    dummy_device = await get_device_for_fixture_protocol(
        "P300(EU)_1.0_1.0.13.json", "SMART"
    )
    led_setter = mocker.patch("kasa.smart.modules.led.Led.set_led")
    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)

    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature", "led", "True"],
        catch_exceptions=False,
    )

    led_setter.assert_called_with(True)
    assert "Changing led from True to True" in res.output
    assert res.exit_code == 0


async def test_feature_set_child(mocker, runner):
    """Test feature command's set value."""
    dummy_device = await get_device_for_fixture_protocol(
        "P300(EU)_1.0_1.0.13.json", "SMART"
    )
    setter = mocker.patch("kasa.smart.smartdevice.SmartDevice.set_state")

    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)
    get_child_device = mocker.spy(dummy_device, "get_child_device")

    child_id = "SCRUBBED_CHILD_DEVICE_ID_1"

    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.123",
            "--debug",
            "feature",
            "--child",
            child_id,
            "state",
            "True",
        ],
        catch_exceptions=False,
    )

    get_child_device.assert_called()
    setter.assert_called_with(True)

    assert f"Targeting child device {child_id}"
    assert "Changing state from False to True" in res.output
    assert res.exit_code == 0


async def test_feature_set_unquoted(mocker, runner):
    """Test feature command's set value."""
    dummy_device = await get_device_for_fixture_protocol(
        "ES20M(US)_1.0_1.0.11.json", "IOT"
    )
    range_setter = mocker.patch("kasa.iot.modules.motion.Motion._set_range_from_str")
    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)

    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature", "pir_range", "Far"],
        catch_exceptions=False,
    )

    range_setter.assert_not_called()
    assert "Error: Invalid value: " in res.output
    assert res.exit_code != 0


async def test_feature_set_badquoted(mocker, runner):
    """Test feature command's set value."""
    dummy_device = await get_device_for_fixture_protocol(
        "ES20M(US)_1.0_1.0.11.json", "IOT"
    )
    range_setter = mocker.patch("kasa.iot.modules.motion.Motion._set_range_from_str")
    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)

    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature", "pir_range", "`Far"],
        catch_exceptions=False,
    )

    range_setter.assert_not_called()
    assert "Error: Invalid value: " in res.output
    assert res.exit_code != 0


async def test_feature_set_goodquoted(mocker, runner):
    """Test feature command's set value."""
    dummy_device = await get_device_for_fixture_protocol(
        "ES20M(US)_1.0_1.0.11.json", "IOT"
    )
    range_setter = mocker.patch("kasa.iot.modules.motion.Motion._set_range_from_str")
    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)

    res = await runner.invoke(
        cli,
        ["--host", "127.0.0.123", "--debug", "feature", "pir_range", "'Far'"],
        catch_exceptions=False,
    )

    range_setter.assert_called()
    assert "Error: Invalid value: " not in res.output
    assert res.exit_code == 0


async def test_cli_child_commands(
    dev: Device, runner: CliRunner, mocker: MockerFixture
):
    if not dev.children:
        res = await runner.invoke(alias, ["--child-index", "0"], obj=dev)
        assert f"Device: {dev.host} does not have children" in res.output
        assert res.exit_code == 1

        res = await runner.invoke(alias, ["--index", "0"], obj=dev)
        assert f"Device: {dev.host} does not have children" in res.output
        assert res.exit_code == 1

        res = await runner.invoke(alias, ["--child", "Plug 2"], obj=dev)
        assert f"Device: {dev.host} does not have children" in res.output
        assert res.exit_code == 1

        res = await runner.invoke(alias, ["--name", "Plug 2"], obj=dev)
        assert f"Device: {dev.host} does not have children" in res.output
        assert res.exit_code == 1

    if dev.children:
        child_alias = dev.children[0].alias
        assert child_alias
        child_device_id = dev.children[0].device_id
        child_count = len(dev.children)
        child_update_method = dev.children[0].update

        # Test child retrieval
        res = await runner.invoke(alias, ["--child-index", "0"], obj=dev)
        assert f"Targeting child device {child_alias}" in res.output
        assert res.exit_code == 0

        res = await runner.invoke(alias, ["--index", "0"], obj=dev)
        assert f"Targeting child device {child_alias}" in res.output
        assert res.exit_code == 0

        res = await runner.invoke(alias, ["--child", child_alias], obj=dev)
        assert f"Targeting child device {child_alias}" in res.output
        assert res.exit_code == 0

        res = await runner.invoke(alias, ["--name", child_alias], obj=dev)
        assert f"Targeting child device {child_alias}" in res.output
        assert res.exit_code == 0

        res = await runner.invoke(alias, ["--child", child_device_id], obj=dev)
        assert f"Targeting child device {child_alias}" in res.output
        assert res.exit_code == 0

        res = await runner.invoke(alias, ["--name", child_device_id], obj=dev)
        assert f"Targeting child device {child_alias}" in res.output
        assert res.exit_code == 0

        # Test invalid name and index
        res = await runner.invoke(alias, ["--child-index", "-1"], obj=dev)
        assert f"Invalid index -1, device has {child_count} children" in res.output
        assert res.exit_code == 1

        res = await runner.invoke(alias, ["--child-index", str(child_count)], obj=dev)
        assert (
            f"Invalid index {child_count}, device has {child_count} children"
            in res.output
        )
        assert res.exit_code == 1

        res = await runner.invoke(alias, ["--child", "foobar"], obj=dev)
        assert "No child device found with device_id or name: foobar" in res.output
        assert res.exit_code == 1

        # Test using both options:

        res = await runner.invoke(
            alias, ["--child", child_alias, "--child-index", "0"], obj=dev
        )
        assert "Use either --child or --child-index, not both." in res.output
        assert res.exit_code == 2

        # Test child with no parameter interactive prompt

        res = await runner.invoke(alias, ["--child"], obj=dev, input="0\n")
        assert "Enter the index number of the child device:" in res.output
        assert f"Alias: {child_alias}" in res.output
        assert res.exit_code == 0

        # Test values and updates

        res = await runner.invoke(alias, ["foo", "--child", child_device_id], obj=dev)
        assert "Alias set to: foo" in res.output
        assert res.exit_code == 0

        # Test help has command options plus child options

        res = await runner.invoke(energy, ["--help"], obj=dev)
        assert "--year" in res.output
        assert "--child" in res.output
        assert "--child-index" in res.output
        assert res.exit_code == 0

        # Test child update patching calls parent and is undone on exit

        parent_update_spy = mocker.spy(dev, "update")
        res = await runner.invoke(alias, ["bar", "--child", child_device_id], obj=dev)
        assert "Alias set to: bar" in res.output
        assert res.exit_code == 0
        parent_update_spy.assert_called_once()
        assert dev.children[0].update == child_update_method


async def test_discover_config_uses_authoritative_discovery(mocker, runner):
    """Discovery config reports TDP parameters even when authentication fails."""
    host = "127.0.0.1"
    raw_response = _iot_klap_tdp_response(host)

    async def discover_single(*args, **kwargs):
        kwargs["on_discovered_raw"](raw_response)
        raise DiscoveryAuthenticationError(
            "Authentication failed",
            host=host,
            discovery_result=raw_response["discovery_response"],
        )

    mocker.patch(
        "kasa.cli.discover.Discover.discover_single", side_effect=discover_single
    )
    try_connect_all = mocker.patch("kasa.cli.discover.Discover.try_connect_all")

    res = await runner.invoke(
        cli,
        ["--host", host, "discover", "config"],
        catch_exceptions=False,
    )

    assert res.exit_code == 0
    assert f"Using TDP/20002 discovery response from {host}" in res.output
    assert (
        "--device-family IOT.SMARTPLUGSWITCH --encrypt-type KLAP "
        "--login-version 2 --klap-version 1 --no-https"
    ) in res.output.replace("\n", "")
    assert "direct connection routes" not in res.output
    try_connect_all.assert_not_called()


async def test_discover_config_falls_back_to_direct_probe(dev: Device, mocker, runner):
    """Test that config falls back when discovery provides no usable response."""
    host = "127.0.0.1"
    mocker.patch(
        "kasa.cli.discover.Discover.discover_single",
        side_effect=KasaException("No discovery response"),
    )
    mocker.patch("kasa.device_factory._connect", side_effect=[Exception, dev])

    res = await runner.invoke(
        cli,
        [
            "--username",
            "foo",
            "--password",
            "bar",
            "--host",
            host,
            "discover",
            "config",
        ],
        catch_exceptions=False,
    )
    assert res.exit_code == 0
    cparam = dev.config.connection_type
    expected_options = [
        f"--device-family {cparam.device_family.value}",
        f"--encrypt-type {cparam.encryption_type.value}",
    ]
    if cparam.login_version is not None:
        expected_options.append(f"--login-version {cparam.login_version}")
    if cparam.klap_version is not None:
        expected_options.append(f"--klap-version {cparam.klap_version}")
    expected_options.append("--https" if cparam.https else "--no-https")
    expected = " ".join(expected_options)
    assert expected in res.output
    assert "Trying direct connection routes instead" in res.output
    assert "Managed to connect using direct probing" in res.output
    assert re.search(
        r"Attempt to connect to 127\.0\.0\.1 with .* failed",
        res.output.replace("\n", ""),
    )
    assert re.search(
        r"Attempt to connect to 127\.0\.0\.1 with .* succeeded",
        res.output.replace("\n", ""),
    )
    assert "SMART." in res.output or "IOT." in res.output


async def test_discover_config_does_not_override_a_discovery_response(mocker, runner):
    """Direct probing does not replace a received discovery response."""
    host = "127.0.0.1"
    raw_response = {
        "discovery_response": {"result": "invalid", "error_code": 0},
        "meta": {"ip": host, "port": 20002, "source": "tdp"},
    }

    async def discover_single(*args, **kwargs):
        kwargs["on_discovered_raw"](raw_response)
        raise UnsupportedDeviceError("Unsupported discovery response", host=host)

    mocker.patch(
        "kasa.cli.discover.Discover.discover_single", side_effect=discover_single
    )
    try_connect_all = mocker.patch("kasa.cli.discover.Discover.try_connect_all")

    res = await runner.invoke(
        cli,
        ["--host", host, "discover", "config"],
        catch_exceptions=False,
    )

    assert res.exit_code == 1
    assert (
        "Unable to determine a connection configuration from the TDP/20002 "
        "discovery response"
    ) in res.output.replace("\n", "")
    try_connect_all.assert_not_called()


async def test_discover_config_invalid(mocker, runner):
    """Test the device config command with invalids."""
    host = "127.0.0.1"
    mocker.patch(
        "kasa.cli.discover.Discover.discover_single",
        side_effect=KasaException("No discovery response"),
    )
    mocker.patch("kasa.discover.Discover.try_connect_all", return_value=None)

    res = await runner.invoke(
        cli,
        [
            "--username",
            "foo",
            "--password",
            "bar",
            "--host",
            host,
            "discover",
            "config",
        ],
        catch_exceptions=False,
    )
    assert res.exit_code == 1
    assert f"Unable to connect to {host}" in res.output

    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar", "discover", "config"],
        catch_exceptions=False,
    )
    assert res.exit_code == 1
    assert "--host option must be supplied to discover config" in res.output

    res = await runner.invoke(
        cli,
        [
            "--username",
            "foo",
            "--password",
            "bar",
            "--host",
            host,
            "--target",
            "127.0.0.2",
            "discover",
            "config",
        ],
        catch_exceptions=False,
    )
    assert res.exit_code == 1
    assert "--target is not a valid option for single host discovery" in res.output
