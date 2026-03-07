#!/usr/bin/env python3
"""
Tailcode - Tailscale QR Code App for NanoKVM Pro
Displays the Tailscale URL as a QR code and shows connection info.
Screen: 172x320 physical (portrait), 320x172 logical (landscape at 270deg rotation)
"""

import subprocess
import time
import io
import qrcode
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from framebuffer import Framebuffer
from input import TouchScreen, GpioKeys

SCREEN_W = 320
SCREEN_H = 172

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

COLOR_BG      = (10,  10,  30)
COLOR_WHITE   = (255, 255, 255)
COLOR_CYAN    = (0,   200, 255)
COLOR_YELLOW  = (255, 220,  50)
COLOR_GRAY    = (140, 140, 160)
COLOR_GREEN   = (80,  220,  80)
COLOR_DIM     = (70,  70,  90)


def get_tailscale_info():
    try:
        ip = subprocess.check_output(['tailscale', 'ip', '--4'],
                                     stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        ip = 'unavailable'

    try:
        import json
        raw = subprocess.check_output(['tailscale', 'status', '--json'],
                                      stderr=subprocess.DEVNULL).decode()
        data = json.loads(raw)
        dns = data['Self']['DNSName'].rstrip('.')
    except Exception:
        dns = ip

    url = f'https://{dns}/kvm/'
    return ip, dns, url


def make_qr_image(url: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    img = img.resize((size, size), Image.NEAREST)
    return img


def render_screen(url: str, ip: str, dns: str) -> Image.Image:
    canvas = Image.new('RGB', (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(canvas)

    try:
        font_small  = ImageFont.truetype(FONT_PATH, 11)
        font_medium = ImageFont.truetype(FONT_PATH, 13)
        font_bold   = ImageFont.truetype(FONT_BOLD, 14)
        font_title  = ImageFont.truetype(FONT_BOLD, 15)
    except Exception:
        font_small = font_medium = font_bold = font_title = ImageFont.load_default()

    # --- QR code (left side) ---
    qr_size = 156
    qr_x = 4
    qr_y = (SCREEN_H - qr_size) // 2
    qr_img = make_qr_image(url, qr_size)
    canvas.paste(qr_img, (qr_x, qr_y))

    # Divider line
    draw.line([(qr_x + qr_size + 4, 8), (qr_x + qr_size + 4, SCREEN_H - 8)],
              fill=COLOR_GRAY, width=1)

    # --- Right side info ---
    rx = qr_x + qr_size + 10
    ry = 10

    # Title
    draw.text((rx, ry), 'Tailcode', font=font_title, fill=COLOR_CYAN)
    ry += 20

    # Tailscale label
    draw.text((rx, ry), 'TAILSCALE', font=font_small, fill=COLOR_GRAY)
    ry += 14

    # IP address
    draw.text((rx, ry), ip, font=font_bold, fill=COLOR_GREEN)
    ry += 20

    # DNS name
    draw.text((rx, ry), 'DNS:', font=font_small, fill=COLOR_GRAY)
    ry += 13

    parts = dns.split('.', 1)
    draw.text((rx, ry), parts[0], font=font_medium, fill=COLOR_WHITE)
    ry += 15
    if len(parts) > 1:
        draw.text((rx, ry), '.' + parts[1], font=font_small, fill=COLOR_GRAY)
        ry += 14

    # URL hint
    ry = SCREEN_H - 42
    draw.text((rx, ry), 'URL:', font=font_small, fill=COLOR_GRAY)
    ry += 13
    draw.text((rx, ry), '/kvm/', font=font_medium, fill=COLOR_YELLOW)
    ry += 16

    # Press to exit
    draw.text((rx, ry), 'Press to exit', font=font_small, fill=COLOR_DIM)

    # Scan hint at bottom of QR
    hint = 'Scan to open'
    bbox = draw.textbbox((0, 0), hint, font=font_small)
    hw = bbox[2] - bbox[0]
    draw.text((qr_x + (qr_size - hw) // 2, SCREEN_H - 14),
              hint, font=font_small, fill=COLOR_GRAY)

    return canvas


def image_to_framebuffer(img: Image.Image, fb: Framebuffer):
    phys_img = img.rotate(90, expand=True)  # 172x320 physical (fixed: was -90, upside down)
    phys_arr = np.array(phys_img)
    r2 = (phys_arr[:, :, 0] >> 3).astype(np.uint16)
    g2 = (phys_arr[:, :, 1] >> 2).astype(np.uint16)
    b2 = (phys_arr[:, :, 2] >> 3).astype(np.uint16)
    phys_rgb565 = (r2 << 11) | (g2 << 5) | b2

    if fb.fbmem and fb.buffer:
        phys_bytes = phys_rgb565.astype('<u2').tobytes()
        fb.buffer[:len(phys_bytes)] = bytearray(phys_bytes)
        fb.swap_buffer()


def main():
    print('Tailcode app starting...')

    fb = Framebuffer('/dev/fb0', rotation=270, font_size=14)

    ip, dns, url = get_tailscale_info()
    print(f'URL: {url}')
    print(f'IP:  {ip}')
    print(f'DNS: {dns}')

    canvas = render_screen(url, ip, dns)
    image_to_framebuffer(canvas, fb)
    print('QR code displayed.')

    last_refresh = time.time()

    try:
        with TouchScreen() as touch, GpioKeys() as keys:
            print('Waiting for input (touch/key to exit)...')
            while True:
                if time.time() - last_refresh > 60:
                    ip, dns, url = get_tailscale_info()
                    canvas = render_screen(url, ip, dns)
                    image_to_framebuffer(canvas, fb)
                    last_refresh = time.time()

                touch_event = touch.read_event(timeout=0.05)
                if touch_event and touch_event[0] == 'touch_down':
                    print('Touch detected, exiting...')
                    break

                key_event = keys.read_event(timeout=0.05)
                if key_event and key_event[0] in ('key_press', 'key_release'):
                    print('Key detected, exiting...')
                    break

    except KeyboardInterrupt:
        print('Interrupted.')
    finally:
        fb.fill_screen((0, 0, 0))


if __name__ == '__main__':
    main()
