# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Target Platform

Apps run on a **Sipeed NanoKVM Pro** — a RISC-V Linux device with a 172x320 physical framebuffer (`/dev/fb0`). The screen is used in landscape orientation (320x172 logical), requiring a 90-degree rotation before writing to the framebuffer.

- Physical framebuffer: 172 wide x 320 tall, RGB565 (16-bit)
- Logical canvas: 320 wide x 172 tall (landscape)
- Rotation: Draw on a 320x172 PIL Image, then `img.rotate(90, expand=True)` before writing to `/dev/fb0`
- Font path: `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` (and `-Bold.ttf`)

## Deployment

Apps live in `/userapp/<appname>/` on the device. Deploy via SCP:
```bash
scp -r ./apps/APPNAME root@<kvm-ip>:/userapp/
```

Apps appear automatically in the NanoKVM touchscreen "UserApp" menu. Each app directory requires an `app.toml` manifest.

## App Structure

Every app has:
- `app.toml` — manifest with `[application]` (name, version, description), `[author]`, and `[interaction]` (requires_user_input)
- `main.py` — entry point, run directly by the system

Shared input drivers are copied per-app (not a shared library):
- `input.py` — `TouchScreen`, `GpioKeys`, `RotaryEncoder` classes reading from Linux input event devices
- `framebuffer.py` — higher-level `Framebuffer` class (used in older apps like PWR-BTN)

## Framebuffer Pattern

All newer apps use a minimal inline `FB` class instead of importing `framebuffer.py`:

```python
class FB:
    def __init__(self):
        sz = PW * PH * 2  # PW=172, PH=320
        self.fd = os.open('/dev/fb0', os.O_RDWR)
        self.mm = mmap.mmap(self.fd, sz, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self.arr = np.frombuffer(self.mm, dtype=np.uint16).reshape(PH, PW)
    def show(self, img: Image.Image):
        p = img.rotate(90, expand=True)
        a = np.array(p, dtype=np.uint16)
        self.arr[:,:] = (a[:,:,0]>>3<<11)|(a[:,:,1]>>2<<5)|(a[:,:,2]>>3)
    def close(self):
        self.mm.close(); os.close(self.fd)
```

## Input Devices

- **TouchScreen**: `/dev/input/by-path/platform-4857000.i2c-event` — raw coords must be mapped with `TouchScreen.map_coords_270(x, y)` to get logical screen coordinates
- **GpioKeys**: `/dev/input/by-path/platform-gpio_keys-event` — knob press; events are `key_press`, `key_release`, `key_long_press` tuples
- **RotaryEncoder**: returns +1/-1 delta on rotate

## App Main Loop Pattern

```python
def run(self):
    with TouchScreen() as touch, GpioKeys() as keys, RotaryEncoder() as rotary:
        while self.running:
            r = rotary.read_event(0)
            k = keys.read_event(0)
            t = touch.read_event(0)
            # handle events...
            if self._dirty:
                self.draw()
            time.sleep(0.05)
    self.fb.close()
```

## Controls Convention

- **Knob rotate**: scroll menus or change values
- **Knob press** (`key_release` + `ENTER`): select/confirm
- **Knob long-press** (`key_long_press`, 2s threshold): exit app and return to system menu
- **Touch**: `TouchScreen.map_coords_270(x, y)` for logical coords; top-left corner typically reserved for back/exit

## Key Paths on Device

- App install dir: `/userapp/`
- SCRNSVR config: `/etc/kvm/screensaver.json`
- EQTY config: `/etc/kvm/stocks_config.json`
- SCRNSVR daemon status: `/tmp/screensaver_status.json`
- PicoClaw login server port: `8080`

## Dependencies

Install on device:
```bash
apt-get update && apt-get install -y libportaudio2 python3-pyaudio
pip3 install yfinance vosk qrcode flask psutil
```

## Apps Summary

| App | Description |
|-----|-------------|
| `hello` | Minimal framebuffer test |
| `CLUCK` | Animated farm clock with chicken sprites, 3 clock modes (Avoid/Bounce/Center), settings menu |
| `EQTY` | Real-time stock ticker with sparklines using yfinance |
| `picoclaw` | AI chat with offline voice (Vosk), QR login server, multi-page UI |
| `SCRNSVR` | Screensaver daemon manager; reads `/userapp` dir for app list |
| `tailcode` | Tailscale status + QR code display |
| `PWR-BTN` | ATX power/reset button controller via `/dev/gpiochip` |
| `samba` | Samba file sharing setup UI |
| `serial` | UART serial terminal |
| `HW-UP` | Hardware firmware updater |
| `conway` | Conway's Game of Life |
| `drawo` | Drawing app |
| `tomato` | Pomodoro timer |
| `coin` | Coin flip |
