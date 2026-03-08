#!/usr/bin/env python3
"""
Screensaver Manager UI
───────────────────────
Manage idle timeouts, cycling, and app selection.
"""
import os, sys, time, json, threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from input import TouchScreen, GpioKeys, RotaryEncoder

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320
LW, LH = 320, 172
BG     = (10, 10, 15)
PANEL  = (25, 25, 35)
ACCENT = (0, 200, 255)
TEXT   = (240, 240, 240)
DIM    = (100, 100, 110)
SEL    = (40, 70, 140)
OK     = (0, 210, 110)

_FP = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def _f(sz, b=False):
    try: return ImageFont.truetype(_FB if b else _FP, sz)
    except: return ImageFont.load_default()

FN, FS, FM = _f(10), _f(12), _f(14)
FT, FH = _f(16, True), _f(20, True)

class FB:
    def __init__(self):
        import mmap
        self.fd = os.open('/dev/fb0', os.O_RDWR)
        self.mm = mmap.mmap(self.fd, PW*PH*2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self.arr = np.frombuffer(self.mm, dtype=np.uint16).reshape(PH, PW)
    def show(self, img):
        p = img.rotate(90, expand=True)
        a = np.array(p, dtype=np.uint16)
        self.arr[:,:] = (a[:,:,0]>>3<<11)|(a[:,:,1]>>2<<5)|(a[:,:,2]>>3)
    def close(self):
        self.mm.close(); os.close(self.fd)

def rrect(d, x0, y0, x1, y1, fill=None, outline=None, r=4):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline)

def centered(d, text, cx, cy, font, color):
    bb = d.textbbox((0, 0), text, font=font)
    d.text((cx - (bb[2]-bb[0])//2, cy - (bb[3]-bb[1])//2), text, font=font, fill=color)

# ── Config ───────────────────────────────────────────────────────────────────
CFG_PATH = "/etc/kvm/screensaver.json"
STATUS_PATH = "/tmp/screensaver_status.json"

def load_cfg():
    try:
        with open(CFG_PATH) as f: return json.load(f)
    except: return {"enabled": True, "idle_timeout": 60, "cycle_interval": 30, "order": "cycle", "apps": {}}

def save_cfg(c):
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    with open(CFG_PATH, 'w') as f: json.dump(c, f, indent=2)

def get_status():
    try:
        with open(STATUS_PATH) as f: return json.load(f)
    except: return {}

# ── App ──────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.fb = FB()
        self.cfg = load_cfg()
        self.page = 0  # 0=Apps, 1=Timers, 2=Options, 3=Status
        self.sel = 0
        self.running = True
        self.dirty = True
        self.apps = sorted([d for d in os.listdir("/userapp") if os.path.isdir(os.path.join("/userapp", d)) and d not in ('screensaver','readme.md')])

    def on_rotate(self, delta):
        if self.page == 0: self.sel = (self.sel + delta) % len(self.apps)
        elif self.page == 1: self.sel = (self.sel + delta) % 2
        elif self.page == 2: self.sel = (self.sel + delta) % 3
        self.dirty = True

    def on_press(self):
        if self.page == 0:
            app = self.apps[self.sel]
            cur = self.cfg['apps'].get(app, True)
            self.cfg['apps'][app] = not cur
            save_cfg(self.cfg)
        elif self.page == 1:
            if self.sel == 0: # timeout
                opts = [30, 60, 120, 300, 600, 0]
                idx = opts.index(self.cfg['idle_timeout'])
                self.cfg['idle_timeout'] = opts[(idx+1)%len(opts)]
            else: # cycle
                opts = [10, 30, 60, 120, 300]
                idx = opts.index(self.cfg['cycle_interval'])
                self.cfg['cycle_interval'] = opts[(idx+1)%len(opts)]
            save_cfg(self.cfg)
        elif self.page == 2:
            if self.sel == 0: self.cfg['enabled'] = not self.cfg['enabled']
            elif self.sel == 1: self.cfg['order'] = "random" if self.cfg['order'] == "cycle" else "cycle"
            elif self.sel == 2: # Restart daemon
                os.system("systemctl restart screensaver")
            save_cfg(self.cfg)
        self.dirty = True

    def draw(self):
        img = Image.new('RGB', (LW, LH), BG)
        d = ImageDraw.Draw(img)
        # Tabs
        tabs = ["Apps", "Time", "Opt", "Stat"]
        tw = LW // 4
        for i, t in enumerate(tabs):
            rrect(d, i*tw+2, 2, (i+1)*tw-2, 22, fill=SEL if self.page == i else PANEL)
            centered(d, t, i*tw+tw//2, 12, FS, TEXT)
        
        y0 = 28
        if self.page == 0: # Apps list
            start = max(0, self.sel - 2)
            for i, app in enumerate(self.apps[start:start+5]):
                idx = i + start
                y = y0 + i*24
                is_sel = (idx == self.sel)
                if is_sel: d.rectangle([4, y, LW-4, y+22], fill=SEL)
                enabled = self.cfg['apps'].get(app, True)
                d.text((10, y+4), f"[{'X' if enabled else ' '}] {app}", font=FM, fill=TEXT)
        
        elif self.page == 1: # Timers
            T = ["Idle Timeout", "Cycle Every"]
            V = [f"{self.cfg['idle_timeout']}s" if self.cfg['idle_timeout'] else "Never", f"{self.cfg['cycle_interval']}s"]
            for i in range(2):
                y = y0 + i*40
                rrect(d, 8, y, LW-8, y+34, fill=SEL if self.sel == i else PANEL)
                d.text((16, y+8), T[i], font=FM, fill=TEXT)
                d.text((LW-70, y+8), V[i], font=FM, fill=ACCENT)

        elif self.page == 2: # Options
            opts = [("Enabled", self.cfg['enabled']), ("Order", self.cfg['order']), ("Action", "RESTART")]
            for i, (l, v) in enumerate(opts):
                y = y0 + i*36
                rrect(d, 8, y, LW-8, y+30, fill=SEL if self.sel == i else PANEL)
                d.text((16, y+6), l, font=FM, fill=TEXT)
                d.text((LW-100, y+6), str(v).upper(), font=FM, fill=ACCENT)

        elif self.page == 3: # Status
            st = get_status()
            lines = [
                f"Daemon: {'Running' if st else 'Stopped'}",
                f"Current: {st.get('current', 'None')}",
                f"Idle: {st.get('idle_seconds', 0)}s",
                f"Next Switch: {st.get('next_switch_in', 0)}s"
            ]
            for i, l in enumerate(lines):
                d.text((12, y0 + i*22), l, font=FM, fill=OK if i==0 else TEXT)

        self.fb.show(img)
        self.dirty = False

    def run(self):
        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                r = rotary.read_event(0)
                if r: self.on_rotate(r)
                k = keys.read_event(0)
                if k and k[0] == 'key_release' and k[1] == 'ENTER': self.on_press()
                elif k and k[0] == 'key_long_press': self.running = False
                t = touch.read_event(0)
                if t and t[0] == 'touch_down':
                    x, y = TouchScreen.map_coords_270(t[1], t[2])
                    if y < 24: self.page = x // (LW//4); self.sel = 0; self.dirty = True
                if self.dirty: self.draw()
                time.sleep(0.05)

if __name__ == "__main__":
    App().run()
