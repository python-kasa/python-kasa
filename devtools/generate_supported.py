#!/usr/bin/env python
"""Script that checks supported devices and updates README.md and SUPPORTED.md."""

import json
import os
import sys
from pathlib import Path
from string import Template
from typing import NamedTuple

from kasa.device_factory import _get_device_type_from_sys_info
from kasa.device_type import DeviceType
from kasa.smart.smartdevice import SmartDevice


class SupportedVersion(NamedTuple):
    """Supported version."""

    region: str
    hw: str
    fw: str
    auth: bool


# The order of devices in this dict drives the display order
DEVICE_TYPE_TO_PRODUCT_GROUP = {
    DeviceType.Plug: "Plugs",
    DeviceType.Strip: "Power Strips",
    DeviceType.StripSocket: "Power Strips",
    DeviceType.Dimmer: "Wall Switches",
    DeviceType.WallSwitch: "Wall Switches",
    DeviceType.Fan: "Wall Switches",
    DeviceType.Bulb: "Bulbs",
    DeviceType.LightStrip: "Light Strips",
    DeviceType.Hub: "Hubs",
    DeviceType.Sensor: "Hub-Connected Devices",
    DeviceType.Thermostat: "Hub-Connected Devices",
}


SUPPORTED_FILENAME = "SUPPORTED.md"
README_FILENAME = "README.md"

IOT_FOLDER = "kasa/tests/fixtures/"
SMART_FOLDER = "kasa/tests/fixtures/smart/"


def generate_supported(args):
    """Generate the SUPPORTED.md from the fixtures."""
    print_diffs = "--print-diffs" in args
    running_in_ci = "CI" in os.environ
    print("Generating supported devices")
    if running_in_ci:
        print_diffs = True
        print("Detected running in CI")

    supported = {"kasa": {}, "tapo": {}}

    _get_iot_supported(supported)
    _get_smart_supported(supported)

    readme_updated = _update_supported_file(
        README_FILENAME, _supported_summary(supported), print_diffs
    )
    supported_updated = _update_supported_file(
        SUPPORTED_FILENAME, _supported_detail(supported), print_diffs
    )
    if not readme_updated and not supported_updated:
        print("Supported devices unchanged.")


def _update_supported_file(filename, supported_text, print_diffs) -> bool:
    with open(filename) as f:
        contents = f.readlines()

    start_index = end_index = None
    for index, line in enumerate(contents):
        if line == "<!--SUPPORTED_START-->\n":
            start_index = index + 1
        if line == "<!--SUPPORTED_END-->\n":
            end_index = index

    current_text = "".join(contents[start_index:end_index])
    if current_text != supported_text:
        print(
            f"{filename} has been modified with updated "
            + "supported devices, add file to commit."
        )
        if print_diffs:
            print("##CURRENT##")
            print(current_text)
            print("##NEW##")
            print(supported_text)

        new_contents = contents[:start_index]
        end_contents = contents[end_index:]
        new_contents.append(supported_text)
        new_contents.extend(end_contents)

        with open(filename, "w") as f:
            new_contents_text = "".join(new_contents)
            f.write(new_contents_text)
        return True
    return False


def _supported_summary(supported):
    return _supported_text(
        supported,
        "### Supported $brand$auth devices\n\n$types\n",
        "- **$type_$type_asterix**: $models\n",
    )


def _supported_detail(supported):
    return _supported_text(
        supported,
        "## $brand devices\n\n$preamble\n\n$types\n",
        "### $type_\n\n$models\n",
        "- **$model**\n$versions",
        "  - Hardware: $hw$region / Firmware: $fw$auth_flag\n",
    )


def _supported_text(
    supported, brand_template, types_template, model_template="", version_template=""
):
    brandt = Template(brand_template)
    typest = Template(types_template)
    modelt = Template(model_template)
    versst = Template(version_template)
    brands = ""
    version: SupportedVersion
    for brand, types in supported.items():
        preamble_text = (
            "Some newer Kasa devices require authentication. "
            + "These are marked with <sup>*</sup> in the list below."
            if brand == "kasa"
            else "All Tapo devices require authentication."
        )
        preamble_text += (
            "<br>Hub-Connected Devices may work across TAPO/KASA branded "
            + "hubs even if they don't work across the native apps."
        )
        brand_text = brand.capitalize()
        brand_auth = r"<sup>\*</sup>" if brand == "tapo" else ""
        types_text = ""
        for supported_type, models in sorted(
            # Sort by device type order in the enum
            types.items(),
            key=lambda st: list(DEVICE_TYPE_TO_PRODUCT_GROUP.values()).index(st[0]),
        ):
            models_list = []
            models_text = ""
            for model, versions in sorted(models.items()):
                auth_count = 0
                versions_text = ""
                for version in sorted(versions):
                    region_text = f" ({version.region})" if version.region else ""
                    auth_count += 1 if version.auth else 0
                    vauth_flag = (
                        r"<sup>\*</sup>" if version.auth and brand == "kasa" else ""
                    )
                    if version_template:
                        versions_text += versst.substitute(
                            hw=version.hw,
                            fw=version.fw,
                            region=region_text,
                            auth_flag=vauth_flag,
                        )
                if brand == "kasa" and auth_count > 0:
                    auth_flag = (
                        r"<sup>\*</sup>"
                        if auth_count == len(versions)
                        else r"<sup>\*\*</sup>"
                    )
                else:
                    auth_flag = ""
                if model_template:
                    models_text += modelt.substitute(
                        model=model, versions=versions_text, auth_flag=auth_flag
                    )
                else:
                    models_list.append(f"{model}{auth_flag}")
            models_text = models_text if models_text else ", ".join(models_list)
            type_asterix = (
                r"<sup>\*\*\*</sup>"
                if supported_type == "Hub-Connected Devices"
                else ""
            )
            types_text += typest.substitute(
                type_=supported_type, type_asterix=type_asterix, models=models_text
            )
        brands += brandt.substitute(
            brand=brand_text, types=types_text, auth=brand_auth, preamble=preamble_text
        )
    return brands


def _get_smart_supported(supported):
    for file in Path(SMART_FOLDER).glob("**/*.json"):
        with file.open() as f:
            fixture_data = json.load(f)

        if "discovery_result" in fixture_data:
            model, _, region = fixture_data["discovery_result"][
                "device_model"
            ].partition("(")
            device_type = fixture_data["discovery_result"]["device_type"]
        else:  # child devices of hubs do not have discovery result
            model = fixture_data["get_device_info"]["model"]
            region = fixture_data["get_device_info"].get("specs")
            device_type = fixture_data["get_device_info"]["type"]
        # P100 doesn't have region HW
        region = region.replace(")", "") if region else ""

        _protocol, devicetype = device_type.split(".")
        brand = devicetype[:4].lower()
        components = [
            component["id"]
            for component in fixture_data["component_nego"]["component_list"]
        ]
        dt = SmartDevice._get_device_type_from_components(components, device_type)
        supported_type = DEVICE_TYPE_TO_PRODUCT_GROUP[dt]

        hw_version = fixture_data["get_device_info"]["hw_ver"]
        fw_version = fixture_data["get_device_info"]["fw_ver"]
        fw_version = fw_version.split(" ", maxsplit=1)[0]

        stype = supported[brand].setdefault(supported_type, {})
        smodel = stype.setdefault(model, [])
        smodel.append(
            SupportedVersion(region=region, hw=hw_version, fw=fw_version, auth=True)
        )


def _get_iot_supported(supported):
    for file in Path(IOT_FOLDER).glob("*.json"):
        with file.open() as f:
            fixture_data = json.load(f)
        sysinfo = fixture_data["system"]["get_sysinfo"]
        dt = _get_device_type_from_sys_info(fixture_data)
        supported_type = DEVICE_TYPE_TO_PRODUCT_GROUP[dt]

        model, _, region = sysinfo["model"][:-1].partition("(")
        auth = "discovery_result" in fixture_data
        stype = supported["kasa"].setdefault(supported_type, {})
        smodel = stype.setdefault(model, [])
        fw = sysinfo["sw_ver"].split(" ", maxsplit=1)[0]
        smodel.append(
            SupportedVersion(region=region, hw=sysinfo["hw_ver"], fw=fw, auth=auth)
        )


def main():
    """Entry point to module."""
    generate_supported(sys.argv[1:])


if __name__ == "__main__":
    generate_supported(sys.argv[1:])
