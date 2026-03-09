#!/usr/bin/env python3
"""
CLUCK v2.0.1 — Farm Clock for NanoKVM (South Park Edition)
- Barn: Classic style with cross, max 1 demon/pentagram.
- Jump Scares: Large goofy South Park-style animal faces slide in.
- Interactions:
  * Farmer & Daughter plant corn/flowers -> Chickens eat.
  * Chickens lay eggs -> Daughter collects.
  * Pigs wallow in mud -> Sometimes fly.
  * Daughter milks cow -> Splatter on screen/face.
  * Farmer tries to hump Goat -> Goat bites -> "Ouch!".
  * Farmer & Boyfriend hump Daughter -> Victory dance.
  * Squirrel hoards nuts -> Plants tree.
"""
import os, sys, time, random, math, mmap
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from input import TouchScreen, GpioKeys, RotaryEncoder

PW, PH = 172, 320
LW, LH = 320, 172
BG_COLOR = (0, 0, 0)

# ── Display ──────────────────────────────────────────────────────────────────
class FB:
    def __init__(self):
        sz = PW * PH * 2
        self.fd = os.open('/dev/fb0', os.O_RDWR)
        self.mm = mmap.mmap(self.fd, sz, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self.arr = np.frombuffer(self.mm, dtype=np.uint16).reshape(PH, PW)
    def show(self, img):
        p = img.rotate(90, expand=True)
        a = np.array(p, dtype=np.uint16)
        self.arr[:,:] = (a[:,:,0]>>3<<11)|(a[:,:,1]>>2<<5)|(a[:,:,2]>>3)
    def close(self): self.mm.close(); os.close(self.fd)

# ── Colors & Fonts ───────────────────────────────────────────────────────────
WHITE   = (255,255,255); RED    = (220, 50, 50); ORANGE = (255,165,  0)
YELLOW  = (255,215,  0); PINK   = (255,182,193); HOTPINK= (255,100,160)
BROWN   = (139, 69, 19); GREEN  = ( 34,139, 34); BLUE   = (100,149,237)
GRAY    = (128,128,128); SKIN   = (255,224,189); ACCENT = (  0,185,255)
STRAW   = (210,175, 50); DKBRN  = (100, 55, 10); PURPLE = (140, 40, 200)
JDG     = (0, 102, 51);  JDY    = (255, 222, 0); MUD    = (101, 67, 33)

_FP = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
def _f(sz, b=False):
    try: return ImageFont.truetype(_FB if b else _FP, sz)
    except: return ImageFont.load_default()

F_CLOCK=_f(48,True); F_BIG=_f(80,True); F_MENU=_f(14,True); F_SM=_f(11); F_BUBBLE=_f(10)

SPAWN_MAP = {
    "chickens": (3,"chicken"), "cows": (1,"cow"), "pigs": (1,"pig"),
    "squirrels": (1,"squirrel"), "goats": (1,"goat"), "farmer": (1,"farmer"),
    "farmer's daughter": (1,"farmer_daughter"), "boyfriend": (1,"boyfriend"),
    "tractor": (1,"tractor"), "barn": (1,"barn"),
}
LABEL_OVERRIDE = {"farmer's daughter":"Daughter","boyfriend":"Boyfriend"}
CAR_COLORS = [(220,50,50),(50,100,220),(50,180,50),JDY,(180,50,180),(50,200,200)]

# ── Sprites ──────────────────────────────────────────────────────────────────
def draw_chicken(d, x, y, s=1.0, face_right=True, pecking=False):
    w,h = 22*s,18*s; x0,y0 = x-w//2, y-h
    d.ellipse([x0,y0,x0+w,y0+h], fill=WHITE)
    hw=12*s; hx=x0+w-6*s if face_right else x0-6*s; hy=y0-8*s+(8*s if pecking else 0)
    d.ellipse([hx,hy,hx+hw,hy+hw], fill=WHITE)
    bx=hx+hw if face_right else hx
    if face_right: d.polygon([(bx,hy+4*s),(bx,hy+8*s),(bx+8*s,hy+6*s)], fill=ORANGE)
    else: d.polygon([(bx,hy+4*s),(bx,hy+8*s),(bx-8*s,hy+6*s)], fill=ORANGE)
    eye_x = hx+8*s if face_right else hx+4*s
    d.ellipse([eye_x-2*s,hy+3*s,eye_x+2*s,hy+7*s], fill=BG_COLOR)
    d.chord([hx+2*s,hy-4*s,hx+hw-2*s,hy+2*s], 180, 360, fill=RED)

def draw_cow(d, x, y, s=1.0, face_right=True, milking=False):
    w,h=44*s,28*s; x0,y0=x-w//2,y-h
    d.rectangle([x0,y0,x0+w,y0+h], fill=WHITE)
    d.ellipse([x0+4*s,y0+4*s,x0+16*s,y0+16*s], fill=BG_COLOR)
    d.ellipse([x0+25*s,y0+10*s,x0+38*s,y0+22*s], fill=BG_COLOR)
    hx=x0+w-2*s if face_right else x0-14*s; hy=y0-8*s
    d.rectangle([hx,hy,hx+16*s,hy+16*s], fill=WHITE)
    d.ellipse([hx+3*s,hy+3*s,hx+7*s,hy+7*s], fill=BG_COLOR)
    d.ellipse([hx+9*s,hy+3*s,hx+13*s,hy+7*s], fill=BG_COLOR)
    d.ellipse([hx+4*s,hy+8*s,hx+14*s,hy+15*s], fill=PINK)
    # Udder
    d.ellipse([x0+14*s,y0+h-2*s,x0+30*s,y0+h+6*s], fill=PINK)
    if milking:
        d.line([x0+18*s,y0+h+6*s,x0+18*s,y0+h+14*s], fill=WHITE, width=2)
        d.line([x0+26*s,y0+h+6*s,x0+26*s,y0+h+14*s], fill=WHITE, width=2)
    for lx in [x0+6*s,x0+w-6*s]: d.rectangle([lx-3*s,y0+h,lx+3*s,y0+h+8*s], fill=WHITE)

def draw_pig(d, x, y, s=1.0, face_right=True, muddy=False, flying=False):
    w,h=32*s,22*s; x0,y0=x-w//2,y-h
    col = (200,100,120) if muddy else PINK
    d.ellipse([x0,y0,x0+w,y0+h], fill=col)
    hx=x0+w-10*s if face_right else x0-6*s; hy=y0+2*s
    d.ellipse([hx,hy,hx+16*s,hy+16*s], fill=col)
    sx=hx+12*s if face_right else hx-6*s
    d.ellipse([sx,hy+5*s,sx+10*s,hy+13*s], fill=(160,80,90) if muddy else (255,130,150))
    ex = hx+6*s if face_right else hx+6*s
    d.ellipse([ex,hy+3*s,ex+2*s,hy+5*s], fill=BG_COLOR)
    d.ellipse([ex+4*s,hy+3*s,ex+6*s,hy+5*s], fill=BG_COLOR)
    for lx in [x0+6*s,x0+w-6*s]: d.rectangle([lx-2*s,y0+h-2*s,lx+2*s,y0+h+6*s], fill=col)
    if flying:
        d.ellipse([x0+8*s,y0-10*s,x0+24*s,y0+4*s], fill=WHITE) # Wing

def draw_squirrel(d, x, y, s=1.0, face_right=True, planting=False):
    w,h=16*s,14*s; x0,y0=x-w//2,y-h
    tx=x0-10*s if face_right else x0+w
    d.ellipse([tx,y0-8*s,tx+14*s,y0+h+4*s], fill=BROWN)
    d.ellipse([x0,y0,x0+w,y0+h], fill=BROWN)
    hx=x0+w-4*s if face_right else x0-4*s; hy=y0-8*s
    d.ellipse([hx,hy,hx+12*s,hy+12*s], fill=BROWN)
    # Cheeks
    if planting: d.ellipse([hx+(8*s if face_right else -2*s),hy+4*s,hx+(14*s if face_right else 4*s),hy+10*s], fill=(160,85,30))

def draw_goat(d, x, y, s=1.0, face_right=True, tongue=False):
    w,h=32*s,22*s; x0,y0=x-w//2,y-h
    d.ellipse([x0,y0,x0+w,y0+h], fill=(200,200,200))
    hx=x0+w-4*s if face_right else x0-8*s; hy=y0-4*s
    d.rectangle([hx,hy,hx+12*s,hy+12*s], fill=(200,200,200))
    # Horns
    d.line([hx+2*s,hy,hx,hy-6*s], fill=GRAY, width=2)
    d.line([hx+10*s,hy,hx+12*s,hy-6*s], fill=GRAY, width=2)
    if tongue:
        tx, ty = hx+12*s if face_right else hx, hy+8*s
        d.ellipse([tx-2*s,ty,tx+6*s,ty+8*s], fill=RED)
    for lx in [x0+5*s,x0+w-5*s]: d.rectangle([lx-2*s,y0+h,lx+2*s,y0+h+8*s], fill=(150,150,150))

def draw_farmer(d, x, y, s=1.0, spreading=False, humping=False):
    w,h=16*s,28*s; x0,y0=x-w//2,y-h; hy=y0-14*s
    d.rectangle([x0,y0,x0+w,y0+h], fill=BLUE)
    d.rectangle([x0+2*s,y0,x0+w-2*s,y0+10*s], fill=WHITE)
    d.ellipse([x0,hy,x0+w,hy+16*s], fill=SKIN)
    d.rectangle([x0-4*s,hy,x0+w+4*s,hy+4*s], fill=STRAW)
    d.rectangle([x0,hy-4*s,x0+w,hy+2*s], fill=STRAW)
    if humping:
        d.line([x0,y0+8*s,x0-6*s,y0+12*s], fill=SKIN, width=3)
        return
    a=math.sin(time.time()*8)*15 if spreading else 0
    d.line([x0,y0+6*s,x0-8*s,y0+10*s-a], fill=SKIN, width=max(1,int(3*s)))
    if not spreading: # Pitchfork
        px, py = x0+w+2*s, y0+4*s
        d.line([px, py+16*s, px, py-10*s], fill=GRAY, width=2)
        d.line([px-4*s, py-10*s, px+4*s, py-10*s], fill=GRAY, width=2)
        for i in range(3): d.line([px-4*s+i*4*s, py-10*s, px-4*s+i*4*s, py-18*s], fill=GRAY, width=2)

def draw_farmer_daughter(d, x, y, s=1.0, state="idle", splattered=False):
    humped = (state in ("humped","bent_over"))
    if state=="bent_over":
        w,h=30*s,15*s; x0,y0=x-w//2,y-h
        d.rectangle([x0+5*s,y0,x0+9*s,y0+15*s], fill=SKIN)
        d.rectangle([x0+11*s,y0,x0+15*s,y0+15*s], fill=SKIN)
        d.ellipse([x0,y0-5*s,x0+16*s,y0+10*s], fill=(80,120,200)) # Skirt up
        d.rectangle([x0+10*s,y0-2*s,x0+25*s,y0+6*s], fill=(220,60,100)) # Torso
        hx, hy_head = x0+22*s, y0-6*s
        d.ellipse([hx,hy_head,hx+14*s,hy_head+14*s], fill=SKIN)
        # Long hair
        d.ellipse([hx-4*s,hy_head-4*s,hx+18*s,hy_head+12*s], fill=YELLOW)
        if splattered: d.ellipse([hx+2*s,hy_head+2*s,hx+8*s,hy_head+8*s], fill=WHITE)
        return

    w,h=16*s,30*s; x0,y0=x-w//2,y-h; hy=y0-16*s
    d.rectangle([x0,y0,x0+w,y0+14*s], fill=(220,60,100))
    d.rectangle([x0+2*s,y0+14*s,x0+6*s,y0+25*s], fill=SKIN)
    d.rectangle([x0+10*s,y0+14*s,x0+14*s,y0+25*s], fill=SKIN)
    d.ellipse([x0,hy,x0+w,hy+18*s], fill=SKIN)
    # Long Hair
    d.ellipse([x0-4*s,hy-4*s,x0+w+4*s,hy+20*s], fill=YELLOW)
    if splattered: d.ellipse([x0+4*s,hy+6*s,x0+10*s,hy+12*s], fill=WHITE)
    if state=="spreading":
        a=math.sin(time.time()*10)*12
        d.line([x0+w,y0+8*s,x0+w+10*s,y0+8*s-a], fill=SKIN, width=max(1,int(3*s)))

def draw_boyfriend(d, x, y, s=1.0, humping=False, dancing=False):
    w,h=14*s,26*s; x0,y0=x-w//2,y-h; hy=y0-12*s
    d.rectangle([x0,y0,x0+w,y0+14*s], fill=WHITE)
    d.rectangle([x0,y0+14*s,x0+w,y0+h], fill=(60,90,200))
    d.ellipse([x0,hy,x0+w,hy+14*s], fill=SKIN)
    for i in range(5): d.line([x0+i*3*s,hy,x0+i*3*s,hy-5*s], fill=(100,60,20), width=max(1,int(s)))
    if humping or dancing:
        t=time.time()*15
        d.line([x0,y0+4*s,x0-8*s,y0+4*s-math.sin(t)*12], fill=SKIN, width=max(1,int(3*s)))
        d.line([x0+w,y0+4*s,x0+w+8*s,y0+4*s-math.cos(t)*12], fill=SKIN, width=max(1,int(3*s)))

def draw_tractor(d, x, y, s=1.0, face_right=True):
    w,h=46*s,30*s; x0,y0=x-w//2,y-h
    rwx = x0+6*s if face_right else x0+w-6*s
    d.ellipse([rwx-12*s,y0+h-24*s,rwx+12*s,y0+h], fill=(30,30,30))
    d.ellipse([rwx-6*s,y0+h-18*s,rwx+6*s,y0+h-6*s], fill=JDY)
    body_x = x0+12*s if face_right else x0+w-34*s
    d.rectangle([body_x, y0+h-18*s, body_x+22*s, y0+h-2*s], fill=JDG)
    cab_x = x0+14*s if face_right else x0+w-28*s
    d.rectangle([cab_x, y0+h-30*s, cab_x+14*s, y0+h-18*s], fill=JDG)

def draw_barn(d, x, y, s=1.0):
    # Old style barn with cross
    w,h=60*s,40*s; x0,y0=x-w//2,y-h; mid=x0+w//2
    d.rectangle([x0,y0,x0+w,y0+h], fill=(180,40,30))
    d.polygon([(x0,y0),(mid,y0-20*s),(x0+w,y0)], fill=(130,25,20))
    # Cross
    cx, cy = mid, y0-8*s
    d.line([cx, cy-6*s, cx, cy+6*s], fill=WHITE, width=2)
    d.line([cx-4*s, cy-2*s, cx+4*s, cy-2*s], fill=WHITE, width=2)
    # Door
    d.rectangle([mid-10*s,y0+h-16*s,mid+10*s,y0+h], fill=(160,100,50))

def draw_south_park_scare(d, kind, slide_factor=0.0):
    # slide_factor: 0.0 (off screen) to 1.0 (center)
    # Goofy, crude, large eyes, cutout style
    cx = LW * slide_factor if slide_factor < 0.5 else LW//2
    cy = LH//2
    s = 4.0 # Big!
    
    # Generic "animal" shape
    d.ellipse([cx-40*s, cy-30*s, cx+40*s, cy+30*s], fill=BROWN)
    
    # Eyes - Huge and misaligned
    d.ellipse([cx-25*s, cy-15*s, cx-5*s, cy+15*s], fill=WHITE, outline=BG_COLOR, width=3)
    d.ellipse([cx+5*s, cy-15*s, cx+35*s, cy+15*s], fill=WHITE, outline=BG_COLOR, width=3)
    
    # Pupils - Tiny dots
    d.ellipse([cx-15*s, cy, cx-12*s, cy+3*s], fill=BG_COLOR)
    d.ellipse([cx+20*s, cy, cx+23*s, cy+3*s], fill=BG_COLOR)
    
    # Mouth - Flapping
    d.arc([cx-20*s, cy+10*s, cx+20*s, cy+25*s], 0, 180, fill=BG_COLOR, width=3)

def draw_hexagram(d, x, y, s=1.0):
    r = 15*s
    for a in range(0, 360, 60):
        x1, y1 = x+r*math.cos(math.radians(a)), y+r*math.sin(math.radians(a))
        x2, y2 = x+r*math.cos(math.radians(a+120)), y+r*math.sin(math.radians(a+120))
        d.line([x1,y1,x2,y2], fill=RED, width=max(1,int(s)))

def draw_demon(d, x, y, s=1.0):
    r=10*s; d.ellipse([x-r,y-r,x+r,y+r], fill=RED)
    d.polygon([(x-r,y-r+2),(x-r-4*s,y-r-8*s),(x-r+4*s,y-r+2)], fill=RED)
    d.polygon([(x+r,y-r+2),(x+r+4*s,y-r-8*s),(x+r-4*s,y-r+2)], fill=RED)
    d.ellipse([x-4*s,y-2*s,x-1*s,y+1*s], fill=JDY); d.ellipse([x+1*s,y-2*s,x+4*s,y+1*s], fill=JDY)

def draw_corn(d, x, y, s=1.0):
    d.line([x,y,x,y-14*s], fill=GREEN, width=2)
    d.ellipse([x-3*s,y-16*s,x+3*s,y-8*s], fill=YELLOW)

def draw_flower(d, x, y, s=1.0):
    d.line([x,y,x,y-10*s], fill=GREEN, width=1)
    d.ellipse([x-4*s,y-14*s,x+4*s,y-6*s], fill=HOTPINK)
    d.ellipse([x-2*s,y-12*s,x+2*s,y-8*s], fill=YELLOW)

def draw_tree(d, x, y, s=1.0):
    d.rectangle([x-2*s,y-10*s,x+2*s,y], fill=DKBRN)
    d.ellipse([x-8*s,y-25*s,x+8*s,y-8*s], fill=GREEN)

def draw_egg(d, x, y, s=1.0):
    d.ellipse([x-3*s,y-4*s,x+3*s,y], fill=WHITE)

def draw_milk_splats(d):
    for _ in range(10):
        x, y = random.randint(0,LW), random.randint(0,LH)
        r = random.randint(2,6)
        d.ellipse([x,y,x+r,y+r], fill=WHITE)

# ── Entities ─────────────────────────────────────────────────────────────────
class Entity:
    def __init__(self, kind, x, y):
        self.kind=kind; self.x=float(x); self.y=float(y); 
        self.vx=random.uniform(-1,1); self.vy=random.uniform(-0.5,0.5)
        self.state="idle"; self.timer=0; self.face_right=(self.vx>0); self.z=y; self.target=None
        self.props={} # generic props

    def update(self, app):
        if self.state in ("humped","bent_over","milking","mud_bath"): self.timer-=1; return

        # Behavior Trees
        if self.kind == "farmer":
            if self.state == "planting":
                if random.random()<0.05: app.plants.append(("corn",self.x,self.y,300))
                self.timer-=1
                if self.timer<=0: self.state="idle"
            elif self.state == "chasing_goat":
                tgt = next((e for e in app.entities if e.kind=="goat"), None)
                if tgt:
                    dx,dy=tgt.x-self.x,tgt.y-self.y; dist=math.hypot(dx,dy)
                    if dist<10:
                        self.state="humping_fail"; self.timer=60; tgt.state="biting"; tgt.timer=60
                    else: self.x+=dx/dist*2.5; self.y+=dy/dist*2.5; self.face_right=(dx>0)
                else: self.state="idle"
            elif self.state == "humping_fail":
                self.timer-=1
                if self.timer==30: app.bubbles.append((self.x,self.y-30,"Ouch!"))
                if self.timer<=0: self.state="idle"
            elif self.state == "chasing_daughter":
                 tgt = next((e for e in app.entities if e.kind=="farmer's daughter"), None)
                 if tgt and tgt.state not in ("humped","bent_over"):
                    dx,dy=tgt.x-self.x,tgt.y-self.y; dist=math.hypot(dx,dy)
                    if dist<10:
                        self.state="humping"; self.timer=100; tgt.state="bent_over"; tgt.timer=100
                    else: self.x+=dx/dist*2.5; self.y+=dy/dist*2.5; self.face_right=(dx>0)
            elif self.state == "humping":
                self.timer-=1; self.y+=math.sin(time.time()*20)*0.5
                if self.timer<=0: self.state="idle"
            else: # Idle
                r = random.random()
                if r < 0.005: self.state="planting"; self.timer=60
                elif r < 0.008: self.state="chasing_goat"; self.timer=200
                elif r < 0.01: self.state="chasing_daughter"; self.timer=200
                self._wander()

        elif self.kind == "farmer's daughter":
            if self.state == "planting":
                if random.random()<0.05: app.plants.append(("flower",self.x,self.y,300))
                self.timer-=1; 
                if self.timer<=0: self.state="idle"
            elif self.state == "collecting":
                if not self.target or self.target not in app.eggs:
                    tgt = next((e for e in app.eggs), None)
                    if tgt: self.target=tgt
                    else: self.state="idle"
                else:
                    dx,dy=self.target[0]-self.x,self.target[1]-self.y; dist=math.hypot(dx,dy)
                    if dist<5:
                        app.eggs.remove(self.target); self.target=None
                    else: self.x+=dx/dist*2; self.y+=dy/dist*2; self.face_right=(dx>0)
            elif self.state == "milking":
                if self.timer==20: app.splat_timer=10; self.props['splattered']=True
                if self.timer<=0: self.state="idle"
            elif self.state == "bent_over":
                self.timer-=1; 
                if self.timer<=0: self.state="idle"
            else: # Idle
                r = random.random()
                if r < 0.005: self.state="planting"; self.timer=60
                elif r < 0.01 and app.eggs: self.state="collecting"
                elif r < 0.005:
                    cow = next((e for e in app.entities if e.kind=="cow"),None)
                    if cow:
                        self.x,self.y = cow.x+10, cow.y+5; self.state="milking"; self.timer=60
                self._wander()

        elif self.kind == "chicken":
            # Eat plants
            tgt = min(app.plants, key=lambda p:math.hypot(p[1]-self.x,p[2]-self.y), default=None)
            if tgt and math.hypot(tgt[1]-self.x,tgt[2]-self.y)<60:
                dx,dy=tgt[1]-self.x,tgt[2]-self.y; dist=math.hypot(dx,dy)
                if dist<5: app.plants.remove(tgt)
                else: self.x+=dx/dist*2; self.y+=dy/dist*2; self.face_right=(dx>0)
            # Lay eggs
            elif random.random()<0.002: app.eggs.append((self.x,self.y))
            else: self._wander()

        elif self.kind == "pig":
            if self.state == "mud_bath":
                if self.timer<=0: 
                    self.state="idle"; self.props['muddy']=True
                    if random.random()<0.3: self.state="flying"; self.timer=100
            elif self.state == "flying":
                self.y -= 1; self.x += self.vx; self.timer-=1
                if self.timer<=0 or self.y < -20: self.state="idle"; self.y=LH-20; self.props['muddy']=False
            else:
                if random.random()<0.005: self.state="mud_bath"; self.timer=80
                self._wander()

        elif self.kind == "squirrel":
            if self.state == "planting":
                self.timer-=1
                if self.timer<=0: 
                    app.trees.append((self.x,self.y)); self.state="idle"
            else:
                if random.random()<0.003: self.state="planting"; self.timer=40
                self._wander()
        
        elif self.kind == "boyfriend":
            if self.state == "chasing":
                tgt = next((e for e in app.entities if e.kind=="farmer's daughter"), None)
                if tgt and tgt.state not in ("humped","bent_over"):
                    dx,dy=tgt.x-self.x,tgt.y-self.y; dist=math.hypot(dx,dy)
                    if dist<10:
                        self.state="humping"; self.timer=100; tgt.state="bent_over"; tgt.timer=100
                    else: self.x+=dx/dist*2.5; self.y+=dy/dist*2.5; self.face_right=(dx>0)
            elif self.state == "humping":
                self.timer-=1; self.y+=math.sin(time.time()*20)*0.5
                if self.timer<=0: self.state="victory"; self.timer=60
            elif self.state == "victory":
                self.timer-=1; self.y-=math.sin(time.time()*15)*2 # Jump
                if self.timer<=0: self.state="idle"
            else:
                if random.random()<0.005: self.state="chasing"
                else: self._wander()

        elif self.kind == "barn":
             if random.random() < 0.002:
                 demons = [e for e in app.entities if e.kind=="demon"]
                 if not demons:
                     app.entities.append(Entity("demon", self.x, self.y-30))
        elif self.kind == "demon":
             self.y += math.sin(time.time()*5)*2
             self.timer += 1
             if self.timer > 300: app.entities.remove(self)

        else: self._wander()
        self.z = self.y

    def _wander(self):
        if random.random()<0.02: self.vx=random.uniform(-1,1); self.vy=random.uniform(-0.5,0.5)
        self.x+=self.vx; self.y+=self.vy
        self.x=max(10,min(LW-10,self.x)); self.y=max(40,min(LH-10,self.y))
        self.face_right=(self.vx>0)

    def draw(self, d):
        fr=self.face_right
        if self.kind=="chicken": draw_chicken(d,self.x,self.y,1.0,fr)
        elif self.kind=="cow": draw_cow(d,self.x,self.y,1.0,fr)
        elif self.kind=="pig": draw_pig(d,self.x,self.y,1.0,fr,self.props.get('muddy'),self.state=="flying")
        elif self.kind=="squirrel": draw_squirrel(d,self.x,self.y,1.0,fr,self.state=="planting")
        elif self.kind=="goat": draw_goat(d,self.x,self.y,1.0,fr,self.state=="biting")
        elif self.kind=="farmer": draw_farmer(d,self.x,self.y,1.0,self.state=="planting",self.state in ("humping","humping_fail"))
        elif self.kind=="farmer's daughter": draw_farmer_daughter(d,self.x,self.y,1.0,self.state,self.props.get('splattered'))
        elif self.kind=="boyfriend": draw_boyfriend(d,self.x,self.y,1.0,self.state=="humping",self.state=="victory")
        elif self.kind=="tractor": draw_tractor(d,self.x,self.y,1.0,fr)
        elif self.kind=="barn": draw_barn(d,self.x,self.y,1.0)
        elif self.kind=="demon": draw_demon(d,self.x,self.y,1.0); draw_hexagram(d,self.x,self.y,1.0)

# ── App ───────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.fb=FB(); self.entities=[]; self.plants=[]; self.trees=[]; self.eggs=[]; self.bubbles=[]
        self.scare_timer=0; self.scare_active=False; self.splat_timer=0
        self.running=True; self.clock_pos=[LW//2,LH//2]; self.clock_vel=[2,1.5]
        self.opts={
            "chickens":True, "cows":False, "pigs":False, "squirrels":False, "goats":False,
            "farmer":True, "farmer's daughter":False, "boyfriend":False, "tractor":False, "barn":True
        }
        self.opt_keys=["SAVE & EXIT"]+list(self.opts.keys()); self.menu_open=False; self.menu_sel=0
        self._spawn_entities()

    def _spawn_entities(self):
        self.entities=[]
        for k,v in self.opts.items():
            if not v: continue
            count,kind=SPAWN_MAP.get(k,(1,k))
            for _ in range(count): self.entities.append(Entity(kind,random.randint(20,LW-20),random.randint(50,LH-20)))

    def update(self):
        if self.menu_open: return
        
        # Scares
        if not self.scare_active and random.random()<0.0005:
            self.scare_active=True; self.scare_timer=0
        
        # Snapshot entity list to iterate safely while modifying
        for e in list(self.entities): e.update(self)
        self.plants = [p for p in self.plants if p[3]>0]; 
        for i in range(len(self.plants)): self.plants[i]=(self.plants[i][0],self.plants[i][1],self.plants[i][2],self.plants[i][3]-1)
        
        if self.splat_timer>0: self.splat_timer-=1
        
        # Bouncing Clock
        self.clock_pos[0]+=self.clock_vel[0]; self.clock_pos[1]+=self.clock_vel[1]
        if self.clock_pos[0]<60 or self.clock_pos[0]>LW-60: self.clock_vel[0]*=-1
        if self.clock_pos[1]<20 or self.clock_pos[1]>LH-20: self.clock_vel[1]*=-1

    def draw(self):
        img=Image.new('RGB',(LW,LH),BG_COLOR); d=ImageDraw.Draw(img)
        
        # Environment
        for t in self.trees: draw_tree(d,t[0],t[1])
        for p in self.plants: 
            if p[0]=="corn": draw_corn(d,p[1],p[2])
            else: draw_flower(d,p[1],p[2])
        for e in self.eggs: draw_egg(d,e[0],e[1])
        
        # Entities
        ents=sorted(self.entities, key=lambda e:e.z)
        for e in ents: e.draw(d)
        
        # Bubbles
        self.bubbles = [b for b in self.bubbles if random.random()>0.05]
        for b in self.bubbles:
            d.rectangle([b[0],b[1],b[0]+40,b[1]+15], fill=WHITE, outline=BG_COLOR)
            d.text((b[0]+2,b[1]), b[2], font=F_BUBBLE, fill=BG_COLOR)

        # Splatter
        if self.splat_timer>0: draw_milk_splats(d)

        # Clock
        t_str=time.strftime("%H:%M"); bb=d.textbbox((0,0),t_str,font=F_CLOCK)
        d.text((self.clock_pos[0]-(bb[2]-bb[0])//2, self.clock_pos[1]-(bb[3]-bb[1])//2), t_str, font=F_CLOCK, fill=WHITE)

        # Scare Overlay
        if self.scare_active:
            self.scare_timer+=1
            factor = min(1.0, self.scare_timer/10.0) # Slide in
            draw_south_park_scare(d, "critter", factor)
            if self.scare_timer > 60: self.scare_active=False # End

        # Menu
        if self.menu_open:
            d.rectangle([30,5,LW-30,LH-5],fill=(20,20,30),outline=ACCENT)
            start_idx = max(0, min(self.menu_sel - 3, len(self.opt_keys) - 7))
            for i in range(7):
                idx = start_idx + i
                if idx >= len(self.opt_keys): break
                k = self.opt_keys[idx]
                sel = (idx == self.menu_sel); label = LABEL_OVERRIDE.get(k, k.upper())
                val = ""
                if k != "SAVE & EXIT": val = " [ON]" if self.opts[k] else " [OFF]"
                d.text((40, 15+i*20), f"{'>' if sel else ' '} {label}{val}", font=F_SM, fill=ORANGE if sel else WHITE)
        self.fb.show(img)

    def run(self):
        with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
            while self.running:
                rev = rotary.read_event(0)
                if rev and self.menu_open: self.menu_sel = (self.menu_sel + rev) % len(self.opt_keys)
                
                kev=keys.read_event(0)
                if kev and kev[0]=='key_release' and kev[1]=='ENTER':
                    if self.menu_open:
                        k=self.opt_keys[self.menu_sel]
                        if k=="SAVE & EXIT": self.menu_open=False
                        else: self.opts[k]=not self.opts[k]; self._spawn_entities()
                    else: self.menu_open=True
                
                t=touch.read_event(0)
                if t and t[0]=='touch_down':
                    tx,ty=TouchScreen.map_coords_270(t[1],t[2])
                    if tx>LW-40 and ty<40: self.menu_open=not self.menu_open
                    elif not self.menu_open: self.clock_pos=[tx,ty]
                
                self.update(); self.draw(); time.sleep(0.05)
        self.fb.close()

if __name__=="__main__": App().run()
