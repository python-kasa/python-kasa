# Tools for developers

This directory contains some simple scripts that can be useful for developers.

## dump_devinfo
* Queries the device and returns a fixture that can be added to the test suite

```shell
Usage: dump_devinfo.py [OPTIONS] HOST

  Generate devinfo file for given device.

Options:
  -d, --debug
  --help       Show this message and exit.
```

## parse_pcap

* Requires dpkt (pip install dpkt)
* Reads a pcap file and prints out the device communications

```shell
Usage: parse_pcap.py [OPTIONS] FILE

  Parse pcap file and pretty print the communications and some statistics.

Options:
  --help  Show this message and exit.
```

## perf_test

* Runs several rounds of update cycles for the given list of addresses, and prints out statistics about the performance

```shell
Usage: perf_test.py [OPTIONS] [ADDRS]...

Options:
  --rounds INTEGER
  --help            Show this message and exit.
```

```shell

```
