# Tools for developers

This directory contains some simple scripts that can be useful for developers.

## dump_devinfo
* Queries the device (if --host is given) or discover devices and creates fixture files that can be added to the test suite.

```shell
Usage: python -m devtools.dump_devinfo [OPTIONS]

  Generate devinfo files for devices.

  Use --host (for a single device) or --target (for a complete network).

Options:
  --host TEXT      Target host.
  --target TEXT    Target network for discovery.
  --username TEXT  Username/email address to authenticate to device.
  --password TEXT  Password to use to authenticate to device.
  --basedir TEXT   Base directory for the git repository
  --autosave       Save without prompting
  -d, --debug
  --help           Show this message and exit.
```

## create_module_fixtures

* Queries the device for all supported modules and outputs module-based fixture files for each device.
* This could be used to create fixture files for module-specific tests, but it might also be useful for other use-cases.

```shell
Usage: create_module_fixtures.py [OPTIONS] OUTPUTDIR

  Create module fixtures for given host/network.

Arguments:
  OUTPUTDIR  [required]

Options:
  --host TEXT
  --network TEXT
  --install-completion  Install completion for the current shell.
  --show-completion     Show completion for the current shell, to copy it or
                        customize the installation.
  --help                Show this message and exit.
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

## perftest

* Runs several rounds of update cycles for the given list of addresses, and prints out statistics about the performance

```shell
Usage: perf_test.py [OPTIONS] [ADDRS]...

Options:
  --rounds INTEGER
  --help            Show this message and exit.
```

```shell
$ python perf_test.py 192.168.xx.x 192.168.xx.y 192.168.xx.z 192.168.xx.f
Running 5 rounds on ('192.168.xx.x', '192.168.xx.y', '192.168.xx.z', '192.168.xx.f')
=== Testing using gather on all devices ===
              took
             count      mean       std      min       25%       50%       75%       max
type
concurrently   5.0  0.097161  0.045544  0.05260  0.055332  0.088811  0.143082  0.145981
sequential     5.0  0.150506  0.005798  0.14162  0.149065  0.150499  0.155579  0.155768
=== Testing per-device performance ===
                           took
                          count      mean       std       min       25%       50%       75%       max
id
<id>-HS110(EU)   5.0  0.044917  0.014984  0.035836  0.037728  0.037950  0.041610  0.071458
<id>-KL130(EU)   5.0  0.067626  0.032027  0.046451  0.046797  0.048406  0.076136  0.120342
<id>-HS110(EU)   5.0  0.055700  0.016174  0.042086  0.045578  0.048905  0.059869  0.082064
<id>-KP303(UK)   5.0  0.010298  0.003765  0.007773  0.007968  0.008546  0.010439  0.016763
```

## benchmark

* Benchmark the protocol

```shell
% python3 devtools/bench/benchmark.py
New parser, parsing 100000 messages took 0.6339647499989951 seconds
Old parser, parsing 100000 messages took 9.473990250000497 seconds
```
