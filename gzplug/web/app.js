// gzplug browser client.
//
// The server is the single source of truth: every event over the WebSocket
// carries a full state snapshot alongside it, so the page never has to
// reconstruct run state from a stream of deltas. A reload, a dropped socket,
// or a second browser tab all converge on the same view.

"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  snapshot: null,
  selected: new Set(),
  socket: null,
  retryMs: 500,
};

// ---- helpers --------------------------------------------------------

function fmt(value, digits, suffix) {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits) + (suffix || "");
}

function clock(iso) {
  const d = iso ? new Date(iso) : new Date();
  return d.toLocaleTimeString([], { hour12: false });
}

function toast(message, ok) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("ok", Boolean(ok));
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 6000);
}

async function api(path, options) {
  const response = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (body && body.detail) || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

// ---- rendering ------------------------------------------------------

function render(snapshot) {
  if (!snapshot) return;
  state.snapshot = snapshot;

  $("setup").classList.toggle("hidden", snapshot.configured);
  renderDevices(snapshot);
  renderRun(snapshot);
}

function renderDevices(snapshot) {
  const host = $("devices");
  const devices = snapshot.devices || [];
  host.innerHTML = "";

  $("device-count").textContent = devices.length
    ? `${devices.length} of ${snapshot.maxDevices}`
    : "";
  $("devices-empty").classList.toggle("hidden", devices.length > 0);

  const busy = snapshot.run.state === "running";

  for (const device of devices) {
    const card = document.createElement("div");
    card.className = "device" + (device.error ? " fault" : "");

    const stateClass =
      device.is_on === true ? "on" : device.is_on === false ? "" : "unknown";
    const stateText =
      device.is_on === true ? "ON" : device.is_on === false ? "OFF" : "?";

    card.innerHTML = `
      <div class="device-top">
        <div>
          <div class="device-name"></div>
          <div class="device-meta"></div>
        </div>
        <span class="state ${stateClass}">${stateText}</span>
      </div>
      <div class="readouts">
        <div><span>Power</span>${fmt(device.power_w, 1, " W")}</div>
        <div><span>Volts</span>${fmt(device.voltage_v, 1, " V")}</div>
        <div><span>Amps</span>${fmt(device.current_a, 3, " A")}</div>
      </div>
      <div class="readouts secondary">
        <div><span>Today</span>${fmt(device.energy_today_kwh, 3, " kWh")}</div>
        <div><span>Month</span>${fmt(device.energy_month_kwh, 2, " kWh")}</div>
        <div><span>On for</span>${since(device.on_since, device.is_on)}</div>
      </div>`;

    const warnings = warningsFor(device);
    if (warnings.length) card.appendChild(warningStrip(warnings));

    card.querySelector(".device-name").textContent = device.label;
    // A plug with no alias is named after its IP, so printing the host again
    // just repeats the title.
    const meta = [];
    if (device.label !== device.host) meta.push(device.host);
    if (device.model) meta.push(device.model);
    const fw = (device.info || {}).firmware;
    if (fw) meta.push(`fw ${String(fw).split(" ")[0]}`);
    if (typeof device.rssi_dbm === "number") meta.push(`${device.rssi_dbm} dBm`);
    if (device.faults) meta.push(`${device.faults} fault(s)`);
    card.querySelector(".device-meta").textContent = meta.join(" · ") || "\u00a0";

    if (device.error) {
      card.appendChild(errorBlock(device));
    }

    const actions = document.createElement("div");
    actions.className = "device-actions";
    if (device.connected) {
      actions.appendChild(
        button("On", busy, () => switchDevice(device.id, true)),
      );
      actions.appendChild(
        button("Off", busy, () => switchDevice(device.id, false)),
      );
    } else {
      actions.appendChild(
        button("Reconnect", busy, () => post(`/devices/${device.id}/reconnect`)),
      );
    }
    actions.appendChild(
      button("Remove", busy, () => removeDevice(device.id, device.label)),
    );
    card.appendChild(actions);
    host.appendChild(card);
  }

  renderPicker(devices, busy);
}

// How long the relay has been in its current state. A bench operator reads
// this far more often than an absolute timestamp.
function since(iso, isOn) {
  if (!iso || isOn !== true) return "—";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 90) return `${Math.round(seconds)} s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  if (seconds < 172800) return `${(seconds / 3600).toFixed(1)} h`;
  return `${Math.round(seconds / 86400)} d`;
}

// Conditions that will quietly ruin a run, surfaced on the tile rather than
// left for the operator to find in the Kasa app afterwards.
function warningsFor(device) {
  const info = device.info || {};
  const out = [];

  if (device.overheated) out.push({ level: "bad", text: "Overheated" });
  if (device.overloaded) out.push({ level: "bad", text: "Overloaded" });

  if (info.auto_off_enabled) {
    out.push({
      level: "bad",
      text: `Auto-off is on (${info.auto_off_minutes ?? "?"} min) — it will end a long run by itself`,
    });
  }
  if (info.power_protection_w) {
    out.push({
      level: "warn",
      text: `Power protection set to ${info.power_protection_w} W — it will cut the plug above that`,
    });
  }
  if (info.auto_update_enabled) {
    out.push({
      level: "warn",
      text: "Auto-update is on — firmware may move to TPAP, which this build cannot talk to",
    });
  }
  if (info.update_available) {
    out.push({ level: "warn", text: "A firmware update is pending" });
  }
  if (device.relocated_from) {
    out.push({
      level: "info",
      text: `Moved from ${device.relocated_from} — found by device ID`,
    });
  }
  if (typeof device.rssi_dbm === "number" && device.rssi_dbm <= -70) {
    out.push({
      level: "warn",
      text: `Weak signal (${device.rssi_dbm} dBm) — expect retries`,
    });
  }
  return out;
}

// Severity decides visibility. A plug that is overheating or will switch
// itself off mid-run has to be unmissable; the rest are worth knowing but
// would otherwise sit on every tile forever -- auto-update is on by default,
// so left inline it becomes furniture nobody reads.
function warningStrip(warnings) {
  const box = document.createElement("div");
  box.className = "warnings";

  const urgent = warnings.filter((w) => w.level === "bad");
  const rest = warnings.filter((w) => w.level !== "bad");

  for (const warning of urgent) {
    const row = document.createElement("div");
    row.className = "warning bad";
    row.textContent = warning.text;
    box.appendChild(row);
  }

  if (rest.length) {
    const details = document.createElement("details");
    details.className = "warning-more";

    const summary = document.createElement("summary");
    summary.textContent = `${rest.length} note${rest.length === 1 ? "" : "s"}`;
    details.appendChild(summary);

    for (const warning of rest) {
      const row = document.createElement("div");
      row.className = `warning ${warning.level}`;
      row.textContent = warning.text;
      details.appendChild(row);
    }
    box.appendChild(details);
  }
  return box;
}

// A one-line summary, with the raw device error behind a disclosure. The
// untouched text still matters when something unexpected happens, but it must
// not be what sets a card's height.
function errorBlock(device) {
  const box = document.createElement("div");
  box.className = "device-error";

  const summary = document.createElement("div");
  summary.textContent = device.error;
  box.appendChild(summary);

  if (device.error_detail && device.error_detail !== device.error) {
    const details = document.createElement("details");
    const toggle = document.createElement("summary");
    toggle.textContent = "Details";
    const pre = document.createElement("pre");
    pre.textContent = device.error_detail;
    details.append(toggle, pre);
    box.appendChild(details);
  }
  return box;
}

function button(label, disabled, onClick) {
  const el = document.createElement("button");
  el.type = "button";
  el.textContent = label;
  el.disabled = disabled;
  el.addEventListener("click", onClick);
  return el;
}

function renderPicker(devices, busy) {
  const host = $("run-devices");
  host.innerHTML = "";

  // Drop selections for plugs that have gone away or gone offline.
  for (const id of [...state.selected]) {
    const device = devices.find((d) => d.id === id);
    if (!device || !device.connected) state.selected.delete(id);
  }
  // First usable plug is selected by default, so Start is never a dead button.
  if (!state.selected.size) {
    const first = devices.find((d) => d.connected);
    if (first) state.selected.add(first.id);
  }

  for (const device of devices) {
    const label = document.createElement("label");
    label.className = "chip" + (device.connected ? "" : " disabled");

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.selected.has(device.id);
    box.disabled = !device.connected || busy;
    box.addEventListener("change", () => {
      if (box.checked) state.selected.add(device.id);
      else state.selected.delete(device.id);
    });

    const text = document.createElement("span");
    text.textContent = device.connected
      ? device.label
      : `${device.label} (offline)`;

    label.append(box, text);
    host.appendChild(label);
  }

  if (!devices.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "Add a plug first.";
    host.appendChild(empty);
  }
}

function renderRun(snapshot) {
  const run = snapshot.run;
  const running = run.state === "running";

  const badge = $("run-badge");
  badge.textContent = run.state;
  badge.className = "badge " + run.state;

  $("btn-start").classList.toggle("hidden", running);
  $("btn-stop").classList.toggle("hidden", !running);
  $("btn-start").disabled = !snapshot.devices.some((d) => d.connected);

  const faults = Object.values(run.faults || {}).reduce((a, b) => a + b, 0);
  const bits = [];
  if (run.cycles) bits.push(`cycle ${run.cycle} of ${run.cycles}`);
  if (faults) bits.push(`${faults} fault(s)`);
  if (run.error) bits.push(run.error);
  $("run-progress").textContent = bits.join("  ·  ");

  const link = $("csv-link");
  if (run.csv) {
    link.href = `/api/runs/${encodeURIComponent(run.csv)}`;
    link.textContent = `Download ${run.csv}`;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }

  for (const input of ["p-cycles", "p-on", "p-off", "p-label", "p-continue", "p-restore"]) {
    $(input).disabled = running;
  }
}

// ---- log ------------------------------------------------------------

function log(event) {
  const isSample = event.kind === "sample";
  if (isSample && !$("show-samples").checked) return;

  const host = $("log");
  const atBottom =
    host.scrollHeight - host.scrollTop - host.clientHeight < 40;

  const line = document.createElement("div");
  line.className = "log-line";
  if (event.result === "error") line.classList.add("error");
  else if (event.result === "retry") line.classList.add("retry");
  else if (isSample) line.classList.add("sample");

  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = clock(event.timestamp);

  const text = document.createElement("span");
  const who = event.device ? `${event.device}: ` : "";
  let body = event.detail || event.action || event.kind;
  if (isSample && event.sample) {
    body = `${event.sample.isOn ? "on " : "off"}  ${fmt(event.sample.powerW, 1, " W")}`;
  }
  text.textContent = who + body;

  const placeholder = host.querySelector(".log-empty");
  if (placeholder) placeholder.remove();

  line.append(time, text);
  host.appendChild(line);

  while (host.children.length > 2000) host.removeChild(host.firstChild);
  if (atBottom) host.scrollTop = host.scrollHeight;
}

// ---- actions --------------------------------------------------------

async function post(path, body) {
  try {
    const result = await api(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    render(result.state || result);
    return result;
  } catch (error) {
    toast(error.message);
    return null;
  }
}

async function switchDevice(id, on) {
  await post(`/devices/${id}/switch`, { on });
}

async function removeDevice(id, label) {
  if (!confirm(`Remove "${label}" from the saved plugs?`)) return;
  try {
    render(await api(`/devices/${id}`, { method: "DELETE" }));
  } catch (error) {
    toast(error.message);
  }
}

async function discover(button) {
  button.disabled = true;
  button.textContent = "Scanning…";
  const panel = $("discover-result");
  panel.classList.add("hidden");
  panel.innerHTML = "";

  const result = await post("/discover", { save: true, timeout: 5 });

  button.disabled = false;
  button.textContent = "Scan network";
  if (!result) return;

  const found = document.createElement("div");
  found.textContent = result.found.length
    ? `Found ${result.found.length} supported plug(s).`
    : "No supported plugs answered.";
  panel.appendChild(found);

  // Collapsed by default. A lab can hold dozens of plugs on newer firmware,
  // and one banner each pushes the plugs and the run form off-screen. The
  // advice is identical for all of them, so it is said once.
  const unsupported = result.unsupported || [];
  if (unsupported.length) {
    const details = document.createElement("details");
    details.className = "unsupported";

    const summary = document.createElement("summary");
    summary.textContent = `${unsupported.length} other plug${
      unsupported.length === 1 ? "" : "s"
    } answered but ${unsupported.length === 1 ? "is" : "are"} not supported`;

    const help = document.createElement("p");
    help.className = "help";
    help.textContent = unsupported[0].help;

    const list = document.createElement("ul");
    list.className = "hosts";
    for (const item of unsupported) {
      const entry = document.createElement("li");
      entry.textContent = item.host;
      list.appendChild(entry);
    }

    details.append(summary, help, list);
    panel.appendChild(details);
  }
  panel.classList.remove("hidden");
}

async function addByIp() {
  const host = prompt("Plug IP address:");
  if (!host) return;
  const label = prompt("Name for this bench position (optional):") || "";
  await post("/devices", { host: host.trim(), label: label.trim() });
}

async function startRun(event) {
  event.preventDefault();
  if (!state.selected.size) {
    toast("Select at least one plug.");
    return;
  }
  const result = await post("/run", {
    devices: [...state.selected],
    cycles: Number($("p-cycles").value),
    on_time_s: Number($("p-on").value),
    off_time_s: Number($("p-off").value),
    continue_on_error: $("p-continue").checked,
    restore_state: $("p-restore").checked,
    label: $("p-label").value.trim(),
  });
  if (result) toast(`Run started — logging to ${result.csv}`, true);
}

// ---- socket ---------------------------------------------------------

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${location.host}/ws`);
  state.socket = socket;

  socket.addEventListener("open", () => {
    state.retryMs = 500;
    $("link").className = "link-dot up";
    $("link").title = "Connected";
  });

  socket.addEventListener("message", (message) => {
    const payload = JSON.parse(message.data);
    if (payload.type === "snapshot") {
      render(payload.data);
    } else if (payload.type === "event") {
      log(payload.data);
      render(payload.state);
    }
  });

  socket.addEventListener("close", () => {
    $("link").className = "link-dot down";
    $("link").title = "Reconnecting…";
    // Backoff, so a stopped server does not spin the browser.
    setTimeout(connect, state.retryMs);
    state.retryMs = Math.min(state.retryMs * 2, 10000);
  });

  socket.addEventListener("error", () => socket.close());
}

// ---- wiring ---------------------------------------------------------

$("creds-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = await post("/credentials", {
    username: $("creds-user").value.trim(),
    password: $("creds-pass").value,
  });
  if (result) {
    $("creds-pass").value = "";
    toast("Credentials saved.", true);
  }
});

$("btn-discover").addEventListener("click", (e) => discover(e.currentTarget));
$("btn-add").addEventListener("click", addByIp);
$("run-form").addEventListener("submit", startRun);
$("btn-stop").addEventListener("click", () => post("/run/stop"));
function clearLog() {
  const host = $("log");
  host.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "log-empty";
  empty.textContent = "Events appear here during a run.";
  host.appendChild(empty);
}

$("btn-clear").addEventListener("click", clearLog);
clearLog();

api("/state").then(render).catch(() => {});
connect();
