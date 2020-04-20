import asyncio

from click.testing import CliRunner

from kasa import SmartDevice
from kasa.cli import alias, brightness, emeter, raw_command, state, sysinfo

from .conftest import handle_turn_on, turn_on


def test_sysinfo(dev):
    runner = CliRunner()
    res = runner.invoke(sysinfo, obj=dev)
    assert "System info" in res.output
    assert dev.alias in res.output


@turn_on
def test_state(dev, turn_on):
    asyncio.run(handle_turn_on(dev, turn_on))
    runner = CliRunner()
    res = runner.invoke(state, obj=dev)
    print(res.output)

    if dev.is_on:
        assert "Device state: ON" in res.output
    else:
        assert "Device state: OFF" in res.output

    if not dev.has_emeter:
        assert "Device has no emeter" in res.output


def test_alias(dev):
    runner = CliRunner()

    res = runner.invoke(alias, obj=dev)
    assert f"Alias: {dev.alias}" in res.output

    new_alias = "new alias"
    res = runner.invoke(alias, [new_alias], obj=dev)
    assert f"Setting alias to {new_alias}" in res.output

    res = runner.invoke(alias, obj=dev)
    assert f"Alias: {new_alias}" in res.output


def test_raw_command(dev):
    runner = CliRunner()
    res = runner.invoke(raw_command, ["system", "get_sysinfo"], obj=dev)

    assert res.exit_code == 0
    assert dev.alias in res.output

    res = runner.invoke(raw_command, obj=dev)
    assert res.exit_code != 0
    assert "Usage" in res.output


def test_emeter(dev: SmartDevice, mocker):
    runner = CliRunner()

    res = runner.invoke(emeter, obj=dev)
    if not dev.has_emeter:
        assert "Device has no emeter" in res.output
        return

    assert "Current State" in res.output

    monthly = mocker.patch.object(dev, "get_emeter_monthly")
    res = runner.invoke(emeter, ["--year", "1900"], obj=dev)
    assert "For year" in res.output
    monthly.assert_called()

    daily = mocker.patch.object(dev, "get_emeter_daily")
    res = runner.invoke(emeter, ["--month", "1900-12"], obj=dev)
    assert "For month" in res.output
    daily.assert_called()


def test_brightness(dev):
    runner = CliRunner()
    res = runner.invoke(brightness, obj=dev)
    if not dev.is_dimmable:
        assert "This device does not support brightness." in res.output
        return

    res = runner.invoke(brightness, obj=dev)
    assert f"Brightness: {dev.brightness}" in res.output

    res = runner.invoke(brightness, ["12"], obj=dev)
    assert "Setting brightness" in res.output

    res = runner.invoke(brightness, obj=dev)
    assert f"Brightness: 12" in res.output


def test_temperature(dev):
    pass


def test_hsv(dev):
    pass


def test_led(dev):
    pass


def test_on(dev):
    pass


def test_off(dev):
    pass


def test_reboot(dev):
    pass
