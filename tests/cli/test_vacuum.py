from pytest_mock import MockerFixture

from kasa import DeviceType, Module
from kasa.cli.vacuum import vacuum

from ..device_fixtures import plug_iot
from ..device_fixtures import vacuum as vacuum_devices


@vacuum_devices
async def test_vacuum_records_group(dev, mocker: MockerFixture, runner):
    """Test that vacuum records calls the expected methods."""
    rec = dev.modules.get(Module.CleanRecords)
    assert rec

    res = await runner.invoke(vacuum, ["records"], obj=dev, catch_exceptions=False)

    latest = rec.parsed_data.last_clean
    expected = (
        f"Totals: {rec.total_clean_area} {rec.area_unit} in {rec.total_clean_time} "
        f"(cleaned {rec.total_clean_count} times)\n"
        f"Last clean: {latest.clean_area} {rec.area_unit} @ {latest.clean_time}"
    )
    assert expected in res.output
    assert res.exit_code == 0


@vacuum_devices
async def test_vacuum_records_list(dev, mocker: MockerFixture, runner):
    """Test that vacuum records list calls the expected methods."""
    rec = dev.modules.get(Module.CleanRecords)
    assert rec

    res = await runner.invoke(
        vacuum, ["records", "list"], obj=dev, catch_exceptions=False
    )

    data = rec.parsed_data
    for record in data.records:
        expected = (
            f"* {record.timestamp}: cleaned {record.clean_area} {rec.area_unit}"
            f" in {record.clean_time}"
        )
        assert expected in res.output
    assert res.exit_code == 0


@plug_iot
async def test_non_vacuum(dev, mocker: MockerFixture, runner):
    """Test that vacuum commands return an error if executed on a non-vacuum."""
    assert dev.device_type is not DeviceType.Vacuum

    res = await runner.invoke(vacuum, ["records"], obj=dev, catch_exceptions=False)
    assert "This device does not support records" in res.output
    assert res.exit_code != 0

    res = await runner.invoke(
        vacuum, ["records", "list"], obj=dev, catch_exceptions=False
    )
    assert "This device does not support records" in res.output
    assert res.exit_code != 0
