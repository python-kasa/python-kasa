# How-to Guides

This section contains guides of how to perform common functions with the api

## Discover devices

```{eval-rst}
.. automodule:: kasa.discover
```

## Connect without discovery

```{eval-rst}
.. automodule:: kasa.deviceconfig
```

## Get Energy Consumption and Usage Statistics

```{note}
    In order to use the helper methods to calculate the statistics correctly, your devices need to have correct time set.
    The devices use NTP and public servers from `NTP Pool Project <https://www.ntppool.org/>`_ to synchronize their time.
```

### Energy Consumption

The availability of energy consumption sensors depend on the device.
While most of the bulbs support it, only specific switches (e.g., HS110) or strips (e.g., HS300) support it.
You can use {attr}`~SmartDevice.has_emeter` to check for the availability.


### Usage statistics

You can use {attr}`~SmartDevice.on_since` to query for the time the device has been turned on.
Some devices also support reporting the usage statistics on daily or monthly basis.
You can access this information using through the usage module ({class}`kasa.modules.Usage`):

```py
dev = SmartPlug("127.0.0.1")
usage = dev.modules["usage"]
print(f"Minutes on this month: {usage.usage_this_month}")
print(f"Minutes on today: {usage.usage_today}")
```
