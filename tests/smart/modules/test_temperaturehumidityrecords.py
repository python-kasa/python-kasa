from datetime import timedelta

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

temp_humidity_records = parametrize(
    "has temperature and humidity records",
    component_filter="temp_humidity_record",
    protocol_filter={"SMART.CHILD"},
)


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
