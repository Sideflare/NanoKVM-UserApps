#!/usr/bin/env python3
"""
PicoClaw NanoKVM Screen App  v1.0.0
────────────────────────────────────
7 pages navigated with the rotary knob and touchscreen:
  Home · Agent · Voice · Skills · Auth · Setup · Status

Controls:
  Knob rotate  → scroll / change selection
  Knob press   → select / confirm
  Knob 2s hold → back to Home (or exit from Home)
  Touch        → tap buttons directly

Voice commands use Vosk offline speech recognition (no API key needed).
Model loaded from ./model/ at startup.
Agent sends messages to picoclaw agent -m via the configured profile.
"""

import os, sys, time, json, threading, mmap, textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import picoclaw_cli as pc
import voice as vc
from input import TouchScreen, GpioKeys, RotaryEncoder

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320      # physical (portrait)
LW, LH = 320, 172      # logical canvas (landscape)

BG     = (8,   8,  22)
PANEL  = (18,  20,  46)
ACCENT = (0,  185, 255)
TEXT   = (230, 235, 255)
DIM    = (90,  95, 130)
OK     = (0,  210, 110)
ERR    = (255,  70,  70)
WARN   = (255, 195,   0)
SEL    = (30,   60, 135)
BTN    = (35,   38,  82)
BTNH   = (55,  100, 205)
REC    = (210,  30,  30)
AI_MSG = (30,  35,  70)
USER_MSG = (0, 95, 140)

_FP = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def _f(sz, bold=False):
    try:   return ImageFont.truetype(_FB if bold else _FP, sz)
    except: return ImageFont.load_default()

FN = _f(9);  FS = _f(11);  FM = _f(13);  FL = _f(16)
FT = _f(15, True);  FH = _f(18, True)


def get_sys_stats():
    """Retrieve system stats for the Status/Setup pages."""
    try:
        import psutil
        cpu = f"{psutil.cpu_percent()}%"
        mem = f"{psutil.virtual_memory().percent}%"
        # temp
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = f"{int(f.read()) // 1000}°C"
        except: temp = "?"
        # ip
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except: ip = "127.0.0.1"
        return {"cpu": cpu, "mem": mem, "temp": temp, "ip": ip}
    except:
        return {"cpu": "?", "mem": "?", "temp": "?", "ip": "?"}


class FB:
    """Fast framebuffer via numpy mmap."""
    def __init__(self):
        sz = PW * PH * 2
        self.fd  = os.open('/dev/fb0', os.O_RDWR)
        self.mm  = mmap.mmap(self.fd, sz, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self.arr = np.frombuffer(self.mm, dtype=np.uint16).reshape(PH, PW)

    def show(self, img: Image.Image):
        # Logical 320×172 → rotate 90° CCW → Physical 172×320
        p = img.rotate(90, expand=True)
        a = np.array(p, dtype=np.uint16)
        self.arr[:, :] = (a[:, :, 0] >> 3 << 11) | (a[:, :, 1] >> 2 << 5) | (a[:, :, 2] >> 3)

    def close(self):
        self.mm.close()
        os.close(self.fd)


# ── UI Helpers ────────────────────────────────────────────────────────────────
def rrect(d, x0, y0, x1, y1, fill=None, outline=None, r=4):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline)

def centered(d, text, cx, cy, font, color):
    bb = d.textbbox((0, 0), text, font=font)
    d.text((cx - (bb[2]-bb[0])//2, cy - (bb[3]-bb[1])//2), text, font=font, fill=color)

def topbar(d, title, dot=OK):
    d.rectangle([0, 0, LW, 21], fill=PANEL)
    d.text((8, 3), title, font=FT, fill=ACCENT)
    d.ellipse([LW-13, 6, LW-5, 14], fill=dot)
    d.line([0, 21, LW, 21], fill=DIM, width=1)

def wordwrap(text, maxw, d, font):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        bb = d.textbbox((0, 0), t, font=font)
        if bb[2]-bb[0] > maxw and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur: lines.append(cur)
    return lines

def drawbtn(d, x0, y0, x1, y1, label, font=FM, color=TEXT, bg=BTN, sel=False):
    rrect(d, x0, y0, x1, y1, fill=BTNH if sel else bg, outline=ACCENT if sel else None)
    centered(d, label, (x0+x1)//2, (y0+y1)//2, font, color)


def drawbubble(d, y, role, text, font=FN):
    """Draw a chat bubble for AI or User."""
    is_user = (role == 'you')
    color   = USER_MSG if is_user else AI_MSG
    txt_col = TEXT
    max_w   = LW - 60
    lines   = wordwrap(text, max_w - 20, d, font)
    if not lines: return y
    bh = len(lines) * (font.getbbox("A")[3] + 2) + 12
    bw = max([d.textbbox((0, 0), l, font=font)[2] for l in lines]) + 16
    
    x0 = LW - bw - 8 if is_user else 8
    x1 = x0 + bw
    rrect(d, x0, y, x1, y + bh, fill=color, r=8)
    # arrow
    if is_user:
        d.polygon([(x1, y+8), (x1+6, y+14), (x1, y+20)], fill=color)
    else:
        d.polygon([(x0, y+8), (x0-6, y+14), (x0, y+20)], fill=color)

    ty = y + 6
    for line in lines:
        d.text((x0 + 8, ty), line, font=font, fill=txt_col)
        ty += font.getbbox("A")[3] + 2
    return y + bh + 6


def drawwaveform(d, x, y, w, h, level):
    """Draw a simple waveform or level meter."""
    # level is ~0..32768, normalize to 0..h
    v = min(h, int(level / 3000 * h)) if level > 0 else 2
    rrect(d, x, y + h//2 - v//2, x + w, y + h//2 + v//2, fill=ACCENT if level > 500 else DIM, r=2)


# ── Pages ──────────────────────────────────────────────────────────────────
PG_HOME, PG_AGENT, PG_VOICE, PG_SKILLS, PG_AUTH, PG_SETUP, PG_STATUS = range(7)
HOME_TARGETS = [PG_AGENT, PG_VOICE, PG_SKILLS, PG_AUTH, PG_SETUP, PG_STATUS]
HOME_LABELS  = ["Agent", "Voice", "Skills", "Auth", "Setup", "Status"]
HOME_ICONS   = [">_ ", "(O)", "## ", "[K]", "{} ", " i "]

# ── Config ────────────────────────────────────────────────────────────────────
CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
CFG_DEF  = {"profile": "claude"}

def load_cfg():
    try:
        with open(CFG_PATH) as f: c = json.load(f)
        for k, v in CFG_DEF.items(): c.setdefault(k, v)
        return c
    except: return dict(CFG_DEF)

def save_cfg(c):
    try:
        with open(CFG_PATH, 'w') as f: json.dump(c, f, indent=2)
    except Exception as e: print(f"cfg save: {e}")


# ── App ───────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.fb  = FB()
        self.rec = vc.Recorder()
        self.cfg = load_cfg()
        self._cache_lock = threading.Lock()
        self._cache = {}
        self._dirty = True

        # ── page state
        self.page     = PG_HOME
        self.home_sel = 0

        self.agent_hist   = []    # [(role, text)]
        self.agent_scroll = 0
        self.agent_busy   = False
        self.agent_msg    = ""

        self.voice_state = "idle"  # idle|recording|processing|done|error
        self.voice_text  = ""      # transcript
        self.voice_err   = ""

        self.skills      = []
        self.skills_sel  = 0
        self.skills_scroll = 0

        self.auth_sel    = 0       # 0=Login 1=Logout 2=Status
        self.auth_result = ""
        self.auth_busy   = False

        self.setup_sel      = 0
        self.setup_profiles = pc.list_profiles()
        self.setup_result   = ""

        # ── system stats
        self.stats = {}
        threading.Thread(target=self._stats_loop, daemon=True).start()

        # ── initial background loads
        self._bg('version', pc.get_version)
        self._bg('auth',    pc.auth_status)

    def _stats_loop(self):
        while True:
            self.stats = get_sys_stats()
            if self.page in (PG_HOME, PG_STATUS, PG_SETUP):
                self._dirty = True
            time.sleep(2)

    # ── Background task helper ────────────────────────────────────────────────
    def _bg(self, key, fn, *args, done=None):
        def _run():
            try:
                r = fn(*args)
                with self._cache_lock: self._cache[key] = ('ok', r)
            except Exception as e:
                with self._cache_lock: self._cache[key] = ('err', str(e))
            self._dirty = True
            if done: done()
        threading.Thread(target=_run, daemon=True).start()

    def _get(self, key):
        with self._cache_lock: return self._cache.get(key)

    # ── Navigation ────────────────────────────────────────────────────────────
    def goto(self, page):
        self.page   = page
        self._dirty = True
        if page == PG_SKILLS: self._bg('skills', pc.list_skills)
        elif page == PG_STATUS: self._bg('status', pc.get_status)
        elif page == PG_AUTH:   self._bg('auth',   pc.auth_status)

    # ── Input handlers ────────────────────────────────────────────────────────
    def on_rotate(self, delta):
        p = self.page
        if   p == PG_HOME:   self.home_sel    = (self.home_sel + delta) % 6
        elif p == PG_AGENT:  self.agent_scroll = max(0, self.agent_scroll + delta)
        elif p == PG_SKILLS: self.skills_sel   = max(0, min(len(self.skills)-1, self.skills_sel + delta))
        elif p == PG_AUTH:   self.auth_sel     = (self.auth_sel + delta) % 3
        elif p == PG_SETUP:  self.setup_sel    = (self.setup_sel + delta) % 5
        self._dirty = True

    def on_press(self):
        p = self.page
        if   p == PG_HOME:   self.goto(HOME_TARGETS[self.home_sel])
        elif p == PG_VOICE:  self._toggle_voice()
        elif p == PG_AGENT:
            if self.voice_text and not self.agent_busy:
                self._agent_send(self.voice_text)
                self.voice_text = ""
        elif p == PG_AUTH:   self._auth_action(self.auth_sel)
        elif p == PG_SETUP:  self._setup_action(self.setup_sel)
        elif p == PG_STATUS: self._bg('status', pc.get_status)
        self._dirty = True

    def on_long_press(self):
        if self.page != PG_HOME:
            self.goto(PG_HOME)
        else:
            self.running = False
        self._dirty = True

    def on_touch(self, raw_x, raw_y):
        x, y = TouchScreen.map_coords_270(raw_x, raw_y)
        # Top-left tap = back
        if x < 44 and y < 30 and self.page != PG_HOME:
            self.goto(PG_HOME); return
        p = self.page
        if   p == PG_HOME:   self._home_touch(x, y)
        elif p == PG_AGENT:  self._agent_touch(x, y)
        elif p == PG_VOICE:  self._voice_touch(x, y)
        elif p == PG_AUTH:   self._auth_touch(x, y)
        elif p == PG_SETUP:  self._setup_touch(x, y)
        elif p == PG_STATUS and x > 255 and y < 30: self._bg('status', pc.get_status)
        self._dirty = True

    def _home_touch(self, x, y):
        if y < 22: return
        col = min(2, x // 107)
        row = min(1, (y - 22) // 65)
        idx = row * 3 + col
        if idx < len(HOME_TARGETS):
            self.goto(HOME_TARGETS[idx])

    def _agent_touch(self, x, y):
        # MIC button bottom-right
        if x > 268 and y > 144:
            self._toggle_voice()
        # Send pending transcript
        elif self.voice_text and 8 < x < 260 and 158 < y < LH:
            if not self.agent_busy:
                self._agent_send(self.voice_text)
                self.voice_text = ""

    def _voice_touch(self, x, y):
        # Big mic circle ~(160,88) r=36
        if 118 < x < 202 and 48 < y < 128:
            self._toggle_voice()
        # "Send to Agent" button
        elif self.voice_state == 'done' and self.voice_text and x > 195 and y > 149:
            self.goto(PG_AGENT)
            if self.voice_text and not self.agent_busy:
                self._agent_send(self.voice_text)
                self.voice_text = ""

    def _auth_touch(self, x, y):
        if 74 < y < 112:
            bw = (LW - 24) // 3
            col = min(2, (x - 8) // (bw + 4))
            self._auth_action(col)

    def _setup_touch(self, x, y):
        IH, Y0 = 22, 26
        for i in range(5):
            iy = Y0 + i * IH
            if iy < y < iy + IH:
                self.setup_sel = i
                self._setup_action(i)
                break

    # ── Voice ─────────────────────────────────────────────────────────────────
    def _toggle_voice(self):
        if self.voice_state in ('idle', 'done', 'error'):
            ok = self.rec.start()
            if ok:
                self.voice_state = 'recording'
                self.voice_text  = ""
                # auto-stop
                def _auto():
                    time.sleep(vc.MAX_SECS)
                    if self.voice_state == 'recording':
                        self._stop_recording()
                threading.Thread(target=_auto, daemon=True).start()
            else:
                self.voice_state = 'error'
                self.voice_err   = self.rec.error or "Failed to open mic"
        elif self.voice_state == 'recording':
            self._stop_recording()
        self._dirty = True

    def _stop_recording(self):
        self.voice_state = 'processing'
        self._dirty = True
        audio = self.rec.stop()

        def _transcribe():
            text, err = vc.transcribe(audio)
            if err:
                self.voice_state = 'error'
                self.voice_err   = err
                self.voice_text  = ""
            else:
                self.voice_state = 'done'
                self.voice_text  = text or ""
            # Auto-send if already on Agent page
            if self.page == PG_AGENT and self.voice_text and not self.agent_busy:
                self._agent_send(self.voice_text)
                self.voice_text = ""
            self._dirty = True

        threading.Thread(target=_transcribe, daemon=True).start()

    # ── Agent ─────────────────────────────────────────────────────────────────
    def _agent_send(self, message):
        if self.agent_busy: return
        self.agent_busy = True
        self.agent_msg  = "Thinking..."
        self.agent_hist.append(('you', message))
        self._dirty = True

        model = pc.get_profile_model(self.cfg.get('profile', 'claude'))

        def _run():
            reply, ok = pc.agent_message(message, model=model or None)
            self.agent_hist.append(('ai', reply[:400]))
            self.agent_scroll = max(0, len(self.agent_hist) - 5)
            self.agent_busy   = False
            self.agent_msg    = ""
            self.voice_state  = 'idle'
            self._dirty = True

        threading.Thread(target=_run, daemon=True).start()

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _auth_action(self, sel):
        if self.auth_busy: return
        self.auth_busy   = True
        self.auth_result = "Working..."
        self._dirty = True

        def _run():
            if sel == 0:   ok, msg = pc.auth_login()
            elif sel == 1: ok, msg = pc.auth_logout()
            else:          msg = pc.auth_status()
            self.auth_result = (msg or "Done")[:80]
            self.auth_busy   = False
            self._bg('auth', pc.auth_status)
            self._dirty = True

        threading.Thread(target=_run, daemon=True).start()

    # ── Setup ─────────────────────────────────────────────────────────────────
    def _setup_action(self, sel):
        items = ['Model Status', 'Profile', 'Onboard', 'Gateway', 'Back']
        item  = items[sel]
        if item == 'Back':
            self.goto(PG_HOME)
        elif item == 'Model Status':
            self.setup_result = "Model ready" if self.rec.model_ready else "Model loading..."
        elif item == 'Profile':
            profs = self.setup_profiles or ['claude', 'gemini']
            cur   = self.cfg.get('profile', 'claude')
            try:   nxt = profs[(profs.index(cur) + 1) % len(profs)]
            except: nxt = profs[0]
            self.cfg['profile'] = nxt
            save_cfg(self.cfg)
            self.setup_result = f"Profile: {nxt}"
        elif item == 'Onboard':
            self.setup_result = "Running onboard..."
            def _run():
                ok, msg = pc.run_onboard()
                self.setup_result = (msg or "Done")[:60]
                self._dirty = True
            threading.Thread(target=_run, daemon=True).start()
        elif item == 'Gateway':
            ok, msg = pc.start_gateway()
            self.setup_result = msg[:60]
        self._dirty = True

    # ── Auth helper ───────────────────────────────────────────────────────────
    def _auth_ok(self):
        r = self._get('auth')
        if r and r[0] == 'ok':
            t = r[1].lower()
            return any(w in t for w in ('logged in', 'authenticated', 'active', 'ok'))
        return False

    # ── Drawing ───────────────────────────────────────────────────────────────
    def draw(self):
        img = Image.new('RGB', (LW, LH), BG)
        d   = ImageDraw.Draw(img)
        p   = self.page
        if   p == PG_HOME:   self._draw_home(d)
        elif p == PG_AGENT:  self._draw_agent(d)
        elif p == PG_VOICE:  self._draw_voice(d)
        elif p == PG_SKILLS: self._draw_skills(d)
        elif p == PG_AUTH:   self._draw_auth(d)
        elif p == PG_SETUP:  self._draw_setup(d)
        elif p == PG_STATUS: self._draw_status(d)
        self.fb.show(img)
        self._dirty = False

    def _draw_home(self, d):
        rv  = self._get('version')
        ver = rv[1] if rv and rv[0] == 'ok' else '...'
        aok = self._auth_ok()
        topbar(d, f"PicoClaw  v{ver}", dot=OK if aok else ERR)

        # 3×2 button grid — y=22..154
        bw, bh = LW // 3, (LH - 44) // 2
        for i, (lbl, ico) in enumerate(zip(HOME_LABELS, HOME_ICONS)):
            col, row = i % 3, i // 3
            x0 = col * bw + 4;       y0 = 24 + row * bh + 4
            x1 = x0 + bw - 8;        y1 = y0 + bh - 8
            sel = (i == self.home_sel)
            rrect(d, x0, y0, x1, y1, fill=SEL if sel else BTN, outline=ACCENT if sel else None)
            d.text((x0 + 8, y0 + 6), ico, font=FN, fill=ACCENT if sel else DIM)
            centered(d, lbl, (x0+x1)//2, (y0+y1)//2 + 6, FM, TEXT if sel else DIM)

        # Status strip
        d.rectangle([0, LH-18, LW, LH], fill=PANEL)
        s = self.stats
        stat_str = f"CPU:{s.get('cpu','?')} RAM:{s.get('mem','?')} T:{s.get('temp','?')} IP:{s.get('ip','?')}"
        d.text((8, LH-15), stat_str, font=FN, fill=DIM)
        prof = self.cfg.get('profile', 'claude')
        d.text((LW - 70, LH-15), f"[{prof}]", font=FN, fill=ACCENT)

    def _draw_agent(self, d):
        topbar(d, "< Agent", dot=OK if self._auth_ok() else WARN)
        # Conversation area y=22..143
        y = 26
        hist = self.agent_hist
        start = max(0, len(hist) - 4 - self.agent_scroll)
        shown = hist[start:start + 4]
        
        if not shown:
            centered(d, "Tap [MIC] to speak", LW//2, 80, FM, DIM)
        else:
            for role, text in shown:
                y = drawbubble(d, y, role, text, font=FN)
                if y > 143: break

        if self.agent_busy:
            d.text((12, 131), self.agent_msg, font=FN, fill=WARN)

        # Bottom bar y=143..172
        d.rectangle([0, 143, LW, LH], fill=PANEL)
        d.line([0, 143, LW, 143], fill=DIM, width=1)
        
        if self.voice_state == 'recording':
            drawwaveform(d, 8, 150, 240, 14, self.rec.level)
            d.text((22, 160), "Listening... press knob to stop", font=FN, fill=ACCENT)
        elif self.voice_state == 'processing':
            d.text((8, 150), "Transcribing...", font=FS, fill=WARN)
        elif self.voice_text:
            d.text((8, 147), f"> {self.voice_text[:34]}", font=FS, fill=TEXT)
            d.text((8, 160), "Press knob to send to agent", font=FN, fill=ACCENT)
        else:
            d.text((8, 153), "Tap [MIC] or knob to record voice", font=FN, fill=DIM)
            
        mic_col = REC if self.voice_state == 'recording' else BTNH
        rrect(d, LW-48, 145, LW-4, LH-4, fill=mic_col)
        centered(d, "MIC", LW-26, 157, FM, TEXT)

    def _draw_voice(self, d):
        topbar(d, "< Voice", dot=DIM)
        SC = {
            'idle':       (DIM,  "Press knob or tap to record"),
            'recording':  (REC,  "Recording...  press to stop"),
            'processing': (WARN, "Transcribing audio..."),
            'done':       (OK,   "Done!"),
            'error':      (ERR,  "Error"),
        }
        col, label = SC.get(self.voice_state, (DIM, ""))
        # Big mic circle
        cx, cy, r = LW // 2, 85, 36
        d.ellipse([cx-r-4, cy-r-4, cx+r+4, cy+r+4], fill=PANEL, outline=col, width=2)
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=col if self.voice_state == 'recording' else BTN)
        centered(d, "MIC", cx, cy, FL, TEXT if self.voice_state == 'recording' else col)
        
        if self.voice_state == 'recording':
            # Live waveform around the circle
            drawwaveform(d, cx-50, 135, 100, 16, self.rec.level)
            centered(d, f"(max {vc.MAX_SECS}s)", LW//2, 153, FN, DIM)
        else:
            centered(d, label, LW//2, 127, FS, col)
            if self.voice_state == 'idle' and not self.rec.model_ready:
                centered(d, "Model loading...", LW//2, 139, FN, WARN)

        d.line([10, 146, LW-10, 146], fill=DIM, width=1)

        if self.voice_state == 'error':
            for i, l in enumerate(wordwrap(self.voice_err, LW-16, d, FN)[:2]):
                d.text((8, 150 + i*12), l, font=FN, fill=ERR)
        elif self.voice_text:
            for i, l in enumerate(wordwrap(self.voice_text, LW-16, d, FS)[:2]):
                d.text((8, 150 + i*13), l, font=FS, fill=TEXT)
            if self.voice_state == 'done':
                rrect(d, LW-122, LH-22, LW-4, LH-4, fill=BTNH)
                centered(d, "> Send to Agent", LW-63, LH-12, FN, TEXT)
        else:
            d.text((8, 151), "Transcript will appear here", font=FN, fill=DIM)

    def _draw_skills(self, d):
        r = self._get('skills')
        if r and r[0] == 'ok':
            self.skills = r[1] if isinstance(r[1], list) else []
        cnt = len(self.skills)
        topbar(d, f"< Skills  ({cnt})", dot=OK if cnt else DIM)
        if not r:
            centered(d, "Loading...", LW//2, LH//2, FM, WARN); return
        if not self.skills:
            centered(d, "No skills installed", LW//2, 70, FM, DIM)
            d.text((10, 88), "picoclaw skills install <name>", font=FS, fill=DIM); return
        
        IH, Y0 = 24, 26
        for i, sk in enumerate(self.skills[self.skills_scroll:self.skills_scroll + 5]):
            idx = i + self.skills_scroll
            y   = Y0 + i * IH
            sel = (idx == self.skills_sel)
            if sel: rrect(d, 4, y, LW-4, y+IH-2, fill=SEL)
            # split name and status if possible
            parts = sk.split()
            name  = parts[0] if parts else "?"
            d.text((12, y+5), name[:20], font=FS, fill=TEXT if sel else DIM)
            if len(parts) > 1:
                d.text((140, y+5), " ".join(parts[1:])[:26], font=FN, fill=OK if sel else DIM)

        d.rectangle([0, LH-18, LW, LH], fill=PANEL)
        d.text((8, LH-15), "Scroll: knob  Long-press: back", font=FN, fill=DIM)

    def _draw_auth(self, d):
        aok = self._auth_ok()
        topbar(d, "< Auth", dot=OK if aok else ERR)
        r = self._get('auth')
        status_line = (r[1].split('\n')[0][:42] if r and r[0] == 'ok' else "Checking...")
        rrect(d, 6, 25, LW-6, 70, fill=PANEL, r=4)
        d.ellipse([12, 36, 22, 46], fill=OK if aok else ERR)
        d.text((28, 35), status_line, font=FS, fill=OK if aok else DIM)
        if self.auth_result:
            for i, l in enumerate(wordwrap(self.auth_result, LW-20, d, FN)[:2]):
                d.text((12, 52 + i*11), l, font=FN, fill=DIM)
        LBLS = ["Login", "Logout", "Status"]
        bw = (LW - 24) // 3
        for i, lbl in enumerate(LBLS):
            x0 = 8 + i*(bw+4);  x1 = x0 + bw
            drawbtn(d, x0, 74, x1, 112, lbl, FM, sel=(i == self.auth_sel))
        if self.auth_busy:
            centered(d, "Working...", LW//2, 125, FS, WARN)
        d.rectangle([0, LH-18, LW, LH], fill=PANEL)
        d.text((8, LH-15), "Knob: select  Press: confirm  Long: back", font=FN, fill=DIM)

    def _draw_setup(self, d):
        topbar(d, "< Setup", dot=DIM)
        items = ['Model', 'Profile', 'Onboard', 'Gateway', 'Back']
        vals  = [
            "ready" if self.rec.model_ready else "wait",
            self.cfg.get('profile', 'claude'),
            "run", "start", "",
        ]
        IH, Y0 = 24, 26
        for i, (item, val) in enumerate(zip(items, vals)):
            y   = Y0 + i * IH
            sel = (i == self.setup_sel)
            if sel: rrect(d, 4, y, LW-4, y+IH-2, fill=SEL)
            d.text((20, y+5), item, font=FS, fill=TEXT if sel else DIM)
            if val:
                d.text((180, y+5), val, font=FN, fill=ACCENT if sel else DIM)
        
        if self.setup_result:
            d.rectangle([0, LH-40, LW, LH-20], fill=PANEL)
            d.text((8, LH-35), self.setup_result[:48], font=FN, fill=OK)
        
        # stats footer
        d.rectangle([0, LH-18, LW, LH], fill=PANEL)
        s = self.stats
        d.text((8, LH-15), f"CPU:{s.get('cpu')} RAM:{s.get('mem')} T:{s.get('temp')}", font=FN, fill=DIM)

    def _draw_status(self, d):
        topbar(d, "< Status", dot=DIM)
        rrect(d, LW-64, 3, LW-4, 19, fill=BTN, r=3)
        centered(d, "Refresh", LW-34, 11, FN, TEXT)
        r = self._get('status')
        if not r:
            centered(d, "Loading...", LW//2, LH//2, FM, WARN); return
        
        lines = r[1].split('\n') if r[0] == 'ok' else [f"Error: {r[1]}"]
        y = 28
        for line in lines[:8]:
            if y > LH - 24: break
            color = ACCENT if ':' in line else TEXT
            d.text((10, y), line[:46], font=FN, fill=color)
            y += 14
        
        d.rectangle([0, LH-18, LW, LH], fill=PANEL)
        d.text((8, LH-15), "Rotate knob to scroll (TBD)", font=FN, fill=DIM)

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        self.running = True
        print("PicoClaw app starting...")
        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                # Rotary
                rot = rotary.read_event(timeout=0)
                if rot is not None:
                    self.on_rotate(rot)

                # Keys (knob button)
                kev = keys.read_event(timeout=0)
                if kev:
                    if kev[0] == 'key_long_press':
                        self.on_long_press()
                    elif kev[0] == 'key_release' and kev[1] == 'ENTER' and not kev[4]:
                        self.on_press()

                # Touch
                tev = touch.read_event(timeout=0)
                if tev and tev[0] == 'touch_down':
                    self.on_touch(tev[1], tev[2])

                if self._dirty:
                    self.draw()

                time.sleep(0.03)   # ~33 fps

    def cleanup(self):
        if self.rec: self.rec.close()
        if self.fb:  self.fb.close()


if __name__ == '__main__':
    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()
        print("PicoClaw app stopped")
