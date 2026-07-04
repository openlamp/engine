# OpenLamp Engine

The **core layer** of the OpenLamp family: instant, 100% local control of smart LED
lamps (Tuya today, WLED experimental), exposed through a stable command contract —
**OpenLamp State (OLS)**, a WLED-compatible JSON state patch (see [OLS.md](OLS.md)).

Part of the [OpenLamp](https://github.com/openlamp/openlamp) family:

| Layer | Repo | Role |
|---|---|---|
| Engine (this repo) | `openlamp-engine` | drivers + dispatcher + local API + daemon + CLI |
| Stream Deck frontend | [lumideck](https://github.com/openlamp/lumideck) | keys, dials, live status on an Elgato Stream Deck |
| MIDI frontend | [openlamp-midi](https://github.com/openlamp/midi) | stage control from physical MIDI controllers |

## What's inside

- **`engine.py`** — the engine: one thread per lamp with a *persistent* connection
  (sub-200 ms commands), the OLS dispatcher, groups, snapshots, animations
  (cycle/flash/tempo), connect-time sync, a rainbow welcome sweep, and the local
  API on `127.0.0.1:8377` (`/cmd`, `/status`, `/syntax`, plus the optional
  WLED-compat `/json/state`). Frontend-agnostic: its only upward link is an
  `on_change` hook.
- **`daemon.py`** — headless host: runs the engine without any frontend app.
- **`run-headless.sh`** — one command to switch to CLI/MIDI-only mode.
- **`lamp.py`** — the CLI (also Bome-callable): `lamp.py vert`, `lamp.py bri:40`…
  Routes through the local API when a host runs, drives lamps directly otherwise.
- **`com.benlab.lumideck-daemon.plist`** — launchd autostart for the daemon.
- **`OLS.md`** — the OpenLamp State contract. **`TUYA-KEYS.md`** — how to get your
  lamps' local keys (official Tuya cloud API, one-time).

## One host at a time — the rule

A Tuya lamp accepts **a single local connection**, and every host binds port 8377.
So run **either** the Stream Deck plugin (it embeds this engine in-process) **or**
`daemon.py` — never both. Deck sessions → plugin; CLI/MIDI-only sessions → daemon.

## Why 8-bit values (0–255)

OLS uses 8-bit for brightness and per-channel color, for three reasons:
1. **WLED compatibility** — WLED's JSON API is 8-bit; OLS is a compatible patch.
2. **It matches the hardware** — RGB LEDs are driven 8 bits per channel
   (16.7 M colors); Tuya's internal 0–1000 scale adds no perceptible precision.
3. **It matches perception** — ~1 % brightness steps are at the threshold of what
   the eye distinguishes; 256 levels cover that.
MIDI frontends (7-bit, 0–127) scale up ×2 — plenty for stage cues.

## Config

`tuya-lamps.json` sits next to `lamp.py` (never committed — it contains your local
keys). Template:

```json
{
  "lamps": [
    {"name": "L1", "mac": "aa:bb:cc:dd:ee:ff", "device_id": "…", "local_key": "…",
     "ips": {"192.168.1": "192.168.1.50"}}
  ],
  "groups": {"front": ["L1"]},
  "sync": {"enabled": true, "state": {"on": true, "col": [0, 100, 200], "bri": 153}}
}
```

Made by **BenLab** with the help of Claude. WLED support is written but untested on
real hardware — testers wanted: open an issue on [lumideck](https://github.com/openlamp/lumideck/issues).
