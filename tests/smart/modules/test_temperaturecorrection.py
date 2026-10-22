import pytest

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

temperature_correction = parametrize(
    "has temperature correction",
    component_filter="temperature_correction",
    protocol_filter={"SMART.CHILD"},
)


@temperature_correction
async def test_features(dev: SmartDevice) -> None:
    """Test the built-in sensor is reported by default."""
    correction = dev.modules[Module.TemperatureCorrection]

    assert isinstance(correction.offset, int)
    assert correction.external_sensor_id is None
    assert correction.using_external_sensor is False
    assert dev.features["external_temperature_sensor"].value is None


@temperature_correction
async def test_set_external_sensor(dev: SmartDevice, mocker) -> None:
    """Test switching to an external sensor and back."""
    correction = dev.modules[Module.TemperatureCorrection]
    sensor = mocker.Mock(device_id="sensor-id", modules={Module.TemperatureSensor: 1})
    mocker.patch.object(type(dev), "parent", new=mocker.PropertyMock(return_value=None))
    call = mocker.spy(correction, "call")

    await correction.set_external_sensor(sensor.device_id)
    call.assert_called_with(
        "set_temperature_correction",
        {
            "use_other_temp_sensor": True,
            "offset": correction.offset,
            "temp_sensor_device_id": "sensor-id",
            "using_other_temp_sensor": True,
        },
    )
    await dev.update()
    assert correction.external_sensor_id == "sensor-id"
    assert correction.using_external_sensor is True

    await correction.set_external_sensor(None)
    await dev.update()
    assert correction.external_sensor_id is None
    assert correction.data["temp_sensor_device_id"] == dev.device_id


@temperature_correction
async def test_set_external_sensor_validation(dev: SmartDevice, mocker) -> None:
    """Test sensors are checked against the hub's children."""
    correction = dev.modules[Module.TemperatureCorrection]

    with pytest.raises(ValueError, match="built-in sensor"):
        await correction.set_external_sensor(dev.device_id)

    no_temp = mocker.Mock(device_id="no-temp", modules={}, alias="Button")
    parent = mocker.Mock(children=[dev, no_temp])
    mocker.patch.object(
        type(dev), "parent", new=mocker.PropertyMock(return_value=parent)
    )
    with pytest.raises(ValueError, match="No device"):
        await correction.set_external_sensor("missing")
    with pytest.raises(ValueError, match="no temperature sensor"):
        await correction.set_external_sensor("no-temp")
