#!/usr/bin/env python
"""XTEST cursor choreography for the showcase video.

Reads a scenario file (JSON lines) and performs smooth, eased pointer moves,
clicks, scrolls, and key presses on the X display — real X11 input events, so
Qt/Chromium react exactly as they would to a human hand.

Scenario ops (one JSON object per line):
  {"op": "move",   "x": 640, "y": 400, "dur": 0.8}     # eased glide
  {"op": "click"}                                        # press+release at cursor
  {"op": "click",  "x": 640, "y": 400, "dur": 0.7}      # move then click
  {"op": "dblclick"}
  {"op": "scroll", "dy": -3}                             # wheel: neg = down
  {"op": "key",    "keysym": "Escape"}
  {"op": "type",   "text": "hola"}
  {"op": "sleep",  "t": 1.2}
  {"op": "cmd",    "line": "show"}                       # append to .context/cmd
  {"op": "mark",   "label": "reviewer-start"}            # timestamp log line

Coordinates are display-global. Run with the venv python (has python-xlib).
"""
import json
import math
import os
import sys
import time

from Xlib import X, XK, display
from Xlib.ext import xtest

DISP = display.Display(os.environ.get("DISPLAY", ":99"))
ROOT = DISP.screen().root

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD_FILE = os.path.join(REPO, ".context", "cmd")


def _flush():
    DISP.sync()


def cur_pos():
    q = ROOT.query_pointer()
    return q.root_x, q.root_y


def warp(x, y):
    ROOT.warp_pointer(int(x), int(y))
    _flush()


def ease(t):
    # easeInOutCubic — reads as a confident human glide
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


def move_to(x2, y2, dur=0.6, wobble=2.0):
    x1, y1 = cur_pos()
    dist = math.hypot(x2 - x1, y2 - y1)
    if dist < 2:
        warp(x2, y2)
        return
    steps = max(2, int(dur * 120))
    # a gentle perpendicular bow so long moves arc instead of beelining
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    px, py = -(y2 - y1) / (dist or 1), (x2 - x1) / (dist or 1)
    bow = min(dist * 0.08, 28.0)
    cx, cy = mx + px * bow, my + py * bow
    t0 = time.perf_counter()
    for i in range(1, steps + 1):
        t = ease(i / steps)
        # quadratic bezier through the bowed midpoint
        a, b = (1 - t) * (1 - t), 2 * (1 - t) * t
        c = t * t
        x = a * x1 + b * cx + c * x2
        y = a * y1 + b * cy + c * y2
        warp(x, y)
        target = t0 + (i / steps) * dur
        delay = target - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
    warp(x2, y2)


def click(button=1):
    xtest.fake_input(DISP, X.ButtonPress, button)
    _flush()
    time.sleep(0.07)
    xtest.fake_input(DISP, X.ButtonRelease, button)
    _flush()


def scroll(dy):
    btn = 5 if dy < 0 else 4
    for _ in range(abs(int(dy))):
        xtest.fake_input(DISP, X.ButtonPress, btn)
        xtest.fake_input(DISP, X.ButtonRelease, btn)
        _flush()
        time.sleep(0.06)


def keysym_to_keycode(name):
    ks = XK.string_to_keysym(name)
    return DISP.keysym_to_keycode(ks)


def key(name, mods=()):
    mod_codes = [keysym_to_keycode(m) for m in mods]
    for mc in mod_codes:
        xtest.fake_input(DISP, X.KeyPress, mc)
    kc = keysym_to_keycode(name)
    xtest.fake_input(DISP, X.KeyPress, kc)
    _flush()
    time.sleep(0.05)
    xtest.fake_input(DISP, X.KeyRelease, kc)
    for mc in reversed(mod_codes):
        xtest.fake_input(DISP, X.KeyRelease, mc)
    _flush()


SHIFTED = {c: n for c, n in zip('!@#$%^&*()_+{}|:"<>?~',
    ["exclam", "at", "numbersign", "dollar", "percent", "asciicircum",
     "ampersand", "asterisk", "parenleft", "parenright", "underscore",
     "plus", "braceleft", "braceright", "bar", "colon", "quotedbl",
     "less", "greater", "question", "asciitilde"])}
PLAIN = {" ": "space", "-": "minus", "=": "equal", "[": "bracketleft",
         "]": "bracketright", ";": "semicolon", "'": "apostrophe",
         ",": "comma", ".": "period", "/": "slash", "\\": "backslash",
         "`": "grave", "\n": "Return"}


def type_text(text, cps=14.0):
    for ch in text:
        if ch.isupper() or ch in SHIFTED:
            name = SHIFTED.get(ch, ch.lower())
            key(name, mods=("Shift_L",))
        else:
            key(PLAIN.get(ch, ch))
        time.sleep(max(0.02, 1.0 / cps + (hash(ch) % 7 - 3) * 0.004))


def run(path):
    with open(path) as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            o = json.loads(raw)
            op = o["op"]
            if op == "move":
                move_to(o["x"], o["y"], o.get("dur", 0.6))
            elif op == "click":
                if "x" in o:
                    move_to(o["x"], o["y"], o.get("dur", 0.6))
                    time.sleep(o.get("settle", 0.12))
                click(o.get("button", 1))
            elif op == "dblclick":
                if "x" in o:
                    move_to(o["x"], o["y"], o.get("dur", 0.6))
                    time.sleep(0.1)
                click()
                time.sleep(0.09)
                click()
            elif op == "scroll":
                scroll(o.get("dy", -2))
            elif op == "key":
                key(o["keysym"], tuple(o.get("mods", ())))
            elif op == "type":
                type_text(o["text"], o.get("cps", 14.0))
            elif op == "sleep":
                time.sleep(o["t"])
            elif op == "cmd":
                # Overwrite, never append: the addon watcher re-dispatches
                # every line in the file whenever its mtime changes.
                with open(CMD_FILE, "w") as c:
                    c.write(o["line"] + "\n")
            elif op == "mark":
                print(f"[{time.perf_counter():.3f}] {o.get('label','')}",
                      flush=True)
            else:
                raise SystemExit(f"unknown op: {op}")


if __name__ == "__main__":
    run(sys.argv[1])
