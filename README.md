# python-kasa

[![PyPI version](https://badge.fury.io/py/python-kasa.svg)](https://badge.fury.io/py/python-kasa)
[![Build Status](https://dev.azure.com/python-kasa/python-kasa/_apis/build/status/python-kasa.python-kasa?branchName=master)](https://dev.azure.com/python-kasa/python-kasa/_build/latest?definitionId=2&branchName=master)
[![Coverage Status](https://coveralls.io/repos/github/python-kasa/python-kasa/badge.svg?branch=master)](https://coveralls.io/github/python-kasa/python-kasa?branch=master)

python-kasa is a Python library to control TPLink smart home devices (plugs, wall switches, power strips, and bulbs) using asyncio.
This project is a maintainer-made fork of [pyHS100](https://github.com/GadgetReactor/pyHS100) project.


**Supported devices**

* Plugs
  * HS100
  * HS103
  * HS105
  * HS107
  * HS110
* Power Strips
  * HS300
  * KP303
* Wall switches
  * HS200
  * HS210
  * HS220
* Bulbs
  * LB100
  * LB110
  * LB120
  * LB130
  * LB230
  * KL60
  * KL110
  * KL120
  * KL130

**Contributions (be it adding missing features, fixing bugs or improving documentation) are more than welcome, feel free to submit pull requests! See below for instructions for setting up a development environment.**


# Usage

The package is shipped with a console tool named kasa, please refer to ```kasa --help``` for detailed usage.
The device to which the commands are sent is chosen by `KASA_HOST` environment variable or passing `--host <address>` as an option.
To see what is being sent to and received from the device, specify option `--debug`.

To avoid discovering the devices when executing commands its type can be passed by specifying either `--plug` or `--bulb`,
if no type is given its type will be discovered automatically with a small delay.
Some commands (such as reading energy meter values and setting color of bulbs) additional parameters are required,
which you can find by adding `--help` after the command, e.g. `kasa emeter --help` or `kasa hsv --help`.

If no command is given, the `state` command will be executed to query the device state.

## Initial Setup

You can provision your device without any extra apps by using the `kasa wifi` command:
1. If the device is unprovisioned, connect to its open network
2. Use `kasa discover` (or check the routes) to locate the IP address of the device (likely 192.168.0.1)
3. Scan for available networks using `kasa wifi scan`
4. Join/change the network using `kasa wifi join` command, see `--help` for details.
## Discovering devices

The devices can be discovered either by using `kasa discover` or by calling `kasa` without any parameters.
In both cases supported devices are discovered from the same broadcast domain, and their current state will be queried and printed out.

```
$ kasa
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
 * `sysinfo` to return raw system information

## Energy meter

Passing no options to `emeter` command will return the current consumption.
Possible options include `--year` and `--month` for retrieving historical state,
and reseting the counters is done with `--erase`.

```
$ kasa emeter
== Emeter ==
Current state: {'total': 133.105, 'power': 108.223577, 'current': 0.54463, 'voltage': 225.296283}
```

## Bulb-specific commands

At the moment setting brightness, color temperature and color (in HSV) are supported depending on the device.
The commands are straightforward, so feel free to check `--help` for instructions how to use them.

# Library usage

The property accesses use the data obtained before by awaiting `update()`.
The values are cached until the next update call.
Each method changing the state of the device will automatically update the cached state.

Errors are raised as `SmartDeviceException` instances for the user to handle.

## Discovering devices

`Discover.discover()` can be used to discover supported devices in the local network.
The return value is a dictionary keyed with the IP address and the value holds a ready-to-use instance of the detected device type.

Example:
```python
import asyncio
from kasa import Discover

devices = asyncio.run(Discover.discover())
for addr, dev in devices.items():
    asyncio.run(dev.update())
    print(f"{addr} >> {dev}")
```
```
$ python example.py
<SmartPlug at 192.168.XXX.XXX (My Smart Plug), is_on: True - dev specific: {'LED state': True, 'On since': datetime.datetime(2017, 3, 26, 18, 29, 17, 52073)}>
```

## Querying basic information

```python
import asyncio
from kasa import SmartPlug
from pprint import pformat as pf

plug = SmartPlug("192.168.XXX.XXX")
asyncio.run(plug.update())
print("Hardware: %s" % pf(plug.hw_info))
print("Full sysinfo: %s" % pf(plug.sys_info))
```

The rest of the examples assume that you have initialized an instance.

## State & switching

Devices can be turned on and off by either calling appropriate methods on the device object.

```python
print("Current state: %s" % plug.is_on)
await plug.turn_off()
await plug.turn_on()
```

## Getting emeter status (if applicable)
```python
print("Current consumption: %s" % await plug.get_emeter_realtime())
print("Per day: %s" % await plug.get_emeter_daily(year=2016, month=12))
print("Per month: %s" % await plug.get_emeter_monthly(year=2016))
```

## Bulb and dimmer-specific APIs

The bulb API is likewise straightforward, so please refer to its API documentation.
Information about supported features can be queried by using properties prefixed with `is_`, e.g. `is_dimmable`.

### Setting the brightness

```python
import asyncio
from kasa import SmartBulb

bulb = SmartBulb("192.168.1.123")
asyncio.run(bulb.update())

if bulb.is_dimmable:
    asyncio.run(bulb.set_brightness(100))
    print(bulb.brightness)
```

### Setting the color temperature
```python
if bulb.is_variable_color_temp:
    await bulb.set_color_temp(3000)
    print(bulb.color_temp)
```

### Setting the color

Hue is given in degrees (0-360) and saturation and value in percentage.

```python
if bulb.is_color:
    await bulb.set_hsv(180, 100, 100) # set to cyan
    print(bulb.hsv)
```

## Contributing

Contributions are very welcome! To simplify the process, we are leveraging automated checks and tests for contributions.

### Resources

* [softScheck's github contains lot of information and wireshark dissector](https://github.com/softScheck/tplink-smartplug#wireshark-dissector)
* [https://github.com/plasticrake/tplink-smarthome-simulator](tplink-smarthome-simulator)

### Setting up development environment

```bash
poetry install
pre-commit install
```

### Code-style checks

We use several tools to automatically check all contributions, which are run automatically when you commit your code.

If you want to manually execute the checks, you can run `tox -e lint` to do the linting checks or `tox` to also execute the tests.
