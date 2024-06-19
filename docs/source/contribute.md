# Contributing

You probably arrived to this page as you are interested in contributing to python-kasa in some form?
All types of contributions are very welcome, so thank you!
This page aims to help you to get started.

```{contents} Contents
   :local:
```

## Setting up the development environment

To get started, simply clone this repository and initialize the development environment.
We are using [uv](https://github.com/astral-sh/uv) for dependency management, so after cloning the repository simply execute
`uv sync` which will install all necessary packages and create a virtual environment for you in `.venv`.

```
$ git clone https://github.com/python-kasa/python-kasa.git
$ cd python-kasa
$ uv sync --all-extras
```

## Code-style checks

We use several tools to automatically check all contributions as part of our CI pipeline.
The simplest way to verify that everything is formatted properly
before creating a pull request, consider activating the pre-commit hooks by executing `pre-commit install`.
This will make sure that the checks are passing when you do a commit.

```{note}
You can also execute the pre-commit hooks on all files by executing `pre-commit run -a`
```

## Running tests

You can run tests on the library by executing `pytest` in the source directory:

```
$ uv run pytest kasa
```

This will run the tests against the contributed example responses.

```{note}
You can also execute the tests against a real device using `pytest --ip <address>`.
Note that this will perform state changes on the device.
```

## Analyzing network captures

The simplest way to add support for a new device or to improve existing ones is to capture traffic between the mobile app and the device.
After capturing the traffic, you can either use the [softScheck's wireshark dissector](https://github.com/softScheck/tplink-smartplug#wireshark-dissector)
or the `parse_pcap.py` script contained inside the `devtools` directory.
Note, that this works currently only on kasa-branded devices which use port 9999 for communications.

## Contributing fixture files

One of the easiest ways to contribute is by creating a fixture file and uploading it for us.
These files will help us to improve the library and run tests against devices that we have no access to.

This library is tested against responses from real devices ("fixture files").
These files contain responses for selected, known device commands and are stored [in our test suite](https://github.com/python-kasa/python-kasa/tree/master/kasa/tests/fixtures).

You can generate these files by using the `dump_devinfo.py` script.
Note, that this script should be run inside the main source directory so that the generated files are stored in the correct directories.
The easiest way to do that is by doing:

```
$ git clone https://github.com/python-kasa/python-kasa.git
$ cd python-kasa
$ uv sync --all-extras
$ source .venv/bin/activate
$ python -m devtools.dump_devinfo --username <username> --password <password> --host 192.168.1.123
```

```{note}
You can also execute the script against a network by using `--target`: `python -m devtools.dump_devinfo --target network 192.168.1.255`
```

The script will run queries against the device, and prompt at the end if you want to save the results.
If you choose to do so, it will save the fixture files directly in their correct place to make it easy to create a pull request.

```{note}
When adding new fixture files, you should run `pre-commit run -a` to re-generate the list of supported devices.
You may need to adjust `device_fixtures.py` to add a new model into the correct device categories.  Verify that test pass by executing `uv run pytest kasa`.
```
