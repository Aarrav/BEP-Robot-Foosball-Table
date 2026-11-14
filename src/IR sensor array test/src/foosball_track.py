#!/usr/bin/env python3
"""
foosball_track.py -- read an evdev multitouch digitizer (IR touch frame),
visualise contacts live, and log raw samples with kernel timestamps.

Built for characterising an IR touch frame used as a foosball ball tracker.

Usage:
    python3 foosball_track.py                       # auto-detect
    python3 foosball_track.py --device /dev/input/by-id/usb-IrScreen_cc_0013-event-if00
    python3 foosball_track.py --width-mm 1200 --height-mm 680 --log run1.csv

Keys (with the window focused):
    c   clear trail
    l   start/stop CSV logging
    r   reset statistics
    q   quit

Requires: python3-evdev  (pip install evdev), tkinter (python3-tk).
Read access to /dev/input/event*: either run with sudo, or add yourself to
the 'input' group (sudo usermod -aG input $USER, then log out and back in).
"""

import argparse
import csv
import statistics
import sys
import threading
import time
from collections import defaultdict, deque
from queue import Empty, Queue

try:
    from evdev import InputDevice, ecodes, list_devices
except ImportError:
    sys.exit("evdev not installed.  pip install evdev")

import tkinter as tk

# ----------------------------------------------------------------------------
# device discovery
# ----------------------------------------------------------------------------

def find_device(explicit=None):
    if explicit:
        return InputDevice(explicit)
    candidates = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except PermissionError:
            continue
        caps = dev.capabilities()
        abs_codes = {c for c, _ in caps.get(ecodes.EV_ABS, [])}
        # a multitouch digitizer, not a mouse
        if ecodes.ABS_MT_POSITION_X in abs_codes or ecodes.ABS_X in abs_codes:
            if ecodes.EV_REL not in caps:
                candidates.append(dev)
    if not candidates:
        sys.exit("No absolute-pointer device found. Pass --device explicitly.")
    if len(candidates) > 1:
        print("Multiple candidates:")
        for d in candidates:
            print(f"  {d.path}  {d.name}")
        print(f"Using {candidates[0].path}. Override with --device.")
    return candidates[0]


def axis_range(dev, code):
    for c, info in dev.capabilities().get(ecodes.EV_ABS, []):
        if c == code:
            return info.min, info.max
    return None


# ----------------------------------------------------------------------------
# reader thread -- decodes the MT type-B protocol, one snapshot per SYN_REPORT
# ----------------------------------------------------------------------------

class Reader(threading.Thread):
    daemon = True

    def __init__(self, dev, out_q):
        super().__init__()
        self.dev = dev
        self.q = out_q
        self.stop_flag = threading.Event()

    def run(self):
        slot = 0
        slots = defaultdict(lambda: {"x": None, "y": None, "id": -1,
                                     "major": 0, "minor": 0})
        single = {"x": None, "y": None}   # fallback for ABS_X / ABS_Y only
        touch = 0
        dirty = False

        try:
            for e in self.dev.read_loop():
                if self.stop_flag.is_set():
                    return

                if e.type == ecodes.EV_ABS:
                    c = e.code
                    if c == ecodes.ABS_MT_SLOT:
                        slot = e.value
                    elif c == ecodes.ABS_MT_TRACKING_ID:
                        slots[slot]["id"] = e.value
                        if e.value == -1:                 # contact lifted
                            slots[slot]["x"] = slots[slot]["y"] = None
                    elif c == ecodes.ABS_MT_POSITION_X:
                        slots[slot]["x"] = e.value
                    elif c == ecodes.ABS_MT_POSITION_Y:
                        slots[slot]["y"] = e.value
                    elif c == ecodes.ABS_MT_TOUCH_MAJOR:
                        slots[slot]["major"] = e.value
                    elif c == ecodes.ABS_MT_TOUCH_MINOR:
                        slots[slot]["minor"] = e.value
                    elif c == ecodes.ABS_X:
                        single["x"] = e.value
                    elif c == ecodes.ABS_Y:
                        single["y"] = e.value
                    dirty = True

                elif e.type == ecodes.EV_KEY and e.code == ecodes.BTN_TOUCH:
                    touch = e.value
                    dirty = True

                elif e.type == ecodes.EV_SYN and e.code == ecodes.SYN_REPORT:
                    if not dirty:
                        continue
                    ts = e.sec + e.usec / 1e6      # kernel timestamp
                    live = {s: dict(v) for s, v in slots.items()
                            if v["x"] is not None and v["y"] is not None}
                    if not live and single["x"] is not None and touch:
                        live = {0: {"x": single["x"], "y": single["y"],
                                    "id": -2, "major": 0, "minor": 0}}
                    self.q.put((ts, live, touch))
                    dirty = False
        except OSError as exc:
            self.q.put(("ERROR", f"device went away: {exc}", None))


# ----------------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------------

class Stats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.intervals = deque(maxlen=3000)
        self.n = 0
        self.dropouts = 0
        self.max_gap = 0.0
        self.last_ts = None
        self.xs = set()
        self.ys = set()
        self.ids_seen = set()
        self.id_changes = 0
        self.max_contacts = 0
        self.major_nonzero = False
        self.t0 = None

    def update(self, ts, live):
        if self.t0 is None:
            self.t0 = ts
        if self.last_ts is not None:
            dt = ts - self.last_ts
            self.intervals.append(dt)
            if dt > self.max_gap:
                self.max_gap = dt
            med = self.median_dt()
            if med and dt > 2.5 * med:
                self.dropouts += 1
        self.last_ts = ts
        self.n += 1
        self.max_contacts = max(self.max_contacts, len(live))
        for s in live.values():
            self.xs.add(s["x"])
            self.ys.add(s["y"])
            if s["major"]:
                self.major_nonzero = True
            if s["id"] >= 0 and s["id"] not in self.ids_seen:
                self.ids_seen.add(s["id"])
                self.id_changes += 1

    def median_dt(self):
        return statistics.median(self.intervals) if self.intervals else None

    def rate(self):
        m = self.median_dt()
        return 1.0 / m if m else 0.0

    def jitter_ms(self):
        if len(self.intervals) < 10:
            return 0.0
        return (max(self.intervals) - min(self.intervals)) * 1000

    def quantum(self, vals):
        """Smallest non-zero step between distinct reported values."""
        if len(vals) < 3:
            return None
        s = sorted(vals)
        diffs = [b - a for a, b in zip(s, s[1:]) if b - a > 0]
        return min(diffs) if diffs else None


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------

PALETTE = ["#ff4b4b", "#4bc0ff", "#7bff4b", "#ffd24b", "#c56bff",
           "#4bffd2", "#ff8f4b", "#8f9bff", "#ff4bd2", "#b0b0b0"]


class App:
    def __init__(self, root, dev, args):
        self.root = root
        self.dev = dev
        self.args = args
        self.q = Queue()
        self.stats = Stats()
        self.trail = deque(maxlen=args.trail)
        self.logger = None
        self.logfile = None
        self.last_live = {}
        self.error = None

        xr = axis_range(dev, ecodes.ABS_MT_POSITION_X) or axis_range(dev, ecodes.ABS_X)
        yr = axis_range(dev, ecodes.ABS_MT_POSITION_Y) or axis_range(dev, ecodes.ABS_Y)
        self.xmin, self.xmax = xr
        self.ymin, self.ymax = yr

        # counts per mm, assuming the frame spans the given physical size
        self.kx = (self.xmax - self.xmin) / args.width_mm
        self.ky = (self.ymax - self.ymin) / args.height_mm

        # canvas keeps the *physical* aspect ratio, not the logical square one
        self.W = args.canvas_width
        self.H = int(self.W * args.height_mm / args.width_mm)

        root.title(f"{dev.name} -- {dev.path}")
        root.configure(bg="#111318")

        self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                bg="#0d3b1e", highlightthickness=0)
        self.canvas.pack(padx=10, pady=(10, 4))
        self.draw_pitch()

        self.info = tk.Label(root, text="", font=("DejaVu Sans Mono", 10),
                             justify="left", anchor="w", bg="#111318",
                             fg="#d8dbe0")
        self.info.pack(fill="x", padx=12, pady=(0, 4))

        self.hint = tk.Label(root,
                             text="c clear trail   l toggle log   r reset stats   q quit",
                             font=("DejaVu Sans", 9), bg="#111318", fg="#6b7280")
        self.hint.pack(fill="x", padx=12, pady=(0, 10))

        root.bind("<Key>", self.on_key)

        if args.log:
            self.start_log(args.log)

        self.reader = Reader(dev, self.q)
        self.reader.start()
        self.root.after(16, self.tick)

    # -- drawing -------------------------------------------------------------

    def draw_pitch(self):
        c = self.canvas
        c.create_rectangle(2, 2, self.W - 2, self.H - 2,
                           outline="#2f6b45", width=2)
        c.create_line(self.W / 2, 0, self.W / 2, self.H, fill="#2f6b45")
        c.create_oval(self.W / 2 - 40, self.H / 2 - 40,
                      self.W / 2 + 40, self.H / 2 + 40, outline="#2f6b45")
        if self.args.rods:
            for frac in (0.09, 0.22, 0.41, 0.59, 0.78, 0.91):
                x = frac * self.W
                c.create_line(x, 0, x, self.H, fill="#3d4450", dash=(4, 4))

    def to_px(self, x, y):
        fx = (x - self.xmin) / (self.xmax - self.xmin)
        fy = (y - self.ymin) / (self.ymax - self.ymin)
        if self.args.flip_x:
            fx = 1 - fx
        if self.args.flip_y:
            fy = 1 - fy
        if self.args.swap_xy:
            fx, fy = fy, fx
        return fx * self.W, fy * self.H

    def redraw(self):
        c = self.canvas
        c.delete("dyn")

        pts = list(self.trail)
        for i in range(1, len(pts)):
            (x0, y0, s0), (x1, y1, s1) = pts[i - 1], pts[i]
            if s0 != s1:
                continue
            px0, py0 = self.to_px(x0, y0)
            px1, py1 = self.to_px(x1, y1)
            shade = int(40 + 160 * i / len(pts))
            c.create_line(px0, py0, px1, py1, tags="dyn", width=2,
                          fill=f"#{shade:02x}{shade:02x}{shade:02x}")

        for slot, s in self.last_live.items():
            px, py = self.to_px(s["x"], s["y"])
            col = PALETTE[slot % len(PALETTE)]
            r = 9
            c.create_oval(px - r, py - r, px + r, py + r,
                          fill=col, outline="white", width=2, tags="dyn")
            c.create_text(px, py - 18, text=f"s{slot} id{s['id']}",
                          fill=col, font=("DejaVu Sans Mono", 8), tags="dyn")

    # -- stats panel ---------------------------------------------------------

    def update_info(self):
        st = self.stats
        qx = st.quantum(st.xs)
        qy = st.quantum(st.ys)
        elapsed = (st.last_ts - st.t0) if st.t0 and st.last_ts else 0.0

        if self.last_live:
            s = next(iter(self.last_live.values()))
            pos = (f"x={s['x']:5d} y={s['y']:5d}  "
                   f"({s['x'] / self.kx:6.1f}, {s['y'] / self.ky:6.1f}) mm  "
                   f"major={s['major']} minor={s['minor']}")
        else:
            pos = "-- no contact --"

        lines = [
            pos,
            f"reports {st.n:<7d} {st.rate():6.1f} Hz (median)   "
            f"jitter {st.jitter_ms():5.1f} ms   "
            f"max gap {st.max_gap * 1000:6.1f} ms   dropouts {st.dropouts}",
            f"quantum  x {qx if qx else '?'} counts "
            f"({qx / self.kx:.2f} mm)" if qx else "quantum  x ?",
            f"quantum  y {qy if qy else '?'} counts "
            f"({qy / self.ky:.2f} mm)" if qy else "quantum  y ?",
            f"contacts now {len(self.last_live)}  max seen {st.max_contacts}   "
            f"tracking ids used {st.id_changes}   "
            f"TOUCH_MAJOR populated: {'yes' if st.major_nonzero else 'NO'}",
            f"scale  {self.kx:.2f} counts/mm in x, {self.ky:.2f} in y   "
            f"elapsed {elapsed:6.1f} s   "
            f"logging: {self.logfile.name if self.logfile else 'off'}",
        ]
        if self.error:
            lines.append(f"!! {self.error}")
        self.info.config(text="\n".join(lines))

    # -- logging -------------------------------------------------------------

    def start_log(self, path):
        self.logfile = open(path, "w", newline="")
        self.logger = csv.writer(self.logfile)
        self.logger.writerow(["t_kernel", "t_rel", "slot", "tracking_id",
                              "x", "y", "x_mm", "y_mm", "major", "minor",
                              "n_contacts"])

    def stop_log(self):
        if self.logfile:
            self.logfile.close()
            self.logfile = None
            self.logger = None

    def log_frame(self, ts, live):
        if not self.logger:
            return
        t_rel = ts - self.stats.t0
        if not live:
            self.logger.writerow([f"{ts:.6f}", f"{t_rel:.6f}", "", "",
                                  "", "", "", "", "", "", 0])
            return
        for slot, s in live.items():
            self.logger.writerow([
                f"{ts:.6f}", f"{t_rel:.6f}", slot, s["id"], s["x"], s["y"],
                f"{s['x'] / self.kx:.2f}", f"{s['y'] / self.ky:.2f}",
                s["major"], s["minor"], len(live)])

    # -- main loop -----------------------------------------------------------

    def tick(self):
        got = False
        while True:
            try:
                item = self.q.get_nowait()
            except Empty:
                break
            if item[0] == "ERROR":
                self.error = item[1]
                break
            ts, live, _touch = item
            self.stats.update(ts, live)
            self.log_frame(ts, live)
            for slot, s in live.items():
                self.trail.append((s["x"], s["y"], slot))
            self.last_live = live
            got = True

        if got or self.error:
            self.redraw()
        self.update_info()
        self.root.after(16, self.tick)

    def on_key(self, event):
        k = event.keysym.lower()
        if k == "q":
            self.quit()
        elif k == "c":
            self.trail.clear()
            self.redraw()
        elif k == "r":
            self.stats.reset()
        elif k == "l":
            if self.logfile:
                self.stop_log()
            else:
                self.start_log(time.strftime("run_%Y%m%d_%H%M%S.csv"))

    def quit(self):
        self.reader.stop_flag.set()
        self.stop_log()
        st = self.stats
        print(f"\n{st.n} reports, median {st.rate():.1f} Hz, "
              f"max gap {st.max_gap * 1000:.1f} ms, dropouts {st.dropouts}")
        qx, qy = st.quantum(st.xs), st.quantum(st.ys)
        if qx:
            print(f"x quantum {qx} counts = {qx / self.kx:.2f} mm")
        if qy:
            print(f"y quantum {qy} counts = {qy / self.ky:.2f} mm")
        self.root.destroy()


# ----------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device", help="/dev/input/eventN or a by-id path")
    p.add_argument("--width-mm", type=float, default=1200.0,
                   help="physical span of the frame along x (default 1200)")
    p.add_argument("--height-mm", type=float, default=680.0,
                   help="physical span of the frame along y (default 680)")
    p.add_argument("--canvas-width", type=int, default=900)
    p.add_argument("--trail", type=int, default=400, help="trail length in samples")
    p.add_argument("--log", help="CSV path to start logging immediately")
    p.add_argument("--flip-x", action="store_true")
    p.add_argument("--flip-y", action="store_true")
    p.add_argument("--swap-xy", action="store_true")
    p.add_argument("--rods", action="store_true", help="draw rod guide lines")
    p.add_argument("--grab", action="store_true",
                   help="grab the device so it stops driving the system cursor")
    args = p.parse_args()

    dev = find_device(args.device)
    print(f"Using {dev.path}  ({dev.name})")

    if args.grab:
        try:
            dev.grab()
            print("Device grabbed -- cursor will not move.")
        except OSError as exc:
            print(f"Could not grab device: {exc}")

    root = tk.Tk()
    app = App(root, dev, args)
    root.protocol("WM_DELETE_WINDOW", app.quit)
    root.mainloop()


if __name__ == "__main__":
    main()
