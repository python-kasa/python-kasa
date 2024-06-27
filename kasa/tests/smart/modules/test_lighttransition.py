from pytest_mock import MockerFixture

from kasa import Feature, Module
from kasa.smart import SmartDevice
from kasa.tests.device_fixtures import get_parent_and_child_modules, parametrize
from kasa.tests.fixtureinfo import ComponentFilter

light_transition_v1 = parametrize(
    "has light transition",
    component_filter=ComponentFilter(
        component_name="on_off_gradually", maximum_version=1
    ),
    protocol_filter={"SMART"},
)
light_transition_gt_v1 = parametrize(
    "has light transition",
    component_filter=ComponentFilter(
        component_name="on_off_gradually", minimum_version=2
    ),
    protocol_filter={"SMART"},
)


@light_transition_v1
async def test_module_v1(dev: SmartDevice, mocker: MockerFixture):
    """Test light transition module."""
    assert isinstance(dev, SmartDevice)
    light_transition = next(get_parent_and_child_modules(dev, Module.LightTransition))
    assert light_transition
    assert "smooth_transitions" in light_transition._module_features
    assert "smooth_transition_on" not in light_transition._module_features
    assert "smooth_transition_off" not in light_transition._module_features

    await light_transition.set_enabled(True)
    await dev.update()
    assert light_transition.enabled is True

    await light_transition.set_enabled(False)
    await dev.update()
    assert light_transition.enabled is False


@light_transition_gt_v1
async def test_module_gt_v1(dev: SmartDevice, mocker: MockerFixture):
    """Test light transition module."""
    assert isinstance(dev, SmartDevice)
    light_transition = next(get_parent_and_child_modules(dev, Module.LightTransition))
    assert light_transition
    assert "smooth_transitions" not in light_transition._module_features
    assert "smooth_transition_on" in light_transition._module_features
    assert "smooth_transition_off" in light_transition._module_features

    await light_transition.set_enabled(True)
    await dev.update()
    assert light_transition.enabled is True

    await light_transition.set_enabled(False)
    await dev.update()
    assert light_transition.enabled is False

    await light_transition.set_turn_on_transition(5)
    await dev.update()
    assert light_transition.turn_on_transition == 5
    # enabled is true if either on or off is enabled
    assert light_transition.enabled is True

    await light_transition.set_turn_off_transition(10)
    await dev.update()
    assert light_transition.turn_off_transition == 10
    assert light_transition.enabled is True

    max_on = light_transition._module_features["smooth_transition_on"].maximum_value
    assert max_on < Feature.DEFAULT_MAX
    max_off = light_transition._module_features["smooth_transition_off"].maximum_value
    assert max_off < Feature.DEFAULT_MAX

    await light_transition.set_turn_on_transition(0)
    await light_transition.set_turn_off_transition(0)
    await dev.update()
    assert light_transition.enabled is False
