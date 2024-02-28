"""Script that checks supported devices and updates README.md and SUPPORTED.md."""
import json
import sys
from pathlib import Path
from string import Template
from typing import NamedTuple


class SupportedVersion(NamedTuple):
    """Supported version."""

    region: str
    hw: str
    fw: str
    auth: bool


SUPPORTED_FILENAME = "SUPPORTED.md"
README_FILENAME = "README.md"

PLUGS = "Plugs"
POWER_STRIPS = "Power Strips"
WALL_SWITCHES = "Wall Switches"
BULBS = "Bulbs"
LIGHT_STRIPS = "Light Strips"
HUBS = "Hubs"


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
        brand_auth = "<sup>\*</sup>" if brand == "tapo" else ""
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
                    vauth_flag = "<sup>\*</sup>" if version.auth else ""
                    vauth_flag = "" if brand == "tapo" else vauth_flag
                    if version_template:
                        versions_text += versst.substitute(
                            hw=version.hw,
                            fw=version.fw,
                            region=region_text,
                            auth_flag=vauth_flag,
                        )
                auth_flag = (
                    "<sup>\*</sup>"
                    if auth_count == len(versions)
                    else "<sup>\*\*</sup>"
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
        brand, type_ = devicetype[:4].lower(), devicetype[4:]
        if brand not in ["kasa", "tapo"]:
            print(
                f"FAIL {smart_file} does not have a "
                + f"supported device_type {device_type}"
            )
            continue
        components = [
            component["id"]
            for component in fixture_data["component_nego"]["component_list"]
        ]
        if type_ == "BULB":
            supported_type = LIGHT_STRIPS if "light_strip" in components else BULBS
        elif type_ == "PLUG":
            supported_type = POWER_STRIPS if "child_device" in components else PLUGS
        elif type_ == "SWITCH":
            supported_type = WALL_SWITCHES
        elif type_ == "HUB":
            supported_type = HUBS
        else:
            print(
                f"FAIL {smart_file} does not have a "
                + f"supported device_type {device_type}"
            )
            continue

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
        model, _, region = sysinfo["model"][:-1].partition("(")
        auth = "discovery_result" in fixture_data
        type_ = sysinfo.get("type", sysinfo.get("mic_type"))
        if type_ == "IOT.SMARTBULB":
            supported_type = LIGHT_STRIPS if "length" in sysinfo else BULBS
        else:
            if "children" in sysinfo:
                supported_type = POWER_STRIPS
            else:
                if "dev_name" not in sysinfo:
                    print(f"FAIL {iot_file} does not have dev_name")
                    continue
                if "light" in sysinfo["dev_name"].lower():
                    supported_type = WALL_SWITCHES
                else:
                    supported_type = PLUGS
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
