from ..device_fixtures import wallswitch_iot


@wallswitch_iot
def test_wallswitch_motion(dev):
    """Check that wallswitches with motion sensor get modules enabled."""
    has_motion = "PIR" in dev.sys_info["dev_name"]
    if has_motion:
        assert "motion" in dev.modules
        assert "ambient" in dev.modules
    else:
        assert "motion" not in dev.modules
        assert "ambient" not in dev.modules
