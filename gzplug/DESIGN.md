# gzplug — Bench Plug Controller

Internal test-team application for driving TP-Link Kasa/Tapo smart plugs
(primarily the KP125M) through scripted on/off cycles, with live status and
per-run logging.

Status: **design, not yet implemented.** Decisions below are settled unless
marked OPEN.

---

## 1. Context

`scratch/kp125m_connect.py` and `scratch/kp125m_toggle.py` prove out auth and
control against a single KP125M at a hardcoded IP, with credentials in the
environment. They work, but they are not distributable: `scratch/` is untracked,
the IP is a constant, and there is no record of what a run did.

This turns that into a tool the test team can install and run on a bench PC.

### Constraints discovered during review

1. **The device stores almost no energy history.** The KP125M fixture
   (`tests/fixtures/smart/KP125M(US)_1.0_1.2.3.json`) exposes `get_energy_usage`
   (today/month totals + runtime), `get_emeter_data` (V / mA / mW) and
   `get_current_power`. There are no per-hour or per-day arrays. So the
   "historical energy usage" to-do is **an app-side logging feature, not a
   device query**. The app has to sample and persist from day one or the history
   simply will not exist when we go to build the view.

2. **The 4-plug interdependence to-do is an architecture decision, not a later
   feature.** Coordinating "plug A turns off → plug B turns on" needs one event
   loop supervising N sessions plus a rules layer. Retrofitting that onto a
   single-device MVP means a rewrite. The MVP is therefore built as **1-of-N**,
   with N capped at 4 in the UI.

3. **`Device` has no async context manager.** `kasa/device.py` defines
   `connect()` and `disconnect()` but no `__aenter__`/`__aexit__` — as the
   toggle script's comment notes, `disconnect()` must be called explicitly or
   aiohttp leaks the session. Every session teardown path must honour this.

4. **Newer plug firmware breaks this tool entirely.** TP-Link firmware from
   KP125M 1.3.0 onward replaced KLAP with a new encryption scheme, TPAP, which
   python-kasa does not support (upstream issue #1590; unmerged PR #1592). A
   plug on that firmware answers discovery and then refuses to talk:
   `Unsupported device ... encrypt_type='TPAP'`. Confirmed on a real plug here
   on 2026-09-17.

   This is a programme risk, not a one-plug annoyance. The library supports
   only KLAP, AES and XOR, and the KP125M has an `auto_update` component -- so
   a bench plug that works today can be pushed onto TPAP firmware overnight and
   take the whole test rig down with it. Three mitigations, in order of
   preference:

   * **Turn off auto-update on every bench plug**, and treat plug firmware as a
     qualified, version-locked part of the test setup rather than something
     that drifts. This is the only durable fix.
   * **Tapo app -> Profile -> Third Party Services -> Third-Party
     Compatibility** reverts an affected plug to KLAP. Works today, but it is a
     per-plug cloud setting that a factory reset or a firmware update can
     undo.
   * **Track upstream PR #1592.** When TPAP support merges, this fork picks it
     up on the next upstream sync and the problem disappears.

   Buying spare plugs on known-good firmware is worth considering before the
   remaining stock ships with 1.3.0+.

5. **Windows exe cannot be built on macOS.** PyInstaller does not
   cross-compile. Builds run on a GitHub Actions `windows-latest` runner.

---

## 2. Settled decisions

| Decision | Choice |
|---|---|
| Code location | New top-level `gzplug/` package in this fork |
| UI | Local web UI — FastAPI + browser |
| Windows build | GitHub Actions `windows-latest`, tag-triggered |
| Credentials | Shared test-team service account |
| Addressing | Discovery scan, then save as named bench profiles |
| Run records | One CSV per run |
| Resilience | Operator-selectable; **fail-fast is the default** |

---

## 3. Architecture

Four layers. The boundary that matters is between `core/` and everything else:
`core/` knows nothing about HTTP or the browser, so it is unit-testable against
the repo's existing offline fixtures.

```
gzplug/
  core/
    session.py      PlugSession  — one device, connect/verify/teardown
    registry.py     DeviceRegistry — up to 4 sessions, keyed by profile id
    runner.py       RunEngine — executes a RunPlan, emits events
    events.py       EventBus — async fan-out to subscribers
    poller.py       Poller — periodic state + energy sampling
    profiles.py     Bench profile load/save
    logging_csv.py  CSV run logger (an EventBus subscriber)
  api/
    app.py          FastAPI app factory
    routes.py       REST: profiles, discovery, run start/stop, settings
    ws.py           WebSocket: live state push to the browser
  web/              Static HTML/CSS/JS (no build step)
  __main__.py       Launcher: uvicorn on 127.0.0.1, opens the browser
  DESIGN.md         This file
```

### 3.1 The EventBus is the seam

Every state change — command issued, state read back, sample taken, fault
recorded — is published as an event. Subscribers:

- **CSV logger** — writes the run record
- **WebSocket broadcaster** — pushes to the browser
- **RuleEngine** *(future)* — the 4-plug interdependence feature

That third one is the point. Interdependence becomes a new subscriber that
issues commands back into `DeviceRegistry`. `RunEngine` does not change.

### 3.2 PlugSession

Wraps one `Device`. Preserves the toggle script's discipline:

- **Read-back verification.** `turn_on()` returning without raising only means
  the command was accepted. Always `update()` and confirm `is_on` matches.
- **Explicit `disconnect()`** in a `finally`, on every exit path including abort.
- **Restore original state** on run completion, abort, or Ctrl-C.

Adds, because a bench tool needs them:

- Reconnect with exponential backoff (only when `continue_on_error` is set)
- Per-command retry budget
- Fault counter, surfaced in the UI and written to the CSV

### 3.3 Fail-fast vs continue-on-error

A GUI toggle, defaulting to **fail-fast** — keeping the current philosophy that
an anomaly stops the run and surfaces the error rather than getting papered
over. `continue_on_error` enables retry/reconnect and keeps a running fault
count.

One caveat worth documenting in the UI: with `continue_on_error` on and a device
that has gone unreachable, the restore-original-state step may itself fail. That
gets logged loudly rather than silently skipped.

---

## 4. Persistence

### 4.1 Bench profiles

**Identity is the device ID, not the address.** A profile stores
`device_id` and `mac` alongside the `DeviceConfig`; the host in that config is
only the last place the plug was seen. When a saved address stops answering,
`AppState._relocate` runs a discovery scan, matches on `device_id`, writes the
new address back to `config.json` and reconnects — the tile then shows
"Moved from <old address>".

This matters because the failure it prevents is a *silent* one. On a DHCP
bench a router reboot can hand a plug's old address to something else, and a
profile keyed on address then points at a stranger's plug. That surfaces as an
authentication failure, not as a missing device, which sends whoever is
debugging it after the credentials rather than the address. Profiles written
before identity was tracked load fine and are backfilled on the next good
connect.


Reuse the library's own serializer rather than inventing a schema.
`kasa/deviceconfig.py` provides `DeviceConfig.to_dict()` / `from_dict()` and
`to_dict_control_credentials(credentials_hash=...)`, which returns the config
with the password stripped and the hash substituted.

```jsonc
// config.json, next to the exe
{
  "profiles": [
    { "id": "bench2-a", "label": "Bench 2 — plug A",
      "config": { /* DeviceConfig.to_dict_control_credentials(...) */ } }
  ]
}
```

Discovery (`Discover.discover()` in `kasa/discover.py`) populates the picker;
the chosen device's connection parameters are cached into the profile, so normal
startup has no discovery round-trip — same as the scratch scripts do today.

### 4.2 Credentials

**Settled: stored in plaintext in `config.json`.** These are a shared lab
service account, insecure by nature, and used by many testers — the
`credentials_hash` exchange and a `keyring` dependency both buy security this
account does not need and cost a per-machine pairing step it cannot afford.

`config.json` is gitignored. The one operational caveat: this is a real TP-Link
account password sitting on shared bench PCs, so that account's password must
not be reused anywhere that matters.

Credentials are stored **once** at the top level of `config.json` and injected
into each profile's `DeviceConfig` on load, rather than duplicated per profile.
Profiles are serialized with
`DeviceConfig.to_dict_control_credentials(exclude_credentials=True)`.

### 4.2a What the plugs actually expose

Surveyed against the KP125M fixture rather than guessed. Beyond power, voltage
and current, the plug reports: `consumption_today` and `consumption_this_month`
in kWh, `overheated`, `overloaded`, `power_protection_threshold`, `on_since`,
`rssi` and `signal_level`, `ssid`, `current_firmware_version`,
`update_available`, `auto_update_enabled`, `auto_off_enabled` and
`auto_off_minutes`, plus `device_id`, `mac` and `hw_ver`.

**`consumption_total` is not supported on this device** — it returns None — so
today and this-month are the only sums available, and a lifetime total would
have to be accumulated by the application.

Two of these are operational traps rather than readouts, and are surfaced on
the tile as warnings rather than buried in a stats row:

* **`auto_off_enabled`** — a plug set to switch itself off after N minutes
  will end a long endurance run by itself, and the run record would show a
  fault with no obvious cause.
* **`auto_update_enabled`** — the firmware risk in section 1.4. A bench plug
  left on auto-update can be moved onto TPAP firmware overnight.

Warnings are split by severity: overheated, overloaded and auto-off show
inline because they must not be missed; the rest collapse behind a "N notes"
disclosure, since auto-update is on by default and an always-visible banner on
every tile becomes furniture nobody reads.

### 4.3 Run CSV

`runs/run_YYYY-MM-DD_HHMMSS_<label>.csv`, next to the exe:

```
timestamp_iso,elapsed_s,device,cycle,phase,action,result,detail,power_w,voltage_v,current_a,energy_today_wh
```

Energy columns come from the `Poller` and are populated on every row, so the
same file serves as both the run record and the raw material for the future
energy-history view.

---

## 5. Windows packaging

- **PyInstaller one-dir, shipped as a zip** — not one-file. One-file re-extracts
  to `%TEMP%` on every launch, which is slow and gets scanned by AV on a locked
  down bench PC.
- **Pin the build to Python 3.12 or 3.13.** The repo supports 3.11–3.14, but
  PyInstaller support for 3.14 is new; the local `.venv` is 3.14, so dev and
  build Python will differ deliberately.
- `.github/workflows/build-gzplug.yml`, tag-triggered, uploads the zip as a
  Release asset. The test team downloads from the Releases page.
- **Document the Windows Firewall prompt** — the first discovery broadcast will
  trigger one, and an operator who clicks Cancel gets a tool that finds nothing.

---

## 5a. What the frozen build needed

Validated by building a real one-dir bundle and running it, not by trusting
the spec. Three things had to be declared explicitly, and each fails at
startup or at runtime rather than at build time:

* **`copy_metadata("python-kasa")`.** `kasa/__init__.py` calls
  `importlib.metadata.version("python-kasa")` at import. Without the
  distribution metadata in the bundle the executable dies immediately with
  `PackageNotFoundError`.
* **`gzplug/web` as `datas`.** `web_dir()` looks under `sys._MEIPASS` for
  exactly that layout; without it the server starts and serves nothing.
* **uvicorn submodules and `websockets` as hidden imports.** uvicorn resolves
  its loop, protocol and lifespan implementations by name at runtime, so
  static analysis cannot see them.

The entry point is `gzplug/packaging/launch.py` rather than
`gzplug/__main__.py`, because PyInstaller freezes a script and a script has no
package context for relative imports. It routes to the same CLI the pip
install exposes, defaulting to `ui` when given no arguments, so the executable
has one interface rather than two.

Bundle size is about 61 MB extracted.

## 6. Fork hygiene

This fork tracks `upstream/python-kasa`. To keep merges trivial:

- **Never edit `kasa/`, `tests/`, or `docs/`.** All app code lives in `gzplug/`.
- `pyproject.toml` gets only a `[project.scripts] gzplug = "gzplug.cli:main"`
  entry and `gzplug/tests` added to `testpaths`. Both are one-liners that are
  trivial to re-apply on conflict.
- **Web dependencies live in `gzplug/requirements.txt`, not in
  `pyproject.toml`.** An optional-dependency group invalidates `uv.lock`
  (verified with `uv lock --check`), which would put a fork-specific diff into
  a 443KB tracked file and cause a conflict on every upstream sync. The script
  entry and the `testpaths` addition do not invalidate it.
- `.gitignore` gains `config.json`, `runs/`, `/dist-gzplug/`.
- Application code under `gzplug/` is held to the repo's full ruff bar,
  including `ANN` annotations and the `S` bandit rules, with no exemptions.
  `gzplug/tests/` gets the same per-file ignores upstream already grants its
  own suite (asserts, docstrings, long lines), plus `S105`/`S106` for test
  passwords.

---

## 7. Testing

The repo ships `tests/fakeprotocol_smart.py`, `tests/device_fixtures.py` and two
KP125M fixtures. The `core/` layer is testable against these with **no
hardware** — run engine, event fan-out, CSV output, and fault handling all get
covered offline.

Note `addopts = "--disable-socket"` in `pyproject.toml`. FastAPI's `TestClient`
uses an in-process ASGI transport and opens no real socket, so API tests are
fine under that flag.

App tests live in `gzplug/tests/` so `testpaths = ["tests"]` keeps upstream's
suite unchanged.

**Hardware smoke test:** the real KP125M at 192.168.10.17 — a short cycle run
verifying read-back, the CSV, and restore-on-abort.

---

## 7a. Hardware verification status

Recorded as it happens, so the gap between "tests pass" and "works on a bench"
stays visible.

| Path | Status |
|---|---|
| Discovery, save profile, reconnect from saved config | Verified on real KP125M plugs, 2026-09-17 |
| Single-plug cycle run, CSV written | Verified |
| **Two plugs driven concurrently** | **Verified 2026-09-17** -- the riskiest path, since both sessions share one event loop |
| Restore-on-completion | Verified |
| Energy column values sane on real hardware | Not yet confirmed |
| Fail-fast against a *real* fault (plug powered off mid-run) | **Not yet tested** |
| Restore-on-abort (Ctrl-C) on hardware | Not yet tested |

The last two matter before this reaches the test team. The retry and reconnect
code has only ever seen injected exceptions, never a real socket timeout, and
the failure mode to rule out is a run that hangs silently rather than stopping
loudly.

## 7b. Traps found by running it, not by testing it

Two Phase 2 bugs passed a green test suite and were caught only by starting a
real server. Both are worth remembering.

* **`gzplug ui` nested two event loops.** The CLI dispatches commands through
  `asyncio.run`, and `uvicorn.run` calls `asyncio.run` again. Fixed by
  splitting the launcher into `serve()` (awaits on the caller's loop, used by
  `gzplug ui`) and `main()` (owns the loop, used by `python -m gzplug` and the
  frozen build).
* **WebSocket upgrades returned 404.** Starlette's `TestClient` speaks ASGI
  directly, so every websocket test passed; a real uvicorn with no websocket
  library refuses the upgrade and the page silently never updates. `websockets`
  is now pinned in `gzplug/requirements.txt`, with a test asserting one is
  installed.

That lesson was carried into Phase 3: the release workflow starts the built
`gzplug.exe` on the Windows runner and checks the page, the static assets,
`/api/state`, the CLI, and a real WebSocket handshake delivering a snapshot
frame. A build that compiles but does not serve produces no release.

## 8. Build order

| Phase | Deliverable |
|---|---|
| 0 | Scaffold, pyproject wiring, lint/test passing |
| 1 | `core/` + offline tests — headless cycle runs with CSV output |
| 2 | FastAPI + WebSocket + web UI -- **done** |
| 3 | PyInstaller spec + GH Actions workflow + first Release -- **done** |
| 4 | *To-dos:* energy-history view, 4-plug rule engine |

Phase 1 is independently useful: it replaces `scratch/kp125m_toggle.py` with
something that logs, before any UI exists.
