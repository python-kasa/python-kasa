import json
import os
import re

import asyncclick as click
import pytest
from asyncclick.testing import CliRunner

from kasa import (
    AuthenticationError,
    Credentials,
    Device,
    DeviceError,
    EmeterStatus,
    KasaException,
    Module,
    UnsupportedDeviceError,
)
from kasa.cli import (
    TYPE_TO_CLASS,
    alias,
    brightness,
    cli,
    cmd_command,
    effect,
    emeter,
    hsv,
    led,
    raw_command,
    reboot,
    state,
    sysinfo,
    temperature,
    toggle,
    update_credentials,
    wifi,
)
from kasa.discover import Discover, DiscoveryResult
from kasa.iot import IotDevice

from .conftest import (
    device_smart,
    get_device_for_fixture_protocol,
    handle_turn_on,
    new_discovery,
    turn_on,
)


@pytest.fixture()
def runner():
    """Runner fixture that unsets the KASA_ environment variables for tests."""
    KASA_VARS = {k: None for k, v in os.environ.items() if k.startswith("KASA_")}
    runner = CliRunner(env=KASA_VARS)

    return runner


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

    await dev.set_alias(old_alias)


async def test_raw_command(dev, mocker, runner):
    update = mocker.patch.object(dev, "update")
    from kasa.smart import SmartDevice

    if isinstance(dev, SmartDevice):
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

        async def _query_helper(*_, **__):
            return {"dummy": "response"}

    dummy_child = DummyDevice()

    mocker.patch.object(dev, "_children", {"XYZ": dummy_child})
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
async def test_wifi_scan(dev, runner):
    res = await runner.invoke(wifi, ["scan"], obj=dev)

    assert res.exit_code == 0
    assert re.search(r"Found [\d]+ wifi networks!", res.output)


@device_smart
async def test_wifi_join(dev, mocker, runner):
    update = mocker.patch.object(dev, "update")
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--keytype", "wpa_psk", "--password", "foobar"],
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


async def test_emeter(dev: Device, mocker, runner):
    res = await runner.invoke(emeter, obj=dev)
    if not dev.has_emeter:
        assert "Device has no emeter" in res.output
        return

    assert "== Emeter ==" in res.output

    if not dev.is_strip:
        res = await runner.invoke(emeter, ["--index", "0"], obj=dev)
        assert "Index and name are only for power strips!" in res.output
        res = await runner.invoke(emeter, ["--name", "mock"], obj=dev)
        assert "Index and name are only for power strips!" in res.output

    if dev.is_strip and len(dev.children) > 0:
        realtime_emeter = mocker.patch.object(dev.children[0], "get_emeter_realtime")
        realtime_emeter.return_value = EmeterStatus({"voltage_mv": 122066})

        res = await runner.invoke(emeter, ["--index", "0"], obj=dev)
        assert "Voltage: 122.066 V" in res.output
        realtime_emeter.assert_called()
        assert realtime_emeter.call_count == 1

        res = await runner.invoke(emeter, ["--name", dev.children[0].alias], obj=dev)
        assert "Voltage: 122.066 V" in res.output
        assert realtime_emeter.call_count == 2

    if isinstance(dev, IotDevice):
        monthly = mocker.patch.object(dev, "get_emeter_monthly")
        monthly.return_value = {1: 1234}
    res = await runner.invoke(emeter, ["--year", "1900"], obj=dev)
    if not isinstance(dev, IotDevice):
        assert "Device has no historical statistics" in res.output
        return
    assert "For year" in res.output
    assert "1, 1234" in res.output
    monthly.assert_called_with(year=1900)

    if isinstance(dev, IotDevice):
        daily = mocker.patch.object(dev, "get_emeter_daily")
        daily.return_value = {1: 1234}
    res = await runner.invoke(emeter, ["--month", "1900-12"], obj=dev)
    if not isinstance(dev, IotDevice):
        assert "Device has no historical statistics" in res.output
        return
    assert "For month" in res.output
    assert "1, 1234" in res.output
    daily.assert_called_with(year=1900, month=12)


async def test_brightness(dev: Device, runner):
    res = await runner.invoke(brightness, obj=dev)
    if not (light := dev.modules.get(Module.Light)) or not light.is_dimmable:
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
    if not (light := dev.modules.get(Module.Light)) or not light.is_variable_color_temp:
        assert "Device does not support color temperature" in res.output
        return

    res = await runner.invoke(temperature, obj=dev)
    assert f"Color temperature: {light.color_temp}" in res.output
    valid_range = light.valid_temperature_range
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
    if not (light := dev.modules.get(Module.Light)) or not light.is_color:
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
    mocker.patch("kasa.Discover.discover", return_value={"127.0.0.1": dev})
    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    res = await runner.invoke(cli, ["--json", "state"], obj=dev)
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

    mocker.patch("kasa.cli.state", new=_state)

    dr = DiscoveryResult(**discovery_mock.discovery_data["result"])
    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.123",
            "--username",
            "foo",
            "--password",
            "bar",
            "--device-family",
            dr.device_type,
            "--encrypt-type",
            dr.mgt_encrypt_schm.encrypt_type,
        ],
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
        timeout=5,
        discovery_timeout=7,
    )


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
    assert "== Discovery Result ==" in res.output


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
    assert isinstance(res.exception, UnsupportedDeviceError)


@new_discovery
async def test_discover_auth_failed(discovery_mock, mocker, runner):
    """Test discovery output."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = Discover._get_device_class(discovery_mock.discovery_data)
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


@new_discovery
async def test_host_auth_failed(discovery_mock, mocker, runner):
    """Test discovery output."""
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = Discover._get_device_class(discovery_mock.discovery_data)
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
    assert isinstance(res.exception, AuthenticationError)


@pytest.mark.parametrize("device_type", list(TYPE_TO_CLASS))
async def test_type_param(device_type, mocker, runner):
    """Test for handling only one of username or password supplied."""
    result_device = FileNotFoundError
    pass_dev = click.make_pass_decorator(Device)

    @pass_dev
    async def _state(dev: Device):
        nonlocal result_device
        result_device = dev

    mocker.patch("kasa.cli.state", new=_state)
    expected_type = TYPE_TO_CLASS[device_type]
    mocker.patch.object(expected_type, "update")
    res = await runner.invoke(
        cli,
        ["--type", device_type, "--host", "127.0.0.1"],
    )
    assert res.exit_code == 0
    assert isinstance(result_device, expected_type)


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
        "Raised error: Managed to invoke callback without a context object of type 'Device' existing."
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
    assert "== Features ==" in res.output
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
    assert res.exit_code == 0


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
    assert "Changing led from False to True" in res.output
    assert res.exit_code == 0


async def test_feature_set_child(mocker, runner):
    """Test feature command's set value."""
    dummy_device = await get_device_for_fixture_protocol(
        "P300(EU)_1.0_1.0.13.json", "SMART"
    )
    setter = mocker.patch("kasa.smart.smartdevice.SmartDevice.set_state")

    mocker.patch("kasa.discover.Discover.discover_single", return_value=dummy_device)
    get_child_device = mocker.spy(dummy_device, "get_child_device")

    child_id = "000000000000000000000000000000000000000001"

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
