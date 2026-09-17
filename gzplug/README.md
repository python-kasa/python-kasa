# gzplug — setup and usage

Bench plug controller for the test team. See `DESIGN.md` for how it is built
and why.

## One-time setup

You need Python 3.11 or newer (this repo will not install on 3.10).

```bash
cd /path/to/gz-python-kasa

python3 --version          # must be 3.11+
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

gzplug --help
```

`-e` means "editable": the command runs the code in this folder, so edits take
effect without reinstalling. `.venv/` is gitignored.

Every later session just needs the activate line:

```bash
cd /path/to/gz-python-kasa
source .venv/bin/activate
```

You can skip activating by calling the command directly:
`.venv/bin/gzplug --help`.

### If you prefer uv

`uv` is a faster drop-in replacement for `venv` + `pip` (same authors as
`ruff`, which this repo already lints with). This repo ships a `uv.lock`, so if
you have uv installed, `uv sync` replaces the three setup lines above and
`uv run gzplug ...` replaces activating. It is optional -- the venv path above
does the same job.

## The web interface

```bash
pip install -r gzplug/requirements.txt   # once
gzplug ui
```

Serves on <http://127.0.0.1:8765/> and opens a browser. Devices and their live
state sit at the top with manual On/Off per plug, run parameters in the middle,
and a scrolling event log at the bottom. The page reconnects on its own if the
server restarts, and several browser tabs stay in sync.

`gzplug ui --no-browser` skips opening a browser; `--port` moves it.

**It binds to loopback only, on purpose.** There is no authentication and
`config.json` holds a shared account password in plaintext, so it must not be
exposed to the lab network.

## Everyday use

```bash
# Store the shared test-team account, once per machine.
gzplug creds --username 'lab@example.com' --password '...'

# Find plugs on the network and remember them as bench profiles.
gzplug discover --save
gzplug devices

# If discovery cannot reach a plug, add it by IP instead.
gzplug add --host 192.168.10.18 --label "Bench 2 - plug B"

# Run a cycle test.
gzplug run --device bench-2-plug-a --cycles 3 --on-time 5 --off-time 5 \
           --label "first bench check"
```

Each run writes `runs/run_<date>_<time>_<label>.csv` next to where you ran it.

### Useful flags on `run`

| Flag | Effect |
|---|---|
| `--device` | Repeat it to drive up to four plugs together. |
| `--continue-on-error` | Retry and press on through faults. Off by default, so an anomaly stops the run rather than producing a clean-looking log of a test that did not happen. |
| `--no-restore` | Leave the plugs as the run left them. By default each plug is returned to the state it was found in, including on Ctrl-C. |
| `-v` | Debug logging. |

## What each tile shows

Live per plug: state, power, voltage, current, energy today and this month,
and how long the relay has been on. The meta line carries address, model,
firmware and signal strength.

Warnings appear when they apply. Three show inline because they will ruin a
run: **overheated**, **overloaded**, and **auto-off is on** (a plug set to
switch itself off will end a long run by itself). The rest — auto-update
enabled, a power-protection threshold, a weak signal, a pending firmware
update — collapse behind a "N notes" line.

If a plug is found at a different address than the one saved, the tile says
so. Bench positions are keyed on the plug's device ID, so a DHCP lease change
is recovered from automatically rather than breaking the profile.

## Where files go

Config and run logs are written to the current directory, or to `$GZPLUG_HOME`
if that is set. In the packaged Windows build they land beside the executable.

`config.json` holds the shared account password in plaintext, by deliberate
choice for a shared lab account. It is gitignored. Do not reuse that password
anywhere that matters.

## Troubleshooting

**Discovery finds nothing on Windows.** The first broadcast triggers a firewall
prompt. If it was dismissed, discovery silently finds nothing thereafter --
allow the app in Windows Defender Firewall and try again.

**Discovery finds some plugs but not others.** Discovery is a UDP broadcast on
the local network (ports 9999 and 20002); it never contacts the TP-Link cloud.
Pairing a plug to the account controls whether you can authenticate to it, not
whether you can see it. If one plug is found and another is not, the broadcast
itself is working, so check the missing plug specifically:

* **Is it actually on the WiFi?** A plug in pairing mode broadcasts its own
  setup SSID and is not on your network at all, so it cannot be discovered. It
  must be fully joined. The KP125M is 2.4GHz only -- pairing it while your
  phone was on a 5GHz or guest SSID can land it somewhere unexpected.
* **Is it on the same subnet?** A broadcast does not cross subnets. Find its IP
  in the Kasa app (Device Settings -> Device Info) or the router's DHCP table,
  and compare it to the plug that was found. For a different subnet, use
  `gzplug discover --target 192.168.20.255`.
* **Is your Mac multi-homed?** On both Ethernet and WiFi, the broadcast may go
  out the wrong interface. Turning off the one the plugs are not on is the
  quickest test.
* **Client isolation.** Many corporate and guest access points block
  device-to-device traffic outright. `gzplug add --host <ip>` still works, as
  it is a unicast probe rather than a broadcast.

**"Unsupported device ... encrypt_scheme ... encrypt_type='TPAP'".** The plug is
reachable; this build just cannot speak its encryption. TP-Link firmware from
KP125M 1.3.0 onward (and Tapo P110 1.4.0+, L535 1.4.2+) switched from KLAP to
TPAP, which python-kasa does not support yet -- upstream issue #1590, with an
unmerged implementation in PR #1592.

Fix it without code: in the **Tapo** app (not Kasa), go to
**Profile -> Third Party Services -> Third-Party Compatibility** and turn it
on. That reverts the plug to KLAP. Your phone must be on the same network as
the plug for the setting to reach it.

See "Firmware risk" in `DESIGN.md` -- this affects every bench plug eventually,
not just a new one.

**Discovery cannot reach a plug at all.** Use `gzplug add --host <ip>`. It
probes that one address directly, which crosses subnets and survives client
isolation, then saves the profile exactly as `discover --save` would.

**`pip install -e .` fails.** Almost always Python 3.10 or older. Check
`python3 --version`.

## The Windows build

The test team does not need Python. Tagged builds produce a zip on the
repository's Releases page:

1. Download `gzplug-<version>-windows-x64.zip`.
2. Extract it anywhere the operator can write — a bench folder or the desktop.
3. Run `gzplug.exe`. It opens the interface in the default browser.

`config.json` and `runs\` are written **next to the executable**, so keeping
each bench's copy in its own folder keeps its plugs and run records separate.

The same executable carries the command line: `gzplug.exe run --device ... `
behaves exactly like the `gzplug` command above. No arguments opens the UI.

### Cutting a release

```bash
git tag gzplug-v0.1.0
git push origin gzplug-v0.1.0
```

That runs `.github/workflows/build-gzplug.yml` on a Windows runner, which
builds the bundle, **smoke-tests the built executable**, zips it and attaches
it to the release. The smoke test starts the real `gzplug.exe` and checks the
page, static assets, `/api/state`, the CLI, and that a WebSocket connects and
delivers a snapshot frame. If any of that fails there is no release — a green
build has twice said nothing about whether the thing actually runs.

Builds are pinned to Python 3.12, deliberately not the 3.14 used for
development: PyInstaller's support for 3.14 is new, and the build interpreter
is a separate decision from the development one.

## Running the tests

```bash
pip install pytest pytest-asyncio pytest-xdist pytest-socket pytest-mock
pytest gzplug/tests
```

These use recorded device fixtures -- no hardware and no network.
