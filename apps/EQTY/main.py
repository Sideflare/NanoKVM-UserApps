#!/usr/bin/env python3
"""
EQTY v2.1.0: Real-time Stock Tracker for NanoKVM.
──────────────────────────────────────────────────
Top nav: < | SYM1..5 | gear  (all scroll-wheel selectable)
Chart: red/green candlesticks with grey after-hours shading.
Settings: edit symbols.
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

# ── Config & Constants ────────────────────────────────────────────────────────
CONFIG_FILE     = '/etc/kvm/stocks_config.json'
DEFAULT_SYMBOLS = ['PSLV', 'CL=F', 'CRF', 'LEAV', 'INES']
ALPHABET   = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ.=^- '
TIMEFRAMES = [
    ("1D",  "1d",  "5m"),
    ("5D",  "5d",  "30m"),
    ("1M",  "1mo", "1d"),
    ("3M",  "3mo", "1wk"),
]

COLOR_WHITE  = (230, 230, 230)
COLOR_CYAN   = (0, 200, 220)
COLOR_GREEN  = (0, 255, 100)
COLOR_RED    = (255, 50, 50)
COLOR_GRAY   = (110, 115, 140)
COLOR_AH     = (40, 45, 65)    # after-hours background shade
COLOR_SEL    = (50, 80, 160)
COLOR_DIM    = (60, 65, 90)
COLOR_PANEL  = (15, 20, 40)
COLOR_ACCENT = (0, 220, 255)

_FP = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def _f(sz, b=False):
    try: return ImageFont.truetype(_FB if b else _FP, sz)
    except: return ImageFont.load_default()

F_SM  = _f(9)
F_MD  = _f(11)
F_LG  = _f(14, True)
F_SYM = _f(10, True)

def rrect(d, x0, y0, x1, y1, fill=None, outline=None, r=3):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline)

def centered(d, text, cx, cy, font, color):
    bb = d.textbbox((0,0), text, font=font)
    d.text((cx-(bb[2]-bb[0])//2, cy-(bb[3]-bb[1])//2), text, font=font, fill=color)

# ── Utils ─────────────────────────────────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_FILE) as f: return json.load(f).get('symbols', list(DEFAULT_SYMBOLS))
    except: return list(DEFAULT_SYMBOLS)

def save_config(syms):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f: json.dump({'symbols': syms}, f)
    except: pass

def is_extended_hours(ts):
    """Return True if timestamp is outside regular market hours (9:30-16:00 ET)."""
    try:
        import pytz
        et = ts.astimezone(pytz.timezone('America/New_York'))
        h = et.hour + et.minute / 60.0
        return h < 9.5 or h >= 16.0
    except:
        return False

def fetch_ohlc(symbol, period="1d", interval="5m"):
    """Fetch OHLC candle data."""
    try:
        import yfinance as yf
        t  = yf.Ticker(symbol)
        prepost = (period == "1d")
        df = t.history(period=period, interval=interval, prepost=prepost)
        if not df.empty:
            cur = df['Close'].iloc[-1]
            opn = df['Open'].iloc[0]
            pct = (cur - opn) / opn * 100 if opn else 0
            return cur, pct, df
    except: pass
    return None, None, None

# ── Pages ─────────────────────────────────────────────────────────────────────
PG_CHART    = 0
PG_SETTINGS = 1

# ── App ───────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.fb      = FB()
        self.symbols = load_config()
        # Ensure exactly 5 symbols
        while len(self.symbols) < 5: self.symbols.append('SPY')
        self.symbols = self.symbols[:5]

        self.page     = PG_CHART
        self.focus    = 1          # 0=back, 1-5=symbol, 6=gear
        self.data     = {}         # sym -> (price, pct, df)
        self.running  = True
        self._dirty   = True
        self.tf_idx   = 0          # current timeframe index

        # Settings state: -1=SAVE(top), 0-4=sym slots, 5=SAVE(bottom)
        self.set_sym_idx  = 0
        self.set_char_idx = 0
        self.set_editing  = False

        self._bg_fetch()

    @property
    def sym_idx(self):
        """Active symbol index (0-based)."""
        return max(0, self.focus - 1) if 1 <= self.focus <= 5 else 0

    @property
    def active_sym(self):
        return self.symbols[self.sym_idx]

    def _bg_fetch(self):
        _, period, interval = TIMEFRAMES[self.tf_idx]
        def _run():
            while self.running:
                _, p2, i2 = TIMEFRAMES[self.tf_idx]
                for s in self.symbols:
                    pr, pct, df = fetch_ohlc(s, p2, i2)
                    if pr is not None: self.data[s] = (pr, pct, df)
                    self._dirty = True
                time.sleep(60)
        threading.Thread(target=_run, daemon=True).start()

    # ── Drawing ───────────────────────────────────────────────────────────────
    def draw(self):
        img = Image.new('RGB', (LW, LH), BG)
        d   = ImageDraw.Draw(img)
        if self.page == PG_CHART:    self._draw_chart(d)
        elif self.page == PG_SETTINGS: self._draw_settings(d)
        self.fb.show(img)
        self._dirty = False

    def _draw_nav(self, d):
        """Top nav bar: < | SYM1 | SYM2 | SYM3 | SYM4 | SYM5 | gear"""
        ITEMS  = 7   # back + 5 syms + gear
        iw     = LW // ITEMS
        d.rectangle([0, 0, LW, 24], fill=COLOR_PANEL)

        # Back arrow
        sel = (self.focus == 0)
        if sel: rrect(d, 2, 2, iw-2, 22, fill=COLOR_SEL)
        centered(d, "\u2190", iw//2, 12, F_LG, COLOR_ACCENT if sel else COLOR_DIM)

        # Symbol tabs
        for i, sym in enumerate(self.symbols):
            sel = (self.focus == i+1)
            x0, x1 = (i+1)*iw+1, (i+2)*iw-1
            if sel: rrect(d, x0, 2, x1, 22, fill=COLOR_SEL)
            label = sym.split('=')[0][:4]  # trim for display
            centered(d, label, (x0+x1)//2, 12, F_SYM, COLOR_CYAN if sel else COLOR_GRAY)

        # Gear icon (Settings)
        sel = (self.focus == 6)
        x0 = 6*iw+1
        if sel: rrect(d, x0, 2, LW-2, 22, fill=COLOR_SEL)
        # Use a proper gear character or a stylized icon
        centered(d, "\u2699", (x0+LW)//2, 12, F_LG, COLOR_ACCENT if sel else COLOR_DIM)

        d.line([0, 24, LW, 24], fill=COLOR_DIM, width=1)

    def _draw_chart(self, d):
        self._draw_nav(d)

        sym         = self.active_sym
        p, pct, df  = self.data.get(sym, (None, None, None))

        # Price header
        py = 28
        tf_label = TIMEFRAMES[self.tf_idx][0]
        if p is not None:
            col = COLOR_GREEN if pct >= 0 else COLOR_RED
            d.text((8, py), sym, font=F_LG, fill=COLOR_CYAN)
            d.text((8, py+16), tf_label, font=F_SM, fill=COLOR_GRAY)
            price_str = f"${p:.2f}"
            pct_str   = f"{pct:+.2f}%"
            bb = d.textbbox((0,0), price_str, font=F_LG)
            pw = bb[2]-bb[0]
            d.text((LW//2 - pw//2, py), price_str, font=F_LG, fill=COLOR_WHITE)
            d.text((LW-65, py+2), pct_str, font=F_MD, fill=col)
        else:
            d.text((8, py+2), sym, font=F_LG, fill=COLOR_CYAN)
            d.text((8, py+16), tf_label, font=F_SM, fill=COLOR_GRAY)
            centered(d, "Loading...", LW//2, py+10, F_MD, COLOR_GRAY)

        # Chart area
        ax, ay  = 6, 50
        aw, ah  = LW - 12, LH - 56

        if df is not None and len(df) > 1:
            pmin = min(df['Low'].min(), df['Open'].min())
            pmax = max(df['High'].max(), df['Close'].max())
            prng = (pmax - pmin) or 1
            n    = len(df)
            cw   = max(2, aw / n - 1)

            # Draw after-hours shading first
            for i, (ts, row) in enumerate(df.iterrows()):
                if is_extended_hours(ts):
                    px = ax + (i / n) * aw
                    d.rectangle([px, ay, px+cw+1, ay+ah], fill=COLOR_AH)

            # Draw candles
            for i, (ts, row) in enumerate(df.iterrows()):
                px   = ax + (i / n) * aw
                o    = ay + ah - ((row['Open']  - pmin) / prng) * ah
                c    = ay + ah - ((row['Close'] - pmin) / prng) * ah
                hi   = ay + ah - ((row['High']  - pmin) / prng) * ah
                lo   = ay + ah - ((row['Low']   - pmin) / prng) * ah
                color = COLOR_GREEN if row['Close'] >= row['Open'] else COLOR_RED
                mid  = px + cw / 2
                # Wick
                d.line([(mid, hi), (mid, lo)], fill=color, width=1)
                # Body
                top = min(o, c); bot = max(o, c)
                if bot - top < 1: bot = top + 1
                d.rectangle([px, top, px+max(1,cw-1), bot], fill=color)

            # Price line at current price
            if p is not None:
                py_line = ay + ah - ((p - pmin) / prng) * ah
                d.line([(ax, py_line), (ax+aw, py_line)], fill=(80,80,100), width=1)

        elif df is None and p is None:
            centered(d, "Waiting for data...", LW//2, ay+ah//2, F_MD, COLOR_GRAY)

        # Footer hint
        d.text((6, LH-13), "Rotate:nav  Press:timeframe  Long:exit", font=F_SM, fill=COLOR_DIM)

    def _draw_settings(self, d):
        d.rectangle([0, 0, LW, 24], fill=COLOR_PANEL)
        centered(d, "SYMBOL SETTINGS", LW//2, 12, F_LG, COLOR_ACCENT)
        d.line([0, 24, LW, 24], fill=COLOR_DIM, width=1)

        def _save_row(y, sel):
            rrect(d, 6, y, LW-6, y+18, fill=(0,130,60) if sel else (0,80,40), r=4)
            centered(d, "SAVE & BACK", LW//2, y+9, F_MD, COLOR_WHITE)

        _save_row(26, self.set_sym_idx == -1)

        for i, sym in enumerate(self.symbols):
            y   = 48 + i*20
            sel = (i == self.set_sym_idx)
            rrect(d, 6, y, LW-6, y+18, fill=COLOR_SEL if sel else (20,25,50), r=3)
            d.text((12, y+3), f"{i+1}:", font=F_SM, fill=COLOR_CYAN if sel else COLOR_DIM)
            cx = 30
            for ci, ch in enumerate(sym.ljust(6)):
                char_sel = sel and self.set_editing and ci == self.set_char_idx
                if char_sel: rrect(d, cx-2, y+2, cx+12, y+16, fill=(60,90,180), r=2)
                centered(d, ch.strip() or '_', cx+5, y+9, F_SM, COLOR_WHITE)
                cx += 14

        _save_row(LH-22, self.set_sym_idx == 5)
        d.text((10, LH-10), "Rotate:move  Press:edit  Long:save+back", font=F_SM, fill=COLOR_DIM)

    # ── Input ─────────────────────────────────────────────────────────────────
    def on_rotate(self, delta):
        if self.page == PG_CHART:
            self.focus = (self.focus + delta) % 7
        elif self.page == PG_SETTINGS:
            if self.set_editing:
                sym = list(self.symbols[self.set_sym_idx].ljust(6))
                cur = ALPHABET.find(sym[self.set_char_idx]) if sym[self.set_char_idx] in ALPHABET else 0
                nxt = (cur + delta) % len(ALPHABET)
                sym[self.set_char_idx] = ALPHABET[nxt]
                self.symbols[self.set_sym_idx] = ''.join(sym).rstrip()
            else:
                self.set_sym_idx = max(-1, min(5, self.set_sym_idx + delta))
        self._dirty = True

    def _save_and_back(self):
        self.set_editing = False
        save_config(self.symbols)
        self.data = {}
        self._bg_fetch()
        self.page = PG_CHART

    def on_press(self):
        if self.page == PG_CHART:
            if self.focus == 0:
                self.running = False
            elif 1 <= self.focus <= 5:
                # Cycle timeframe for active symbol
                self.tf_idx = (self.tf_idx + 1) % len(TIMEFRAMES)
                self.data = {}
                self._bg_fetch()
            elif self.focus == 6:
                self.page = PG_SETTINGS
                self.set_sym_idx = 0
                self.set_char_idx = 0
                self.set_editing = False
        elif self.page == PG_SETTINGS:
            if self.set_sym_idx in (-1, 5):
                self._save_and_back()
            elif self.set_editing:
                self.set_char_idx += 1
                if self.set_char_idx >= 6:
                    self.set_char_idx = 0
                    self.set_editing = False
            else:
                self.set_editing = True
                self.set_char_idx = 0
        self._dirty = True

    def on_long_press(self):
        if self.page == PG_SETTINGS:
            save_config(self.symbols)
        self.running = False

    def run(self):
        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                r = rotary.read_event(0)
                if r: self.on_rotate(r)
                kev = keys.read_event(0)
                if kev:
                    if kev[0] == 'key_long_press': self.on_long_press()
                    elif kev[0] == 'key_release' and kev[1] == 'ENTER': self.on_press()
                tev = touch.read_event(0)
                if tev and tev[0] == 'touch_down':
                    tx, ty = TouchScreen.map_coords_270(tev[1], tev[2])
                    if ty < 24:
                        iw = LW // 7
                        tap = tx // iw
                        if tap == 0:
                            if self.page == PG_SETTINGS: self._save_and_back()
                            else: self.running = False
                        elif 1 <= tap <= 5: self.focus = tap; self.page = PG_CHART
                        elif tap == 6:
                            self.page = PG_SETTINGS; self.set_sym_idx=0; self.set_editing=False
                    self._dirty = True

                if self._dirty: self.draw()
                time.sleep(0.05)
        self.fb.close()

if __name__ == "__main__":
    App().run()
