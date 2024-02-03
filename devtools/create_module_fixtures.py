"""Create fixture files for modules supported by a device.

This script can be used to create fixture files for individual modules.
"""

import asyncio
import json
from pathlib import Path
from typing import cast

import typer

from kasa import Discover
from kasa.iot import IotDevice

app = typer.Typer()


def create_fixtures(dev: IotDevice, outputdir: Path):
    """Iterate over supported modules and create version-specific fixture files."""
    for name, module in dev.modules.items():
        module_dir = outputdir / name
        if not module_dir.exists():
            module_dir.mkdir(exist_ok=True, parents=True)

        sw_version = dev.hw_info["sw_ver"]
        sw_version = sw_version.split(" ", maxsplit=1)[0]
        filename = f"{dev.model}_{dev.hw_info['hw_ver']}_{sw_version}.json"
        module_file = module_dir / filename

        if module_file.exists():
            continue

        typer.echo(f"Creating {module_file} for {dev.model}")
        with module_file.open("w") as f:
            json.dump(module.data, f, indent=4)


@app.command()
def create_module_fixtures(
    outputdir: Path,
    host: str = typer.Option(default=None),
    network: str = typer.Option(default=None),
):
    """Create module fixtures for given host/network."""
    devs = []
    if host is not None:
        dev: IotDevice = cast(IotDevice, asyncio.run(Discover.discover_single(host)))
        devs.append(dev)
    else:
        if network is None:
            network = "255.255.255.255"
        devs = asyncio.run(Discover.discover(target=network)).values()
        for dev in devs:
            dev = cast(IotDevice, dev)
            asyncio.run(dev.update())

    for dev in devs:
        create_fixtures(dev, outputdir)


if __name__ == "__main__":
    app()
