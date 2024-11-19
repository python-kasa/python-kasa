from kasa import Device, Module

from ...device_fixtures import parametrize

triggerlogs = parametrize(
    "has trigger_logs",
    component_filter="trigger_log",
    protocol_filter={"SMART", "SMART.CHILD"},
)


@triggerlogs
async def test_trigger_logs(dev: Device):
    """Test that features are registered and work as expected."""
    triggerlogs = dev.modules.get(Module.TriggerLogs)
    assert triggerlogs is not None
    if logs := triggerlogs.logs:
        first = logs[0]
        assert isinstance(first.id, int)
        assert isinstance(first.timestamp, int)
        assert isinstance(first.event, str)
        assert isinstance(first.event_id, str)
