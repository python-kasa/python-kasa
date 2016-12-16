# pyHS100
Python Library to control TPLink Switch (HS100 / HS110)

# Usage

For all available API functions run ```help(SmartPlug)```

```python
from pyHS100 import SmartPlug
from pprint import pformat as pf

plug = SmartPlug("192.168.250.186")
print("Alias, type and supported features: %s" % (plug.identify(),))
print("Hardware: %s" % pf(plug.hw_info))
print("Full sysinfo: %s" % pf(plug.get_sysinfo())) # this prints lots of information about the device
```

## Time information
```python
print("Current time: %s" % plug.time)
print("Timezone: %s" % plug.timezone)
```

## Getting and setting the name
```python
print("Alias: %s" % plug.alias)
plug.alias = "My New Smartplug"
```

## State & switching
```python
print("Current state: %s" % plug.state)
plug.turn_off()
plug.turn_on()
```
or
```python
plug.state = "ON"
plug.state = "OFF"
```

## Getting emeter status (on HS110)
```python
print("Current consumption: %s" % plug.get_emeter_realtime())
print("Per day: %s" % plug.get_emeter_daily(year=2016, month=12))
print("Per month: %s" % plug.get_emeter_monthly(year=2016))
```

## Switching the led
```python
print("Current LED state: %s" % plug.led)
plug.led = False # turn off led
print("New LED state: %s" % plug.led)

```

# Example
There is also a simple tool for testing connectivity in examples, to use:
```python
python -m examples.cli <ip>
```
