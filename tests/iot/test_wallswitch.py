from ..device_fixtures import wallswitch_iot


@wallswitch_iot
def test_wallswitch_motion(dev):
    """Check that wallswitches with motion sensor get modules enabled."""
    has_motion = "PIR" in dev.sys_info["dev_name"]
    assert "motion" in dev.modules if has_motion else True
    assert "ambient" in dev.modules if has_motion else True
