from pytest_mock import MockerFixture

from kasa.iot import IotWallSwitch

from ..device_fixtures import parametrize, parametrize_subtract, wallswitch_iot

ks200m_iot = parametrize("ks200m", model_filter={"KS200M"}, protocol_filter={"IOT"})


@wallswitch_iot
def test_wallswitch_motion(dev: IotWallSwitch) -> None:
    """Check that wallswitches with motion sensor get modules enabled."""
    has_motion = "PIR" in dev.sys_info["dev_name"]
    assert "motion" in dev.modules if has_motion else True
    assert "ambient" in dev.modules if has_motion else True


@ks200m_iot
async def test_ks200m_update_split(dev: IotWallSwitch, mocker: MockerFixture) -> None:
    """Check that the KS200M update is split into smaller requests."""
    assert dev.max_device_response_size == 2048

    spy = mocker.spy(dev.protocol, "query")
    await dev.update()

    assert [sorted(call.args[0]) for call in spy.call_args_list] == [
        ["schedule", "system"],
        ["schedule"],
        ["anti_theft", "cnCloud", "smartlife.iot.LAS", "smartlife.iot.PIR", "time"],
    ]


@parametrize_subtract(wallswitch_iot, ks200m_iot)
async def test_wallswitch_update_not_split(
    dev: IotWallSwitch, mocker: MockerFixture
) -> None:
    """Check that the other wallswitches keep a single update request."""
    assert dev.max_device_response_size == 16 * 1024

    spy = mocker.spy(dev.protocol, "query")
    await dev.update()

    assert spy.call_count == 1


def test_wallswitch_max_device_response_size_before_update() -> None:
    """Check that the response size is available before the first update."""
    assert IotWallSwitch("127.0.0.1").max_device_response_size == 16 * 1024
