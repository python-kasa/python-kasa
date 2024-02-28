"""Script that checks supported devices and updates README.md and SUPPORTED.md."""
import json
import sys
from pathlib import Path
from string import Template
from typing import NamedTuple

from kasa.device_factory import (
    get_device_supported_type_from_components,
    get_device_supported_type_from_sysinfo,
)


class SupportedVersion(NamedTuple):
    """Supported version."""

    region: str
    hw: str
    fw: str
    auth: bool


SUPPORTED_FILENAME = "SUPPORTED.md"
README_FILENAME = "README.md"

IOT_FOLDER = "kasa/tests/fixtures/"
SMART_FOLDER = "kasa/tests/fixtures/smart/"


def generate_supported(args):
    """Generate the SUPPORTED.md from the fixtures."""
    print("Generating supported devices")

    supported = {"kasa": {}, "tapo": {}}

    _get_iot_supported(supported)
    _get_smart_supported(supported)

    readme_updated = _update_supported_file(
        README_FILENAME, _supported_summary(supported)
    )
    supported_updated = _update_supported_file(
        SUPPORTED_FILENAME, _supported_detail(supported)
    )
    if not readme_updated and not supported_updated:
        print("Supported devices unchanged.")


def _update_supported_file(filename, supported_text) -> bool:
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
        "- **$type_**: $models\n",
    )


def _supported_detail(supported):
    return _supported_text(
        supported,
        "## $brand devices\n\n$types\n",
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
        brand_text = brand.capitalize()
        brand_auth = r"<sup>\*</sup>" if brand == "tapo" else ""
        types_text = ""
        for type_, models in types.items():
            models_list = []
            models_text = ""
            for model, versions in sorted(models.items()):
                auth_count = 0
                versions_text = ""
                for version in versions:
                    region_text = f" ({version.region})" if version.region else ""
                    auth_count += 1 if version.auth else 0
                    vauth_flag = r"<sup>\*</sup>" if version.auth else ""
                    vauth_flag = "" if brand == "tapo" else vauth_flag
                    if version_template:
                        versions_text += versst.substitute(
                            hw=version.hw,
                            fw=version.fw,
                            region=region_text,
                            auth_flag=vauth_flag,
                        )
                auth_flag = (
                    r"<sup>\*</sup>"
                    if auth_count == len(versions)
                    else r"<sup>\*\*</sup>"
                    if auth_count > 0
                    else ""
                )
                auth_flag = "" if brand == "tapo" else auth_flag
                if model_template:
                    models_text += modelt.substitute(
                        model=model, versions=versions_text, auth_flag=auth_flag
                    )
                else:
                    models_list.append(f"{model}{auth_flag}")
            models_text = models_text if models_text else ", ".join(models_list)
            types_text += typest.substitute(type_=type_, models=models_text)
        brands += brandt.substitute(brand=brand_text, types=types_text, auth=brand_auth)
    return brands


def _get_smart_supported(supported):
    smart_files = [f for f in Path(SMART_FOLDER).glob("*.json")]
    for smart_file in smart_files:
        with open(smart_file) as f:
            fixture_data = json.load(f)

        model, _, region = fixture_data["discovery_result"]["device_model"].partition(
            "("
        )
        # P100 doesn't have region HW
        region = region.replace(")", "") if region else ""
        device_type = fixture_data["discovery_result"]["device_type"]
        _protocol, devicetype = device_type.split(".")
        brand = devicetype[:4].lower()
        components = [
            component["id"]
            for component in fixture_data["component_nego"]["component_list"]
        ]
        supported_device_type = get_device_supported_type_from_components(
            components, device_type
        )
        supported_type = supported_device_type.value

        hw_version = fixture_data["get_device_info"]["hw_ver"]
        fw_version = fixture_data["get_device_info"]["fw_ver"]
        fw_version = fw_version.split(" ", maxsplit=1)[0]

        stype = supported[brand].setdefault(supported_type, {})
        smodel = stype.setdefault(model, [])
        smodel.append(
            SupportedVersion(region=region, hw=hw_version, fw=fw_version, auth=True)
        )


def _get_iot_supported(supported):
    iot_files = [f for f in Path(IOT_FOLDER).glob("*.json")]
    for iot_file in iot_files:
        with open(iot_file) as f:
            fixture_data = json.load(f)
        sysinfo = fixture_data["system"]["get_sysinfo"]
        supported_device_type = get_device_supported_type_from_sysinfo(sysinfo)
        supported_type = supported_device_type.value

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
