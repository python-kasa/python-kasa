from datetime import timedelta

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

temperature_records = parametrize(
    "has temperature records",
    component_filter="temp_record",
    protocol_filter={"SMART.CHILD"},
)


@temperature_records
async def test_temperature_records(dev: SmartDevice) -> None:
    """Test the thermostat temperature history."""
    records = dev.modules[Module.TemperatureRecords]

    temps = records.temperatures
    assert len(temps) == 96
    assert all(t is None or isinstance(t, float) for t in temps)
    assert temps[-1] is not None
    assert timedelta(minutes=15) == records.INTERVAL
