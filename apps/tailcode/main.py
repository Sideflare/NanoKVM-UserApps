#!/usr/bin/env python3
"""
Tailcode - Tailscale QR Code App for NanoKVM Pro
Displays the Tailscale URL as a QR code and shows connection info.
Screen: 172x320 physical (portrait), 320x172 logical (landscape at 270deg rotation)
"""

import subprocess, time, io, qrcode, mmap, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from input import TouchScreen, GpioKeys

# ── Display ──────────────────────────────────────────────────────────────────
PW, PH = 172, 320
LW, LH = 320, 172
BG_COLOR = (10, 10, 30)

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

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

COLOR_WHITE   = (255, 255, 255)
COLOR_CYAN    = (0,   200, 255)
COLOR_YELLOW  = (255, 220,  50)
COLOR_GRAY    = (140, 140, 160)
COLOR_GREEN   = (80,  220,  80)
COLOR_DIM     = (70,  70,  90)

def get_tailscale_info():
    try:
        ip = subprocess.check_output(['tailscale', 'ip', '--4'], stderr=subprocess.DEVNULL).decode().strip()
    except Exception: ip = 'unavailable'
    try:
        import json
        raw = subprocess.check_output(['tailscale', 'status', '--json'], stderr=subprocess.DEVNULL).decode()
        data = json.loads(raw)
        dns = data['Self']['DNSName'].rstrip('.')
    except Exception: dns = ip
    return ip, dns, f'https://{dns}/kvm/'

def make_qr_image(url: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    return img.resize((size, size), Image.NEAREST)

def render_screen(url: str, ip: str, dns: str) -> Image.Image:
    canvas = Image.new('RGB', (LW, LH), BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    try:
        f_small  = ImageFont.truetype(FONT_PATH, 11)
        f_medium = ImageFont.truetype(FONT_PATH, 13)
        f_bold   = ImageFont.truetype(FONT_BOLD, 14)
        f_title  = ImageFont.truetype(FONT_BOLD, 15)
    except: f_small = f_medium = f_bold = f_title = ImageFont.load_default()

    qr_size = 156
    canvas.paste(make_qr_image(url, qr_size), (4, (LH - qr_size) // 2))
    draw.line([(qr_size + 8, 8), (qr_size + 8, LH - 8)], fill=COLOR_GRAY, width=1)

    rx, ry = qr_size + 14, 10
    draw.text((rx, ry), 'Tailcode', font=f_title, fill=COLOR_CYAN); ry += 20
    draw.text((rx, ry), 'TAILSCALE', font=f_small, fill=COLOR_GRAY); ry += 14
    draw.text((rx, ry), ip, font=f_bold, fill=COLOR_GREEN); ry += 20
    draw.text((rx, ry), 'DNS:', font=f_small, fill=COLOR_GRAY); ry += 13
    parts = dns.split('.', 1)
    draw.text((rx, ry), parts[0], font=f_medium, fill=COLOR_WHITE); ry += 15
    if len(parts) > 1: draw.text((rx, ry), '.' + parts[1], font=f_small, fill=COLOR_GRAY); ry += 14
    ry = LH - 42
    draw.text((rx, ry), 'URL:', font=f_small, fill=COLOR_GRAY); ry += 13
    draw.text((rx, ry), '/kvm/', font=f_medium, fill=COLOR_YELLOW); ry += 16
    draw.text((rx, ry), 'Long-press to exit', font=f_small, fill=COLOR_DIM)
    return canvas

def main():
    import os
    fb = FB()
    ip, dns, url = get_tailscale_info()
    canvas = render_screen(url, ip, dns)
    fb.show(canvas)
    
    last_refresh = time.time()
    running = True
    try:
        with TouchScreen() as touch, GpioKeys() as keys:
            while running:
                if time.time() - last_refresh > 60:
                    ip, dns, url = get_tailscale_info()
                    fb.show(render_screen(url, ip, dns))
                    last_refresh = time.time()
                kev = keys.read_event(timeout=0.05)
                if kev and kev[0] == 'key_long_press': running = False
                tev = touch.read_event(timeout=0)
                if tev and tev[0] == 'touch_down': running = False
                time.sleep(0.05)
    finally:
        fb.show(Image.new('RGB', (LW, LH), (0,0,0)))
        fb.close()

if __name__ == '__main__':
    main()
