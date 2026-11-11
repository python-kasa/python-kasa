from copy import deepcopy

import pytest
from freezegun.api import FrozenDateTimeFactory
from pytest_mock import MockerFixture

from kasa import Feature, KasaException, Module
from kasa.smart import SmartChildDevice, SmartDevice

from ...device_fixtures import (
    get_device_for_fixture,
    get_fixture_info,
    get_parent_and_child_modules,
    parametrize,
)
from ...fakeprotocol_smart import FakeSmartTransport
from ...fixtureinfo import ComponentFilter

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
light_transition_any = parametrize(
    "has light transition",
    component_filter="on_off_gradually",
    protocol_filter={"SMART"},
)


@light_transition_v1
async def test_module_v1(dev: SmartDevice, mocker: MockerFixture) -> None:
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
async def test_module_gt_v1(dev: SmartDevice, mocker: MockerFixture) -> None:
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


@light_transition_any
async def test_change_transition(dev: SmartDevice, mocker: MockerFixture) -> None:
    """Test the state change transition flag, which only newer firmware reports."""
    light_transition = next(get_parent_and_child_modules(dev, Module.LightTransition))
    supported = isinstance(light_transition.data.get("change_state"), dict)

    if not supported:
        assert "smooth_transition_change" not in light_transition._module_features
        with pytest.raises(KasaException, match="does not support state change"):
            _ = light_transition.change_transition
        return

    feat = light_transition._module_features["smooth_transition_change"]
    assert feat.type is Feature.Type.Switch
    assert feat.value == light_transition.change_transition

    call_spy = mocker.spy(light_transition, "call")
    await light_transition.set_change_transition(True)
    call_spy.assert_called_once_with(
        "set_on_off_gradually_info", {"change_state": {"enable": True}}
    )

    await dev.update()
    assert light_transition.change_transition is True

    await light_transition.set_change_transition(False)
    await dev.update()
    assert light_transition.change_transition is False


@pytest.mark.parametrize("component_version", [3, 4])
@pytest.mark.parametrize("as_child", [False, True])
async def test_transition_features_recover_after_missing_states(
    component_version: int, as_child: bool, freezer: FrozenDateTimeFactory
) -> None:
    """Defer duration controls until a later update supplies their states."""
    fixture = deepcopy(get_fixture_info("L530B(EU)_3.0_1.1.9.json", "SMART"))
    for component in fixture.data["component_nego"]["component_list"]:
        if component["id"] == "on_off_gradually":
            component["ver_code"] = component_version
            break
    fixture.data["get_on_off_gradually_info"] = {"enable": True}

    dev = await get_device_for_fixture(fixture, update_after_init=False)
    assert isinstance(dev, SmartDevice)
    if as_child:
        parent = SmartDevice(dev.host, protocol=dev.protocol)
        dev = await SmartChildDevice.create(
            parent,
            fixture.data["get_device_info"],
            fixture.data["component_nego"],
            protocol=dev.protocol,
        )
        parent._children[dev.device_id] = dev
    await dev.update()
    transition = dev.modules[Module.LightTransition]
    assert transition._last_update_error is not None
    assert "brightness" in dev.features
    assert "smooth_transition_on" not in dev.features
    assert "smooth_transition_off" not in dev.features

    transport = dev.protocol._transport
    assert isinstance(transport, FakeSmartTransport)
    transport.info["get_on_off_gradually_info"] = {
        "on_state": {"duration": 5, "enable": True, "max_duration": 45},
        "off_state": {"duration": 7, "enable": False, "max_duration": 30},
    }
    if component_version == 4:
        transport.info["get_on_off_gradually_info"]["change_state"] = {"enable": True}
    freezer.tick(transition.UPDATE_INTERVAL_AFTER_ERROR_SECS)
    await dev.update()

    assert transition._last_update_error is None
    turn_on = dev.features["smooth_transition_on"]
    turn_off = dev.features["smooth_transition_off"]
    assert (turn_on.minimum_value, turn_on.maximum_value, turn_on.value) == (0, 45, 5)
    assert (turn_off.minimum_value, turn_off.maximum_value, turn_off.value) == (
        0,
        30,
        0,
    )

    change = dev.features.get("smooth_transition_change")
    if component_version == 4:
        assert change is not None
        assert change.value is True
        await change.set_value(False)
    else:
        assert change is None

    await turn_on.set_value(12)
    await turn_off.set_value(8)
    await dev.update()
    assert turn_on.value == 12
    assert turn_off.value == 8
    assert transition._last_update_error is None
    assert dev.features["smooth_transition_on"] is turn_on
    assert dev.features["smooth_transition_off"] is turn_off
    if change is not None:
        assert change.value is False
        assert dev.features["smooth_transition_change"] is change


async def test_recovered_features_wait_for_sibling_and_child_updates(
    freezer: FrozenDateTimeFactory, mocker: MockerFixture
) -> None:
    """Recovery observes the same hook ordering as initial feature creation."""
    fixture = deepcopy(get_fixture_info("L530B(EU)_3.0_1.1.9.json", "SMART"))
    recovered_state = deepcopy(fixture.data["get_on_off_gradually_info"])
    fixture.data["get_on_off_gradually_info"] = {"enable": True}
    dev = await get_device_for_fixture(fixture)
    assert isinstance(dev, SmartDevice)
    transition = dev.modules[Module.LightTransition]
    sibling = dev.modules[Module.Cloud]
    dev._modules.move_to_end(sibling.name)
    events = []
    original_sibling_hook = sibling._post_update_hook

    async def sibling_hook() -> None:
        await original_sibling_hook()
        events.append("sibling")

    async def child_update() -> None:
        events.append("child")

    original_initializer = transition._initialize_features

    def initialize_features() -> None:
        assert events == ["sibling", "child"]
        original_initializer()
        events.append("features")

    mocker.patch.object(sibling, "_post_update_hook", side_effect=sibling_hook)
    mocker.patch.object(
        transition, "_initialize_features", side_effect=initialize_features
    )
    child = mocker.Mock()
    child._update = mocker.AsyncMock(side_effect=child_update)
    dev._children["ordering-probe"] = child
    transport = dev.protocol._transport
    assert isinstance(transport, FakeSmartTransport)
    transport.info["get_on_off_gradually_info"] = recovered_state
    freezer.tick(transition.UPDATE_INTERVAL_AFTER_ERROR_SECS)

    await dev.update()

    assert events == ["sibling", "child", "features"]
    assert transition._last_update_error is None
    assert dev.features["smooth_transition_on"].maximum_value == 60


@pytest.mark.parametrize("failure_stage", ["initialize", "register"])
async def test_recovered_feature_registration_retries_after_failure(
    failure_stage: str, freezer: FrozenDateTimeFactory, mocker: MockerFixture
) -> None:
    """An interrupted registration leaves both feature maps ready for retry."""
    fixture = deepcopy(get_fixture_info("L530B(EU)_3.0_1.1.9.json", "SMART"))
    recovered_state = deepcopy(fixture.data["get_on_off_gradually_info"])
    fixture.data["get_on_off_gradually_info"] = {"enable": True}
    dev = await get_device_for_fixture(fixture)
    assert isinstance(dev, SmartDevice)
    transition = dev.modules[Module.LightTransition]
    module_features = transition._module_features
    device_features = dev.features
    previous_features = device_features.copy()
    transport = dev.protocol._transport
    assert isinstance(transport, FakeSmartTransport)
    transport.info["get_on_off_gradually_info"] = recovered_state
    failure_pending = True

    if failure_stage == "initialize":
        original_initializer = transition._initialize_features

        def initialize_features() -> None:
            nonlocal failure_pending
            original_initializer()
            if failure_pending:
                failure_pending = False
                raise RuntimeError("interrupted feature initialization")

        mocker.patch.object(
            transition, "_initialize_features", side_effect=initialize_features
        )
    else:
        original_add_feature = dev._add_feature

        def add_feature(feature: Feature) -> None:
            nonlocal failure_pending
            original_add_feature(feature)
            if failure_pending and feature.id == "smooth_transition_off":
                failure_pending = False
                raise RuntimeError("interrupted feature registration")

        mocker.patch.object(dev, "_add_feature", side_effect=add_feature)

    freezer.tick(transition.UPDATE_INTERVAL_AFTER_ERROR_SECS)
    with pytest.raises(RuntimeError, match="interrupted feature"):
        await dev.update()

    assert transition._module_features is module_features
    assert module_features == {}
    assert dev.features is device_features
    assert device_features == previous_features

    await dev.update()

    assert transition._last_update_error is None
    assert dev.features["smooth_transition_on"].maximum_value == 60
    assert dev.features["smooth_transition_off"].maximum_value == 60


async def test_pending_transition_features_survive_another_update_error(
    freezer: FrozenDateTimeFactory, mocker: MockerFixture
) -> None:
    """A queued recovery must wait for fresh state after a subsequent error."""
    fixture = deepcopy(get_fixture_info("L530B(EU)_3.0_1.1.9.json", "SMART"))
    recovered_state = deepcopy(fixture.data["get_on_off_gradually_info"])
    fixture.data["get_on_off_gradually_info"] = {"enable": True}
    dev = await get_device_for_fixture(fixture)
    assert isinstance(dev, SmartDevice)
    transition = dev.modules[Module.LightTransition]
    initialize = mocker.spy(transition, "_initialize_features")
    transport = dev.protocol._transport
    assert isinstance(transport, FakeSmartTransport)
    transport.info["get_on_off_gradually_info"] = recovered_state
    child_failure_pending = True

    async def child_update() -> None:
        nonlocal child_failure_pending
        if child_failure_pending:
            child_failure_pending = False
            raise RuntimeError("interrupted child update")

    child = mocker.Mock()
    child._update = mocker.AsyncMock(side_effect=child_update)
    dev._children["recovery-probe"] = child
    freezer.tick(transition.update_interval)
    with pytest.raises(RuntimeError, match="interrupted child update"):
        await dev.update()

    assert transition._last_update_error is None
    initialize.assert_not_called()
    assert "smooth_transition_on" not in dev.features

    transport.info["get_on_off_gradually_info"] = {"enable": True}
    freezer.tick(transition.update_interval)
    await dev.update()

    assert transition._last_update_error is not None
    initialize.assert_not_called()
    assert "brightness" in dev.features
    assert "smooth_transition_on" not in dev.features
    assert "smooth_transition_off" not in dev.features

    transport.info["get_on_off_gradually_info"] = {
        "on_state": {"duration": 9, "enable": True, "max_duration": 42},
        "off_state": {"duration": 11, "enable": True, "max_duration": 18},
    }
    freezer.tick(transition.update_interval)
    await dev.update()

    assert transition._last_update_error is None
    initialize.assert_called_once()
    turn_on = dev.features["smooth_transition_on"]
    turn_off = dev.features["smooth_transition_off"]
    assert (turn_on.maximum_value, turn_on.value) == (42, 9)
    assert (turn_off.maximum_value, turn_off.value) == (18, 11)

    await dev.update()

    initialize.assert_called_once()
    assert dev.features["smooth_transition_on"] is turn_on
    assert dev.features["smooth_transition_off"] is turn_off
