from datetime import timedelta

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

temperature_records = parametrize(
    "has temperature records",
    component_filter="temp_record",
    protocol_filter={"SMART.CHILD"},
)
temp_humidity_records = parametrize(
    "has temperature and humidity records",
    component_filter="temp_humidity_record",
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


@temp_humidity_records
async def test_temperature_humidity_records(dev: SmartDevice) -> None:
    """Test the sensor temperature and humidity history."""
    module = dev.modules[Module.TemperatureHumidityRecords]

    records = module.records
    assert records
    assert records[-1].timestamp == module.last_record_time
    assert records[-1].timestamp - records[-2].timestamp == timedelta(minutes=15)
    for record in records:
        assert record.temperature is None or isinstance(record.temperature, float)
        assert record.humidity is None or isinstance(record.humidity, int)
