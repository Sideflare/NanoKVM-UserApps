# NanoKVM UserApp Suite

This repository contains a collection of high-quality touchscreen applications for the Sipeed NanoKVM Pro.

## Applications

### 🐔 CLUCK (Farm Clock)
A quirky, interactive clock featuring animated farm life.
- **Clock:** High-readability display that erratically changes scale and position. Strictly clamped to prevent going off-screen.
- **Goofy Zooms:** Every character has a unique "in your face" jump-scare animation:
  - **Chicken:** Big goofy eyes.
  - **Cow:** Massive snout and long eyelashes.
  - **Pig:** Huge snout and spiral dizzy eyes.
  - **Squirrel:** Giant cheeks and buck teeth.
  - **Farmer:** Massive bushy beard and shocked stare.
  - **Farmer's Daughter:** Yellow pigtails and surprised mouth.
- **Pecking Interaction:** Chickens will peck at the clock, causing it to "flee" to another part of the screen.
- **Entity Menu:** Toggles for all characters, Tractor, and House.
- **Controls:** Knob rotate to move clock; Knob press to open settings; Long-press to exit.

### 🤖 PicoClaw (AI Agent)
A consolidated AI assistant interface with voice and chat capabilities.
- **Chat UI:** Modern chat bubble interface for both User and AI responses.
- **Voice Integration:** Built-in offline speech recognition using Vosk (no API keys required).
- **QR Login:** Generates a dynamic QR code linked to a local web server (port 8080) for easy API key configuration.
- **System Stats:** Real-time CPU, RAM, and IP address monitoring.
- **Skills:** Management of NanoKVM skills via the picoclaw CLI.

### 📈 EQTY (Stock Tickers)
Real-time financial monitoring with high-speed rendering.
- **Live Updates:** Fetches latest prices for symbols like PSLV, CL=F, CRF, LEAV, INES.
- **Visuals:** High-performance sparkline-style price indicators.
- **Controls:** Knob rotate to switch symbols; Long-press to exit.

### 🛡️ SCRNSVR (Screensaver Manager)
A background daemon and UI to manage device idle states.
- **App Cycling:** Automatically rotates through enabled apps when the device is idle.
- **Status Dashboard:** Live view of idle time, current app, and next switch countdown.
- **Service-Based:** Runs as a systemd service for persistence.

### 🔗 Tailcode (Tailscale Status)
Quick access to network connectivity information.
- **QR Code:** Shows a join/login QR code for your Tailscale network.
- **Performance:** Optimized with fast numpy-based rendering.

---

## Global Controls
- **Knob Rotate:** Scroll menus or change values.
- **Knob Press:** Select, confirm, or toggle.
- **Knob Long-Press (2s):** Exit the current app and return to the main system menu.
