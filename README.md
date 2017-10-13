# pyHS100

[![PyPI version](https://badge.fury.io/py/pyHS100.svg)](https://badge.fury.io/py/pyHS100)
[![Build Status](https://travis-ci.org/GadgetReactor/pyHS100.svg?branch=master)](https://travis-ci.org/GadgetReactor/pyHS100)
[![Coverage Status](https://coveralls.io/repos/github/GadgetReactor/pyHS100/badge.svg?branch=master)](https://coveralls.io/github/GadgetReactor/pyHS100?branch=master)

Python Library to control TPLink smart plugs/switches and smart bulbs.

**Supported devices**

* Plugs
  * HS100
  * HS105
  * HS110
* Wall switches
  * HS200
* Bulbs
  * LB100
  * LB110
  * LB120
  * LB130

# Usage

The package is shipped with a console tool named pyhs100, please refer to ```pyhs100 --help``` for detailed usage.
The device to which the commands are sent is chosen by `PYHS100_IP` environment variable or passing `--ip <address>` as an option.
To see what is being sent to and received from the device, specify option `--debug`.

To avoid discovering the devices when executing commands its type can be passed by specifying either `--plug` or `--bulb`,
if no type is given its type will be discovered automatically with a small delay.
Some commands (such as reading energy meter values and setting color of bulbs) additional parameters are required,
which you can find by adding `--help` after the command, e.g. `pyhs100 emeter --help` or `pyhs100 hsv --help`.

If no command is given, the `state` command will be executed to query the device state.


## Discovering devices

The devices can be discovered either by using `pyhs100 discover` or by calling `pyhs100` without any parameters.
In both cases supported devices are discovered from the same broadcast domain, and their current state will be queried and printed out.

```
$ pyhs100
No --bulb nor --plug given, discovering..
Discovering devices for 3 seconds
== My Smart Plug - HS110(EU) ==
Device state: ON
IP address: 192.168.x.x
LED state: False
On since: 2017-03-26 18:29:17.242219
== Generic information ==
Time:         1970-06-22 02:39:41
Hardware:     1.0
Software:     1.0.8 Build 151101 Rel.24452
MAC (rssi):   50:C7:BF:XX:XX:XX (-77)
Location:     {'latitude': XXXX, 'longitude': XXXX}
== Emeter ==
Current state: {'total': 133.082, 'power': 100.418681, 'current': 0.510967, 'voltage': 225.600477}
```

## Basic controls

All devices support a variety of common commands, including:
 * `state` which returns state information
 * `on` and `off` for turning the device on or off
 * `emeter` (where applicable) to return energy consumption information
 * `sysinfo` to return raw system information which is used by e.g. `state`, useful for debugging and when adding support for new device types

## Energy meter

Passing no options to `emeter` command will return the current consumption.
Possible options include `--year` and `--month` for retrieving historical state,
and reseting the counters is done with `--erase`.

```
$ pyhs100 emeter
== Emeter ==
Current state: {'total': 133.105, 'power': 108.223577, 'current': 0.54463, 'voltage': 225.296283}
```

## Plug-specific commands

At the moment only switching the state of the LED is implemented.
**Feel free to submit patches as pull requests for further features!**
### Controlling the LED

`led` command can be used to control whether the LED light on front of the plug is on or off.

```
$ pyhs100 --plug led
LED state: False
$ pyhs100 --plug led 1
Turning led to True
```

## Bulb-specific commands

At the moment setting brightness, color temperature and color (in HSV) is supported.
The commands are straightforward, so feel free to check `--help` for instructions how to use them.

**Feel free to submit patches as pull requests to add more functionality (e.g. scenes)!**

# Library usage

The public API is well documented, but here are some examples to get you started.
For all available API functions run ```help(SmartPlug)``` or ```help(SmartBulb)```.

## Discovering devices

`Discover` class' `discover()` can be used to discover supported devices,
which returns a dictionary keyed with the IP address whose value hold a ready-to-use instance of the detected device type.

Example:
```python
from pyHS100 import Discover

for dev in Discover.discover().values():
    print(dev)
```
```
$ python3 example.py
<SmartPlug at 192.168.XXX.XXX (My Smart Plug), is_on: True - dev specific: {'LED state': True, 'On since': datetime.datetime(2017, 3, 26, 18, 29, 17, 52073)}>
```

## Querying basic information

*Please note that most property getters do I/O (e.g. fetching the system information) on each call.
If you want to avoid unnecessary communication with the device please use `get_sysinfo` and handle parsing of information by yourself.*

```python
from pyHS100 import SmartPlug, SmartBulb
from pprint import pformat as pf

plug = SmartPlug("192.168.XXX.XXX")
print("Hardware: %s" % pf(plug.hw_info))
print("Full sysinfo: %s" % pf(plug.get_sysinfo())) # this prints lots of information about the device
```

## State & switching

Devices can be turned on and off by either calling appropriate methods on the device object,
or by assigning a new state to `state` property.

```python
print("Current state: %s" % plug.state)
plug.turn_off()
plug.turn_on()
```

```python
plug.state = "ON"
plug.state = "OFF"
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

## Getting emeter status (if applicable)
```python
print("Current consumption: %s" % plug.get_emeter_realtime())
print("Per day: %s" % plug.get_emeter_daily(year=2016, month=12))
print("Per month: %s" % plug.get_emeter_monthly(year=2016))
```

## Plug-specific

### Switching the led (plugs only)
```python
print("Current LED state: %s" % plug.led)
plug.led = False # turn off led
print("New LED state: %s" % plug.led)
```

## Bulb-specific API

The bulb API is likewise straightforward, so please refer to its API documentation.
Information about supported features can be queried by using properties prefixed with `is_`, e.g. `is_dimmable`.

### Setting the brightness

The `brightness` property works in percentages.

```python
print(bulb.brightness)
if bulb.is_dimmable:
    bulb.brightness = 100
```

### Setting the color temperature
```python
print(bulb.color_temp)
if bulb.is_variable_color_temp:
    bulb.color_temp = 3000
```

### Setting the color

Hue is given in degrees (0-360) and saturation and value in percentage.

```python
print(bulb.hsv)
if bulb.is_color:
   bulb.hsv = (180, 100, 100) # set to cyan
```

## Development Setup

### Docker

The following assumes you have a working installation of Docker.

Set up the environment and run the tests on demand.

```shell
docker build . -t pyhs100 && docker run -v $(PWD)/pyHS100/tests:/opt/pyHS100/pyHS100/tests  pyhs100 pytest
```