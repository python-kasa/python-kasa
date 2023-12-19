import json

import asyncclick as click
import pytest
from asyncclick.testing import CliRunner

from kasa import AuthenticationException, SmartDevice, UnsupportedDeviceException
from kasa.cli import alias, brightness, cli, emeter, raw_command, state, sysinfo, toggle
from kasa.device_factory import DEVICE_TYPE_TO_CLASS
from kasa.discover import Discover

from .conftest import device_iot, handle_turn_on, new_discovery, turn_on


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


@device_iot
async def test_raw_command(dev):
    runner = CliRunner()
    res = await runner.invoke(raw_command, ["system", "get_sysinfo"], obj=dev)

    assert res.exit_code == 0
    assert dev.alias in res.output

    res = await runner.invoke(raw_command, obj=dev)
    assert res.exit_code != 0
    assert "Usage" in res.output


@device_iot
async def test_emeter(dev: SmartDevice, mocker):
    runner = CliRunner()

    res = await runner.invoke(emeter, obj=dev)
    if not dev.has_emeter:
        assert "Device has no emeter" in res.output
        return

    assert "== Emeter ==" in res.output

    monthly = mocker.patch.object(dev, "get_emeter_monthly")
    monthly.return_value = {1: 1234}
    res = await runner.invoke(emeter, ["--year", "1900"], obj=dev)
    assert "For year" in res.output
    assert "1, 1234" in res.output
    monthly.assert_called_with(year=1900)

    daily = mocker.patch.object(dev, "get_emeter_daily")
    daily.return_value = {1: 1234}
    res = await runner.invoke(emeter, ["--month", "1900-12"], obj=dev)
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
async def test_json_output(dev: SmartDevice, mocker):
    """Test that the json output produces correct output."""
    mocker.patch("kasa.Discover.discover", return_value=[dev])
    runner = CliRunner()
    res = await runner.invoke(cli, ["--json", "state"], obj=dev)
    assert res.exit_code == 0
    assert json.loads(res.output) == dev.internal_state


@new_discovery
async def test_credentials(discovery_mock, mocker):
    """Test credentials are passed correctly from cli to device."""
    # Patch state to echo username and password
    pass_dev = click.make_pass_decorator(SmartDevice)

    @pass_dev
    async def _state(dev: SmartDevice):
        if dev.credentials:
            click.echo(
                f"Username:{dev.credentials.username} Password:{dev.credentials.password}"
            )

    mocker.patch("kasa.cli.state", new=_state)
    for subclass in DEVICE_TYPE_TO_CLASS.values():
        mocker.patch.object(subclass, "update")

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
        ],
    )
    assert res.exit_code == 0

    assert "Username:foo Password:bar\n" in res.output


@device_iot
async def test_without_device_type(discovery_data: dict, dev, mocker):
    """Test connecting without the device type."""
    runner = CliRunner()
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
    )
    assert res.exit_code == 0


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
            "discover",
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
            "discover",
            "--verbose",
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
            "discover",
            "--verbose",
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
        ],
    )

    assert res.exit_code != 0
    assert isinstance(res.exception, AuthenticationException)
