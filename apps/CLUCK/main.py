#!/usr/bin/env python3
"""
CLUCK: A quirky farm clock for NanoKVM.
Features:
- Animated chickens and farm animals.
- Erratic "in your face" moments.
- Interactive clock that avoids pecking.
- Configurable entities via gear menu.
"""
import os, sys, time, random, math, threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from input import TouchScreen, GpioKeys, RotaryEncoder

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320
LW, LH = 320, 172
BG_COLOR = (0, 0, 0)

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

# ── Sprites & Drawing ────────────────────────────────────────────────────────
def draw_chicken(d, x, y, s=1.0, face_right=True, pecking=False):
    """Draw a simple chicken at (x,y) with scale s."""
    # Body
    w, h = 20*s, 16*s
    x0, y0 = x - w//2, y - h
    body = [x0, y0, x0+w, y0+h]
    d.ellipse(body, fill=WHITE)
    
    # Head
    hw = 10*s
    hx = x0+w-4*s if face_right else x0-6*s
    hy = y0-6*s
    if pecking: hy += 8*s
    d.ellipse([hx, hy, hx+hw, hy+hw], fill=WHITE)
    
    # Beak & Wattle
    bx = hx+hw if face_right else hx
    d.polygon([(bx, hy+4*s), (bx, hy+8*s), (bx+(6*s if face_right else -6*s), hy+6*s)], fill=ORANGE)
    d.ellipse([bx+(0 if face_right else -2*s), hy-4*s, bx+(4*s if face_right else -6*s), hy], fill=RED) # Comb
    
    # Eye
    ex = hx+6*s if face_right else hx+2*s
    d.rectangle([ex, hy+3*s, ex+2*s, hy+5*s], fill=BG_COLOR)
    
    # Legs
    lx = x0 + w//2
    d.line([lx-4*s, y0+h, lx-4*s, y0+h+6*s], fill=ORANGE, width=int(2*s))
    d.line([lx+4*s, y0+h, lx+4*s, y0+h+6*s], fill=ORANGE, width=int(2*s))

def draw_cow(d, x, y, s=1.0, face_right=True):
    w, h = 40*s, 26*s
    x0, y0 = x - w//2, y - h
    d.rectangle([x0, y0, x0+w, y0+h], fill=WHITE) # Body
    # Spots
    d.rectangle([x0+4*s, y0+4*s, x0+12*s, y0+12*s], fill=BG_COLOR)
    d.rectangle([x0+24*s, y0+10*s, x0+32*s, y0+20*s], fill=BG_COLOR)
    # Head
    hx = x0+w-4*s if face_right else x0-10*s
    hy = y0-4*s
    d.rectangle([hx, hy, hx+14*s, hy+14*s], fill=WHITE)
    d.rectangle([hx, hy+8*s, hx+14*s, hy+14*s], fill=PINK) # Nose
    # Legs
    d.line([x0+4*s, y0+h, x0+4*s, y0+h+8*s], fill=WHITE, width=int(3*s))
    d.line([x0+w-4*s, y0+h, x0+w-4*s, y0+h+8*s], fill=WHITE, width=int(3*s))

def draw_pig(d, x, y, s=1.0, face_right=True):
    w, h = 30*s, 20*s
    x0, y0 = x - w//2, y - h
    d.ellipse([x0, y0, x0+w, y0+h], fill=PINK)
    # Head
    hx = x0+w-8*s if face_right else x0-6*s
    hy = y0+2*s
    d.ellipse([hx, hy, hx+14*s, hy+14*s], fill=PINK)
    # Snout
    sx = hx+10*s if face_right else hx-2*s
    d.ellipse([sx, hy+4*s, sx+6*s, hy+10*s], fill=(255,100,100))

def draw_squirrel(d, x, y, s=1.0, face_right=True):
    w, h = 16*s, 12*s
    x0, y0 = x - w//2, y - h
    d.ellipse([x0, y0, x0+w, y0+h], fill=BROWN)
    # Tail
    tx = x0-8*s if face_right else x0+w
    d.ellipse([tx, y0-8*s, tx+12*s, y0+4*s], fill=BROWN)

def draw_farmer(d, x, y, s=1.0, is_girl=False):
    # Body
    w, h = 14*s, 24*s
    x0, y0 = x - w//2, y - h
    color = BLUE if not is_girl else PINK
    d.rectangle([x0, y0, x0+w, y0+h], fill=color)
    # Head
    hy = y0 - 10*s
    d.ellipse([x0, hy, x0+w, hy+12*s], fill=SKIN)
    # Hat/Hair
    if not is_girl:
        d.rectangle([x0-2*s, hy, x0+w+2*s, hy+4*s], fill=BROWN) # Hat
    else:
        d.rectangle([x0-2*s, hy, x0+w+2*s, hy+4*s], fill=YELLOW) # Hair

def draw_tractor(d, x, y, s=1.0, face_right=True):
    w, h = 40*s, 24*s
    x0, y0 = x - w//2, y - h
    # Big wheel
    wx = x0+8*s if face_right else x0+w-8*s
    d.ellipse([wx-10*s, y0+h-10*s, wx+10*s, y0+h+10*s], fill=BG_COLOR, outline=RED, width=int(3*s))
    # Body
    d.rectangle([x0, y0, x0+w, y0+h], fill=GREEN)
    # Cabin
    d.rectangle([x0+10*s, y0-10*s, x0+30*s, y0], fill=GREEN)

def draw_house(d, x, y, s=1.0):
    w, h = 60*s, 40*s
    x0, y0 = x - w//2, y - h
    d.rectangle([x0, y0, x0+w, y0+h], fill=RED)
    # Roof
    d.polygon([(x0-4*s, y0), (x+10*s, y0-20*s), (x0+w+4*s, y0)], fill=BROWN)
    # Door
    d.rectangle([x-6*s, y0+h-16*s, x+6*s, y0+h], fill=BG_COLOR)

# ── Logic ────────────────────────────────────────────────────────────────────
class Entity:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.x, self.y = x, y
        self.vx, self.vy = random.uniform(-1, 1), random.uniform(-0.5, 0.5)
        self.scale = 1.0
        self.state = "idle" # idle, walk, peck, zoom
        self.timer = 0
        self.face_right = (self.vx > 0)
        self.z = y  # depth sorting

    def update(self):
        if self.state == "zoom":
            self.timer -= 1
            if self.timer <= 0:
                self.state = "idle"
                self.scale = 1.0
                self.x = random.randint(20, LW-20)
                self.y = random.randint(40, LH-10)
            return

        # Movement
        if random.random() < 0.02: # Change state
            self.state = random.choice(["idle", "walk", "walk", "peck"])
            self.vx = random.uniform(-2, 2)
            self.vy = random.uniform(-0.5, 0.5)
        
        if self.state == "walk":
            self.x += self.vx
            self.y += self.vy
            self.x = max(10, min(LW-10, self.x))
            self.y = max(40, min(LH-10, self.y))
            self.face_right = (self.vx > 0)
        
        # Random Zoom (In your face!)
        if self.kind == "chicken" and random.random() < 0.001:
            self.state = "zoom"
            self.scale = 5.0
            self.x, self.y = LW//2, LH-20
            self.timer = 60 # 2 seconds

        self.z = self.y # Update depth

    def draw(self, d):
        if self.kind == "chicken": draw_chicken(d, self.x, self.y, self.scale, self.face_right, self.state=="peck")
        elif self.kind == "cow":   draw_cow(d, self.x, self.y, self.scale, self.face_right)
        elif self.kind == "pig":   draw_pig(d, self.x, self.y, self.scale, self.face_right)
        elif self.kind == "squirrel": draw_squirrel(d, self.x, self.y, self.scale, self.face_right)
        elif self.kind == "farmer":   draw_farmer(d, self.x, self.y, self.scale, False)
        elif self.kind == "daughter": draw_farmer(d, self.x, self.y, self.scale, True)
        elif self.kind == "tractor":  draw_tractor(d, self.x, self.y, self.scale, self.face_right)
        elif self.kind == "house":    draw_house(d, self.x, self.y, self.scale)

class App:
    def __init__(self):
        from framebuffer import FB
        self.fb = FB()
        self.clock_pos = [LW-60, 40]
        self.clock_scale = 1.0
        self.clock_target_scale = 1.0
        self.entities = []
        self.running = True
        self.menu_open = False
        self.menu_sel = 0
        
        # Config
        self.opts = {
            "chickens": True,
            "cows": False,
            "pigs": False,
            "squirrels": True,
            "farmer": False,
            "daughter": False,
            "tractor": False,
            "house": False
        }
        self.opt_keys = list(self.opts.keys())
        self._spawn_entities()

    def _spawn_entities(self):
        self.entities = []
        if self.opts["house"]:    self.entities.append(Entity("house", 40, 60))
        if self.opts["tractor"]:  self.entities.append(Entity("tractor", LW-40, 80))
        
        count = 3 if self.opts["chickens"] else 0
        for _ in range(count): self.entities.append(Entity("chicken", random.randint(20, LW), random.randint(40, LH)))
        
        if self.opts["cows"]: self.entities.append(Entity("cow", random.randint(20, LW), random.randint(40, LH)))
        if self.opts["pigs"]: self.entities.append(Entity("pig", random.randint(20, LW), random.randint(40, LH)))
        if self.opts["squirrels"]: self.entities.append(Entity("squirrel", random.randint(20, LW), random.randint(40, LH)))
        if self.opts["farmer"]: self.entities.append(Entity("farmer", random.randint(20, LW), random.randint(40, LH)))
        if self.opts["daughter"]: self.entities.append(Entity("daughter", random.randint(20, LW), random.randint(40, LH)))

    def update_clock(self):
        # Random big clock moment
        if random.random() < 0.002:
            self.clock_target_scale = 2.0
        elif self.clock_scale > 1.1 and random.random() < 0.01:
            self.clock_target_scale = 1.0
            
        # Move clock away from chickens if pecking
        for e in self.entities:
            if e.kind == "chicken" and e.state == "peck":
                dx = self.clock_pos[0] - e.x
                dy = self.clock_pos[1] - e.y
                dist = math.hypot(dx, dy)
                if dist < 40:
                    self.clock_pos[0] += dx * 0.1
                    self.clock_pos[1] += dy * 0.1
        
        # Clamp clock
        self.clock_pos[0] = max(40, min(LW-40, self.clock_pos[0]))
        self.clock_pos[1] = max(20, min(LH-20, self.clock_pos[1]))
        
        # Smooth scale
        self.clock_scale += (self.clock_target_scale - self.clock_scale) * 0.1

    def draw(self):
        img = Image.new('RGB', (LW, LH), BG_COLOR)
        d = ImageDraw.Draw(img)
        
        # Draw entities sorted by Y (depth)
        self.entities.sort(key=lambda e: e.z)
        for e in self.entities:
            e.update()
            e.draw(d)
        
        # Draw Clock
        t_str = time.strftime("%H:%M")
        font = F_BIG if self.clock_scale > 1.5 else F_CLOCK
        bb = d.textbbox((0,0), t_str, font=font)
        cw, ch = bb[2]-bb[0], bb[3]-bb[1]
        cx, cy = self.clock_pos
        
        # Center clock if big
        if self.clock_scale > 1.5:
            cx, cy = LW//2, LH//2
            
        d.text((cx - cw//2, cy - ch//2), t_str, font=font, fill=WHITE)
        
        # Gear Icon (Top Right)
        d.text((LW-20, 4), "@", font=F_MENU, fill=GRAY)

        # Menu Overlay
        if self.menu_open:
            d.rectangle([20, 20, LW-20, LH-20], fill=(20, 20, 30), outline=WHITE)
            d.text((100, 24), "OPTIONS", font=F_MENU, fill=WHITE)
            y = 44
            for i, k in enumerate(self.opt_keys):
                if y > LH-30: break
                sel = (i == self.menu_sel)
                val = self.opts[k]
                label = f"{'>' if sel else ' '} {k.upper()}: {'ON' if val else 'OFF'}"
                d.text((40, y), label, font=F_MENU, fill=ORANGE if sel else WHITE)
                y += 16

        self.fb.show(img)

    def run(self):
        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                # Input
                r = rotary.read_event(0)
                if r:
                    if self.menu_open:
                        self.menu_sel = (self.menu_sel + r) % len(self.opt_keys)
                    else:
                        # Rotate moves clock for fun
                        self.clock_pos[0] += r * 5

                k = keys.read_event(0)
                if k and k[0] == 'key_release' and k[1] == 'ENTER':
                    if self.menu_open:
                        key = self.opt_keys[self.menu_sel]
                        self.opts[key] = not self.opts[key]
                        self._spawn_entities()
                    else:
                        self.menu_open = True
                
                t = touch.read_event(0)
                if t and t[0] == 'touch_down':
                    tx, ty = TouchScreen.map_coords_270(t[1], t[2])
                    # Toggle menu
                    if tx > LW-30 and ty < 30:
                        self.menu_open = not self.menu_open
                    elif self.menu_open and (tx < 20 or tx > LW-20 or ty < 20 or ty > LH-20):
                        self.menu_open = False
                    elif not self.menu_open:
                        # Move clock to touch
                        self.clock_pos = [tx, ty]

                if not self.menu_open:
                    self.update_clock()
                
                self.draw()
                time.sleep(0.08)

if __name__ == "__main__":
    App().run()
