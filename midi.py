#!/usr/bin/env python3
"""OpenLamp MIDI — reference implementation of the wled-midi convention, in the engine.

Opens a virtual MIDI input port (default "OpenLamp") and translates incoming MIDI into
OpenLamp State (OLS = WLED-compatible JSON patch) commands, per the
github.com/openlamp/wled-midi convention (v0.2). It POSTs to the engine's local API
(127.0.0.1:8377/cmd); the engine owns the persistent device connections.

Model (wled-midi v0.2):
  - CHANNEL = a lamp group/target (1-16 per port; channel 1 = "all").
  - NOTES are organised in zones:
      LOOKS (60-68)      what the lamp SHOWS, mutually exclusive: 8 colours + effect.
      POWER/UTIL (48-56) on/off/toggle/blackout/restore/solid.
      MODIFIERS (72-75)  overlay the current look: beat toggle, flash.
  - CC (1-8) shapes the current look: bri/cct/hue/sat/fx/sx/ix/pal.
  - VELOCITY (optional, off by default) sets the look's brightness.
  - PROGRAM CHANGE recalls a WLED preset (ps = n+1).
  - MIDI CLOCK derives tempo.

Beat (note 72) toggles a per-channel beat flag and emits beat:on/off; the actual
on-the-beat pulsing is done by the tempo layer (openlamp-midi beatsync). In-process
dispatch (skipping loopback HTTP) is a future optimisation.

Run:  python3 midi.py            (Ctrl-C to quit)
Config: midi-mapping.json (auto-written next to this file; remappable).
"""
import json, os, time, colorsys, urllib.request, urllib.parse
import rtmidi

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "midi-mapping.json")
API = "http://127.0.0.1:8377"

# Fallbacks when the device's fxcount/palcount aren't known (wled-midi SPEC §5).
FALLBACK_FXCOUNT = 118
FALLBACK_PALCOUNT = 71

# wled-midi v0.2.0 default map. Numbers remappable in midi-mapping.json; the CC
# transforms and zone semantics are the stable contract.
DEFAULT = {
    "port_name": "OpenLamp",
    # ONE MIDI CHANNEL PER TARGET (device / segment / group), or "all".
    "channels": {"1": "all", "2": "front", "3": "back", "4": "L1", "5": "L2"},
    # LOOKS (what the lamp shows) — note -> [r,g,b], or "effect".
    "looks": {
        "60": [255, 0, 0], "61": [255, 85, 0], "62": [255, 200, 0], "63": [0, 255, 0],
        "64": [0, 200, 255], "65": [0, 0, 255], "66": [255, 0, 170], "67": [255, 255, 255],
        "68": "effect",
    },
    # POWER / UTIL — note -> OLS command string.
    "util": {
        "48": '{"on":false}', "50": '{"on":true}', "52": '{"on":"t"}',
        "53": "blackout", "55": "restore", "56": '{"fx":0}',
    },
    # MODIFIERS (overlay the current look) — note -> modifier name.
    "modifiers": {"72": "beat", "73": "flash"},
    "cc": {"1": "bri", "2": "cct", "3": "hue", "4": "sat",
           "5": "fx", "6": "sx", "7": "ix", "8": "pal"},
    "programs": [],              # empty -> Program Change n maps to WLED preset n+1
    "velocity_to_bri": False,    # true -> a look note-on also sets brightness from velocity
    "clock_tempo": False,
    "clock_channel": 1,
}


def load_cfg():
    if os.path.exists(CONFIG):
        c = dict(DEFAULT); c.update(json.load(open(CONFIG))); return c
    json.dump(DEFAULT, open(CONFIG, "w"), indent=2)
    return dict(DEFAULT)


def send(cmd, lamps):
    q = urllib.parse.quote(cmd)
    if lamps:
        q += "&lamps=" + ",".join(lamps)
    try:
        urllib.request.urlopen(API + "/cmd?c=" + q, timeout=3).read()
    except Exception as e:
        print("  ! engine API unreachable (is the daemon running?):", e)


class Bridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.clock_ticks = 0
        self.clock_t0 = None
        self.last_bpm = None
        self.hue = {}                 # per-channel hue (continuous colour)
        self.sat = {}                 # per-channel saturation
        self.fx = {}                  # per-channel WLED effect {fx,sx,ix,pal}
        self.beat = {}                # per-channel beat-mode on/off

    def _target(self, chan):
        chans = self.cfg.get("channels")
        if chans is not None:
            tgt = chans.get(str(chan))
            if tgt is None:
                return None            # unmapped channel -> ignore
            return [] if tgt in ("all", "*", "") else [tgt]
        want = self.cfg.get("channel", 1)
        if want and chan != want:
            return None
        return self.cfg.get("lamps") or []

    def _effect_cmd(self, chan):
        f = self.fx.setdefault(chan, {"fx": 1, "sx": 128, "ix": 128, "pal": 0})
        if f["fx"] == 0:               # entering the effect look needs a visible effect
            f["fx"] = 1
        return '{"fx":%d,"sx":%d,"ix":%d,"pal":%d}' % (f["fx"], f["sx"], f["ix"], f["pal"])

    def on_note(self, note, vel, chan, target):
        if vel <= 0:                   # note-on only
            return
        n = str(note)
        looks = self.cfg.get("looks", {})
        util = self.cfg.get("util", {})
        mods = self.cfg.get("modifiers", {})
        if n in looks:
            v = looks[n]
            if v == "effect":
                cmd = self._effect_cmd(chan)
            else:
                r, g, b = v
                if self.cfg.get("velocity_to_bri"):
                    cmd = '{"col":[%d,%d,%d],"fx":0,"bri":%d}' % (r, g, b, round(vel / 127 * 255))
                else:
                    cmd = '{"col":[%d,%d,%d],"fx":0}' % (r, g, b)
            print("  ch->%s  look note %d -> %s" % (target or "all", note, cmd))
            send(cmd, target)
        elif n in util:
            send(util[n], target)
        elif n in mods:
            m = mods[n]
            if m == "flash":
                send("flash:blanc@300", target)     # engine handles the momentary flash
            elif m == "beat":
                st = not self.beat.get(chan, False)  # toggle per channel
                self.beat[chan] = st
                # beat:on/off -> the tempo layer (openlamp-midi beatsync) pulses the look.
                send("beat:on" if st else "beat:off", target)

    def on_cc(self, num, val, target, chan):
        kind = self.cfg["cc"].get(str(num))
        if kind == "bri":
            send('{"bri":%d}' % round(val / 127 * 255), target)
        elif kind == "cct":
            send('{"cct":%d}' % round(val / 127 * 255), target)
        elif kind in ("hue", "sat"):
            if kind == "hue":
                self.hue[chan] = val / 127.0
            else:
                self.sat[chan] = val / 127.0
            h = self.hue.get(chan, 0.0)
            s = self.sat.get(chan, 1.0)
            r, g, b = colorsys.hsv_to_rgb(h, s, 1.0)
            send('{"col":[%d,%d,%d]}' % (round(r*255), round(g*255), round(b*255)), target)
        elif kind in ("fx", "sx", "ix", "pal"):
            f = self.fx.setdefault(chan, {"fx": 0, "sx": 128, "ix": 128, "pal": 0})
            if kind == "fx":
                f["fx"] = round(val / 127 * (FALLBACK_FXCOUNT - 1))
            elif kind == "pal":
                f["pal"] = round(val / 127 * (FALLBACK_PALCOUNT - 1))
            else:
                f[kind] = round(val / 127 * 255)
            send('{"fx":%d,"sx":%d,"ix":%d,"pal":%d}' % (f["fx"], f["sx"], f["ix"], f["pal"]), target)

    def on_program(self, prog, target):
        progs = self.cfg.get("programs") or []
        if not progs:
            send('{"ps":%d}' % (prog + 1), target)    # wled-midi core: PC n -> preset n+1
            return
        if not (0 <= prog < len(progs)):
            return
        name = str(progs[prog])
        if name.startswith("snap:") or name.startswith("preset:"):
            cmd = name
        elif name.startswith("ps:"):
            cmd = "preset:" + name[3:]
        elif name.isdigit():
            cmd = "preset:" + name
        else:
            cmd = "scene:" + name
        send(cmd, target)

    def on_clock(self):
        if not self.cfg.get("clock_tempo"):
            return
        now = time.monotonic()
        self.clock_ticks += 1
        if self.clock_ticks % 24 != 0:                # 24 ticks = 1 beat
            return
        if self.clock_t0 is not None:
            bpm = round(60.0 / (now - self.clock_t0))
            if 20 <= bpm <= 300 and bpm != self.last_bpm:
                self.last_bpm = bpm
                tgt = self._target(self.cfg.get("clock_channel", 1)) or []
                send("tempo:%d" % max(20, min(120, bpm)), tgt)
        self.clock_t0 = now

    def dispatch(self, msg):
        status = msg[0]
        if status == 0xF8:                            # clock -> global tempo
            self.on_clock(); return
        typ, chan = status & 0xF0, (status & 0x0F) + 1
        target = self._target(chan)
        if target is None:
            return
        if typ == 0x90:
            self.on_note(msg[1], msg[2], chan, target)
        elif typ == 0xB0:
            self.on_cc(msg[1], msg[2], target, chan)
        elif typ == 0xC0:
            self.on_program(msg[1], target)


def main():
    cfg = load_cfg()
    br = Bridge(cfg)
    midi_in = rtmidi.MidiIn()
    midi_in.open_virtual_port(cfg["port_name"])
    midi_in.ignore_types(timing=False)                # keep MIDI clock (0xF8)

    def cb(event, data=None):
        msg, _ = event
        try:
            br.dispatch(msg)
        except Exception as e:
            print("  ! dispatch error:", e)

    midi_in.set_callback(cb)
    print("OpenLamp MIDI (wled-midi v0.2) — virtual port '%s' open." % cfg["port_name"])
    print("Route your DAW/controller MIDI to it. Ctrl-C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        midi_in.close_port()


if __name__ == "__main__":
    main()
