# Noyce Joyce Nixie Clock for Home Assistant

Local Bluetooth LE integration for the [Noyce Joyce Nixie Clock](https://eshop.3dsimo.com/collections/noyce-joyce).
Keeps the clock on time (it has no radio sync and drifts) and exposes the settings of the
discontinued phone app. Protocol taken from the official Flutter app
([michalvalkoun/noyce_joyce_nixie](https://github.com/michalvalkoun/noyce_joyce_nixie)).

Supported: **Nixie Clock** with firmware 1.17. Nixie Alarm-Clock, Radio and Itron are not supported.

## How it works

- Auto-discovered via HA Bluetooth (local name `Nixie Clock`). Works with the host adapter
  and with ESPHome Bluetooth proxies (`bluetooth_proxy: active: true`).
- **Connect on demand**: every operation opens a short GATT connection and closes it. The clock
  accepts one connection at a time - close the phone app, otherwise HA cannot connect.
- Every refresh = measure drift + set time (aligned to a full second) first, then read the
  settings. If the link drops after the time write, the sync counts and the previous settings
  are kept.
- Refresh triggers: setup / HA restart (in the background, never blocks startup), the sync
  interval (default 24 h), the *Sync time* button, an hourly check that resyncs when the UTC
  offset changed (DST) or the last sync failed, and - after a failure - the next advertisement
  of the clock (at most every 2 min).
- **The clock stops advertising while anything is connected to it** (phone/tablet app). HA then
  cannot reach it; the integration stays loaded with unavailable entities and resyncs as soon
  as the clock is heard again.
- The clock stores **local** time (unix seconds + UTC offset) and knows nothing about DST,
  hence the hourly offset check.

## Entities

| Entity | Type | Notes |
|---|---|---|
| Sync time | button | Always available, also to recover from a failed sync |
| Drift | sensor (s) | Clock minus real time, measured right before each sync. Positive = clock ahead |
| Last sync | sensor (timestamp) | diagnostic |
| Signal strength | sensor (dBm) | diagnostic; live RSSI from advertisements (max. 1 update/min), `source` attribute names the adapter/proxy HA would connect through |
| Night mode | switch | Tubes off in the time window |
| Night mode start / end | time | `raw_value` attribute holds the stored local-epoch value |
| Nixie dots | switch | |
| Hourglass interval | select | Cathode-poisoning prevention cycle: 1/10/30/60 min or daily at 3:00 |
| Time format | select | 24 h / 12 h |

Firmware version is shown on the device page.

## Install

HACS -> Custom repositories -> this repo (Integration), or copy `custom_components/nixie_clock`
to `/config/custom_components/`. Restart HA; the clock shows up under *Discovered*.

Options: sync interval (1-168 h).

## Protocol

Vendor service `A8ED1400-130A-4D4B-ACBA-5DE7E77E9B47`, no pairing (the firmware rejects
bonded peers), little-endian integers.

| Characteristic | Meaning | Format |
|---|---|---|
| `A8ED1410` | date/time | uint32, unix seconds + UTC offset |
| `A8ED1420` | time format | uint8, 0 = 24 h, 1 = 12 h |
| `A8ED1421` | hourglass | uint8 index 0-4 |
| `A8ED1423` | night mode on/off | uint8 |
| `A8ED1424` / `A8ED1425` | night mode end / start | uint32 local epoch (time of day used) |
| `A8ED1426` | nixie dots | uint8 |
| `180A/2A26` | firmware revision | string |
| **`A8ED14FF`** | **writing `0x99` enters the DFU bootloader** | **never used; writes are whitelisted** |

## Known unknowns

- Night mode: the app writes a full timestamp; we assume the firmware uses only the time of
  day (`value % 86400`). Check `raw_value` against the display.
- Older firmware without `2A26` is untested.

## Development

```sh
uv venv && uv pip install -r requirements_test.txt
pytest -q && ruff check . && ruff format --check .
```
