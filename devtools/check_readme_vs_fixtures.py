"""Script that checks if README.md is missing devices that have fixtures."""
import re
import sys

from kasa.tests.conftest import (
    ALL_DEVICES,
    BULBS,
    DIMMERS,
    LIGHT_STRIPS,
    PLUGS,
    STRIPS,
)

with open("README.md") as f:
    readme = f.read()

typemap = {
    "light strips": LIGHT_STRIPS,
    "bulbs": BULBS,
    "plugs": PLUGS,
    "strips": STRIPS,
    "dimmers": DIMMERS,
}


def _get_device_type(dev, typemap):
    for typename, devs in typemap.items():
        if dev in devs:
            return typename
    else:
        return "Unknown type"


found_unlisted = False
for dev in ALL_DEVICES:
    regex = rf"^\*.*\s{dev}"
    match = re.search(regex, readme, re.MULTILINE)
    if match is None:
        print(f"{dev} not listed in {_get_device_type(dev, typemap)}")
        found_unlisted = True

if found_unlisted:
    sys.exit(-1)
