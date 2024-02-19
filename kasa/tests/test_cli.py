import json
import re

import asyncclick as click
import pytest
from asyncclick.testing import CliRunner

from kasa import (
    AuthenticationException,
    Credentials,
    Device,
    EmeterStatus,
    SmartDeviceException,
    UnsupportedDeviceException,
)
from kasa.cli import (
    TYPE_TO_CLASS,
    alias,
    brightness,
    cli,
    emeter,
    raw_command,
    reboot,
    state,
    sysinfo,
    toggle,
    update_credentials,
    wifi,
)
from kasa.discover import Discover, DiscoveryResult
from kasa.iot import IotDevice

from .conftest import device_iot, device_smart, handle_turn_on, new_discovery, turn_on


async def test_update_called_by_cli(dev, mocker):
    """Test that device update is called on main."""
    runner = CliRunner()
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


@device_iot
async def test_sysinfo(dev):
    runner = CliRunner()
    res = await runner.invoke(sysinfo, obj=dev)
    assert "System info" in res.output
    assert dev.alias in res.output


@turn_on
async def test_state(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    runner = CliRunner()
    res = await runner.invoke(state, obj=dev)
    await dev.update()

    if dev.is_on:
        assert "Device state: True" in res.output
    else:
        assert "Device state: False" in res.output


@turn_on
async def test_toggle(dev, turn_on, mocker):
    await handle_turn_on(dev, turn_on)
    runner = CliRunner()
    await runner.invoke(toggle, obj=dev)

    if turn_on:
        assert not dev.is_on
    else:
        assert dev.is_on


@device_iot
async def test_alias(dev):
    runner = CliRunner()

    res = await runner.invoke(alias, obj=dev)
    assert f"Alias: {dev.alias}" in res.output

    old_alias = dev.alias

    new_alias = "new alias"
    res = await runner.invoke(alias, [new_alias], obj=dev)
    assert f"Setting alias to {new_alias}" in res.output

    res = await runner.invoke(alias, obj=dev)
    assert f"Alias: {new_alias}" in res.output

    await dev.set_alias(old_alias)


async def test_raw_command(dev, mocker):
    runner = CliRunner()
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


@device_smart
async def test_reboot(dev, mocker):
    """Test that reboot works on SMART devices."""
    runner = CliRunner()
    query_mock = mocker.patch.object(dev.protocol, "query")

    res = await runner.invoke(
        reboot,
        obj=dev,
    )

    query_mock.assert_called()
    assert res.exit_code == 0


@device_smart
async def test_wifi_scan(dev):
    runner = CliRunner()
    res = await runner.invoke(wifi, ["scan"], obj=dev)

    assert res.exit_code == 0
    assert re.search(r"Found \d wifi networks!", res.output)


@device_smart
async def test_wifi_join(dev, mocker):
    runner = CliRunner()
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
async def test_wifi_join_no_creds(dev):
    runner = CliRunner()
    dev.protocol._transport._credentials = None
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--keytype", "wpa_psk", "--password", "foobar"],
        obj=dev,
    )

    assert res.exit_code != 0
    assert isinstance(res.exception, AuthenticationException)


@device_smart
async def test_wifi_join_exception(dev, mocker):
    runner = CliRunner()
    mocker.patch.object(
        dev.protocol, "query", side_effect=SmartDeviceException(error_code=9999)
    )
    res = await runner.invoke(
        wifi,
        ["join", "FOOBAR", "--keytype", "wpa_psk", "--password", "foobar"],
        obj=dev,
    )

    assert res.exit_code != 0
    assert isinstance(res.exception, SmartDeviceException)


@device_smart
async def test_update_credentials(dev):
    runner = CliRunner()
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


async def test_emeter(dev: Device, mocker):
    runner = CliRunner()

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


@device_iot
async def test_brightness(dev):
    runner = CliRunner()
    res = await runner.invoke(brightness, obj=dev)
    if not dev.is_dimmable:
        assert "This device does not support brightness." in res.output
        return

    res = await runner.invoke(brightness, obj=dev)
    assert f"Brightness: {dev.brightness}" in res.output

    res = await runner.invoke(brightness, ["12"], obj=dev)
    assert "Setting brightness" in res.output

    res = await runner.invoke(brightness, obj=dev)
    assert "Brightness: 12" in res.output


@device_iot
async def test_json_output(dev: Device, mocker):
    """Test that the json output produces correct output."""
    mocker.patch("kasa.Discover.discover", return_value={"127.0.0.1": dev})
    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    runner = CliRunner()
    res = await runner.invoke(cli, ["--json", "state"], obj=dev)
    assert res.exit_code == 0
    assert json.loads(res.output) == dev.internal_state


@new_discovery
async def test_credentials(discovery_mock, mocker):
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

    mocker.patch("kasa.IotProtocol.query", return_value=discovery_mock.query_data)
    mocker.patch("kasa.SmartProtocol.query", return_value=discovery_mock.query_data)

    dr = DiscoveryResult(**discovery_mock.discovery_data["result"])
    runner = CliRunner()
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


@device_iot
async def test_without_device_type(dev, mocker):
    """Test connecting without the device type."""
    runner = CliRunner()
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
async def test_invalid_credential_params(auth_param):
    """Test for handling only one of username or password supplied."""
    runner = CliRunner()

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


async def test_duplicate_target_device():
    """Test that defining both --host or --alias gives an error."""
    runner = CliRunner()

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


async def test_discover(discovery_mock, mocker):
    """Test discovery output."""
    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    runner = CliRunner()
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


async def test_discover_host(discovery_mock, mocker):
    """Test discovery output."""
    # These will mock the features to avoid accessing non-existing
    mocker.patch("kasa.device.Device.features", return_value={})
    mocker.patch("kasa.iot.iotdevice.IotDevice.features", return_value={})

    runner = CliRunner()
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


async def test_discover_unsupported(unsupported_device_info):
    """Test discovery output."""
    runner = CliRunner()
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


async def test_host_unsupported(unsupported_device_info):
    """Test discovery output."""
    runner = CliRunner()
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
    assert isinstance(res.exception, UnsupportedDeviceException)


@new_discovery
async def test_discover_auth_failed(discovery_mock, mocker):
    """Test discovery output."""
    runner = CliRunner()
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = Discover._get_device_class(discovery_mock.discovery_data)
    mocker.patch.object(
        device_class,
        "update",
        side_effect=AuthenticationException("Failed to authenticate"),
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
async def test_host_auth_failed(discovery_mock, mocker):
    """Test discovery output."""
    runner = CliRunner()
    host = "127.0.0.1"
    discovery_mock.ip = host
    device_class = Discover._get_device_class(discovery_mock.discovery_data)
    mocker.patch.object(
        device_class,
        "update",
        side_effect=AuthenticationException("Failed to authenticate"),
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
    assert isinstance(res.exception, AuthenticationException)


@pytest.mark.parametrize("device_type", list(TYPE_TO_CLASS))
async def test_type_param(device_type, mocker):
    """Test for handling only one of username or password supplied."""
    runner = CliRunner()

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
async def test_shell(dev: Device, mocker):
    """Test that the shell commands tries to embed a shell."""
    mocker.patch("kasa.Discover.discover", return_value=[dev])
    # repl = mocker.patch("ptpython.repl")
    mocker.patch.dict(
        "sys.modules",
        {"ptpython": mocker.MagicMock(), "ptpython.repl": mocker.MagicMock()},
    )
    embed = mocker.patch("ptpython.repl.embed")
    runner = CliRunner()
    res = await runner.invoke(cli, ["shell"], obj=dev)
    assert res.exit_code == 0
    embed.assert_called()


async def test_errors(mocker):
    runner = CliRunner()
    err = SmartDeviceException("Foobar")

    # Test masking
    mocker.patch("kasa.Discover.discover", side_effect=err)
    res = await runner.invoke(
        cli,
        ["--username", "foo", "--password", "bar"],
    )
    assert res.exit_code == 1
    assert (
        "Kasa:: Command line: cli --username USERNAME --password PASSWORD" in res.output
    )
    assert "Kasa:: Raised error: Foobar" in res.output
    assert "SmartDeviceException" not in res.output
    assert "Run with --debug enabled to see stacktrace" in res.output
    print(res.output)

    # Test --debug
    res = await runner.invoke(
        cli,
        ["--debug"],
    )
    assert res.exit_code == 1
    assert "Kasa:: Command line: cli --debug" in res.output
    assert "Kasa:: Raised error: Foobar" in res.output
    assert res.exception == err

    # Test no device passed to subcommand
    mocker.patch("kasa.Discover.discover", return_value={})
    res = await runner.invoke(
        cli,
        ["sysinfo"],
    )
    assert res.exit_code == 1
    assert "Kasa:: Command line: cli sysinfo" in res.output
    assert (
        "Kasa:: Raised error: Managed to invoke callback without a context object of type 'Device' existing."
        in res.output
    )
    assert isinstance(res.exception, SystemExit)

    # Test click error
    res = await runner.invoke(
        cli,
        ["--foobar"],
    )
    assert res.exit_code == 2
    assert "Kasa:: Raised error:" not in res.output
