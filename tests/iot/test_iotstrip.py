from unittest.mock import AsyncMock

from kasa import Module
from tests.conftest import strip_emeter_iot, strip_iot


@strip_iot
async def test_strip_update_and_child_update_behaviors(dev):
    await dev.update()
    await dev.update(update_children=False)

    assert dev.children, "Expected strip device to have children"

    child = dev.children[0]
    await child.update(update_children=False)

    assert getattr(child, "_features", None)


@strip_iot
async def test_strip_child_delegated_properties(dev):
    await dev.update()
    child = dev.children[0]

    assert child.led is False
    assert child.time == dev.time
    assert child.timezone == dev.timezone

    na = child.next_action
    assert isinstance(na, dict)
    assert "type" in na


@strip_emeter_iot
async def test_strip_emeter_erase_stats(dev, mocker):
    await dev.update()

    for child in dev.children:
        energy = child.modules.get(Module.Energy)
        if energy:
            mocker.patch.object(energy, "erase_stats", AsyncMock(return_value={}))

    res = await dev.modules[Module.Energy].erase_stats()
    assert res == {}
