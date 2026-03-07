#!/usr/bin/env python3
"""
Stock Tracker App for NanoKVM Pro
- Rotary encoder (event0, EV_REL): one detent = one letter step (debounced)
- Push button ENTER (event1): short = next char, long = save & exit editor / exit app
- Editor touch:
    * Tap symbol slot      -> select that slot for editing
    * Tap char in slot     -> select that specific char position
    * Tap/drag alphabet    -> select letter directly
    * Tap SAVE button      -> save & return to chart
"""

import time
import json
import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from framebuffer import Framebuffer
from input import TouchScreen, GpioKeys, RotaryEncoder

CONFIG_FILE     = '/etc/kvm/stocks_config.json'
DEFAULT_SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'SPY']

SCREEN_W = 320
SCREEN_H = 172

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'

COLOR_BG       = (8,   12,  24)
COLOR_GRID     = (30,  40,  60)
COLOR_WHITE    = (230, 230, 230)
COLOR_GRAY     = (120, 120, 140)
COLOR_CYAN     = (0,   200, 220)
COLOR_GREEN    = (60,  200,  80)
COLOR_RED      = (220,  60,  60)
COLOR_YELLOW   = (240, 210,  50)
COLOR_SEL      = (50,   80, 160)
COLOR_ORANGE   = (255, 140,  20)
COLOR_FOCUS    = (60,  120, 240)
COLOR_FOCUS_BG = (18,  35,  75)
COLOR_DIM      = (50,  55,  70)
COLOR_SAVE     = (30, 130,  60)
COLOR_SAVE_HI  = (50, 200,  90)

ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ.'

TIMEFRAMES = [
    ('5d',  '1h',  '5d/1h'),
    ('1d',  '5m',  '1d/5m'),
    ('1mo', '1d',  '1mo/1d'),
    ('6mo', '1wk', '6mo/wk'),
    ('1y',  '1wk', '1yr/wk'),
]

FOCUS_SYMBOL = 0
FOCUS_CHART  = 1
FOCUS_GEAR   = 2

HEADER_H = 30

ZONE_SYM_X1,  ZONE_SYM_X2  = 0,   90
ZONE_CHT_X1,  ZONE_CHT_X2  = 91,  284
ZONE_GEAR_X1, ZONE_GEAR_X2 = 285, 319

# Editor layout constants
ED_HEADER_H  = 20        # title bar height
ED_SLOT_Y1   = 20        # symbol slots top
ED_SLOT_Y2   = 62        # symbol slots bottom
ED_SLOT_H    = ED_SLOT_Y2 - ED_SLOT_Y1
ED_ALPHA_Y1  = 66        # alphabet strip top
ED_ALPHA_Y2  = 126       # alphabet strip bottom
ED_ALPHA_H   = ED_ALPHA_Y2 - ED_ALPHA_Y1
# Bottom button bar  (y=148..172, full width split in half)
ED_BTN_Y1    = 148
ED_BTN_Y2    = 172
ED_CANCEL_X2 = 159       # CANCEL: x=0..159
ED_SAVE_X1   = 160       # SAVE:   x=160..319

SLOT_W    = 56
SLOT_GAP  = 2
SLOTS_TOTAL = 5 * SLOT_W + 4 * SLOT_GAP   # 292
SLOT_START_X = (SCREEN_W - SLOTS_TOTAL) // 2   # 14

ENCODER_DEBOUNCE = 0.20   # seconds between encoder steps (200ms handles mechanical bounce)

# Auto-refresh intervals: (seconds, display label).  0 = off.
REFRESH_OPTIONS = [
    (0,    'Off'),
    (60,   '1 min'),
    (300,  '5 min'),
    (900,  '15 min'),
    (1800, '30 min'),
    (3600, '1 hr'),
]


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            d = json.load(f)
        syms = d.get('symbols', DEFAULT_SYMBOLS)[:5]
        while len(syms) < 5:
            syms.append('SPY')
        return syms
    except Exception:
        return list(DEFAULT_SYMBOLS)


def save_config(symbols):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump({'symbols': symbols}, f)
    except Exception:
        pass


def fetch_candles(symbol, period='5d', interval='1h'):
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)
        if df is None or len(df) < 2:
            return None
        result = []
        for _, row in df.iterrows():
            try:
                result.append((float(row['Open']), float(row['High']),
                                float(row['Low']),  float(row['Close'])))
            except Exception:
                pass
        return result if result else None
    except Exception as e:
        print(f'fetch error: {e}')
        return None


def draw_candles(draw, candles, ax, ay, aw, ah):
    if not candles:
        draw.text((ax + aw // 2 - 20, ay + ah // 2), 'NO DATA', fill=COLOR_GRAY)
        return
    highs = [c[1] for c in candles]
    lows  = [c[2] for c in candles]
    pmax  = max(highs) * 1.001
    pmin  = min(lows)  * 0.999
    prng  = pmax - pmin or 1

    def py(p):
        return int(ay + ah - (p - pmin) / prng * ah)

    n  = len(candles)
    cw = max(2, aw // n - 1)
    sp = aw / n

    for i in range(1, 4):
        gy = ay + int(ah * i / 4)
        draw.line([(ax, gy), (ax + aw, gy)], fill=COLOR_GRID, width=1)

    for i, (o, h, l, c) in enumerate(candles):
        cx  = int(ax + i * sp + sp / 2)
        col = COLOR_GREEN if c >= o else COLOR_RED
        draw.line([(cx, py(h)), (cx, py(l))], fill=col, width=1)
        bt = py(max(o, c))
        bb = max(py(min(o, c)), bt + 1)
        draw.rectangle([cx - cw // 2, bt, cx + cw // 2, bb], fill=col)


def draw_gear(draw, cx, cy, r=10, color=COLOR_GRAY):
    draw.ellipse((cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3),
                 outline=color, width=2)
    for i in range(8):
        a  = (i / 8) * 2 * math.pi
        x1 = cx + math.cos(a) * (r - 3)
        y1 = cy + math.sin(a) * (r - 3)
        x2 = cx + math.cos(a) * r
        y2 = cy + math.sin(a) * r
        draw.line((x1, y1, x2, y2), fill=color, width=3)


def render_chart(symbol, candles, sym_idx, total, focus, tf_label):
    img  = Image.new('RGB', (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    try:
        fsm = ImageFont.truetype(FONT_PATH, 10)
        fmd = ImageFont.truetype(FONT_PATH, 12)
        fbg = ImageFont.truetype(FONT_BOLD, 17)
    except Exception:
        fsm = fmd = fbg = ImageFont.load_default()

    draw.rectangle([0, 0, SCREEN_W - 1, HEADER_H], fill=(12, 18, 40))

    zones = [(ZONE_SYM_X1, ZONE_SYM_X2),
             (ZONE_CHT_X1, ZONE_CHT_X2),
             (ZONE_GEAR_X1, ZONE_GEAR_X2)]
    zx1, zx2 = zones[focus]
    draw.rectangle([zx1, 0, zx2, HEADER_H], fill=COLOR_FOCUS_BG)
    draw.rectangle([zx1, HEADER_H - 2, zx2, HEADER_H], fill=COLOR_FOCUS)

    sym_col = COLOR_CYAN if focus == FOCUS_SYMBOL else COLOR_WHITE
    draw.text((4, 7), symbol, font=fbg, fill=sym_col)
    for i in range(total):
        col = COLOR_CYAN if i == sym_idx else (45, 45, 70)
        draw.ellipse([4 + i * 8, 2, 9 + i * 8, 7], fill=col)

    cht_col = COLOR_CYAN if focus == FOCUS_CHART else COLOR_GRAY
    if candles:
        lc   = candles[-1][3]
        fo   = candles[0][0]
        chg  = lc - fo
        pct  = chg / fo * 100 if fo else 0
        pcol = COLOR_GREEN if chg >= 0 else COLOR_RED
        sign = '+' if chg >= 0 else ''
        draw.text((ZONE_CHT_X1 + 4, 3),   f'${lc:.2f}',        font=fmd, fill=COLOR_WHITE)
        draw.text((ZONE_CHT_X1 + 4, 17),  f'{sign}{pct:.2f}%', font=fsm, fill=pcol)
        draw.text((ZONE_CHT_X1 + 80, 10), tf_label,            font=fsm, fill=cht_col)
    else:
        draw.text((ZONE_CHT_X1 + 4, 10),  'Loading...', font=fsm, fill=COLOR_GRAY)
        draw.text((ZONE_CHT_X1 + 80, 10), tf_label,     font=fsm, fill=cht_col)

    gear_col = COLOR_CYAN if focus == FOCUS_GEAR else COLOR_GRAY
    gcx = ZONE_GEAR_X1 + (ZONE_GEAR_X2 - ZONE_GEAR_X1) // 2
    draw_gear(draw, gcx, HEADER_H // 2, r=10, color=gear_col)

    draw_candles(draw, candles, 2, HEADER_H + 2, SCREEN_W - 4,
                 SCREEN_H - HEADER_H - 14)

    ts = time.strftime('%H:%M')
    draw.text((SCREEN_W - 35, SCREEN_H - 12), ts, font=fsm, fill=COLOR_GRAY)
    draw.text((2, SCREEN_H - 12), 'Wheel:focus  Press:action  Long:exit',
              font=fsm, fill=COLOR_DIM)
    return img


def render_editor(syms, editing_sym, editing_char, char_idx):
    img  = Image.new('RGB', (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    try:
        fsm  = ImageFont.truetype(FONT_PATH, 10)
        fmed = ImageFont.truetype(FONT_PATH, 12)
        fbg  = ImageFont.truetype(FONT_BOLD, 14)
        fmn  = ImageFont.truetype(FONT_MONO, 13)
        fal  = ImageFont.truetype(FONT_BOLD, 13)   # alphabet normal
        fal2 = ImageFont.truetype(FONT_BOLD, 18)   # alphabet selected
    except Exception:
        fsm = fmed = fbg = fmn = fal = fal2 = ImageFont.load_default()

    # --- Header ---
    draw.rectangle([0, 0, SCREEN_W, ED_HEADER_H], fill=(14, 22, 48))
    draw.text((4, 3), 'EDIT SYMBOLS', font=fbg, fill=COLOR_CYAN)

    # --- Symbol slots ---
    char_w = 10  # pixels per char in slot
    for i, sym in enumerate(syms):
        sx  = SLOT_START_X + i * (SLOT_W + SLOT_GAP)
        sel = (i == editing_sym)
        bg  = (22, 38, 80) if sel else (16, 24, 48)
        border = COLOR_CYAN if sel else (50, 60, 90)
        draw.rectangle([sx, ED_SLOT_Y1, sx + SLOT_W - 1, ED_SLOT_Y2 - 1],
                        fill=bg, outline=border, width=1)
        sd = sym.ljust(5)[:5]
        for ci, ch in enumerate(sd):
            cx2 = sx + 3 + ci * char_w
            cy2 = ED_SLOT_Y1 + (ED_SLOT_H - 16) // 2
            if sel and ci == editing_char:
                # Highlighted current char
                draw.rectangle([cx2 - 1, cy2 - 1, cx2 + char_w - 1, cy2 + 15],
                                fill=COLOR_ORANGE)
                draw.text((cx2, cy2), ch, font=fmn, fill=COLOR_BG)
            else:
                draw.text((cx2, cy2), ch, font=fmn,
                           fill=COLOR_WHITE if sel else (80, 90, 110))

    # --- Divider ---
    draw.line([(0, ED_ALPHA_Y1 - 2), (SCREEN_W, ED_ALPHA_Y1 - 2)],
              fill=(30, 40, 70), width=1)

    # --- Alphabet strip ---
    n_chars  = len(ALPHABET)
    cell_w   = SCREEN_W / n_chars  # ~11.85px each

    # Background
    draw.rectangle([0, ED_ALPHA_Y1, SCREEN_W, ED_ALPHA_Y2], fill=(10, 16, 36))

    for ai, ch in enumerate(ALPHABET):
        cx2  = int(ai * cell_w + cell_w / 2)
        sel  = (ai == char_idx)
        if sel:
            # Highlight background for selected letter
            bx1 = int(ai * cell_w)
            bx2 = int((ai + 1) * cell_w)
            draw.rectangle([bx1, ED_ALPHA_Y1, bx2, ED_ALPHA_Y2],
                            fill=(30, 60, 120))
            # Large selected letter centered vertically
            bbox = draw.textbbox((0, 0), ch, font=fal2)
            tw   = bbox[2] - bbox[0]
            th   = bbox[3] - bbox[1]
            ty   = ED_ALPHA_Y1 + (ED_ALPHA_H - th) // 2 - bbox[1]
            draw.text((cx2 - tw // 2, ty), ch, font=fal2, fill=COLOR_YELLOW)
        else:
            bbox = draw.textbbox((0, 0), ch, font=fal)
            tw   = bbox[2] - bbox[0]
            th   = bbox[3] - bbox[1]
            ty   = ED_ALPHA_Y1 + (ED_ALPHA_H - th) // 2 - bbox[1]
            # Dim neighbours, brighter as distance shrinks
            dist = min(abs(ai - char_idx), n_chars - abs(ai - char_idx))
            alpha = max(60, 180 - dist * 18)
            col  = (alpha, alpha, alpha)
            draw.text((cx2 - tw // 2, ty), ch, font=fal, fill=col)

    # --- Instructions row ---
    iy = ED_ALPHA_Y2 + 4
    draw.text((2, iy),      'Wheel / drag strip: change letter', font=fsm, fill=COLOR_GRAY)
    draw.text((2, iy + 12), 'Tap slot or char to jump position', font=fsm, fill=COLOR_GRAY)

    # --- Bottom button bar ---
    # CANCEL (left half)
    draw.rectangle([0, ED_BTN_Y1, ED_CANCEL_X2, ED_BTN_Y2],
                    fill=(60, 20, 20), outline=(160, 60, 60), width=1)
    bbox = draw.textbbox((0, 0), 'CANCEL', font=fmed)
    tw = bbox[2] - bbox[0]
    draw.text(((ED_CANCEL_X2 - tw) // 2, ED_BTN_Y1 + 5), 'CANCEL', font=fmed, fill=(220, 100, 100))

    # SAVE (right half)
    draw.rectangle([ED_SAVE_X1, ED_BTN_Y1, SCREEN_W - 1, ED_BTN_Y2],
                    fill=(20, 70, 30), outline=(60, 180, 80), width=1)
    bbox = draw.textbbox((0, 0), 'SAVE', font=fmed)
    tw = bbox[2] - bbox[0]
    sx_mid = ED_SAVE_X1 + (SCREEN_W - ED_SAVE_X1) // 2
    draw.text((sx_mid - tw // 2, ED_BTN_Y1 + 5), 'SAVE', font=fmed, fill=(80, 220, 100))

    return img


def render_gear_menu(selected, refresh_label):
    img  = Image.new('RGB', (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    try:
        fsm = ImageFont.truetype(FONT_PATH, 10)
        fmd = ImageFont.truetype(FONT_PATH, 14)
        fbg = ImageFont.truetype(FONT_BOLD, 16)
    except Exception:
        fsm = fmd = fbg = ImageFont.load_default()

    draw.text((4, 4), 'SETTINGS', font=fbg, fill=COLOR_CYAN)
    options = [
        'Refresh Data Now',
        f'Auto-Refresh: {refresh_label}',
        'Back',
    ]
    for i, label in enumerate(options):
        y = 35 + i * 30
        if i == selected:
            draw.rectangle([4, y - 2, SCREEN_W - 4, y + 24],
                            fill=COLOR_FOCUS_BG, outline=COLOR_FOCUS, width=1)
        # Show arrow hint on the refresh row
        suffix = '  < >' if i == 1 else ''
        draw.text((12, y + 4), label + suffix, font=fmd,
                   fill=COLOR_CYAN if i == selected else COLOR_WHITE)

    draw.text((4, SCREEN_H - 24), 'Wheel: navigate  Press: select/cycle', font=fsm, fill=COLOR_GRAY)
    draw.text((4, SCREEN_H - 12), 'Long press: exit app',                  font=fsm, fill=COLOR_GRAY)
    return img


def image_to_fb(img, fb):
    phys   = img.rotate(90, expand=True)
    arr    = np.array(phys, dtype=np.uint16)
    rgb565 = (((arr[:,:,0] >> 3) << 11) |
              ((arr[:,:,1] >> 2) << 5)  |
               (arr[:,:,2] >> 3)).astype('<u2')
    data = rgb565.tobytes()
    if fb.fbmem and fb.buffer:
        fb.buffer[:len(data)] = bytearray(data)
        fb.swap_buffer()


def alpha_idx_from_x(screen_x):
    """Map logical screen x (0-319) to ALPHABET index."""
    idx = int(screen_x * len(ALPHABET) / SCREEN_W)
    return max(0, min(len(ALPHABET) - 1, idx))


def slot_and_char_from_touch(screen_x, screen_y):
    """
    If touch is inside symbol slot area, return (slot_idx, char_idx_in_slot).
    Otherwise return (None, None).
    """
    if not (ED_SLOT_Y1 <= screen_y <= ED_SLOT_Y2):
        return None, None
    for i in range(5):
        sx = SLOT_START_X + i * (SLOT_W + SLOT_GAP)
        if sx <= screen_x <= sx + SLOT_W - 1:
            char_w = 10
            rel_x  = screen_x - sx - 3
            ci     = max(0, min(4, rel_x // char_w))
            return i, int(ci)
    return None, None


class StockApp:
    def __init__(self, fb):
        self.fb           = fb
        self.symbols      = load_config()
        self.current      = 0
        self.focus        = FOCUS_CHART
        self.tf_idx       = 0
        self.refresh_idx  = 2       # default: 5 min (REFRESH_OPTIONS index)
        self.cache        = {}
        self.last_fetch   = {}

    def tf(self):
        return TIMEFRAMES[self.tf_idx]

    def refresh_interval(self):
        return REFRESH_OPTIONS[self.refresh_idx][0]

    def refresh_label(self):
        return REFRESH_OPTIONS[self.refresh_idx][1]

    def get_candles(self, sym=None):
        sym    = sym or self.symbols[self.current]
        period, interval, _ = self.tf()
        key    = (sym, period, interval)
        now    = time.time()
        ttl    = self.refresh_interval() or 300   # use 5min as cache TTL even when auto-refresh is off
        if key in self.cache and now - self.last_fetch.get(key, 0) < ttl:
            return self.cache[key]
        data = fetch_candles(sym, period, interval)
        self.cache[key]      = data
        self.last_fetch[key] = now
        return data

    def show_chart(self):
        sym = self.symbols[self.current]
        _, _, tf_label = self.tf()
        img = render_chart(sym, self.get_candles(sym),
                           self.current, len(self.symbols),
                           self.focus, tf_label)
        image_to_fb(img, self.fb)

    def run_editor(self, keys, touch, encoder):
        editing_sym  = 0
        editing_char = 0
        syms         = [s.ljust(5)[:5] for s in self.symbols]
        char_idx     = ALPHABET.find(syms[0][0])
        if char_idx < 0:
            char_idx = 0

        last_encoder_step = 0.0
        touch_ctx         = None   # 'slot', 'alpha', 'btn', or None

        def set_char(new_idx):
            nonlocal char_idx
            char_idx = new_idx % len(ALPHABET)
            syms[editing_sym] = (syms[editing_sym][:editing_char] +
                                  ALPHABET[char_idx] +
                                  syms[editing_sym][editing_char + 1:])

        def move_to(sym_i, char_i):
            nonlocal editing_sym, editing_char, char_idx
            editing_sym  = sym_i
            editing_char = char_i
            ci = ALPHABET.find(syms[editing_sym][editing_char])
            char_idx = ci if ci >= 0 else 0

        def do_save():
            self.symbols = [s.strip('.').strip() or 'SPY' for s in syms]
            save_config(self.symbols)
            self.cache.clear()

        def redraw():
            image_to_fb(render_editor(syms, editing_sym, editing_char, char_idx), self.fb)

        redraw()

        while True:
            # --- Encoder: one step per detent, debounced ---
            re = encoder.read_event(timeout=0)
            if re:
                _, delta = re
                now = time.time()
                if delta != 0 and (now - last_encoder_step) >= ENCODER_DEBOUNCE:
                    last_encoder_step = now
                    step = 1 if delta > 0 else -1
                    set_char(char_idx + step)
                    redraw()

            # --- Touch ---
            te = touch.read_event(timeout=0)
            if te:
                ev, raw_x, raw_y, _ = te
                sx, sy = TouchScreen.map_coords_270(raw_x, raw_y)

                if ev == 'touch_down':
                    # Classify where the touch started
                    if ED_BTN_Y1 <= sy <= ED_BTN_Y2:
                        touch_ctx = 'btn'
                    elif ED_ALPHA_Y1 <= sy <= ED_ALPHA_Y2:
                        touch_ctx = 'alpha'
                        set_char(alpha_idx_from_x(sx))
                        redraw()
                    else:
                        slot_i, char_i = slot_and_char_from_touch(sx, sy)
                        if slot_i is not None:
                            touch_ctx = 'slot'
                            move_to(slot_i, char_i)
                            redraw()
                        else:
                            touch_ctx = None

                elif ev == 'touch_move':
                    # Only drag-update letter if touch started on alphabet strip
                    if touch_ctx == 'alpha' and ED_ALPHA_Y1 <= sy <= ED_ALPHA_Y2:
                        new_idx = alpha_idx_from_x(sx)
                        if new_idx != char_idx:
                            set_char(new_idx)
                            redraw()

                elif ev == 'touch_up':
                    if touch_ctx == 'btn':
                        if sx <= ED_CANCEL_X2:   # CANCEL
                            return               # discard changes
                        else:                    # SAVE
                            do_save()
                            return
                    touch_ctx = None

            # --- Button ---
            ke = keys.read_event(timeout=0.02)
            if ke:
                ev, kn, _, _, _ = ke
                if ev == 'key_long_press':
                    do_save()
                    return
                elif ev == 'key_press' and kn == 'ENTER':
                    editing_char = (editing_char + 1) % 5
                    ci = ALPHABET.find(syms[editing_sym][editing_char])
                    char_idx = ci if ci >= 0 else 0
                    redraw()

    def run_gear_menu(self, keys, touch, encoder):
        selected   = 0
        opts_count = 3
        last_step  = 0.0

        def redraw():
            image_to_fb(render_gear_menu(selected, self.refresh_label()), self.fb)

        redraw()
        while True:
            te = touch.read_event(timeout=0)
            if te and te[0] == 'touch_down':
                return False

            re = encoder.read_event(timeout=0)
            if re:
                _, delta = re
                now = time.time()
                if delta != 0 and (now - last_step) >= ENCODER_DEBOUNCE:
                    last_step = now
                    step     = 1 if delta > 0 else -1
                    selected = (selected + step) % opts_count
                    redraw()

            ke = keys.read_event(timeout=0.02)
            if ke:
                ev, kn, _, _, _ = ke
                if ev == 'key_long_press':
                    return True
                elif ev == 'key_press' and kn == 'ENTER':
                    if selected == 0:                       # Refresh now
                        self.cache.clear()
                        return False
                    elif selected == 1:                     # Cycle refresh interval
                        self.refresh_idx = (self.refresh_idx + 1) % len(REFRESH_OPTIONS)
                        redraw()
                    elif selected == 2:                     # Back
                        return False

    def run(self):
        print('Stock Tracker starting...')
        self.show_chart()
        last_auto      = time.time()
        last_enc_step  = 0.0
        td_time = td_x = td_y = 0
        touching = False

        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as encoder:
            while True:
                ri = self.refresh_interval()
                if ri > 0 and time.time() - last_auto > ri:
                    self.cache.clear()
                    self.show_chart()
                    last_auto = time.time()

                # Rotary encoder -> cycle focus (one step per detent)
                re = encoder.read_event(timeout=0)
                if re:
                    _, delta = re
                    now = time.time()
                    if delta != 0 and (now - last_enc_step) >= ENCODER_DEBOUNCE:
                        last_enc_step = now
                        step       = 1 if delta > 0 else -1
                        self.focus = (self.focus + step) % 3
                        self.show_chart()

                # Touch
                te = touch.read_event(timeout=0)
                if te:
                    ev, x, y, _ = te
                    sx, sy = TouchScreen.map_coords_270(x, y)

                    if ev == 'touch_down':
                        td_time = time.time()
                        td_x, td_y = sx, sy
                        touching = True

                    elif ev == 'touch_up' and touching:
                        touching = False
                        dur = time.time() - td_time
                        if dur > 1.5:
                            break

                        if td_y <= HEADER_H:
                            if ZONE_SYM_X1 <= td_x <= ZONE_SYM_X2:
                                if self.focus == FOCUS_SYMBOL:
                                    self.run_editor(keys, touch, encoder)
                                else:
                                    self.focus = FOCUS_SYMBOL
                                self.show_chart()
                            elif ZONE_CHT_X1 <= td_x <= ZONE_CHT_X2:
                                if self.focus == FOCUS_CHART:
                                    self.tf_idx = (self.tf_idx + 1) % len(TIMEFRAMES)
                                    self.cache.clear()
                                else:
                                    self.focus = FOCUS_CHART
                                self.show_chart()
                            elif ZONE_GEAR_X1 <= td_x <= ZONE_GEAR_X2:
                                if self.focus == FOCUS_GEAR:
                                    if self.run_gear_menu(keys, touch, encoder):
                                        break
                                else:
                                    self.focus = FOCUS_GEAR
                                self.show_chart()
                        else:
                            self.current = (self.current + 1) % len(self.symbols)
                            self.show_chart()

                # Button
                ke = keys.read_event(timeout=0.02)
                if ke:
                    ev, kn, _, _, _ = ke
                    if ev == 'key_long_press':
                        break
                    elif ev == 'key_press' and kn == 'ENTER':
                        if self.focus == FOCUS_SYMBOL:
                            self.run_editor(keys, touch, encoder)
                            self.show_chart()
                        elif self.focus == FOCUS_CHART:
                            self.tf_idx = (self.tf_idx + 1) % len(TIMEFRAMES)
                            self.cache.clear()
                            self.show_chart()
                        elif self.focus == FOCUS_GEAR:
                            if self.run_gear_menu(keys, touch, encoder):
                                break
                            self.show_chart()


def main():
    fb  = Framebuffer('/dev/fb0', rotation=90, font_size=12)
    app = StockApp(fb)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        fb.fill_screen((0, 0, 0))


if __name__ == '__main__':
    main()
