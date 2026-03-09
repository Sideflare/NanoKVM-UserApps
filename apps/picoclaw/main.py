#!/usr/bin/env python3
"""
PicoClaw NanoKVM Screen App  v1.3.0
────────────────────────────────────
Consolidated Settings + Improved Voice + Better Navigation/Exit.
"""

import os, sys, time, json, threading, mmap, textwrap, socket, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import qrcode

import picoclaw_cli as pc
import voice as vc
from input import TouchScreen, GpioKeys, RotaryEncoder

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320
LW, LH = 320, 172

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
    try:
        import psutil
        cpu = f"{psutil.cpu_percent()}%"
        mem = f"{psutil.virtual_memory().percent}%"
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = f"{int(f.read()) // 1000}°C"
        except: temp = "?"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]; s.close()
        except: ip = "127.0.0.1"
        return {"cpu": cpu, "mem": mem, "temp": temp, "ip": ip}
    except: return {"cpu": "?", "mem": "?", "temp": "?", "ip": "?"}

class FB:
    def __init__(self):
        sz = PW * PH * 2
        self.fd  = os.open('/dev/fb0', os.O_RDWR)
        self.mm  = mmap.mmap(self.fd, sz, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self.arr = np.frombuffer(self.mm, dtype=np.uint16).reshape(PH, PW)
    def show(self, img: Image.Image):
        p = img.rotate(90, expand=True)
        a = np.array(p, dtype=np.uint16)
        self.arr[:, :] = (a[:, :, 0] >> 3 << 11) | (a[:, :, 1] >> 2 << 5) | (a[:, :, 2] >> 3)
    def close(self):
        self.mm.close(); os.close(self.fd)

# ── UI Helpers ────────────────────────────────────────────────────────────────
def rrect(d, x0, y0, x1, y1, fill=None, outline=None, r=4):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline)

def centered(d, text, cx, cy, font, color):
    bb = d.textbbox((0, 0), text, font=font)
    d.text((cx - (bb[2]-bb[0])//2, cy - (bb[3]-bb[1])//2), text, font=font, fill=color)

WHITE = (255, 255, 255)

def topbar(d, title, dot=OK, back_sel=False):
    d.rectangle([0, 0, LW, 21], fill=SEL if back_sel else PANEL)
    d.text((8, 3), "\u2190 BACK", font=FT, fill=WHITE if back_sel else ACCENT)
    centered(d, title, LW//2 + 20, 11, FT, TEXT)
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
        else: cur = t
    if cur: lines.append(cur)
    return lines

def drawbubble(d, y, role, text, font=FN):
    is_user = (role == 'you')
    color   = USER_MSG if is_user else AI_MSG
    max_w   = LW - 60
    lines   = wordwrap(text, max_w - 20, d, font)
    if not lines: return y
    lh = font.getbbox("A")[3] + 2
    bh = len(lines) * lh + 12
    bw = max([d.textbbox((0, 0), l, font=font)[2] for l in lines]) + 16
    x0 = LW - bw - 8 if is_user else 8
    x1 = x0 + bw
    rrect(d, x0, y, x1, y + bh, fill=color, r=8)
    ty = y + 6
    for line in lines:
        d.text((x0 + 8, ty), line, font=font, fill=TEXT)
        ty += lh
    return y + bh + 6

def drawwaveform(d, x, y, w, h, level):
    v = min(h, int(level / 3000 * h)) if level > 0 else 2
    rrect(d, x, y + h//2 - v//2, x + w, y + h//2 + v//2, fill=ACCENT if level > 500 else DIM, r=2)

# ── Pages ──────────────────────────────────────────────────────────────────
PG_HOME, PG_AGENT, PG_SKILLS, PG_SETTINGS, PG_STATUS = range(5)
# 4 pages — EXIT removed (use back arrow or long-press)
HOME_TARGETS = [PG_AGENT, PG_SKILLS, PG_SETTINGS, PG_STATUS]
HOME_LABELS  = ["Agent Chat", "Skills", "Settings", "Status/Claw"]
HOME_ICONS   = [">_ ", "## ", "{} ", " \u26a1 "]

# Claw service state colors: red=stopped, yellow=starting, green=running
CLAW_STOPPED  = (210, 40, 40)
CLAW_STARTING = (230, 185, 0)
CLAW_RUNNING  = (0, 200, 100)

class App:
    def __init__(self):
        self.fb  = FB()
        self.rec = vc.Recorder()
        self.cfg = {"profile": "claude"}
        self._cache_lock = threading.Lock()
        self._cache = {}
        self._dirty = True
        self.running = True

        self.page     = PG_HOME
        self.home_sel = 0
        self.sub_sel  = 0 # 0=Back bar, 1=Content

        self.agent_hist   = []
        self.agent_scroll = 0
        self.agent_busy   = False
        self.voice_state  = "idle"
        self.voice_text   = ""
        self.voice_timer  = 0

        self.settings_sel = 0
        self.stats        = {}
        self.skills       = []
        self.skills_sel   = 0
        self.auth_qr      = None
        self.qr_mode      = False

        # Claw service state: "stopped", "starting", "running"
        self.claw_state   = "stopped"
        self._check_claw_state()

        threading.Thread(target=self._stats_loop, daemon=True).start()
        self._bg('auth', pc.auth_status)
        self._bg('version', pc.get_version)

    def _check_claw_state(self):
        try:
            r = subprocess.run(["systemctl", "is-active", "picoclaw"],
                               capture_output=True, text=True, timeout=2)
            self.claw_state = "running" if r.stdout.strip() == "active" else "stopped"
        except:
            self.claw_state = "stopped"

    def _toggle_claw(self):
        def _run():
            self.claw_state = "starting"
            self._dirty = True
            if self.claw_state != "running":
                subprocess.run(["systemctl", "start", "picoclaw"], timeout=10)
            else:
                subprocess.run(["systemctl", "stop", "picoclaw"], timeout=10)
            self._check_claw_state()
            self._dirty = True
        threading.Thread(target=_run, daemon=True).start()

    def _stats_loop(self):
        while self.running:
            self.stats = get_sys_stats()
            self._check_claw_state()
            if self.page in (PG_HOME, PG_STATUS, PG_SETTINGS): self._dirty = True
            time.sleep(3)

    def _bg(self, key, fn, *args):
        def _run():
            try:
                r = fn(*args)
                with self._cache_lock: self._cache[key] = ('ok', r)
            except Exception as e:
                with self._cache_lock: self._cache[key] = ('err', str(e))
            self._dirty = True
        threading.Thread(target=_run, daemon=True).start()

    def _get(self, key):
        with self._cache_lock: return self._cache.get(key)

    def goto(self, page):
        if page is None: self.running = False; return
        self.page = page
        self.sub_sel = 1 if page == PG_HOME else 0
        self._dirty = True
        self.qr_mode = False
        if page == PG_SKILLS: self._bg('skills', pc.list_skills)

    def _gen_auth_qr(self):
        ip = self.stats.get('ip', '127.0.0.1')
        url = f"http://{ip}:8080/picoclaw_login"
        qr = qrcode.QRCode(box_size=3, border=1)
        qr.add_data(url); qr.make(fit=True)
        self.auth_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        self.qr_mode = True; self._dirty = True

    def on_rotate(self, delta):
        if self.page == PG_HOME:
            self.home_sel = (self.home_sel + delta) % len(HOME_TARGETS)
        else:
            if self.sub_sel == 0: # on top bar
                if delta != 0: self.sub_sel = 1 # move to content
            else: # in content
                p = self.page
                if   p == PG_AGENT:    self.agent_scroll = max(0, self.agent_scroll + delta)
                elif p == PG_SETTINGS: self.settings_sel = (self.settings_sel + delta) % 8
                elif p == PG_SKILLS:   self.skills_sel   = max(0, min(len(self.skills)-1, self.skills_sel + delta))
                # can't move back to bar via scroll yet, keep it simple
        self._dirty = True

    def on_press(self):
        if self.qr_mode: self.qr_mode = False; self._dirty = True; return
        if self.page != PG_HOME and self.sub_sel == 0:
            self.goto(PG_HOME); return

        p = self.page
        if   p == PG_HOME:     self.goto(HOME_TARGETS[self.home_sel])
        elif p == PG_AGENT:    self._toggle_voice()
        elif p == PG_SETTINGS: self._settings_action(self.settings_sel)
        elif p == PG_STATUS:   self._toggle_claw()
        self._dirty = True

    def _toggle_voice(self):
        if self.voice_state in ('idle', 'done', 'error'):
            print("Voice: Stopping KVM services...")
            subprocess.run(["systemctl", "stop", "nanokvm", "kvmcomm"])
            time.sleep(1.0)
            if self.rec.start():
                self.voice_state = 'recording'
                self.voice_timer = vc.MAX_SECS
                threading.Thread(target=self._auto_stop_countdown, daemon=True).start()
            else: 
                self.voice_state = 'error'
                subprocess.run(["systemctl", "start", "nanokvm", "kvmcomm"])
        elif self.voice_state == 'recording':
            self._stop_recording()
        self._dirty = True

    def _auto_stop_countdown(self):
        while self.voice_state == 'recording' and self.voice_timer > 0:
            time.sleep(1)
            self.voice_timer -= 1
            self._dirty = True
        if self.voice_state == 'recording': self._stop_recording()

    def _stop_recording(self):
        if self.voice_state != 'recording': return
        self.voice_state = 'processing'
        self._dirty = True
        audio = self.rec.stop()
        print("Voice: Restarting KVM services...")
        subprocess.run(["systemctl", "start", "nanokvm", "kvmcomm"])
        def _trans():
            text, err = vc.transcribe(audio)
            if not err and text:
                self.voice_text = text
                self._agent_send(text)
            self.voice_state = 'idle'; self._dirty = True
        threading.Thread(target=_trans, daemon=True).start()

    def _agent_send(self, message):
        if self.agent_busy: return
        self.agent_busy = True
        self.agent_hist.append(('you', message))
        self._dirty = True
        def _run():
            reply, ok = pc.agent_message(message)
            self.agent_hist.append(('ai', reply[:400]))
            self.agent_busy = False; self._dirty = True
        threading.Thread(target=_run, daemon=True).start()

    def _settings_action(self, sel):
        if sel == 0: self._gen_auth_qr()
        elif sel == 7: self.goto(PG_HOME)

    def draw(self):
        img = Image.new('RGB', (LW, LH), BG)
        d = ImageDraw.Draw(img)
        if self.qr_mode: self._draw_qr(d); self.fb.show(img); self._dirty=False; return
        p = self.page
        if   p == PG_HOME:     self._draw_home(d)
        elif p == PG_AGENT:    self._draw_agent(d)
        elif p == PG_SKILLS:   self._draw_skills(d)
        elif p == PG_SETTINGS: self._draw_settings(d)
        elif p == PG_STATUS:   self._draw_status(d)
        self.fb.show(img)
        self._dirty = False

    def _draw_qr(self, d):
        topbar(d, "Scan to Login")
        if self.auth_qr:
            img_qr = self.auth_qr.resize((100, 100))
            d.bitmap((LW//2-50, 30), img_qr)
        centered(d, "Configure API Keys on Phone", LW//2, 140, FS, TEXT)
        centered(d, "Tap screen or press knob to back", LW//2, 155, FN, DIM)

    def _draw_home(self, d):
        ver = self._get('version')[1] if self._get('version') else "..."
        topbar(d, f"PicoClaw v{ver}")
        # 2x2 grid for 4 items — larger buttons, easier to read on small screen
        bw, bh = LW // 2, (LH - 44) // 2
        for i, (lbl, ico) in enumerate(zip(HOME_LABELS, HOME_ICONS)):
            col, row = i % 2, i // 2
            x0, y0 = col*bw+4, 24+row*bh+4
            x1, y1 = x0+bw-8, y0+bh-8
            sel = (i == self.home_sel)
            # Status/Claw button gets a dynamic color
            if i == 3:
                claw_col = {"running": CLAW_RUNNING, "starting": CLAW_STARTING,
                            "stopped": CLAW_STOPPED}.get(self.claw_state, CLAW_STOPPED)
                outline = claw_col
                fill = SEL if sel else (30, 15, 15) if self.claw_state=="stopped" else (10,30,15)
            else:
                fill, outline = (SEL if sel else BTN), (ACCENT if sel else None)
            rrect(d, x0, y0, x1, y1, fill=fill, outline=outline)
            d.text((x0+8, y0+5), ico, font=FM, fill=ACCENT if sel else DIM)
            centered(d, lbl, (x0+x1)//2, (y0+y1)//2+7, FS, TEXT if sel else DIM)
        s = self.stats
        stat_str = f"CPU:{s.get('cpu')} MEM:{s.get('mem')} {s.get('ip')}"
        d.text((8, LH-13), stat_str, font=FN, fill=DIM)

    def _draw_agent(self, d):
        topbar(d, "Agent Chat", back_sel=(self.sub_sel==0))
        y = 26
        for role, text in self.agent_hist[max(0, len(self.agent_hist)-3):]:
            y = drawbubble(d, y, role, text)
        d.rectangle([0, 143, LW, LH], fill=PANEL)
        if self.voice_state == 'recording':
            drawwaveform(d, 8, 150, 240, 14, self.rec.level)
            d.text((22, 160), f"Listening... ({self.voice_timer}s)", font=FN, fill=ACCENT)
        elif self.agent_busy:
            d.text((8, 153), "Thinking...", font=FN, fill=WARN)
        else:
            d.text((8, 153), "Press knob to speak", font=FN, fill=DIM)
        rrect(d, LW-48, 145, LW-4, LH-4, fill=REC if self.voice_state=='recording' else BTNH)
        centered(d, "MIC", LW-26, 157, FM, TEXT)

    def _draw_skills(self, d):
        topbar(d, "Skills", back_sel=(self.sub_sel==0))
        r = self._get('skills')
        if r and r[0]=='ok':
            self.skills = r[1]
            for i, sk in enumerate(self.skills[:5]):
                y = 26 + i*24
                sel = (self.sub_sel==1 and i == self.skills_sel)
                if sel: rrect(d, 4, y, LW-4, y+22, fill=SEL)
                d.text((12, y+5), sk[:40], font=FS, fill=TEXT if sel else DIM)
        else: centered(d, "Loading skills...", LW//2, LH//2, FM, DIM)

    def _draw_settings(self, d):
        topbar(d, "Settings", back_sel=(self.sub_sel==0))
        items = ["QR Login", "AI Profile", "Model Info", "Mic Check", "Onboard", "Gateway", "Clear Cache", "Back"]
        start = max(0, min(self.settings_sel-2, 3))
        for i, item in enumerate(items[start:start+5]):
            idx = i + start
            y = 26 + i*24
            sel = (self.sub_sel==1 and idx == self.settings_sel)
            if sel: rrect(d, 4, y, LW-4, y+22, fill=SEL)
            d.text((12, y+5), item, font=FS, fill=TEXT if sel else DIM)

    def _draw_status(self, d):
        claw_col = {"running": CLAW_RUNNING, "starting": CLAW_STARTING,
                    "stopped": CLAW_STOPPED}.get(self.claw_state, CLAW_STOPPED)
        topbar(d, "Status / Claw", dot=claw_col, back_sel=(self.sub_sel==0))
        y = 28
        for k, v in self.stats.items():
            d.text((10, y), f"{k.upper()}: {v}", font=FM, fill=TEXT)
            y += 18
        # CLAW START/STOP button
        y = LH - 36
        btn_lbl = "CLAW: STOP" if self.claw_state == "running" else \
                  "CLAW: STARTING..." if self.claw_state == "starting" else "CLAW: START"
        rrect(d, 8, y, LW-8, y+28, fill=claw_col, r=6)
        centered(d, btn_lbl, LW//2, y+14, FM, (10,10,10))

    def run(self):
        def _start_server():
            try: subprocess.run(["python3", "/userapp/picoclaw/login_server.py"])
            except: pass
        threading.Thread(target=_start_server, daemon=True).start()

        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                r = rotary.read_event(0)
                if r: self.on_rotate(r)
                k = keys.read_event(0)
                if k:
                    if k[0]=='key_long_press': self.running=False
                    elif k[0]=='key_release' and k[1]=='ENTER': self.on_press()
                t = touch.read_event(0)
                if t and t[0]=='touch_down':
                    tx, ty = TouchScreen.map_coords_270(t[1], t[2])
                    if ty < 30: self.goto(PG_HOME)
                    elif self.page == PG_HOME:
                        col, row = tx // (LW // 2), (ty-24) // ((LH-44)//2)
                        idx = row * 2 + col
                        if idx < len(HOME_TARGETS): self.goto(HOME_TARGETS[idx])
                    elif self.page == PG_AGENT and tx > 260 and ty > 140:
                        self._toggle_voice()
                    elif self.qr_mode: self.qr_mode = False; self._dirty = True
                if self._dirty: self.draw()
                time.sleep(0.05)
        self.fb.close(); self.rec.close()

if __name__ == "__main__":
    App().run()
