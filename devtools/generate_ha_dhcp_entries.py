"""Generate entries for homeassistant dhcp discovery."""
import json
from pathlib import Path
from pprint import pprint as pp

import asyncclick as click

MANUAL_ENTRIES = {
    "P115(EU)": ["50-91-E3-00-00-00", "3C-52-A1-00-00-00", "30-DE-4B-00-00-00"],
}


def _get_mac_and_model(fixture_data):
    def _legacy(sysinfo):
        mac = sysinfo.get("mac", sysinfo.get("mic_mac"))
        mac = mac.replace(":", "").replace("-", "")
        return mac[:6].lower(), sysinfo.get("model")

    def _new(sysinfo):
        mac = sysinfo.get("mac").replace("-", "")[:6]
        model = sysinfo.get("model")
        return mac[:6].lower(), model

    if "system" in fixture_data:
        return _legacy(fixture_data["system"]["get_sysinfo"])
    else:
        return _new(fixture_data["get_device_info"])

    raise Exception("Unable to find mac & model")


@click.command()
@click.option("--fixture-path", default="kasa/tests/fixtures/")
async def cli(fixture_path):
    """Generate dhcp discovery entries for homeassistant."""
    fixtures = Path(fixture_path)
    mac_to_model = {}
    for file in fixtures.rglob("*.json"):
        mac, model = _get_mac_and_model(json.load(file.open()))
        entries = mac_to_model.setdefault(mac, set())
        if mac == "000000":
            print("No valid mac for %s" % file)
            continue
        entries.add(model)

    for model, macs in MANUAL_ENTRIES.items():
        for mac in macs:
            mac = mac.replace("-", "")[:6].lower()
            entries = mac_to_model.setdefault(mac, set())
            entries.add(model)

    # TODO: fill mac_to_model from static, non-fixture data from homeassistant
    # TODO: generate entries directly to the manifest.json
    pp(mac_to_model)


if __name__ == "__main__":
    cli()
