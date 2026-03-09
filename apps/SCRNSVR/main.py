#!/usr/bin/env python3
"""
Screensaver Manager v2.1.0
──────────────────────────
Single consolidated menu:
  SAVE & START  (top)
  EXIT
  ── Settings ──
  Enabled, Idle Timeout, Cycle Every, Order
  ── App List ──
  [X] appname  (auto-populated, toggle on/off)
  SAVE & START  (bottom)
"""
import os, sys, time, json, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from input import TouchScreen, GpioKeys, RotaryEncoder

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320
LW, LH = 320, 172
BG     = (10, 10, 18)
PANEL  = (22, 24, 38)
ACCENT = (0, 200, 255)
TEXT   = (235, 238, 255)
DIM    = (90, 95, 120)
SEL    = (35, 65, 140)
OK     = (0, 210, 110)
WARN   = (255, 185, 0)
ERR    = (220, 60, 60)

_FP = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def _f(sz, b=False):
    try: return ImageFont.truetype(_FB if b else _FP, sz)
    except: return ImageFont.load_default()

FN, FS, FM, FT = _f(9), _f(11), _f(13), _f(15, True)

class FB:
    def __init__(self):
        import mmap
        self.fd  = os.open('/dev/fb0', os.O_RDWR)
        self.mm  = mmap.mmap(self.fd, PW*PH*2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self.arr = np.frombuffer(self.mm, dtype=np.uint16).reshape(PH, PW)
    def show(self, img):
        p = img.rotate(90, expand=True)
        a = np.array(p, dtype=np.uint16)
        self.arr[:,:] = (a[:,:,0]>>3<<11)|(a[:,:,1]>>2<<5)|(a[:,:,2]>>3)
    def close(self):
        self.mm.close(); os.close(self.fd)

def rrect(d, x0, y0, x1, y1, fill=None, outline=None, r=4):
    d.rounded_rectangle([x0,y0,x1,y1], radius=r, fill=fill, outline=outline)

def centered(d, text, cx, cy, font, color):
    bb = d.textbbox((0,0), text, font=font)
    d.text((cx-(bb[2]-bb[0])//2, cy-(bb[3]-bb[1])//2), text, font=font, fill=color)

# ── Config ───────────────────────────────────────────────────────────────────
CFG_PATH    = "/etc/kvm/screensaver.json"
SKIP_APPS   = {'screensaver', 'readme.md', 'SCRNSVR'}

def load_cfg():
    try:
        with open(CFG_PATH) as f: return json.load(f)
    except:
        return {"enabled": True, "idle_timeout": 60, "cycle_interval": 30,
                "order": "cycle", "apps": {}}

def save_cfg(c):
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    with open(CFG_PATH, 'w') as f: json.dump(c, f, indent=2)

def get_apps():
    try:
        return sorted([d for d in os.listdir("/userapp")
                       if os.path.isdir(os.path.join("/userapp", d))
                       and d.lower() not in {s.lower() for s in SKIP_APPS}])
    except: return []

def start_screensaver():
    try:
        subprocess.run(["systemctl", "restart", "screensaver"], timeout=5)
    except: pass

# ── Menu Builder ─────────────────────────────────────────────────────────────
def build_menu(cfg, apps):
    items = []
    items.append({"type": "action",   "label": "SAVE & START",  "id": "save_start"})
    items.append({"type": "action",   "label": "EXIT",           "id": "exit"})
    items.append({"type": "divider",  "label": "── Settings ──"})
    items.append({"type": "toggle",   "label": "Enabled",        "key": "enabled"})
    items.append({"type": "cycle",    "label": "Idle Timeout",   "key": "idle_timeout",
                  "opts": [30, 60, 120, 300, 600, 0],
                  "fmt": lambda v: f"{v}s" if v else "Never"})
    items.append({"type": "cycle",    "label": "Cycle Every",    "key": "cycle_interval",
                  "opts": [10, 30, 60, 120, 300],
                  "fmt": lambda v: f"{v}s"})
    items.append({"type": "cycle",    "label": "Order",          "key": "order",
                  "opts": ["cycle", "random"],
                  "fmt": lambda v: v.upper()})
    items.append({"type": "divider",  "label": "── App List ──"})
    for app in apps:
        items.append({"type": "app",  "label": app, "app": app})
    items.append({"type": "action",   "label": "SAVE & START",  "id": "save_start"})
    return items

# ── App ───────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.fb    = FB()
        self.cfg   = load_cfg()
        self.apps  = get_apps()
        self.items = build_menu(self.cfg, self.apps)
        self.sel   = 0
        self.scroll= 0
        self.running = True
        self.dirty = True
        self.status_msg = ""
        self.status_timer = 0

    def set_status(self, msg, ok=True):
        self.status_msg   = msg
        self.status_timer = 40
        self.dirty = True

    def on_press(self):
        item = self.items[self.sel]
        t = item["type"]
        if t == "divider": return

        if t == "action":
            if item["id"] == "save_start":
                save_cfg(self.cfg)
                start_screensaver()
                self.set_status("Saved & Started!", ok=True)
            elif item["id"] == "exit":
                self.running = False

        elif t == "toggle":
            self.cfg[item["key"]] = not self.cfg[item["key"]]

        elif t == "cycle":
            opts = item["opts"]
            cur  = self.cfg.get(item["key"], opts[0])
            try:   idx = opts.index(cur)
            except: idx = 0
            self.cfg[item["key"]] = opts[(idx+1) % len(opts)]

        elif t == "app":
            app = item["app"]
            self.cfg["apps"][app] = not self.cfg["apps"].get(app, True)

        self.dirty = True

    def draw(self):
        img = Image.new('RGB', (LW, LH), BG)
        d   = ImageDraw.Draw(img)

        # Header bar
        d.rectangle([0, 0, LW, 22], fill=PANEL)
        centered(d, "SCREENSAVER MANAGER", LW//2, 11, FM, ACCENT)
        d.line([0, 22, LW, 22], fill=(40,45,70), width=1)

        # Visible rows
        ROW_H   = 22
        visible = (LH - 34) // ROW_H
        start   = self.scroll

        for i in range(visible):
            idx = i + start
            if idx >= len(self.items): break
            item = self.items[idx]
            y    = 24 + i * ROW_H
            sel  = (idx == self.sel)
            t    = item["type"]

            if t == "divider":
                d.line([8, y+ROW_H//2, LW-8, y+ROW_H//2], fill=(40,50,80), width=1)
                centered(d, item["label"], LW//2, y+ROW_H//2, FN, DIM)
                continue

            if sel:
                rrect(d, 4, y+1, LW-4, y+ROW_H-1, fill=SEL, r=3)

            if t == "action":
                is_save = (item["id"] == "save_start")
                col = OK if is_save else (ERR if item["id"]=="exit" else TEXT)
                centered(d, item["label"], LW//2, y+ROW_H//2, FM, col if not sel else WHITE)

            elif t == "toggle":
                val = self.cfg.get(item["key"], False)
                d.text((10, y+4), item["label"], font=FS, fill=TEXT)
                tag = "ON" if val else "OFF"
                col = OK if val else ERR
                d.text((LW-42, y+4), tag, font=FS, fill=col if not sel else TEXT)

            elif t == "cycle":
                val = self.cfg.get(item["key"])
                d.text((10, y+4), item["label"], font=FS, fill=TEXT)
                try:   label = item["fmt"](val)
                except: label = str(val)
                d.text((LW-70, y+4), label, font=FS, fill=ACCENT if not sel else TEXT)

            elif t == "app":
                app = item["app"]
                en  = self.cfg["apps"].get(app, True)
                box_col = OK if en else DIM
                rrect(d, 10, y+4, 24, y+ROW_H-4, fill=box_col if en else None, outline=box_col, r=2)
                if en: centered(d, "X", 17, y+ROW_H//2, FN, BG)
                d.text((32, y+4), app, font=FS, fill=TEXT)

        # Status / Footer
        y_foot = LH - 12
        if self.status_timer > 0:
            self.status_timer -= 1
            centered(d, self.status_msg, LW//2, y_foot, FN, OK)
        else:
            d.text((8, y_foot), "Rotate:scroll  Press:select  Long:exit", font=FN, fill=DIM)

        self.fb.show(img)
        self.dirty = False

    def run(self):
        ROW_H   = 22
        visible = (LH - 34) // ROW_H

        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                r = rotary.read_event(0)
                if r:
                    self.sel = (self.sel + r) % len(self.items)
                    while self.items[self.sel]["type"] == "divider":
                        self.sel = (self.sel + r) % len(self.items)
                    if self.sel < self.scroll: self.scroll = self.sel
                    elif self.sel >= self.scroll + visible: self.scroll = self.sel - visible + 1
                    self.dirty = True

                k = keys.read_event(0)
                if k:
                    if k[0] == 'key_long_press': self.running = False
                    elif k[0] == 'key_release' and k[1] == 'ENTER': self.on_press()
                
                t = touch.read_event(0)
                if t and t[0] == 'touch_down':
                    tx, ty = TouchScreen.map_coords_270(t[1], t[2])
                    if ty < 24: pass # header
                    else:
                        row = (ty - 24) // ROW_H
                        if 0 <= row < visible:
                            idx = row + self.scroll
                            if idx < len(self.items) and self.items[idx]["type"] != "divider":
                                self.sel = idx
                                self.on_press()
                    self.dirty = True

                if self.status_timer > 0: self.dirty = True
                if self.dirty: self.draw()
                time.sleep(0.05)
        self.fb.close()

if __name__ == "__main__":
    App().run()
