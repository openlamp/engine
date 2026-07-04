# OpenLamp engine — Node.js port (DRAFT)

**Status: draft port of engine.py, NOT validated on real lamps.** tuyapi ^7.7.1 accepts `version: '3.5'` and exposes the documented API (connect / get({schema}) / set({multiple,data,shouldWaitForResponse}) / refresh / isConnected / events), but its protocol 3.5 behavior (session key negotiation, ack shape of multi-DP sets, the "empty response = dead session" rule) must be validated on the real lamps before any live use.

- Run daemon: `npm install && node engine.js` (config: `tuya-lamps.json` next to engine.js, or `OPENLAMP_CONFIG=<path>`; local API on 127.0.0.1:8377).
- Run test: `node test-mock.js` (offline, mocked tuyapi device, API on port 18377).

**ONE-HOST RULE — never run this alongside the Python host (Stream Deck plugin or daemon.py):** each Tuya lamp accepts a single local connection and both hosts bind port 8377. Starting this daemon while the plugin runs would steal/collide the lamps' only connection slot on a live system.

Deliberate deltas vs Python: IPs come only from the config (no ARP subnet re-sweep, no Mango SSH deauth — macOS/OpenWrt-specific), heartbeat = tuyapi's internal ping + isConnected() check, `_status()` does a single fresh read (acked sends don't accumulate stale acks like tinytuya nowait mode did).

Open questions for real-lamp validation: (1) does `set({multiple:true, shouldWaitForResponse:true})` resolve falsy on a half-dead 3.5 session (our reconnect trigger) or throw/timeout? (2) does tuyapi accept our raw DP24 `HHHHSSSSVVVV` hex string as-is? (3) fade pacing ≤ 4 acked cmd/s must be re-measured through tuyapi's stack.
