import pytest

from kasa import Device, Module
from kasa.iot.modules.rulemodule import Action, TimeOption

from ...device_fixtures import device_iot


@device_iot
@pytest.mark.xdist_group(name="caplog")
def test_schedule(dev: Device, caplog: pytest.LogCaptureFixture):
    schedule = dev.modules.get(Module.IotSchedule)
    assert schedule
    if rules := schedule.rules:
        first = rules[0]
        assert isinstance(first.sact, Action)
        assert isinstance(first.stime_opt, TimeOption)
    assert "Unable to read rule list" not in caplog.text
