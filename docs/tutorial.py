# ruff: noqa
"""
The kasa library is fully async and methods that perform IO need to be run inside an async couroutine.
These examples assume async code is called from within `async def` or are running in a asyncio REPL
(python -m asyncio)

The main entry point for the api is :func:`~kasa.Discover.discover` and
:func:`~kasa.Discover.discover_single` which return Device objects.
Most newer devices require your tplink cloud username and password but this can be ommitted for older devices.

>>> from kasa import Device, Discover

:func:`~kasa.Discover.discover` returns a list of devices on your network

>>> devices = await Discover.discover(username="user@mail.com", password="great_password")
>>> for dev in devices:
>>>     await dev.update()
>>>     print(dev.host)
127.0.0.1
127.0.0.2

:func:`~kasa.Discover.discover_single` returns a single device by hostname

>>> dev = await Discover.discover_single("127.0.0.1", username="user@mail.com", password="great_password")
>>> await dev.update()
>>> dev.alias
Living Room
>>> dev.model
L530
>>> dev.rssi
-52
>>> dev.mac
5C:E9:31:00:00:00
>>> await dev.set_alias("Dining Room")
>>> await dev.update()
>>> dev.alias
Dining Room

Different groups of functionality are supported by modules which you can access with Module.Name.
Modules will only be available on the device if they are supported but some individual features of
a module may not be available for your device.  You can check for this with `is_feature`, e.g. is_color.

>>> from kasa import Module
>>> Module.Light in dev.modules
True
>>> light = dev.modules[Module.Light]
>>> light.brightness
100
>>> await light.set_brightness(50)
>>> await dev.update()
>>> light.brightness
50
>>> light.is_color
True
>>> if light.is_color:
>>>     print(light.hsv)
HSV(hue=0, saturation=100, value=50)

You can test if a module is supported before trying to access it.

>>> if effect := dev.modules.get(Module.LightEffect):
>>>     print(effect.effect)
>>>     print(effect.effect_list)
>>> if effect := dev.modules.get(Module.LightEffect):
>>>     await effect.set_effect("Party")
>>>     await dev.update()
>>>     print(effect.effect)
Off
['Off', 'Party', 'Relax']
Party

Individual pieces of functionality are also exposed via features and will only be present if they are supported.

>>> if "overheated" in dev.features:
>>>     print(dev.features["overheated"].value)
False

"""
