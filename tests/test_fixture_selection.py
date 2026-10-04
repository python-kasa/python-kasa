"""Tests for representative device fixture selection."""

from __future__ import annotations

import pytest

from .fixture_selection import (
    find_fixture_infos,
    fixture_traits,
    select_representative_fixtures,
)
from .fixtureinfo import FIXTURE_DATA, FixtureInfo


def _fixture(
    name: str,
    protocol: str,
    *,
    keys: tuple[str, ...] = (),
    components: tuple[tuple[str, int], ...] = (),
) -> FixtureInfo:
    data: dict[str, object] = {key: {} for key in keys}
    if components:
        data["component_nego"] = {
            "component_list": [
                {"id": component_id, "ver_code": version}
                for component_id, version in components
            ]
        }
    return FixtureInfo(name=name, protocol=protocol, data=data)


def test_selection_keeps_small_fixture_pools():
    fixtures = (
        _fixture("B.json", "SMART"),
        _fixture("A.json", "IOT"),
    )

    assert select_representative_fixtures(fixtures, limit=2) == (
        fixtures[1],
        fixtures[0],
    )


def test_selection_is_deterministic_and_limited():
    fixtures = tuple(
        _fixture(
            f"MODEL{index}.json",
            "IOT" if index % 2 else "SMART",
            keys=(f"method_{index}",),
        )
        for index in range(8)
    )

    selected = select_representative_fixtures(fixtures, limit=4)

    assert len(selected) == 4
    assert selected == select_representative_fixtures(reversed(fixtures), limit=4)
    assert {fixture.protocol for fixture in selected} == {"IOT", "SMART"}


def test_selection_covers_distinct_components():
    fixtures = (
        _fixture("PLUG1.json", "SMART", components=(("device", 1),)),
        _fixture("PLUG2.json", "SMART", components=(("device", 2),)),
        _fixture("BULB.json", "SMART", components=(("brightness", 1),)),
    )

    selected = select_representative_fixtures(fixtures, limit=2)
    selected_traits = set().union(*(fixture_traits(item) for item in selected))

    assert "component:device" in selected_traits
    assert "component:brightness" in selected_traits


def test_repository_selection_covers_every_protocol():
    selected = select_representative_fixtures(FIXTURE_DATA)

    assert {fixture.protocol for fixture in selected} == {
        fixture.protocol for fixture in FIXTURE_DATA
    }


def test_selection_rejects_invalid_limit():
    with pytest.raises(
        ValueError,
        match="representative fixture limit must be positive",
    ):
        select_representative_fixtures((), limit=0)


def test_find_fixture_infos_in_nested_parameters():
    first = _fixture("FIRST.json", "IOT")
    second = _fixture("SECOND.json", "SMART")

    assert find_fixture_infos({"first": [first], "nested": ("value", {second})}) == (
        first,
        second,
    )
    assert find_fixture_infos("not a fixture") == ()
