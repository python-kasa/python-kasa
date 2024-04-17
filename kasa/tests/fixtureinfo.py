from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import NamedTuple

from kasa.device_factory import _get_device_type_from_sys_info
from kasa.device_type import DeviceType
from kasa.smart.smartdevice import SmartDevice


class FixtureInfo(NamedTuple):
    name: str
    protocol: str
    data: dict


FixtureInfo.__hash__ = lambda self: hash((self.name, self.protocol))  # type: ignore[attr-defined, method-assign]
FixtureInfo.__eq__ = lambda x, y: hash(x) == hash(y)  # type: ignore[method-assign]


SUPPORTED_IOT_DEVICES = [
    (device, "IOT")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/*.json"
    )
]

SUPPORTED_SMART_DEVICES = [
    (device, "SMART")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/smart/*.json"
    )
]

SUPPORTED_SMART_CHILD_DEVICES = [
    (device, "SMART.CHILD")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/smart/child/*.json"
    )
]


SUPPORTED_DEVICES = (
    SUPPORTED_IOT_DEVICES + SUPPORTED_SMART_DEVICES + SUPPORTED_SMART_CHILD_DEVICES
)


def idgenerator(paramtuple: FixtureInfo):
    try:
        return paramtuple.name + (
            "" if paramtuple.protocol == "IOT" else "-" + paramtuple.protocol
        )
    except:  # TODO: HACK as idgenerator is now used by default  # noqa: E722
        return None


def get_fixture_info() -> list[FixtureInfo]:
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_data = []
    for file, protocol in SUPPORTED_DEVICES:
        p = Path(file)
        folder = Path(__file__).parent / "fixtures"
        if protocol == "SMART":
            folder = folder / "smart"
        if protocol == "SMART.CHILD":
            folder = folder / "smart/child"
        p = folder / file

        with open(p) as f:
            data = json.load(f)

        fixture_name = p.name
        fixture_data.append(
            FixtureInfo(data=data, protocol=protocol, name=fixture_name)
        )
    return fixture_data


FIXTURE_DATA: list[FixtureInfo] = get_fixture_info()


def filter_fixtures(
    desc,
    *,
    data_root_filter: str | None = None,
    protocol_filter: set[str] | None = None,
    model_filter: set[str] | None = None,
    component_filter: str | None = None,
    device_type_filter: list[DeviceType] | None = None,
):
    """Filter the fixtures based on supplied parameters.

    data_root_filter: return fixtures containing the supplied top
        level key, i.e. discovery_result
    protocol_filter: set of protocols to match, IOT, SMART, SMART.CHILD
    model_filter: set of device models to match
    component_filter: filter SMART fixtures that have the provided
    component in component_nego details.
    """

    def _model_match(fixture_data: FixtureInfo, model_filter):
        file_model_region = fixture_data.name.split("_")[0]
        file_model = file_model_region.split("(")[0]
        return file_model in model_filter

    def _component_match(fixture_data: FixtureInfo, component_filter):
        if (component_nego := fixture_data.data.get("component_nego")) is None:
            return False
        components = {
            component["id"]: component["ver_code"]
            for component in component_nego["component_list"]
        }
        return component_filter in components

    def _device_type_match(fixture_data: FixtureInfo, device_type):
        if (component_nego := fixture_data.data.get("component_nego")) is None:
            return _get_device_type_from_sys_info(fixture_data.data) in device_type
        components = [component["id"] for component in component_nego["component_list"]]
        if (info := fixture_data.data.get("get_device_info")) and (
            type_ := info.get("type")
        ):
            return (
                SmartDevice._get_device_type_from_components(components, type_)
                in device_type
            )
        return False

    filtered = []
    if protocol_filter is None:
        protocol_filter = {"IOT", "SMART"}
    for fixture_data in FIXTURE_DATA:
        if data_root_filter and data_root_filter not in fixture_data.data:
            continue
        if fixture_data.protocol not in protocol_filter:
            continue
        if model_filter is not None and not _model_match(fixture_data, model_filter):
            continue
        if component_filter and not _component_match(fixture_data, component_filter):
            continue
        if device_type_filter and not _device_type_match(
            fixture_data, device_type_filter
        ):
            continue

        filtered.append(fixture_data)

    print(f"# {desc}")
    for value in filtered:
        print(f"\t{value.name}")
    filtered.sort()
    return filtered
