import pytest
from pytest_mock import MockFixture

from kasa import Feature


class DummyDevice:
    pass


@pytest.fixture
def dummy_feature() -> Feature:
    # create_autospec for device slows tests way too much, so we use a dummy here

    feat = Feature(
        device=DummyDevice(),  # type: ignore[arg-type]
        name="dummy_feature",
        attribute_getter="dummygetter",
        attribute_setter="dummysetter",
        container=None,
        icon="mdi:dummy",
        type=Feature.Type.Switch,
        unit="dummyunit",
    )
    return feat


def test_feature_api(dummy_feature: Feature):
    """Test all properties of a dummy feature."""
    assert dummy_feature.device is not None
    assert dummy_feature.name == "dummy_feature"
    assert dummy_feature.attribute_getter == "dummygetter"
    assert dummy_feature.attribute_setter == "dummysetter"
    assert dummy_feature.container is None
    assert dummy_feature.icon == "mdi:dummy"
    assert dummy_feature.type == Feature.Type.Switch
    assert dummy_feature.unit == "dummyunit"


def test_feature_missing_type():
    """Test that creating a feature with a setter but without type causes an error."""
    with pytest.raises(ValueError):
        Feature(
            device=DummyDevice(),  # type: ignore[arg-type]
            name="dummy error",
            attribute_getter="dummygetter",
            attribute_setter="dummysetter",
        )


def test_feature_value(dummy_feature: Feature):
    """Verify that property gets accessed on *value* access."""
    dummy_feature.attribute_getter = "test_prop"
    dummy_feature.device.test_prop = "dummy"  # type: ignore[attr-defined]
    assert dummy_feature.value == "dummy"


def test_feature_value_container(mocker, dummy_feature: Feature):
    """Test that container's attribute is accessed when expected."""

    class DummyContainer:
        @property
        def test_prop(self):
            return "dummy"

    dummy_feature.container = DummyContainer()
    dummy_feature.attribute_getter = "test_prop"

    mock_dev_prop = mocker.patch.object(
        dummy_feature, "test_prop", new_callable=mocker.PropertyMock, create=True
    )

    assert dummy_feature.value == "dummy"
    mock_dev_prop.assert_not_called()


def test_feature_value_callable(dev, dummy_feature: Feature):
    """Verify that callables work as *attribute_getter*."""
    dummy_feature.attribute_getter = lambda x: "dummy value"
    assert dummy_feature.value == "dummy value"


async def test_feature_setter(dev, mocker, dummy_feature: Feature):
    """Verify that *set_value* calls the defined method."""
    mock_set_dummy = mocker.patch.object(dummy_feature.device, "set_dummy", create=True)
    dummy_feature.attribute_setter = "set_dummy"
    await dummy_feature.set_value("dummy value")
    mock_set_dummy.assert_called_with("dummy value")


async def test_feature_setter_read_only(dummy_feature):
    """Verify that read-only feature raises an exception when trying to change it."""
    dummy_feature.attribute_setter = None
    with pytest.raises(ValueError):
        await dummy_feature.set_value("value for read only feature")


async def test_feature_action(mocker):
    """Test that setting value on button calls the setter."""
    feat = Feature(
        device=DummyDevice(),  # type: ignore[arg-type]
        name="dummy_feature",
        attribute_setter="call_action",
        container=None,
        icon="mdi:dummy",
        type=Feature.Type.Action,
    )
    mock_call_action = mocker.patch.object(feat.device, "call_action", create=True)
    assert feat.value == "<Action>"
    await feat.set_value(1234)
    mock_call_action.assert_called()


async def test_feature_choice_list(dummy_feature, caplog, mocker: MockFixture):
    """Test the choice feature type."""
    dummy_feature.type = Feature.Type.Choice
    dummy_feature.choices = ["first", "second"]

    mock_setter = mocker.patch.object(dummy_feature.device, "dummysetter", create=True)
    await dummy_feature.set_value("first")
    mock_setter.assert_called_with("first")
    mock_setter.reset_mock()

    with pytest.raises(ValueError):
        await dummy_feature.set_value("invalid")
        assert "Unexpected value" in caplog.text

    mock_setter.assert_not_called()


@pytest.mark.parametrize("precision_hint", [1, 2, 3])
async def test_precision_hint(dummy_feature, precision_hint):
    """Test that precision hint works as expected."""
    dummy_value = 3.141593
    dummy_feature.type = Feature.Type.Sensor
    dummy_feature.precision_hint = precision_hint

    dummy_feature.attribute_getter = lambda x: dummy_value
    assert dummy_feature.value == dummy_value
    assert f"{round(dummy_value, precision_hint)} dummyunit" in repr(dummy_feature)
