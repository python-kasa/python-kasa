"""Module for childsetup interface.

The childsetup module allows pairing and unpairing of supported child device types to
hubs.

>>> from kasa import Discover, Module, LightState
>>>
>>> dev = await Discover.discover_single(
>>>     "127.0.0.6",
>>>     username="user@example.com",
>>>     password="great_password"
>>> )
>>> await dev.update()
>>> print(dev.alias)
Tapo Hub

>>> childsetup = dev.modules[Module.ChildSetup]
>>> childsetup.supported_categories
['camera', 'subg.trv', 'subg.trigger', 'subg.plugswitch']

Put child devices in pairing mode.
The hub will pair with all supported devices in pairing mode:

>>> added = await childsetup.pair()
>>> added
[{'device_id': 'SCRUBBED_CHILD_DEVICE_ID_5', 'category': 'subg.trigger.button', \
'device_model': 'S200B', 'name': 'I01BU0tFRF9OQU1FIw===='}]

>>> for child in dev.children:
>>>     print(f"{child.device_id} - {child.model}")
SCRUBBED_CHILD_DEVICE_ID_1 - T310
SCRUBBED_CHILD_DEVICE_ID_2 - T315
SCRUBBED_CHILD_DEVICE_ID_3 - T110
SCRUBBED_CHILD_DEVICE_ID_4 - S200B
SCRUBBED_CHILD_DEVICE_ID_5 - S200B

Unpair with the child `device_id`:

>>> await childsetup.unpair("SCRUBBED_CHILD_DEVICE_ID_4")
>>> for child in dev.children:
>>>     print(f"{child.device_id} - {child.model}")
SCRUBBED_CHILD_DEVICE_ID_1 - T310
SCRUBBED_CHILD_DEVICE_ID_2 - T315
SCRUBBED_CHILD_DEVICE_ID_3 - T110
SCRUBBED_CHILD_DEVICE_ID_5 - S200B

"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..module import Module


class ChildSetup(Module, ABC):
    """Interface for child setup on hubs."""

    @property
    @abstractmethod
    def supported_categories(self) -> list[str]:
        """Supported child device categories."""

    @abstractmethod
    async def pair(self, *, timeout: int = 10) -> list[dict]:
        """Scan for new devices and pair them."""

    @abstractmethod
    async def unpair(self, device_id: str) -> dict:
        """Remove device from the hub."""
