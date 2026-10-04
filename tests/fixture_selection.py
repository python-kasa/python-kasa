"""Select deterministic representative device fixtures for broad test matrices."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .fixtureinfo import FixtureInfo

DEFAULT_REPRESENTATIVE_LIMIT = 6


def _model_name(fixture: FixtureInfo) -> str:
    """Return the model portion of a fixture filename."""
    return fixture.name.split("_", maxsplit=1)[0].split("(", maxsplit=1)[0]


def _component_traits(fixture: FixtureInfo) -> set[str]:
    """Return component identifiers and versions advertised by a fixture."""
    traits: set[str] = set()
    component_nego = fixture.data.get("component_nego", {})
    for component in component_nego.get("component_list", []):
        component_id = component.get("id")
        version = component.get("ver_code")
        if component_id:
            traits.add(f"component:{component_id}")
            traits.add(f"component-version:{component_id}:{version}")

    app_components = fixture.data.get("getAppComponentList", {}).get(
        "app_component", {}
    )
    for component in app_components.get("app_component_list", []):
        component_id = component.get("name")
        version = component.get("version")
        if component_id:
            traits.add(f"component:{component_id}")
            traits.add(f"component-version:{component_id}:{version}")
    return traits


def _discovery_traits(fixture: FixtureInfo) -> set[str]:
    """Return transport and authentication traits from discovery data."""
    traits: set[str] = set()
    discovery_result = fixture.data.get("discovery_result", {}).get("result", {})
    encryption = discovery_result.get("mgt_encrypt_schm", {})
    for key in ("encrypt_type", "is_support_https", "lv"):
        if key in encryption:
            traits.add(f"discovery:{key}:{encryption[key]}")

    for key in ("device_type", "device_model", "result_type"):
        if key in discovery_result:
            value = discovery_result[key]
            if key == "device_model":
                value = str(value).split("(", maxsplit=1)[0]
            traits.add(f"discovery:{key}:{value}")
    return traits


def fixture_traits(fixture: FixtureInfo) -> frozenset[str]:
    """Return stable behavioral traits used for representative selection."""
    top_level_keys = tuple(sorted(fixture.data))
    traits = {
        f"protocol:{fixture.protocol}",
        f"model:{_model_name(fixture)}",
        f"role:{'child' if '.CHILD' in fixture.protocol else 'parent'}",
        f"top-level-shape:{'|'.join(top_level_keys)}",
        *(f"top-level-key:{key}" for key in top_level_keys),
    }
    traits.update(_component_traits(fixture))
    traits.update(_discovery_traits(fixture))
    return frozenset(traits)


def select_representative_fixtures(
    fixtures: Iterable[FixtureInfo],
    *,
    limit: int = DEFAULT_REPRESENTATIVE_LIMIT,
) -> tuple[FixtureInfo, ...]:
    """Select a deterministic, diverse subset of fixtures.

    Selection happens independently for each parametrized test function. A greedy
    set-cover pass favors fixtures that add the most protocol, model, component,
    discovery, and response-shape traits. Stable filename/protocol ordering breaks
    ties so every xdist worker collects the same tests.
    """
    if limit < 1:
        raise ValueError("representative fixture limit must be positive")

    fixture_list = sorted(set(fixtures), key=lambda item: (item.name, item.protocol))
    if len(fixture_list) <= limit:
        return tuple(fixture_list)

    traits_by_fixture = {fixture: fixture_traits(fixture) for fixture in fixture_list}
    uncovered = set().union(*traits_by_fixture.values())
    selected: list[FixtureInfo] = []
    remaining = set(fixture_list)

    # Protocol implementations have different transports, discovery formats, and
    # device classes. Reserve one slot for every protocol present in the test's
    # fixture pool before the general set-cover pass.
    for protocol in sorted({fixture.protocol for fixture in fixture_list}):
        if len(selected) >= limit:
            break
        fixture = min(
            (candidate for candidate in remaining if candidate.protocol == protocol),
            key=lambda candidate: (-len(traits_by_fixture[candidate]), candidate.name),
        )
        selected.append(fixture)
        uncovered.difference_update(traits_by_fixture[fixture])
        remaining.remove(fixture)

    while remaining and len(selected) < limit:
        fixture = min(
            remaining,
            key=lambda candidate: (
                -len(traits_by_fixture[candidate] & uncovered),
                len(traits_by_fixture[candidate]),
                candidate.name,
                candidate.protocol,
            ),
        )
        selected.append(fixture)
        uncovered.difference_update(traits_by_fixture[fixture])
        remaining.remove(fixture)

    return tuple(sorted(selected, key=lambda item: (item.name, item.protocol)))


def find_fixture_infos(value: Any) -> tuple[FixtureInfo, ...]:
    """Recursively find fixture parameters embedded in a pytest callspec value."""
    if isinstance(value, FixtureInfo):
        return (value,)
    if isinstance(value, dict):
        nested = (find_fixture_infos(item) for item in value.values())
    elif isinstance(value, list | tuple | set | frozenset):
        nested = (find_fixture_infos(item) for item in value)
    else:
        return ()
    return tuple(fixture for group in nested for fixture in group)
