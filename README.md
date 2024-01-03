<h2 align="center">python-kasa</h2>

[![PyPI version](https://badge.fury.io/py/python-kasa.svg)](https://badge.fury.io/py/python-kasa)
[![Build Status](https://github.com/python-kasa/python-kasa/actions/workflows/ci.yml/badge.svg)](https://github.com/python-kasa/python-kasa/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/python-kasa/python-kasa/branch/master/graph/badge.svg?token=5K7rtN5OmS)](https://codecov.io/gh/python-kasa/python-kasa)
[![Documentation Status](https://readthedocs.org/projects/python-kasa/badge/?version=latest)](https://python-kasa.readthedocs.io/en/latest/?badge=latest)

python-kasa is a Python library to control TPLink's smart home devices (plugs, wall switches, power strips, and bulbs).

This is a voluntary, community-driven effort and is not affiliated, sponsored, or endorsed by TPLink.

**Contributions in any form (adding missing features, reporting issues, fixing or triaging existing ones, improving the documentation, or device donations) are more than welcome!**

---

## Getting started

You can install the most recent release using pip:
```
pip install python-kasa
```

If you are using cpython, it is recommended to install with `[speedups]` to enable orjson (faster json support):
```
pip install python-kasa[speedups]
```

With `[speedups]`, the protocol overhead is roughly an order of magnitude lower (benchmarks available in devtools).

Alternatively, you can clone this repository and use poetry to install the development version:
```
git clone https://github.com/python-kasa/python-kasa.git
cd python-kasa/
poetry install
```

If you have not yet provisioned your device, [you can do so using the cli tool](https://python-kasa.readthedocs.io/en/latest/cli.html#provisioning).

## Discovering devices

Running `kasa discover` will send discovery packets to the default broadcast address (`255.255.255.255`) to discover supported devices.
If your system has multiple network interfaces, you can specify the broadcast address using the `--target` option.

The `discover` command will automatically execute the `state` command on all the discovered devices:

```
$ kasa discover
Discovering devices on 255.255.255.255 for 3 seconds

== Bulb McBulby - KL130(EU) ==
        Host: 192.168.xx.xx
        Port: 9999
        Device state: True
        == Generic information ==
        Time:         2023-12-05 14:33:23 (tz: {'index': 6, 'err_code': 0}
        Hardware:     1.0
        Software:     1.8.8 Build 190613 Rel.123436
        MAC (rssi):   1c:3b:f3:xx:xx:xx (-56)
        Location:     {'latitude': None, 'longitude': None}

        == Device specific information ==
        Brightness: 16
        Is dimmable: True
        Color temperature: 2500
        Valid temperature range: ColorTempRange(min=2500, max=9000)
        HSV: HSV(hue=0, saturation=0, value=16)
        Presets:
                index=0 brightness=50 hue=0 saturation=0 color_temp=2500 custom=None id=None mode=None
                index=1 brightness=100 hue=299 saturation=95 color_temp=0 custom=None id=None mode=None
                index=2 brightness=100 hue=120 saturation=75 color_temp=0 custom=None id=None mode=None
                index=3 brightness=100 hue=240 saturation=75 color_temp=0 custom=None id=None mode=None

        == Current State ==
        <EmeterStatus power=2.4 voltage=None current=None total=None>

        == Modules ==
        + <Module Schedule (smartlife.iot.common.schedule) for 192.168.xx.xx>
        + <Module Usage (smartlife.iot.common.schedule) for 192.168.xx.xx>
        + <Module Antitheft (smartlife.iot.common.anti_theft) for 192.168.xx.xx>
        + <Module Time (smartlife.iot.common.timesetting) for 192.168.xx.xx>
        + <Module Emeter (smartlife.iot.common.emeter) for 192.168.xx.xx>
        - <Module Countdown (countdown) for 192.168.xx.xx>
        + <Module Cloud (smartlife.iot.common.cloud) for 192.168.xx.xx>
```

If your device requires authentication to control it,
you need to pass the credentials using `--username` and `--password` options.

## Basic functionalities

All devices support a variety of common commands, including:

* `state` which returns state information
* `on` and `off` for turning the device on or off
* `emeter` (where applicable) to return energy consumption information
* `sysinfo` to return raw system information

The syntax to control device is `kasa --host <ip address> <command>`.
Use `kasa --help` ([or consult the documentation](https://python-kasa.readthedocs.io/en/latest/cli.html#kasa-help)) to get a list of all available commands and options.
Some examples of available options include JSON output (`--json`), defining timeouts (`--timeout` and `--discovery-timeout`).

Each individual command may also have additional options, which are shown when called with the `--help` option.
For example, `--transition` on bulbs requests a smooth state change, while `--name` and `--index` are used on power strips to select the socket to act on:

```
$ kasa on --help

Usage: kasa on [OPTIONS]

  Turn the device on.

Options:
  --index INTEGER
  --name TEXT
  --transition INTEGER
  --help                Show this message and exit.
```


### Bulbs

Common commands for bulbs and light strips include:

* `brightness` to control the brightness
* `hsv` to control the colors
* `temperature` to control the color temperatures

When executed without parameters, these commands will report the current state.

Some devices support `--transition` option to perform a smooth state change.
For example, the following turns the light to 30% brightness over a period of five seconds:
```
$ kasa --host <addr> brightness --transition 5000 30
```

See `--help` for additional options and [the documentation](https://python-kasa.readthedocs.io/en/latest/smartbulb.html) for more details about supported features and limitations.

### Power strips

Each individual socket can be controlled separately by passing `--index` or `--name` to the command.
If neither option is defined, the commands act on the whole power strip.

For example:
```
$ kasa --host <addr> off  # turns off all sockets
$ kasa --host <addr> off --name 'Socket1'  # turns off socket named 'Socket1'
```

See `--help` for additional options and [the documentation](https://python-kasa.readthedocs.io/en/latest/smartstrip.html) for more details about supported features and limitations.


## Energy meter

Running `kasa emeter` command will return the current consumption.
Possible options include `--year` and `--month` for retrieving historical state,
and reseting the counters can be done with `--erase`.

```
$ kasa emeter
== Emeter ==
Current state: {'total': 133.105, 'power': 108.223577, 'current': 0.54463, 'voltage': 225.296283}
```

# Library usage

If you want to use this library in your own project, a good starting point is to check [the documentation on discovering devices](https://python-kasa.readthedocs.io/en/latest/discover.html).
You can find several code examples in the API documentation of each of the implementation base classes, check out the [documentation for the base class shared by all supported devices](https://python-kasa.readthedocs.io/en/latest/smartdevice.html).

[The library design and module structure is described in a separate page](https://python-kasa.readthedocs.io/en/latest/design.html).

The device type specific documentation can be found in their separate pages:
* [Plugs](https://python-kasa.readthedocs.io/en/latest/smartplug.html)
* [Bulbs](https://python-kasa.readthedocs.io/en/latest/smartbulb.html)
* [Dimmers](https://python-kasa.readthedocs.io/en/latest/smartdimmer.html)
* [Power strips](https://python-kasa.readthedocs.io/en/latest/smartstrip.html)
* [Light strips](https://python-kasa.readthedocs.io/en/latest/smartlightstrip.html)

## Contributing

Contributions are very welcome! To simplify the process, we are leveraging automated checks and tests for contributions.

### Setting up development environment

To get started, simply clone this repository and initialize the development environment.
We are using [poetry](https://python-poetry.org) for dependency management, so after cloning the repository simply execute
`poetry install` which will install all necessary packages and create a virtual environment for you.

### Code-style checks

We use several tools to automatically check all contributions. The simplest way to verify that everything is formatted properly
before creating a pull request, consider activating the pre-commit hooks by executing `pre-commit install`.
This will make sure that the checks are passing when you do a commit.

You can also execute the checks by running either `tox -e lint` to only do the linting checks, or `tox` to also execute the tests.

### Running tests

You can run tests on the library by executing `pytest` in the source directory.
This will run the tests against contributed example responses, but you can also execute the tests against a real device:
```
$ pytest --ip <address>
```
Note that this will perform state changes on the device.

### Analyzing network captures

The simplest way to add support for a new device or to improve existing ones is to capture traffic between the mobile app and the device.
After capturing the traffic, you can either use the [softScheck's  wireshark dissector](https://github.com/softScheck/tplink-smartplug#wireshark-dissector)
or the `parse_pcap.py` script contained inside the `devtools` directory.
Note, that this works currently only on kasa-branded devices which use port 9999 for communications.


## Supported devices

In principle, most kasa-branded devices that are locally controllable using the official Kasa mobile app work with this library.

The following lists the devices that have been manually verified to work.
**If your device is unlisted but working, please open a pull request to update the list and add a fixture file (use `devtools/dump_devinfo.py` to generate one).**

### Plugs

* HS100
* HS103
* HS105
* HS107
* HS110
* KP100
* KP105
* KP115
* KP125
* KP125M [See note below](#tapo-and-newer-kasa-branded-devices)
* KP401
* EP10
* EP25 [See note below](#tapo-and-newer-kasa-branded-devices)

### Power Strips

* EP40
* HS300
* KP303
* KP200 (in wall)
* KP400
* KP405 (dimmer)

### Wall switches

* ES20M
* HS200
* HS210
* HS220
* KS200M (partial support, no motion, no daylight detection)
* KS220M (partial support, no motion, no daylight detection)
* KS230

### Bulbs

* LB100
* LB110
* LB120
* LB130
* LB230
* KL50
* KL60
* KL110
* KL120
* KL125
* KL130
* KL135

### Light strips

* KL400L5
* KL420L5
* KL430

### Tapo and newer Kasa branded devices

The library has recently added a limited supported for devices that carry Tapo branding.

At the moment, the following devices have been confirmed to work:

* Tapo P110 (plug)
* Tapo L530E (bulb)
* Kasa KS205 (Wifi/Matter Wall Switch)
* Kasa KS225 (Wifi/Matter Wall Dimmer Switch)

Some newer hardware versions of Kasa branded devices are now using the same protocol as
Tapo branded devices.  Support for these devices is currently limited as per TAPO branded
devices:

* Kasa EP25 (plug) hw_version 2.6
* Kasa KP125M (plug)

**If your device is unlisted but working, please open a pull request to update the list and add a fixture file (use `devtools/dump_devinfo.py` to generate one).**

## Resources

### Developer Resources

* [softScheck's github contains lot of information and wireshark dissector](https://github.com/softScheck/tplink-smartplug#wireshark-dissector)
* [TP-Link Smart Home Device Simulator](https://github.com/plasticrake/tplink-smarthome-simulator)
* [Unofficial API documentation](https://github.com/plasticrake/tplink-smarthome-api)
* [Another unofficial API documentation](https://github.com/whitslack/kasa)
* [pyHS100](https://github.com/GadgetReactor/pyHS100) provides synchronous interface and is the unmaintained predecessor of this library.


### Library Users

* [Home Assistant](https://www.home-assistant.io/integrations/tplink/)
* [MQTT access to TP-Link devices, using python-kasa](https://github.com/flavio-fernandes/mqtt2kasa)

### TP-Link Tapo support

This library has recently added a limited supported for devices that carry Tapo branding.
That support is currently limited to the cli.  The package `kasa.tapo` is in flux and if you
use it directly you should expect it could break in future releases until this statement is removed.

Other TAPO libraries are:

* [PyTapo - Python library for communication with Tapo Cameras](https://github.com/JurajNyiri/pytapo)
* [Tapo P100 (Tapo P105/P100 plugs, Tapo L510E bulbs)](https://github.com/fishbigger/TapoP100)
  * [Home Assistant integration](https://github.com/fishbigger/HomeAssistant-Tapo-P100-Control)
* [plugp100, another tapo library](https://github.com/petretiandrea/plugp100)
  * [Home Assistant integration](https://github.com/petretiandrea/home-assistant-tapo-p100)
