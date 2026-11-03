from pytest_mock import MockerFixture

from kasa.deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.iot import IotWallSwitch

from ..device_fixtures import parametrize, wallswitch_iot

ks200m_iot = parametrize("ks200m", model_filter={"KS200M"}, protocol_filter={"IOT"})


@wallswitch_iot
def test_wallswitch_motion(dev: IotWallSwitch) -> None:
    """Check that wallswitches with motion sensor get modules enabled."""
    has_motion = "PIR" in dev.sys_info["dev_name"]
    assert "motion" in dev.modules if has_motion else True
    assert "ambient" in dev.modules if has_motion else True


@ks200m_iot
async def test_ks200m_update_split_klap(
    dev: IotWallSwitch, mocker: MockerFixture
) -> None:
    """Check that a KS200M update over KLAP is split into smaller requests."""
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    assert spy.call_count == 1

    klap = DeviceConnectionParameters(
        DeviceFamily.IotSmartPlugSwitch, DeviceEncryptionType.Klap, login_version=2
    )
    mocker.patch.object(dev.config, "connection_type", klap)
    spy.reset_mock()
    await dev.update()

    assert [sorted(call.args[0]) for call in spy.call_args_list] == [
        ["schedule", "system"],
        ["schedule"],
        ["anti_theft", "cnCloud", "smartlife.iot.LAS", "smartlife.iot.PIR", "time"],
    ]
