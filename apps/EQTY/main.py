#!/usr/bin/env python3
"""
EQTY v1.1.0: Real-time Stock Tracker for NanoKVM.
────────────────────────────────────────────────
Fixes: Fast numpy FB, standard long-press exit, improved touch.
"""
import os, sys, time, json, math, threading, mmap
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from input import TouchScreen, GpioKeys, RotaryEncoder

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320
LW, LH = 320, 172
BG     = (8, 12, 24)

class FB:
    def __init__(self):
        sz = PW * PH * 2
        self.fd = os.open('/dev/fb0', os.O_RDWR)
        self.mm = mmap.mmap(self.fd, sz, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self.arr = np.frombuffer(self.mm, dtype=np.uint16).reshape(PH, PW)
    def show(self, img: Image.Image):
        p = img.rotate(90, expand=True)
        a = np.array(p, dtype=np.uint16)
        self.arr[:,:] = (a[:,:,0]>>3<<11)|(a[:,:,1]>>2<<5)|(a[:,:,2]>>3)
    def close(self):
        self.mm.close(); os.close(self.fd)

# ── Config & Constants ───────────────────────────────────────────────────────
CONFIG_FILE     = '/etc/kvm/stocks_config.json'
DEFAULT_SYMBOLS = ['PSLV', 'CL=F', 'CRF', 'LEAV', 'INES']
ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ.='

COLOR_WHITE  = (230, 230, 230)
COLOR_CYAN   = (0, 200, 220)
COLOR_GREEN  = (60, 200, 80)
COLOR_RED    = (220, 60, 60)
COLOR_GRAY   = (120, 120, 140)
COLOR_SEL    = (50, 80, 160)
COLOR_DIM    = (50, 55, 70)

_FP = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def _f(sz, b=False):
    try: return ImageFont.truetype(_FB if b else _FP, sz)
    except: return ImageFont.load_default()

F_SM, F_MD, F_LG = _f(10), _f(12), _f(17, True)

# ── Utils ────────────────────────────────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_FILE) as f: return json.load(f).get('symbols', DEFAULT_SYMBOLS)
    except: return list(DEFAULT_SYMBOLS)

def save_config(syms):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f: json.dump({'symbols': syms}, f)
    except: pass

def fetch_price(symbol):
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        d = t.history(period="1d", interval="1m")
        if not d.empty:
            cur = d['Close'].iloc[-1]
            opn = d['Open'].iloc[0]
            pct = (cur - opn) / opn * 100
            return cur, pct, d['Close'].tolist()
    except: pass
    return None, None, None

# ── App ──────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.fb = FB()
        self.symbols = load_config()
        self.idx = 0
        self.data = {} # sym: (price, pct, history)
        self.running = True
        self.editing = False
        self._dirty = True
        self._bg_fetch()

    def _bg_fetch(self):
        def _run():
            while self.running:
                for s in self.symbols:
                    p, pct, hist = fetch_price(s)
                    if p: self.data[s] = (p, pct, hist)
                    self._dirty = True
                time.sleep(60)
        threading.Thread(target=_run, daemon=True).start()

    def draw(self):
        img = Image.new('RGB', (LW, LH), BG)
        d = ImageDraw.Draw(img)
        
        sym = self.symbols[self.idx]
        p, pct, hist = self.data.get(sym, (None, None, None))
        
        # Header
        d.rectangle([0, 0, LW, 30], fill=(12, 18, 40))
        d.text((8, 5), sym, font=F_LG, fill=COLOR_CYAN)
        if p:
            col = COLOR_GREEN if pct >= 0 else COLOR_RED
            d.text((100, 5), f"${p:.2f}", font=F_LG, fill=WHITE)
            d.text((200, 8), f"{pct:+.2f}%", font=F_MD, fill=col)
        else:
            d.text((100, 8), "Loading...", font=F_MD, fill=COLOR_GRAY)

        # Sparkline
        if hist:
            ax, ay, aw, ah = 10, 40, LW-20, LH-60
            pmin, pmax = min(hist), max(hist)
            prng = (pmax - pmin) or 1
            pts = []
            for i, val in enumerate(hist):
                px = ax + (i / len(hist)) * aw
                py = ay + ah - ((val - pmin) / prng) * ah
                pts.append((px, py))
            d.line(pts, fill=COLOR_CYAN, width=2)

        # Footer
        d.rectangle([0, LH-20, LW, LH], fill=(12, 18, 40))
        d.text((8, LH-15), "Rotate: Switch | Long-press: Exit", font=F_SM, fill=COLOR_GRAY)
        
        self.fb.show(img)
        self._dirty = False

    def run(self):
        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                r = rotary.read_event(0)
                if r: self.idx = (self.idx + r) % len(self.symbols); self._dirty = True
                
                kev = keys.read_event(0)
                if kev:
                    if kev[0] == 'key_long_press': self.running = False
                    elif kev[0] == 'key_release' and kev[1] == 'ENTER': 
                        # Simple force refresh
                        self.data = {}; self._dirty = True
                
                tev = touch.read_event(0)
                if tev and tev[0] == 'touch_down':
                    self.idx = (self.idx + 1) % len(self.symbols); self._dirty = True

                if self._dirty: self.draw()
                time.sleep(0.05)
        self.fb.close()

if __name__ == "__main__":
    App().run()
