"""Interact with child devices.

>>> from kasa import Discover
>>>
>>> dev = await Discover.discover_single(
>>>     "127.0.0.1",
>>>     username="user@example.com",
>>>     password="great_password"
>>> )
>>> await dev.update()
>>> print(dev.alias)
Bedroom Power Strip

All methods act on the whole strip:

>>> for plug in dev.children:
>>>    print(f"{plug.alias}: {plug.is_on}")
Plug 1: True
Plug 2: False
Plug 3: False
>>> dev.is_on
True
>>> await dev.turn_off()
>>> await dev.update()

Accessing individual plugs can be done using the `children` property:

>>> len(dev.children)
3
>>> for plug in dev.children:
>>>    print(f"{plug.alias}: {plug.is_on}")
Plug 1: False
Plug 2: False
Plug 3: False
>>> await dev.children[1].turn_on()
>>> await dev.update()
>>> dev.is_on
True
"""

from ..smartmodule import SmartModule


class ChildDevice(SmartModule):
    """Implementation for child devices."""

    REQUIRED_COMPONENT = "child_device"
    QUERY_GETTER_NAME = "get_child_device_list"
