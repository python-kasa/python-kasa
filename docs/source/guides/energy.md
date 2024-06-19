
# Get Energy Consumption and Usage Statistics

:::{note}
In order to use the helper methods to calculate the statistics correctly, your devices need to have correct time set.
The devices use NTP (123/UDP) and public servers from [NTP Pool Project](https://www.ntppool.org/) to synchronize their time.
:::

## Energy Consumption

The availability of energy consumption sensors depend on the device.
While most of the bulbs support it, only specific switches (e.g., HS110) or strips (e.g., HS300) support it.
You can use {attr}`~Device.has_emeter` to check for the availability.


## Usage statistics

You can use {attr}`~Device.on_since` to query for the time the device has been turned on.
Some devices also support reporting the usage statistics on daily or monthly basis.
You can access this information using through the usage module ({class}`kasa.modules.Usage`):

```py
dev = SmartPlug("127.0.0.1")
usage = dev.modules["usage"]
print(f"Minutes on this month: {usage.usage_this_month}")
print(f"Minutes on today: {usage.usage_today}")
```
