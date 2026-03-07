# NanoKVM UserApp Suite

This repository contains a collection of high-quality touchscreen applications for the Sipeed NanoKVM Pro.

## Applications

### 🐔 CLUCK (Farm Clock)
A quirky, interactive clock featuring animated farm life.
- **Clock:** High-readability display that erratically changes scale and position. Strictly clamped to prevent going off-screen.
- **In-Your-Face Chickens:** Randomly, a chicken will zoom in with big goofy eyes for a "jump scare" effect.
- **Pecking Interaction:** Chickens will peck at the clock, causing it to "flee" to another part of the screen.
- **Entity Menu:** Toggles for Chickens, Cows, Pigs, Squirrels, Farmer, Farmer's Daughter, Tractor, and House.
- **Controls:** Knob rotate to move clock; Knob press to open settings; Long-press to exit.

### 🤖 PicoClaw (AI Agent)
A consolidated AI assistant interface with voice and chat capabilities.
- **Chat UI:** Modern chat bubble interface for both User and AI responses.
- **Voice Integration:** Built-in offline speech recognition using Vosk (no API keys required).
- **QR Login:** Generates a dynamic QR code linked to a local web server (port 8080) for easy API key configuration and provider setup.
- **System Stats:** Real-time CPU, RAM, and IP address monitoring in the footer.
- **Skills:** Management of NanoKVM skills via the picoclaw CLI.

### 📈 EQTY (Stock Tickers)
Real-time financial monitoring for your NanoKVM screen.
- **Live Updates:** Fetches latest prices for a configured set of symbols.
- **Default Portfolio:** PSLV, CL=F (Crude Oil), CRF, LEAV, INES.
- **Visuals:** Sparkline-style price indicators and percentage change tracking.

### 🛡️ SCRNSVR (Screensaver Manager)
A background daemon and UI to manage device idle states.
- **App Cycling:** Automatically rotates through enabled apps (EQTY, PicoClaw, CLUCK, etc.) when the device is idle.
- **Idle Timeout:** Configurable delay before the screensaver kicks in.
- **Blackout Mode:** Option to completely blank the screen to save power/life.
- **Service-Based:** Runs as a systemd service (`screensaver.service`) for persistence.

### 🔗 Tailcode (Tailscale Status)
Quick access to network connectivity information.
- **QR Code:** Shows a join/login QR code for your Tailscale network.
- **Connectivity:** Displays current IP and node status.

---

## Global Controls
- **Knob Rotate:** Scroll menus or change values.
- **Knob Press:** Select, confirm, or toggle.
- **Knob Long-Press (2s):** Exit the current app and return to the main system menu.
