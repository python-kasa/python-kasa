(topics-hub-children)=
# Tapo / Kasa hubs and child devices

Tapo hubs (for example **H500**, **H200**) expose paired sensors, cameras, and other
accessories as *child devices*. python-kasa discovers and controls those children
through the hub's SMART camera protocol.

```{contents} Contents
   :local:
```

## How child enumeration works

On each {meth}`~kasa.Device.update()`, hub devices query:

| API | Role |
|-----|------|
| {code}`getChildDeviceList` | Returns the roster used to build {attr}`~kasa.Device.children` |
| {code}`getChildDeviceComponentList` | Component negotiation data for each child |
| {code}`getDeviceInfo` | Device metadata, including {code}`child_num` |
| {code}`getSupportChildDeviceCategory` | Supported child categories (cameras, Sub-G triggers, etc.) |

The library builds {attr}`~kasa.Device.children` **only** from
{code}`getChildDeviceList.child_device_list`. Each entry must include at least a
{code}`device_id` and {code}`category` so python-kasa can construct the correct
child device class and route hub-proxied requests.

Pairing new devices uses a different API surface ({code}`startScanChildDevice`,
{code}`getScanChildDeviceList`, {code}`addScanChildDeviceList`) via the
{mod}`~kasa.smartcam.modules.childsetup` module. That path is for **adding**
devices, not listing ones that are already paired.

## `child_num` vs `getChildDeviceList`

These fields answer different questions and **must not be treated as equivalent**.

| Field | Source | Meaning |
|-------|--------|---------|
| {code}`child_num` | {code}`getDeviceInfo` → {code}`basic_info` | Metadata: how many children the hub believes are paired (often cloud/account state) |
| {code}`sum` / {code}`child_device_list` | {code}`getChildDeviceList` | Enumeration: which children are exposed to this LAN session right now |

On some hubs (notably **H500** with current firmware), live testing shows:

- {code}`child_num` may be greater than zero (for example {code}`6`)
- {code}`getChildDeviceList` returns {code}`sum: 0` and an empty or omitted
  {code}`child_device_list`

In that case {attr}`~kasa.Device.children` is empty after {meth}`~kasa.Device.update()`
even though the Tapo app shows paired cameras. This is **hub firmware behaviour**,
not a python-kasa parsing bug. The library logs a warning when it detects the
mismatch.

Other hub models can show the opposite pattern. For example the **H200** fixture
in the test suite has {code}`child_num: 0` while {code}`getChildDeviceList.sum` is
{code}`5` with five list entries. Do not use {code}`child_num` as a substitute for
the list API on any model.

## No LAN "reason code"

There is currently **no documented LAN method** that explains *why*
{code}`getChildDeviceList` is empty while {code}`child_num` is non-zero. Probing
has not found an alternate roster API: category-filtered
{code}`getChildDeviceList`, {code}`getChildDeviceComponentList`,
{code}`getScanChildDeviceList`, and various {code}`get` module shapes either
return empty results or are unsupported.

The Tapo mobile app may use cloud or additional local channels not exposed through
the third-party SMART protocol surface python-kasa implements.

## Controlling hub children

When children **are** listed, commands target a child by {code}`device_id`. The CLI
documents this pattern:

```shell
kasa --host <hub-ip> --child <device-id> state
```

At the library level, child devices appear on {attr}`~kasa.Device.children` after
{meth}`~kasa.Device.update()`. Each child shares the hub transport; the protocol
wrapper injects the child {code}`device_id` into requests.

Hub-paired cameras may **reject direct LAN authentication** at their own IP address
(challenge mismatch) because they expect hub or cloud context. Connecting to the
**hub** and enumerating children is the supported path when the list API works.

## Capturing hub fixtures (`dump_devinfo`)

{mod}`devtools.dump_devinfo` records hub responses and, when
{code}`child_device_list` contains entries, dumps per-child fixtures under
{code}`child_devices/`.

If {code}`getChildDeviceList` omits {code}`child_device_list` or returns
{code}`sum: 0`, the tool continues with a **hub-only** fixture (no child files).
That accurately reflects what the LAN API returned; re-running the dump while
children are online will not help on hubs that withhold the list over local
access.

## Summary for integrators

1. Call {meth}`~kasa.Device.update()` on the hub and inspect
   {attr}`~kasa.Device.children`, not {code}`child_num`.
2. An empty {attr}`~kasa.Device.children` with non-zero {code}`child_num` means
   the hub did not expose children on {code}`getChildDeviceList` — there is no
   further diagnostic field to query.
3. If you need a specific hub-paired camera and the list API is empty, you may need
   to connect to that camera by IP when it accepts direct auth (model/firmware
   dependent), or wait for Tapo to expose enumeration on LAN.
4. See {class}`~kasa.smartcam.modules.childdevice.ChildDevice` and
   {class}`~kasa.smartcam.smartcamdevice.SmartCamDevice` for implementation details.
