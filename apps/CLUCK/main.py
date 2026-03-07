#!/usr/bin/env python3
"""
CLUCK v1.1.0: A quirky farm clock for NanoKVM.
─────────────────────────────────────────────
Fixes: Clock clamping, goofy zoom chicken, scrollable menu, long-press exit.
"""
import os, sys, time, random, math, threading, mmap
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from input import TouchScreen, GpioKeys, RotaryEncoder

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320
LW, LH = 320, 172
BG_COLOR = (0, 0, 0)

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

# Colors
WHITE  = (255, 255, 255)
RED    = (255, 50, 50)
ORANGE = (255, 165, 0)
YELLOW = (255, 215, 0)
PINK   = (255, 182, 193)
BROWN  = (139, 69, 19)
GREEN  = (34, 139, 34)
BLUE   = (100, 149, 237)
GRAY   = (128, 128, 128)
SKIN   = (255, 224, 189)

_FP = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def _f(sz, b=False):
    try: return ImageFont.truetype(_FB if b else _FP, sz)
    except: return ImageFont.load_default()

F_CLOCK = _f(48, True)
F_BIG   = _f(80, True)
F_MENU  = _f(14, True)
F_SM    = _f(11)

# ── Sprites & Drawing ────────────────────────────────────────────────────────
def draw_chicken(d, x, y, s=1.0, face_right=True, pecking=False, zoom=False):
    """Draw a simple chicken at (x,y) with scale s."""
    # Body
    w, h = 20*s, 16*s
    x0, y0 = x - w//2, y - h
    d.ellipse([x0, y0, x0+w, y0+h], fill=WHITE)
    
    # Head
    hw = 10*s
    hx = x0+w-4*s if face_right else x0-6*s
    hy = y0-6*s
    if pecking: hy += 8*s
    d.ellipse([hx, hy, hx+hw, hy+hw], fill=WHITE)
    
    # Beak & Comb
    bx = hx+hw if face_right else hx
    if face_right:
        d.polygon([(bx, hy+4*s), (bx, hy+8*s), (bx+6*s, hy+6*s)], fill=ORANGE)
        d.ellipse([bx, hy-4*s, bx+4*s, hy], fill=RED) 
    else:
        d.polygon([(bx, hy+4*s), (bx, hy+8*s), (bx-6*s, hy+6*s)], fill=ORANGE)
        d.ellipse([bx-4*s, hy-4*s, bx, hy], fill=RED)
    
    # Eyes
    if zoom:
        er = 4*s
        d.ellipse([hx+s, hy+s, hx+s+er, hy+s+er], fill=WHITE, outline=BG_COLOR)
        d.ellipse([hx+5*s, hy+s, hx+5*s+er, hy+s+er], fill=WHITE, outline=BG_COLOR)
        d.ellipse([hx+2*s, hy+2*s, hx+2*s+2*s, hy+2*s+2*s], fill=BG_COLOR)
        d.ellipse([hx+6*s, hy+2*s, hx+6*s+2*s, hy+2*s+2*s], fill=BG_COLOR)
    else:
        ex = hx+6*s if face_right else hx+2*s
        d.rectangle([ex, hy+3*s, ex+2*s, hy+5*s], fill=BG_COLOR)
    
    # Legs
    lx = x0 + w//2
    d.line([lx-4*s, y0+h, lx-4*s, y0+h+6*s], fill=ORANGE, width=max(1,int(2*s)))
    d.line([lx+4*s, y0+h, lx+4*s, y0+h+6*s], fill=ORANGE, width=max(1,int(2*s)))

def draw_cow(d, x, y, s=1.0, face_right=True, zoom=False):
    w, h = 40*s, 26*s
    x0, y0 = x - w//2, y - h
    d.rectangle([x0, y0, x0+w, y0+h], fill=WHITE)
    d.rectangle([x0+4*s, y0+4*s, x0+12*s, y0+12*s], fill=BG_COLOR)
    d.rectangle([x0+24*s, y0+10*s, x0+32*s, y0+20*s], fill=BG_COLOR)
    # Head
    hx = x0+w-4*s if face_right else x0-10*s
    hy = y0-4*s
    d.rectangle([hx, hy, hx+14*s, hy+14*s], fill=WHITE)
    # Goofy Snout
    snw, snh = (20*s if zoom else 14*s), (14*s if zoom else 6*s)
    d.rectangle([hx-2*s, hy+8*s, hx+snw, hy+8*s+snh], fill=PINK)
    if zoom:
        # Giant nostrils
        d.ellipse([hx+2*s, hy+10*s, hx+6*s, hy+14*s], fill=BG_COLOR)
        d.ellipse([hx+12*s, hy+10*s, hx+16*s, hy+14*s], fill=BG_COLOR)
        # Eyelashes
        d.line([hx, hy, hx-4*s, hy-4*s], fill=BG_COLOR, width=2)
        d.line([hx+4*s, hy, hx+4*s, hy-6*s], fill=BG_COLOR, width=2)
    
    d.line([x0+4*s, y0+h, x0+4*s, y0+h+8*s], fill=WHITE, width=max(1,int(3*s)))
    d.line([x0+w-4*s, y0+h, x0+w-4*s, y0+h+8*s], fill=WHITE, width=max(1,int(3*s)))

def draw_pig(d, x, y, s=1.0, face_right=True, zoom=False):
    w, h = 30*s, 20*s
    x0, y0 = x - w//2, y - h
    d.ellipse([x0, y0, x0+w, y0+h], fill=PINK)
    hx = x0+w-8*s if face_right else x0-6*s
    hy = y0+2*s
    d.ellipse([hx, hy, hx+14*s, hy+14*s], fill=PINK)
    # Massive Snout
    sx = hx+10*s if face_right else hx-4*s
    snw = 12*s if zoom else 6*s
    d.ellipse([sx, hy+4*s, sx+snw, hy+12*s], fill=(255,100,100))
    if zoom:
        # Spiral eyes
        d.arc([hx+2*s, hy+2*s, hx+6*s, hy+6*s], 0, 360, fill=BG_COLOR)
        d.arc([hx+8*s, hy+2*s, hx+12*s, hy+6*s], 0, 360, fill=BG_COLOR)

def draw_squirrel(d, x, y, s=1.0, face_right=True, zoom=False):
    w, h = 16*s, 12*s
    x0, y0 = x - w//2, y - h
    d.ellipse([x0, y0, x0+w, y0+h], fill=BROWN)
    tx = x0-8*s if face_right else x0+w
    d.ellipse([tx, y0-8*s, tx+12*s, y0+4*s], fill=BROWN)
    if zoom:
        # Giant cheeks and teeth
        d.ellipse([x-6*s, y-4*s, x+s, y+2*s], fill=PINK)
        d.ellipse([x, y-4*s, x+7*s, y+2*s], fill=PINK)
        d.rectangle([x-2*s, y, x+3*s, y+6*s], fill=WHITE) # Teeth

def draw_farmer(d, x, y, s=1.0, is_girl=False, zoom=False):
    w, h = 14*s, 24*s
    x0, y0 = x - w//2, y - h
    color = BLUE if not is_girl else PINK
    d.rectangle([x0, y0, x0+w, y0+h], fill=color)
    hy = y0 - 10*s
    d.ellipse([x0, hy, x0+w, hy+12*s], fill=SKIN)
    if not is_girl:
        d.rectangle([x0-2*s, hy, x0+w+2*s, hy+4*s], fill=BROWN)
        if zoom:
            # Huge beard
            d.polygon([(x0, hy+8*s), (x0+w, hy+8*s), (x+w//2, hy+20*s)], fill=GRAY)
            # Shocked eyes
            d.ellipse([x0+2*s, hy+2*s, x0+5*s, hy+5*s], fill=WHITE, outline=BG_COLOR)
            d.ellipse([x0+8*s, hy+2*s, x0+11*s, hy+5*s], fill=WHITE, outline=BG_COLOR)
    else:
        # Pigtails
        d.rectangle([x0-4*s, hy, x0, hy+4*s], fill=YELLOW)
        d.rectangle([x0+w, hy, x0+w+4*s, hy+4*s], fill=YELLOW)
        d.rectangle([x0-2*s, hy, x0+w+2*s, hy+4*s], fill=YELLOW)
        if zoom:
            # Surprised face
            d.ellipse([x0+2*s, hy+6*s, x0+w-2*s, hy+10*s], fill=RED) # O-mouth

def draw_tractor(d, x, y, s=1.0, face_right=True):
    w, h = 40*s, 24*s
    x0, y0 = x - w//2, y - h
    wx = x0+8*s if face_right else x0+w-8*s
    d.ellipse([wx-10*s, y0+h-10*s, wx+10*s, y0+h+10*s], fill=BG_COLOR, outline=RED, width=max(1,int(3*s)))
    d.rectangle([x0, y0, x0+w, y0+h], fill=GREEN)
    d.rectangle([x0+10*s, y0-10*s, x0+30*s, y0], fill=GREEN)

def draw_house(d, x, y, s=1.0):
    w, h = 60*s, 40*s
    x0, y0 = x - w//2, y - h
    d.rectangle([x0, y0, x0+w, y0+h], fill=RED)
    d.polygon([(x0-4*s, y0), (x0+w//2, y0-20*s), (x0+w+4*s, y0)], fill=BROWN)
    d.rectangle([x0+w//2-6*s, y0+h-16*s, x0+w//2+6*s, y0+h], fill=BG_COLOR)

# ── Logic ────────────────────────────────────────────────────────────────────
class Entity:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.x, self.y = x, y
        self.vx, self.vy = random.uniform(-1, 1), random.uniform(-0.5, 0.5)
        self.scale = 1.0
        self.state = "idle" 
        self.timer = 0
        self.face_right = (self.vx > 0)
        self.z = y

    def update(self):
        if self.state == "zoom":
            self.timer -= 1
            if self.timer <= 0:
                self.state = "idle"
                self.scale = 1.0
                self.x, self.y = random.randint(20, LW-20), random.randint(40, LH-10)
            return

        if random.random() < 0.02:
            self.state = random.choice(["idle", "walk", "walk", "peck"])
            self.vx, self.vy = random.uniform(-2, 2), random.uniform(-0.5, 0.5)
        
        if self.state == "walk":
            self.x += self.vx; self.y += self.vy
            if self.x < -20: self.x = LW+20
            if self.x > LW+20: self.x = -20
            self.y = max(40, min(LH-10, self.y))
            self.face_right = (self.vx > 0)
        
        # EVERYONE can zoom!
        if self.kind not in ("house", "tractor") and random.random() < 0.0015:
            self.state = "zoom"; self.scale = 5.0
            self.x, self.y = LW//2, LH-20; self.timer = 60

        self.z = self.y

    def draw(self, d):
        z = (self.state == "zoom")
        if self.kind == "chicken": draw_chicken(d, self.x, self.y, self.scale, self.face_right, self.state=="peck", z)
        elif self.kind == "cow":   draw_cow(d, self.x, self.y, self.scale, self.face_right, z)
        elif self.kind == "pig":   draw_pig(d, self.x, self.y, self.scale, self.face_right, z)
        elif self.kind == "squirrel": draw_squirrel(d, self.x, self.y, self.scale, self.face_right, z)
        elif self.kind == "farmer":   draw_farmer(d, self.x, self.y, self.scale, False, z)
        elif self.kind == "farmer's daughter": draw_farmer(d, self.x, self.y, self.scale, True, z)
        elif self.kind == "tractor":  draw_tractor(d, self.x, self.y, self.scale, self.face_right)
        elif self.kind == "house":    draw_house(d, self.x, self.y, self.scale)

class App:
    def __init__(self):
        self.fb = FB()
        self.clock_pos = [LW//2, LH//2]
        self.clock_scale = 1.0
        self.clock_target_scale = 1.0
        self.entities = []
        self.running = True
        self.menu_open = False
        self.menu_sel = 0
        self.menu_scroll = 0
        
        self.opts = {
            "chickens": True, "cows": False, "pigs": False, "squirrels": True,
            "farmer": False, "farmer's daughter": False, "tractor": False, "house": False
        }
        self.opt_keys = list(self.opts.keys()) + ["SAVE & EXIT"]
        self._spawn_entities()

    def _spawn_entities(self):
        self.entities = []
        for k, v in self.opts.items():
            if v:
                if k == "chickens":
                    for _ in range(3): self.entities.append(Entity("chicken", random.randint(20, LW), random.randint(40, LH)))
                else: self.entities.append(Entity(k, random.randint(20, LW), random.randint(40, LH)))

    def update_clock(self):
        if random.random() < 0.002: self.clock_target_scale = 2.0
        elif self.clock_scale > 1.1 and random.random() < 0.01: self.clock_target_scale = 1.0
        
        for e in self.entities:
            if e.kind == "chicken" and e.state == "peck":
                dx, dy = self.clock_pos[0]-e.x, self.clock_pos[1]-e.y
                if math.hypot(dx, dy) < 40:
                    self.clock_pos[0] += dx * 0.1; self.clock_pos[1] += dy * 0.1
        
        self.clock_scale += (self.clock_target_scale - self.clock_scale) * 0.1

    def draw(self):
        img = Image.new('RGB', (LW, LH), BG_COLOR)
        d = ImageDraw.Draw(img)
        
        self.entities.sort(key=lambda e: e.z)
        for e in self.entities:
            if not self.menu_open: e.update()
            e.draw(d)
        
        # Clock
        t_str = time.strftime("%H:%M")
        font = F_BIG if self.clock_scale > 1.5 else F_CLOCK
        bb = d.textbbox((0,0), t_str, font=font)
        cw, ch = bb[2]-bb[0], bb[3]-bb[1]
        cx, cy = (LW//2, LH//2) if self.clock_scale > 1.5 else self.clock_pos
        
        # STRICT CLAMPING
        cx = max(cw//2 + 2, min(LW - cw//2 - 2, cx))
        cy = max(ch//2 + 2, min(LH - ch//2 - 2, cy))
        self.clock_pos = [cx, cy]
        
        d.text((cx - cw//2, cy - ch//2), t_str, font=font, fill=WHITE)
        d.text((LW-20, 4), "@", font=F_MENU, fill=GRAY) # Gear

        if self.menu_open:
            d.rectangle([40, 10, LW-40, LH-10], fill=(20, 20, 30), outline=ACCENT)
            d.text((LW//2-30, 15), "SETTINGS", font=F_MENU, fill=ACCENT)
            start = self.menu_scroll
            for i, k in enumerate(self.opt_keys[start:start+6]):
                idx = i + start
                y = 35 + i*22
                sel = (idx == self.menu_sel)
                if k == "SAVE & EXIT":
                    label = f"{'>' if sel else ' '} {k}"
                    d.text((50, y), label, font=F_MENU, fill=GREEN if sel else WHITE)
                else:
                    val = self.opts[k]
                    label = f"{'>' if sel else ' '} {k.upper()}: {'ON' if val else 'OFF'}"
                    d.text((50, y), label, font=F_SM, fill=ORANGE if sel else WHITE)
        self.fb.show(img)

    def run(self):
        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                r = rotary.read_event(0)
                if r:
                    if self.menu_open:
                        self.menu_sel = (self.menu_sel + r) % len(self.opt_keys)
                        if self.menu_sel < self.menu_scroll: self.menu_scroll = self.menu_sel
                        elif self.menu_sel >= self.menu_scroll + 6: self.menu_scroll = self.menu_sel - 5
                    else: self.clock_pos[0] += r * 8
                
                kev = keys.read_event(0)
                if kev:
                    if kev[0] == 'key_long_press': self.running = False
                    elif kev[0] == 'key_release' and kev[1] == 'ENTER':
                        if self.menu_open:
                            k = self.opt_keys[self.menu_sel]
                            if k == "SAVE & EXIT": self.menu_open = False
                            else: self.opts[k] = not self.opts[k]; self._spawn_entities()
                        else: self.menu_open = True
                
                t = touch.read_event(0)
                if t and t[0] == 'touch_down':
                    tx, ty = TouchScreen.map_coords_270(t[1], t[2])
                    if tx > LW-40 and ty < 40: self.menu_open = not self.menu_open
                    elif self.menu_open and (tx < 40 or tx > LW-40): self.menu_open = False
                    elif not self.menu_open: self.clock_pos = [tx, ty]

                self.draw()
                time.sleep(0.05)
        self.fb.close()

if __name__ == "__main__":
    App().run()
