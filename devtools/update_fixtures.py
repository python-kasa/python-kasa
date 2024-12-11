"""Module to mass update fixture files."""

import json
import logging
from collections.abc import Callable
from pathlib import Path

import asyncclick as click

from devtools.dump_devinfo import _wrap_redactors
from kasa.discover import NEW_DISCOVERY_REDACTORS, redact_data
from kasa.protocols.iotprotocol import REDACTORS as IOT_REDACTORS
from kasa.protocols.smartprotocol import REDACTORS as SMART_REDACTORS

FIXTURE_FOLDER = "tests/fixtures/"

_LOGGER = logging.getLogger(__name__)


def update_fixtures(update_func: Callable[[dict], bool], *, dry_run: bool) -> None:
    """Run the update function against the fixtures."""
    for file in Path(FIXTURE_FOLDER).glob("**/*.json"):
        with file.open("r") as f:
            fixture_data = json.load(f)

        if file.parent.name == "serialization":
            continue
        changed = update_func(fixture_data)
        if changed:
            click.echo(f"Will update {file.name}\n")
        if changed and not dry_run:
            with file.open("w") as f:
                json.dump(fixture_data, f, sort_keys=True, indent=4)
                f.write("\n")


def _discovery_result_update(info) -> bool:
    """Update discovery_result to be the raw result and error_code."""
    if (disco_result := info.get("discovery_result")) and "result" not in disco_result:
        info["discovery_result"] = {
            "result": disco_result,
            "error_code": 0,
        }
        return True
    return False


def _child_device_id_update(info) -> bool:
    """Update child device ids to be the scrubbed ids from dump_devinfo."""
    changed = False
    if get_child_device_list := info.get("get_child_device_list"):
        child_device_list = get_child_device_list["child_device_list"]
        child_component_list = info["get_child_device_component_list"][
            "child_component_list"
        ]
        for index, child_device in enumerate(child_device_list):
            child_component = child_component_list[index]
            if "SCRUBBED" not in child_device["device_id"]:
                dev_id = f"SCRUBBED_CHILD_DEVICE_ID_{index + 1}"
                click.echo(
                    f"child_device_id{index}: {child_device['device_id']} -> {dev_id}"
                )
                child_device["device_id"] = dev_id
                child_component["device_id"] = dev_id
                changed = True

    if children := info.get("system", {}).get("get_sysinfo", {}).get("children"):
        for index, child_device in enumerate(children):
            if "SCRUBBED" not in child_device["id"]:
                dev_id = f"SCRUBBED_CHILD_DEVICE_ID_{index + 1}"
                click.echo(f"child_device_id{index}: {child_device['id']} -> {dev_id}")
                child_device["id"] = dev_id
                changed = True

    return changed


def _diff_data(fullkey, data1, data2, diffs):
    if isinstance(data1, dict):
        for k, v in data1.items():
            _diff_data(fullkey + "/" + k, v, data2[k], diffs)
    elif isinstance(data1, list):
        for index, item in enumerate(data1):
            _diff_data(fullkey + "/" + str(index), item, data2[index], diffs)
    elif data1 != data2:
        diffs[fullkey] = (data1, data2)


def _redactor_result_update(info) -> bool:
    """Update fixtures with the output using the common redactors."""
    changed = False

    redactors = IOT_REDACTORS if "system" in info else SMART_REDACTORS

    for key, val in info.items():
        if not isinstance(val, dict):
            continue
        if key == "discovery_result":
            info[key] = redact_data(val, _wrap_redactors(NEW_DISCOVERY_REDACTORS))
        else:
            info[key] = redact_data(val, _wrap_redactors(redactors))
        diffs: dict[str, tuple[str, str]] = {}
        _diff_data(key, val, info[key], diffs)
        if diffs:
            for k, v in diffs.items():
                click.echo(f"{k}: {v[0]} -> {v[1]}")
            changed = True

    return changed


@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    is_flag=True,
    type=bool,
    help="Perform a dry run without saving.",
)
@click.command()
async def cli(dry_run: bool) -> None:
    """Cli method fo rupdating fixtures."""
    update_fixtures(_discovery_result_update, dry_run=dry_run)
    update_fixtures(_child_device_id_update, dry_run=dry_run)
    update_fixtures(_redactor_result_update, dry_run=dry_run)


if __name__ == "__main__":
    cli()
