from __future__ import annotations

import copy
import glob
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import pytest

from kasa.device_type import DeviceType
from kasa.iot import IotDevice
from kasa.smart.smartdevice import SmartDevice
from kasa.smartcam import SmartCamDevice


class FixtureInfo(NamedTuple):
    name: str
    protocol: str
    data: dict


class ComponentFilter(NamedTuple):
    component_name: str
    minimum_version: int = 0
    maximum_version: int | None = None


FixtureInfo.__hash__ = lambda self: hash((self.name, self.protocol))  # type: ignore[attr-defined, method-assign]
FixtureInfo.__eq__ = lambda x, y: hash(x) == hash(y)  # type: ignore[method-assign]


SUPPORTED_IOT_DEVICES = [
    (device, "IOT")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/iot/*.json"
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

SUPPORTED_SMARTCAM_DEVICES = [
    (device, "SMARTCAM")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/smartcam/*.json"
    )
]

SUPPORTED_SMARTCAM_CHILD_DEVICES = [
    (device, "SMARTCAM.CHILD")
    for device in glob.glob(
        os.path.dirname(os.path.abspath(__file__)) + "/fixtures/smartcam/child/*.json"
    )
]

SUPPORTED_DEVICES = (
    SUPPORTED_IOT_DEVICES
    + SUPPORTED_SMART_DEVICES
    + SUPPORTED_SMART_CHILD_DEVICES
    + SUPPORTED_SMARTCAM_DEVICES
    + SUPPORTED_SMARTCAM_CHILD_DEVICES
)


def idgenerator(paramtuple: FixtureInfo):
    try:
        return paramtuple.name + (
            "" if paramtuple.protocol == "IOT" else "-" + paramtuple.protocol
        )
    except:  # TODO: HACK as idgenerator is now used by default  # noqa: E722
        return None


def get_fixture_infos() -> list[FixtureInfo]:
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_data = []
    for file, protocol in SUPPORTED_DEVICES:
        p = Path(file)

        with open(file) as f:
            data = json.load(f)

        fixture_name = p.name
        fixture_data.append(
            FixtureInfo(data=data, protocol=protocol, name=fixture_name)
        )
    return fixture_data


FIXTURE_DATA: list[FixtureInfo] = get_fixture_infos()


def filter_fixtures(
    desc,
    *,
    data_root_filter: str | None = None,
    protocol_filter: set[str] | None = None,
    model_filter: set[str] | None = None,
    model_startswith_filter: str | None = None,
    component_filter: str | ComponentFilter | None = None,
    device_type_filter: Iterable[DeviceType] | None = None,
    fixture_list: list[FixtureInfo] = FIXTURE_DATA,
):
    """Filter the fixtures based on supplied parameters.

    data_root_filter: return fixtures containing the supplied top
        level key, i.e. discovery_result
    protocol_filter: set of protocols to match, IOT, SMART, SMART.CHILD
    model_filter: set of device models to match
    component_filter: filter SMART fixtures that have the provided
    component in component_nego details.
    """

    def _model_match(fixture_data: FixtureInfo, model_filter: set[str]):
        if isinstance(model_filter, str):
            model_filter = {model_filter}
        assert isinstance(model_filter, set), "model filter must be a set"
        model_filter_list = [mf for mf in model_filter]
        if (
            len(model_filter_list) == 1
            and (model := model_filter_list[0])
            and len(model.split("_")) == 3
        ):
            # filter string includes hw and fw, return exact match
            return fixture_data.name == f"{model}.json"
        file_model_region = fixture_data.name.split("_")[0]
        file_model = file_model_region.split("(")[0]
        return file_model in model_filter

    def _model_startswith_match(fixture_data: FixtureInfo, starts_with: str):
        return fixture_data.name.startswith(starts_with)

    def _component_match(
        fixture_data: FixtureInfo, component_filter: str | ComponentFilter
    ):
        components = {}
        if component_nego := fixture_data.data.get("component_nego"):
            components = {
                component["id"]: component["ver_code"]
                for component in component_nego["component_list"]
            }
        if get_app_component_list := fixture_data.data.get("getAppComponentList"):
            components = {
                component["name"]: component["version"]
                for component in get_app_component_list["app_component"][
                    "app_component_list"
                ]
            }
        if not components:
            return False
        if isinstance(component_filter, str):
            return component_filter in components
        else:
            return (
                (ver_code := components.get(component_filter.component_name))
                and ver_code >= component_filter.minimum_version
                and (
                    component_filter.maximum_version is None
                    or ver_code <= component_filter.maximum_version
                )
            )

    def _device_type_match(fixture_data: FixtureInfo, device_type):
        if fixture_data.protocol in {"SMART", "SMART.CHILD"}:
            info = fixture_data.data["get_device_info"]
            component_nego = fixture_data.data["component_nego"]
            components = [
                component["id"] for component in component_nego["component_list"]
            ]
            return (
                SmartDevice._get_device_type_from_components(components, info["type"])
                in device_type
            )
        elif fixture_data.protocol == "IOT":
            return (
                IotDevice._get_device_type_from_sys_info(fixture_data.data)
                in device_type
            )
        elif fixture_data.protocol in {"SMARTCAM", "SMARTCAM.CHILD"}:
            info = fixture_data.data["getDeviceInfo"]["device_info"]["basic_info"]
            return SmartCamDevice._get_device_type_from_sysinfo(info) in device_type
        return False

    filtered = []
    if protocol_filter is None:
        protocol_filter = {"IOT", "SMART", "SMARTCAM"}
    for fixture_data in fixture_list:
        if data_root_filter and data_root_filter not in fixture_data.data:
            continue
        if fixture_data.protocol not in protocol_filter:
            continue
        if model_filter is not None and not _model_match(fixture_data, model_filter):
            continue
        if model_startswith_filter is not None and not _model_startswith_match(
            fixture_data, model_startswith_filter
        ):
            continue
        if component_filter and not _component_match(fixture_data, component_filter):
            continue
        if device_type_filter and not _device_type_match(
            fixture_data, device_type_filter
        ):
            continue

        filtered.append(fixture_data)

    filtered.sort()
    return filtered


@pytest.fixture(
    params=filter_fixtures("all fixture infos"),
    ids=idgenerator,
)
def fixture_info(request, mocker):
    """Return raw discovery file contents as JSON. Used for discovery tests."""
    fixture_info = request.param
    fixture_data = copy.deepcopy(fixture_info.data)
    return FixtureInfo(fixture_info.name, fixture_info.protocol, fixture_data)
