# ruff: noqa
"""
>>> from kasa import Discover

:func:`~kasa.Discover.discover` returns a dict[str,Device] of devices on your network:

>>> devices = await Discover.discover(username="user@example.com", password="great_password")
>>> for dev in devices.values():
>>>     await dev.update()
>>>     print(dev.host)
127.0.0.1
127.0.0.2
127.0.0.3
127.0.0.4
127.0.0.5

:meth:`~kasa.Discover.discover_single` returns a single device by hostname:

>>> dev = await Discover.discover_single("127.0.0.3", username="user@example.com", password="great_password")
>>> await dev.update()
>>> dev.alias
Living Room Bulb
>>> dev.model
L530
>>> dev.rssi
-52
>>> dev.mac
5C:E9:31:00:00:00

You can update devices by calling different methods (e.g., ``set_``-prefixed ones).
Note, that these do not update the internal state, but you need to call :meth:`~kasa.Device.update()` to query the device again.
back to the device.

>>> await dev.set_alias("Dining Room")
>>> await dev.update()
>>> dev.alias
Dining Room

Different groups of functionality are supported by modules which you can access via :attr:`~kasa.Device.modules` with a typed
key from :class:`~kasa.Module`.

Modules will only be available on the device if they are supported but some individual features of a module may not be available for your device.
You can check the availability using ``is_``-prefixed properties like `is_color`.

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

You can test if a module is supported by using `get` to access it.

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

Individual pieces of functionality are also exposed via features which you can access via :attr:`~kasa.Device.features` and will only be present if they are supported.

Features are similar to modules in that they provide functionality that may or may not be present.

Whereas modules group functionality into a common interface, features expose a single function that may or may not be part of a module.

The advantage of features is that they have a simple common interface of `id`, `name`, `value` and `set_value` so no need to learn the module API.

They are useful if you want write code that dynamically adapts as new features are added to the API.

>>> if auto_update := dev.features.get("auto_update_enabled"):
>>>     print(auto_update.value)
False
>>> if auto_update:
>>>     await auto_update.set_value(True)
>>>     await dev.update()
>>>     print(auto_update.value)
True
>>> for feat in dev.features.values():
>>>     print(f"{feat.name}: {feat.value}")
Device ID: 0000000000000000000000000000000000000000\nState: True\nSignal Level: 2\nRSSI: -52\nSSID: #MASKED_SSID#\nOverheated: False\nReboot: <Action>\nBrightness: 50\nCloud connection: True\nHSV: HSV(hue=0, saturation=100, value=50)\nColor temperature: 2700\nAuto update enabled: True\nUpdate available: None\nCurrent firmware version: 1.1.6 Build 240130 Rel.173828\nAvailable firmware version: None\nCheck latest firmware: <Action>\nLight effect: Party\nLight preset: Light preset 1\nSmooth transition on: 2\nSmooth transition off: 2\nDevice time: 2024-02-23 02:40:15+01:00
"""
