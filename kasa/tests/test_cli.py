import json
import sys

import pytest
from asyncclick.testing import CliRunner

from kasa import SmartDevice, TPLinkSmartHomeProtocol
from kasa.cli import alias, brightness, cli, emeter, raw_command, state, sysinfo, toggle

from .conftest import handle_turn_on, turn_on
from .newfakes import FakeTransportProtocol


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


async def test_raw_command(dev):
    runner = CliRunner()
    res = await runner.invoke(raw_command, ["system", "get_sysinfo"], obj=dev)

    assert res.exit_code == 0
    assert dev.alias in res.output

    res = await runner.invoke(raw_command, obj=dev)
    assert res.exit_code != 0
    assert "Usage" in res.output


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


async def test_json_output(dev: SmartDevice, mocker):
    """Test that the json output produces correct output."""
    mocker.patch("kasa.Discover.discover", return_value=[dev])
    runner = CliRunner()
    res = await runner.invoke(cli, ["--json", "state"], obj=dev)
    assert res.exit_code == 0
    assert json.loads(res.output) == dev.internal_state


async def test_credentials(discovery_data: dict, mocker):
    """Test credentials are passed correctly."""
    # As this is testing the device constructor need to explicitly wire in
    # the FakeTransportProtocol
    ftp = FakeTransportProtocol(discovery_data)
    mocker.patch.object(TPLinkSmartHomeProtocol, "query", ftp.query)

    def discovery_info_to_type(info):
        sysinfo = info["system"]["get_sysinfo"]
        type_ = sysinfo.get("type", sysinfo.get("mic_type"))
        if "dev_name" in sysinfo and "Dimmer" in sysinfo["dev_name"]:
            return "dimmer"
        if "smartplug" in type_.lower():
            if "children" in sysinfo:
                return "strip"
            return "plug"
        if "smartbulb" in type_.lower():
            if "length" in sysinfo:  # strips have length
                return "lightstrip"
            return "bulb"

    runner = CliRunner()
    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--type",
            discovery_info_to_type(discovery_data),
            "--username",
            "foo",
            "--password",
            "bar",
        ],
    )
    assert res.exit_code == 0
    assert "Username: foo" in res.output and "Password: bar" in res.output

    # Test for handling only one of username or passowrd supplied.
    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--type",
            discovery_info_to_type(discovery_data),
            "--username",
            "foo",
        ],
    )
    assert res.exit_code == 0
    assert (
        res.output == "Using authentication requires both --username and --password\n"
    )
    res = await runner.invoke(
        cli,
        [
            "--host",
            "127.0.0.1",
            "--type",
            discovery_info_to_type(discovery_data),
            "--password",
            "bar",
        ],
    )
    assert res.exit_code == 0
    assert (
        res.output == "Using authentication requires both --username and --password\n"
    )
