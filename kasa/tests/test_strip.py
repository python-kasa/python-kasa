from datetime import datetime

import pytest

from kasa import SmartDeviceException, SmartStrip

from .conftest import handle_turn_on, pytestmark, strip, turn_on


@strip
@turn_on
async def test_children_change_state(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    for plug in dev.children:
        orig_state = plug.is_on
        if orig_state:
            await plug.turn_off()
            assert not plug.is_on
            assert plug.is_off

            await plug.turn_on()
            assert plug.is_on
            assert not plug.is_off
        else:
            await plug.turn_on()
            assert plug.is_on
            assert not plug.is_off

            await plug.turn_off()
            assert not plug.is_on
            assert plug.is_off


@strip
async def test_children_alias(dev):
    test_alias = "TEST1234"
    for plug in dev.children:
        original = plug.alias
        await plug.set_alias(alias=test_alias)
        await dev.update()  # TODO: set_alias does not call parent's update()..
        assert plug.alias == test_alias

        await plug.set_alias(alias=original)
        await dev.update()  # TODO: set_alias does not call parent's update()..
        assert plug.alias == original


@strip
async def test_children_on_since(dev):
    on_sinces = []
    for plug in dev.children:
        if plug.is_on:
            on_sinces.append(plug.on_since)
            assert isinstance(plug.on_since, datetime)
        else:
            assert plug.on_since is None

    if dev.is_off:
        assert dev.on_since is None
    # TODO: testing this would require some mocking utcnow which is not
    # very straightforward.
    # else:
    #    assert dev.on_since == max(on_sinces)


@strip
async def test_get_plug_by_name(dev: SmartStrip):
    name = dev.children[0].alias
    assert dev.get_plug_by_name(name) == dev.children[0]

    with pytest.raises(SmartDeviceException):
        dev.get_plug_by_name("NONEXISTING NAME")


@strip
async def test_get_plug_by_index(dev: SmartStrip):
    assert dev.get_plug_by_index(0) == dev.children[0]

    with pytest.raises(SmartDeviceException):
        dev.get_plug_by_index(-1)

    with pytest.raises(SmartDeviceException):
        dev.get_plug_by_index(len(dev.children))


@pytest.mark.skip("this test will wear out your relays")
async def test_all_binary_states(dev):
    # test every binary state
    # TODO: this needs to be fixed, dev.plugs is not available for each device..
    for state in range(2 ** len(dev.children)):
        # create binary state map
        state_map = {}
        for plug_index in range(len(dev.children)):
            state_map[plug_index] = bool((state >> plug_index) & 1)

            if state_map[plug_index]:
                await dev.turn_on(index=plug_index)
            else:
                await dev.turn_off(index=plug_index)

        # check state map applied
        for index, state in dev.is_on.items():
            assert state_map[index] == state

        # toggle each outlet with state map applied
        for plug_index in range(len(dev.children)):

            # toggle state
            if state_map[plug_index]:
                await dev.turn_off(index=plug_index)
            else:
                await dev.turn_on(index=plug_index)

            # only target outlet should have state changed
            for index, state in dev.is_on.items():
                if index == plug_index:
                    assert state != state_map[index]
                else:
                    assert state == state_map[index]

            # reset state
            if state_map[plug_index]:
                await dev.turn_on(index=plug_index)
            else:
                await dev.turn_off(index=plug_index)

            # original state map should be restored
            for index, state in dev.is_on.items():
                assert state == state_map[index]
