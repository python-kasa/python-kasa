# python-kasa

[![PyPI version](https://badge.fury.io/py/python-kasa.svg)](https://badge.fury.io/py/python-kasa)
[![Build Status](https://dev.azure.com/python-kasa/python-kasa/_apis/build/status/python-kasa.python-kasa?branchName=master)](https://dev.azure.com/python-kasa/python-kasa/_build/latest?definitionId=2&branchName=master)
[![Coverage Status](https://coveralls.io/repos/github/python-kasa/python-kasa/badge.svg?branch=master)](https://coveralls.io/github/python-kasa/python-kasa?branch=master)
[![Documentation Status](https://readthedocs.org/projects/python-kasa/badge/?version=latest)](https://python-kasa.readthedocs.io/en/latest/?badge=latest)

python-kasa is a Python library to control TPLink smart home devices (plugs, wall switches, power strips, and bulbs) using asyncio.
This project is a maintainer-made fork of [pyHS100](https://github.com/GadgetReactor/pyHS100) project.

## Getting started

You can install the most recent release using pip. Until
```
pip install python-kasa --pre
```

Alternatively, you can clone this repository and use poetry to install the development version:
```
git clone https://github.com/python-kasa/python-kasa.git
cd python-kasa/
poetry install
```

## Discovering devices

After installation, the devices can be discovered either by using `kasa discover` or by calling `kasa` without any parameters.

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

Use `kasa --help` to get list of all available commands, or alternatively, [consult the documentation](https://python-kasa.readthedocs.io/en/latest/cli.html).

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

You can find several code examples in [the API documentation](https://python-kasa.readthedocs.io).

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

### Analyzing network captures

The simplest way to add support for a new device or to improve existing ones is to capture traffic between the mobile app and the device.
After capturing the traffic, you can either use the [softScheck's  wireshark dissector](https://github.com/softScheck/tplink-smartplug#wireshark-dissector)
or the `parse_pcap.py` script contained inside the `devtools` directory.


## Supported devices

### Plugs

* HS100
* HS103
* HS105
* HS107
* HS110

### Power Strips

* HS300
* KP303
* KP400

### Wall switches

* HS200
* HS210
* HS220

### Bulbs

* LB100
* LB110
* LB120
* LB130
* LB230
* KL60
* KL110
* KL120
* KL125
* KL130

### Light strips

* KL430

**Contributions (be it adding missing features, fixing bugs or improving documentation) are more than welcome, feel free to submit pull requests!**

## Resources

### Links

* [softScheck's github contains lot of information and wireshark dissector](https://github.com/softScheck/tplink-smartplug#wireshark-dissector)
* [TP-Link Smart Home Device Simulator](https://github.com/plasticrake/tplink-smarthome-simulator)
* [Unofficial API documentation](https://github.com/plasticrake/tplink-smarthome-api/blob/master/API.md)
* [MQTT access to TP-Link devices, using python-kasa](https://github.com/flavio-fernandes/mqtt2kasa)

### TP-Link Tapo support

* [Tapo P100 (Tapo P105/P100 plugs, Tapo L510E bulbs)](https://github.com/fishbigger/TapoP100)
  * [Home Assistant integration](https://github.com/fishbigger/HomeAssistant-Tapo-P100-Control)
