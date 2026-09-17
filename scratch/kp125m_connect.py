"""Minimal connect example for the KP125M at 192.168.10.17.

Run with credentials in the environment:
    KASA_USERNAME=you@example.com KASA_PASSWORD=... .venv/bin/python kp125m_connect.py
"""

import asyncio
import os

from kasa import Credentials, Device, DeviceConfig, DeviceConnectionParameters
from kasa.deviceconfig import DeviceEncryptionType, DeviceFamily

HOST = "192.168.10.17"


async def main() -> None:
    creds = Credentials(os.environ["KASA_USERNAME"], os.environ["KASA_PASSWORD"])

    # Values taken from the discovery result, so no discovery round-trip is needed.
    config = DeviceConfig(
        host=HOST,
        credentials=creds,
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.SmartKasaPlug,
            encryption_type=DeviceEncryptionType.Klap,
            login_version=2,
            https=False,
        ),
    )

    dev = await Device.connect(config=config)
    async with dev:
        await dev.update()
        print(f"{dev.alias} ({dev.model}) @ {dev.host} — on: {dev.is_on}")
        for feat in dev.features.values():
            print(f"  {feat.name} ({feat.id}): {feat.value}")

        # Persist this instead of the password for later connections:
        print("\ncredentials_hash:", dev.credentials_hash)


asyncio.run(main())
